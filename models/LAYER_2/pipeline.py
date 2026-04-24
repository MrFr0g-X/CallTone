"""
LAYER 2 Pipeline - Call Quality Rating

Takes Layer 1 output (transcription + diarization + emotions) and rates the
customer service agent on 7 criteria using company-specific context.

Architecture:
1. Load Layer 1 output (JSON with transcript, roles, emotions)
2. Run prompt-injection scanner on the transcript (security gate)
3. Load company context and build context graph
4. For each criterion, retrieve relevant context from the graph
5. Format input for each rating skill (transcript + relevant context)
   — transcript is wrapped in structural sandbox delimiters
6. Run each rating skill through the consensus runner
7. Combine all ratings into final output

This pipeline uses the skill-based architecture for deterministic evaluation:
- Each criterion has its own dedicated skill (prompt-only, no logic)
- The consensus runner ensures stable scores across runs
- The context graph handles large documents by chunking into searchable nodes
- The change tracker prevents score drift from protocol rewording
- The injection scanner protects against transcript-borne prompt injection
"""

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "skill_implementation"))

from LAYER_2.company_context.context_store import ContextStore
from LAYER_2.context_graph.graph import ContextGraph
from LAYER_2.context_graph.builder import GraphBuilder
from LAYER_2.context_graph.retriever import GraphRetriever
from LAYER_2.consensus.consensus_runner import ConsensusRunner, get_rubric_text
from LAYER_2.security.injection_scanner import scan as injection_scan, wrap_transcript_for_rating
from skill_runtime.loader import load_skill


class InjectionBlockedError(Exception):
    """Raised when the injection scanner blocks a transcript from being rated."""
    def __init__(self, scan_result):
        self.scan_result = scan_result
        super().__init__(
            f"Transcript blocked — prompt injection detected "
            f"(severity={scan_result.severity}). "
            f"Reason: {scan_result.overall_reasoning}"
        )


# Mapping from criterion names to skill names
CRITERION_SKILLS = {
    "script_compliance": "rate-script-compliance",
    "factual_accuracy": "rate-factual-accuracy",
    "politeness_tone": "rate-politeness-tone",
    "empathy": "rate-empathy",
    "conflict_detection": "rate-conflict-detection",
    "issue_resolution": "rate-issue-resolution",
    "overall_severity": "rate-overall-severity",
}

CRITERION_WEIGHTS = {
    "script_compliance": 0.25,
    "factual_accuracy": 0.25,
    "politeness_tone": 0.15,
    "empathy": 0.10,
    "conflict_detection": 0.15,
    "issue_resolution": 0.05,
    "overall_severity": 0.05,
}


# OPT-A9: cache the context graph per (company, version) so repeat calls on
# the same company skip the rebuild (ingest → builder → graph). Keyed by
# version so context updates invalidate the entry automatically.
@lru_cache(maxsize=32)
def _build_cached_context_graph(company_name: str, context_version: str) -> "ContextGraph":
    store = ContextStore()
    context_dict = store.load_raw(company_name)
    builder = GraphBuilder()
    return builder.build_from_context(context_dict)


def format_transcript_for_rating(layer1_output: dict) -> str:
    """
    Format the Layer 1 JSON output into a readable transcript string
    that includes speaker roles, emotions, and behavioral signals.
    """
    lines = []

    # Add call metadata
    meta = layer1_output.get("call_metadata", {})
    lines.append(f"CALL METADATA:")
    lines.append(f"  Duration: {meta.get('duration_seconds', 0):.0f} seconds")
    lines.append(f"  Speakers: {meta.get('num_speakers', 0)}")
    lines.append("")

    # Add speaker summary
    lines.append("SPEAKER SUMMARY:")
    for speaker, info in layer1_output.get("speaker_summary", {}).items():
        talk_pct = info.get("talk_time_pct", 0)
        signals = info.get("behavioral_signals", {})
        signal_str = ", ".join(f"{k}:{v}" for k, v in signals.items()) or "none"
        lines.append(f"  {speaker}: {talk_pct:.1f}% talk time, signals: {signal_str}")
    lines.append("")

    # Add transcript
    lines.append("TRANSCRIPT:")
    for seg in layer1_output.get("transcript", []):
        speaker = seg.get("role", seg.get("speaker", "UNKNOWN"))
        text = seg.get("text", "")
        emotion = seg.get("audio_emotion", "")
        emotion_conf = seg.get("audio_emotion_confidence", 0)
        signals = seg.get("signals", [])

        emotion_str = ""
        if emotion and emotion != "neutral" and emotion_conf > 0.5:
            emotion_str = f" [emotion: {emotion} ({emotion_conf:.0%})]"

        signal_str = ""
        if signals:
            signal_str = f" [signals: {', '.join(signals)}]"

        lines.append(f"  {speaker}: {text}{emotion_str}{signal_str}")

    return "\n".join(lines)


def build_criterion_input(
    criterion: str,
    transcript_text: str,
    retriever: GraphRetriever,
    raw_transcript: str = "",
) -> str:
    """
    Build the input text for a specific criterion's rating skill.

    Combines the transcript with relevant company context retrieved from the graph.
    The transcript section is wrapped in structural sandbox delimiters to reduce
    the impact of any prompt injection that slipped past the security scanner.
    """
    # Retrieve relevant context nodes using semantic tag matching (Zettelkasten path).
    # Falls back to keyword-frequency matching automatically for old-format graphs.
    nodes = retriever.retrieve_by_semantic_tags(
        transcript=raw_transcript or transcript_text,
        criterion=criterion,
        max_nodes=20,
    )

    # Format context
    context_text = retriever.format_context_for_prompt(nodes)

    # Wrap transcript in structural sandbox delimiters (Layer 3 defense-in-depth).
    # The rating LLM sees clear markers that the transcript content is DATA,
    # not instructions — helping it resist any injection that bypassed scanning.
    sandboxed_transcript = wrap_transcript_for_rating(transcript_text)

    # Combine
    parts = []
    parts.append("=== COMPANY CONTEXT FOR THIS CRITERION ===")
    parts.append(context_text)
    parts.append("")
    parts.append("=== CALL TRANSCRIPT ===")
    parts.append(sandboxed_transcript)

    return "\n".join(parts)


# ── OPT-A5: Parallel LAYER 2 skill dispatch ────────────────────────────────
# Each thread needs its own LlamaCppBackend (llama-cpp-python is not
# thread-safe). Qwen3-8B Q4_K_M is ~5 GB per instance. 7 instances ≈ 35 GB
# fits comfortably on A100 80 GB with LAYER 1 still resident.
_PARALLEL_VRAM_THRESHOLD_GB = 50.0


def _gpu_free_vram_gb() -> float:
    """
    Real free VRAM in GB on first CUDA device (0.0 if no GPU).

    Uses the CUDA driver's global view so we account for allocations outside
    PyTorch too (onnxruntime, llama.cpp, cuDNN workspaces).
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free_bytes, _total_bytes = torch.cuda.mem_get_info(0)
        return free_bytes / 1024 ** 3
    except Exception:
        return 0.0


def _should_use_parallel_skills() -> tuple[bool, float]:
    """Return (use_parallel, free_vram_gb)."""
    free_gb = _gpu_free_vram_gb()
    return free_gb >= _PARALLEL_VRAM_THRESHOLD_GB, free_gb


def _score_one_criterion(
    criterion: str,
    bundle: dict,
    transcript_text: str,
    raw_transcript: str,
    retriever,
    runner,
    use_consensus: bool,
) -> tuple[str, dict]:
    """Run one criterion's rating skill and return (criterion, enriched_result)."""
    criterion_input = build_criterion_input(
        criterion=criterion,
        transcript_text=transcript_text,
        retriever=retriever,
        raw_transcript=raw_transcript,
    )
    if use_consensus:
        result, confidence = runner.run_consensus(bundle, criterion_input)
    else:
        result = runner.run_single(bundle, criterion_input)
        ev_count = len(result.get("evidence", []) or [])
        confidence = round(min(1.0, ev_count / 3.0), 2)
    result["weight"] = CRITERION_WEIGHTS[criterion]
    result["consensus_confidence"] = confidence
    return criterion, result


def _run_skills_sequential(
    *,
    skill_bundles: dict,
    transcript_text: str,
    raw_transcript: str,
    retriever,
    use_consensus: bool,
) -> dict:
    """Original path: shared ConsensusRunner, one criterion at a time."""
    runner = ConsensusRunner()
    results: dict = {}
    for criterion, bundle in skill_bundles.items():
        _, result = _score_one_criterion(
            criterion=criterion,
            bundle=bundle,
            transcript_text=transcript_text,
            raw_transcript=raw_transcript,
            retriever=retriever,
            runner=runner,
            use_consensus=use_consensus,
        )
        results[criterion] = result
    return results


def _run_skills_parallel(
    *,
    skill_bundles: dict,
    transcript_text: str,
    raw_transcript: str,
    retriever,
    use_consensus: bool,
) -> dict:
    """
    Parallel path: dedicated LlamaCppBackend per criterion (one thread each).

    llama-cpp-python is not thread-safe across calls, so we instantiate a
    fresh backend per criterion. With Qwen3-8B Q4_K_M (~5 GB per instance)
    this fits A100 80 GB comfortably.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from skill_runtime.backends.llama_cpp_backend import LlamaCppBackend

    # Build a per-criterion runner with its own backend instance.
    # Reuses the same model GGUF file → only the in-memory KV cache + sampler
    # state are independent. The on-disk weights are mmap-shared by the OS.
    criterion_runners: dict = {}
    for criterion, bundle in skill_bundles.items():
        backend = LlamaCppBackend(bundle["model_dir"])
        criterion_runners[criterion] = ConsensusRunner(backend=backend)

    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(skill_bundles)) as pool:
        futures = {
            pool.submit(
                _score_one_criterion,
                criterion,
                bundle,
                transcript_text,
                raw_transcript,
                retriever,
                criterion_runners[criterion],
                use_consensus,
            ): criterion
            for criterion, bundle in skill_bundles.items()
        }
        for future in as_completed(futures):
            criterion, result = future.result()
            results[criterion] = result
    return results


def run_layer2_pipeline(
    layer1_json_path: Optional[str] = None,
    company_name: str = "",
    use_consensus: bool = False,
    context_graph_path: Optional[str] = None,
    output_path: Optional[str] = None,
    injection_scan_mode: str = "llm",
    layer1_dict: Optional[dict] = None,
) -> dict:
    """
    Run the complete Layer 2 rating pipeline.

    Args:
        layer1_json_path:    Path to the Layer 1 output JSON file
        layer1_dict:         OPT-A7: in-memory Layer 1 output (alternative to
                             layer1_json_path — skips disk read/write between
                             layers when both run in the same process). When
                             provided, layer1_json_path is ignored.
        company_name:        Name of the company (must have context saved)
        use_consensus:       Whether to use consensus voting for extra reliability
        context_graph_path:  Optional path to pre-built context graph
        output_path:         Optional path to save the output JSON
        injection_scan_mode: How to run the injection scanner:
                             "llm"    — static scan + LLM detector (default)
                             "static" — static regex only, no LLM
                             "off"    — disable scanning (not recommended)

    Returns:
        Complete rating results dict. If injection is detected and blocked,
        raises InjectionBlockedError.
    """
    # 1. Load Layer 1 output (in-memory dict preferred — OPT-A7).
    if layer1_dict is not None:
        layer1_output = layer1_dict
    elif layer1_json_path:
        with open(layer1_json_path, "r", encoding="utf-8") as f:
            layer1_output = json.load(f)
    else:
        raise ValueError(
            "run_layer2_pipeline requires either layer1_json_path or layer1_dict"
        )

    # 2. Format transcript
    transcript_text = format_transcript_for_rating(layer1_output)

    # Also get raw transcript for keyword extraction
    raw_transcript = " ".join(
        seg.get("text", "") for seg in layer1_output.get("transcript", [])
    )

    # 3. Security: prompt-injection scan ─────────────────────────────────────
    scan_result = None
    if injection_scan_mode != "off":
        use_llm      = (injection_scan_mode == "llm")
        scan_result  = injection_scan(transcript_text, use_llm=use_llm)

        print(f"\n[Security] Injection scan: severity={scan_result.severity}, "
              f"verdict={scan_result.verdict}, action={scan_result.recommended_action}")

        if scan_result.is_blocked():
            raise InjectionBlockedError(scan_result)

        if scan_result.verdict == "suspicious":
            print(f"[Security] WARNING — suspicious content detected. "
                  f"Proceeding with sandboxed transcript. Review report for details.")

    # 4. Load or build context graph (OPT-A9: in-process LRU cache).
    # Cache key includes context version so updates invalidate stale entries.
    if context_graph_path and Path(context_graph_path).exists():
        graph = ContextGraph.load(context_graph_path)
    else:
        # Pull just the version field for cache keying (cheap read).
        try:
            _store_for_ver = ContextStore()
            _ver = (_store_for_ver.load_raw(company_name) or {}).get("version", "1.0.0")
        except Exception:
            _ver = "1.0.0"

        graph = _build_cached_context_graph(company_name, _ver)

        # Save the graph for on-disk reuse (idempotent — overwriting is safe).
        graph_save_path = context_graph_path or str(
            Path(__file__).parent / "company_context" / "contexts" /
            f"{company_name.lower().replace(' ', '_')}_graph.json"
        )
        graph.save(graph_save_path)

    # 4. Create retriever
    retriever = GraphRetriever(graph)

    # 5. Load all rating skills
    skill_bundles = {}
    for criterion, skill_name in CRITERION_SKILLS.items():
        skill_bundles[criterion] = load_skill(skill_name)

    # 6. Run skills (parallel on big GPU, sequential otherwise — OPT-A5)
    use_parallel, vram_free_gb = _should_use_parallel_skills()
    if use_parallel:
        print(f"[LAYER 2] Parallel mode: {vram_free_gb:.0f} GB VRAM free → 7 concurrent runners")
        try:
            results = _run_skills_parallel(
                skill_bundles=skill_bundles,
                transcript_text=transcript_text,
                raw_transcript=raw_transcript,
                retriever=retriever,
                use_consensus=use_consensus,
            )
        except Exception as exc:
            print(f"[LAYER 2] Parallel startup failed ({exc}) — retrying sequential mode")
            try:
                import gc
                gc.collect()
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            results = _run_skills_sequential(
                skill_bundles=skill_bundles,
                transcript_text=transcript_text,
                raw_transcript=raw_transcript,
                retriever=retriever,
                use_consensus=use_consensus,
            )
    else:
        print(f"[LAYER 2] Sequential mode: {vram_free_gb:.0f} GB VRAM free (need ≥{_PARALLEL_VRAM_THRESHOLD_GB} GB for parallel)")
        results = _run_skills_sequential(
            skill_bundles=skill_bundles,
            transcript_text=transcript_text,
            raw_transcript=raw_transcript,
            retriever=retriever,
            use_consensus=use_consensus,
        )

    # 7. Calculate overall weighted score
    weighted_sum = 0
    weight_sum = 0
    for criterion, result in results.items():
        if criterion == "overall_severity":
            continue
        w = CRITERION_WEIGHTS[criterion]
        weighted_sum += result.get("score", 0) * w
        weight_sum += w

    overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0

    # 8. Build final output
    output = {
        "call_metadata": layer1_output.get("call_metadata", {}),
        "company_name": company_name,
        "scoring_method": "consensus" if use_consensus else "single_run",
        "overall_weighted_score": round(overall_score, 1),
        "criteria_ratings": results,
        "graph_stats": graph.stats(),
        "security": scan_result.to_dict() if scan_result else {"injection_scan": "disabled"},
    }

    # 9. Save output
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    return output


def format_context_with_skill(
    company_name: str,
    context_store: Optional[ContextStore] = None,
) -> dict:
    """
    Use the format-company-context skill to optimize the company's
    raw context for LLM consumption.

    This should be run ONCE when the QA head first submits the context,
    not on every call evaluation.
    """
    store = context_store or ContextStore()
    context = store.load(company_name)
    raw_dict = context.to_dict()

    # Load the formatting skill
    format_bundle = load_skill("format-company-context")

    # Run it
    runner = ConsensusRunner()
    input_text = json.dumps(raw_dict, indent=2)
    result = runner.run_single(format_bundle, input_text)

    return result


def process_context_change(
    company_name: str,
    old_text: str,
    new_text: str,
    field_name: str,
    topic: str,
    category: str,
    submitted_by: str = "QA_Head",
    context_graph_path: Optional[str] = None,
) -> dict:
    """
    Process a change to company context using the change management system.

    1. Creates a change ticket
    2. Runs the process-context-change skill to check semantic equivalence
    3. Updates the context graph accordingly
    4. Returns the result

    Args:
        company_name: Company name
        old_text: The original text being changed
        new_text: The new replacement text
        field_name: Which context field this belongs to
        topic: The topic in the graph
        category: The category (script_compliance, etc.)
        submitted_by: Who is making the change
        context_graph_path: Path to the context graph file
    """
    from LAYER_2.change_management.change_tracker import ChangeTracker

    # 1. Create the ticket
    tracker = ChangeTracker()
    ticket = tracker.create_ticket(
        old_text=old_text,
        new_text=new_text,
        reason="Context update",
        field_name=field_name,
        topic=topic,
        category=category,
        submitted_by=submitted_by,
    )

    # 2. Run the equivalence skill
    change_bundle = load_skill("process-context-change")
    runner = ConsensusRunner()

    # Format input: old and new text together
    input_text = f"OLD TEXT:\n{old_text}\n\nNEW TEXT:\n{new_text}"
    equivalence_result = runner.run_single(change_bundle, input_text)

    # 3. Load the context graph
    graph_path = context_graph_path or str(
        Path(__file__).parent / "company_context" / "contexts" /
        f"{company_name.lower().replace(' ', '_')}_graph.json"
    )

    if Path(graph_path).exists():
        graph = ContextGraph.load(graph_path)
    else:
        store = ContextStore()
        context_dict = store.load_raw(company_name)
        builder = GraphBuilder()
        graph = builder.build_from_context(context_dict)

    # 4. Process the ticket (updates the graph)
    ticket = tracker.process_ticket(ticket, graph, equivalence_result)

    # 5. Save updated graph
    graph.save(graph_path)

    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "is_semantically_equivalent": ticket.is_semantically_equivalent,
        "equivalence_confidence": ticket.equivalence_confidence,
        "explanation": ticket.equivalence_explanation,
        "graph_updated": True,
    }


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LAYER 2 - Call Quality Rating Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # Rate command
    rate_parser = subparsers.add_parser("rate", help="Rate a call")
    rate_parser.add_argument("--input", required=True, help="Path to Layer 1 JSON output")
    rate_parser.add_argument("--company", required=True, help="Company name")
    rate_parser.add_argument("--output", help="Output JSON path")
    rate_parser.add_argument("--consensus", action="store_true", help="Use consensus voting")
    rate_parser.add_argument("--graph", help="Path to pre-built context graph")

    # Format context command
    format_parser = subparsers.add_parser("format-context", help="Format company context")
    format_parser.add_argument("--company", required=True, help="Company name")

    # Process change command
    change_parser = subparsers.add_parser("process-change", help="Process a context change")
    change_parser.add_argument("--company", required=True, help="Company name")
    change_parser.add_argument("--old-text", required=True, help="Original text")
    change_parser.add_argument("--new-text", required=True, help="New text")
    change_parser.add_argument("--field", required=True, help="Field name")
    change_parser.add_argument("--topic", required=True, help="Topic")
    change_parser.add_argument("--category", required=True, help="Category")

    # Ingest plain-text command
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Convert a plain-text company policy file into structured JSON",
    )
    ingest_parser.add_argument("text_file", help="Path to the .txt file written by the QA head")
    ingest_parser.add_argument("--company", required=True, help="Company name")
    ingest_parser.add_argument("--version", default="1.0.0", help="Context version")
    ingest_parser.add_argument("--skip-validation", action="store_true", help="Skip validation pass")

    args = parser.parse_args()

    if args.command == "rate":
        result = run_layer2_pipeline(
            layer1_json_path=args.input,
            company_name=args.company,
            use_consensus=args.consensus,
            context_graph_path=args.graph,
            output_path=args.output,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "format-context":
        result = format_context_with_skill(args.company)
        print(json.dumps(result, indent=2))

    elif args.command == "process-change":
        result = process_context_change(
            company_name=args.company,
            old_text=args.old_text,
            new_text=args.new_text,
            field_name=args.field,
            topic=args.topic,
            category=args.category,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "ingest":
        from LAYER_2.company_context.text_ingestion import ingest_text_context

        result = ingest_text_context(
            text_path=args.text_file,
            company_name=args.company,
            context_version=args.version,
            skip_validation=args.skip_validation,
        )
        print(f"\nJSON saved to: {result['json_path']}")

    else:
        parser.print_help()
