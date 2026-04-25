"""Adapter that runs ``models/run_full_pipeline.py`` as a subprocess.

D-3 scaffolds the interface only. D-4 will wire real step-tracking and
result-file collection. We use a subprocess (not an in-process import) for
two reasons:

1. **Clean VRAM per job.** On the single-GPU Vast box, torch + llama-cpp +
   pyannote all hold on to allocations that are painful to free reliably
   from Python. Exiting the process is a 100% guaranteed ``cudaFree``.
2. **Crash isolation.** A segfault in ``pyannote`` or ``llama_cpp`` would
   take down the whole FastAPI worker if it ran in-process. As a
   subprocess, it only fails the one job.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

log = logging.getLogger("calltone.model_server.pipeline")

# Ordered stage markers emitted by ``models/run_full_pipeline.py``. The first
# regex that matches a stdout line wins, and the corresponding status becomes
# the job's current state. Order matters only for documentation — status is
# set directly, not inferred from sequence.
STAGE_MARKERS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"LAYER 1 — STEP 1: DENOIS", re.I), "denoising", 10),
    (re.compile(r"LAYER 1 — STEP 2: TRANSCRIPTION", re.I), "transcribing", 30),
    (re.compile(r"LAYER 1 — STEP 3: ROLE IDENT", re.I), "role_ident", 50),
    (re.compile(r"LAYER 1 — STEP 4: EMOTION", re.I), "emotion", 65),
    (re.compile(r"LAYER 2 — CALL QUALITY", re.I), "scoring", 80),
    (re.compile(r"LAYER 3 — REPORT", re.I), "rendering", 95),
]


def classify_line(line: str) -> tuple[str, int] | None:
    """Return ``(status, progress_pct)`` if *line* matches a stage marker."""
    for pattern, status, pct in STAGE_MARKERS:
        if pattern.search(line):
            return status, pct
    return None

# Resolve to the sibling ``models/run_full_pipeline.py`` regardless of CWD.
_MODEL_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODEL_SERVER_DIR.parent
_PIPELINE_SCRIPT = _REPO_ROOT / "models" / "run_full_pipeline.py"


class PipelineNotInstalledError(RuntimeError):
    pass


def pipeline_script_path() -> Path:
    if not _PIPELINE_SCRIPT.is_file():
        raise PipelineNotInstalledError(
            f"pipeline entrypoint not found at {_PIPELINE_SCRIPT}"
        )
    return _PIPELINE_SCRIPT


def build_command(
    *,
    audio_path: Path,
    company: str,
    output_dir: Path,
    speakers: int | None = None,
    report_mode: str = "both",
    asr_engine: str = "fasterwhisper",
    use_consensus: bool = False,
) -> list[str]:
    # QA calls are agent + customer = 2 speakers. Letting pyannote auto-detect
    # over-segments short calls into 3+ clusters, leaving the extra cluster
    # without a role label and zeroing Issue Resolution downstream.
    effective_speakers = 2 if speakers is None else speakers

    cmd: list[str] = [
        sys.executable,
        str(pipeline_script_path()),
        str(audio_path),
        "--company",
        company,
        "--output-dir",
        str(output_dir),
        "--report",
        report_mode,
        "--asr",
        asr_engine,
        "--speakers",
        str(effective_speakers),
    ]
    if use_consensus:
        cmd.append("--use-consensus")
    return cmd


def run_pipeline_blocking(
    *,
    audio_path: Path,
    company: str,
    output_dir: Path,
    speakers: int | None = None,
    report_mode: str = "both",
    asr_engine: str = "fasterwhisper",
    use_consensus: bool = False,
    timeout_seconds: int | None = None,
    on_line: Callable[[str], None] | None = None,
) -> int:
    """Run the pipeline subprocess synchronously and stream its stdout.

    ``on_line(line)`` is invoked for each line of stdout as it arrives, which
    is how ``endpoints.py`` keeps job status updated while the subprocess
    runs. Returns the subprocess exit code (0 on success).

    Intended to be called via ``asyncio.to_thread`` from the FastAPI event
    loop so polling clients can still hit ``/v1/jobs/{id}`` while the
    pipeline is mid-run.
    """
    cmd = build_command(
        audio_path=audio_path,
        company=company,
        output_dir=output_dir,
        speakers=speakers,
        report_mode=report_mode,
        asr_engine=asr_engine,
        use_consensus=use_consensus,
    )
    log.info(
        "model_server.pipeline.start",
        extra={"event": "pipeline_start", "cmd": cmd},
    )
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    env.setdefault("OMP_NUM_THREADS", "4")
    env.setdefault("MKL_NUM_THREADS", "4")
    env.setdefault("OPENBLAS_NUM_THREADS", "4")
    env.setdefault("NUMEXPR_NUM_THREADS", "4")

    pipeline_log = output_dir / "pipeline.log"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Popen so we can stream stdout as the pipeline progresses. stderr is
    # merged in so stack traces don't get lost on failure.
    proc = subprocess.Popen(  # noqa: S603 — cmd is built from trusted inputs
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    try:
        assert proc.stdout is not None
        with pipeline_log.open("a", encoding="utf-8", buffering=1) as log_file:
            for raw in proc.stdout:
                line = raw.rstrip()
                print(line, file=log_file)
                if on_line is not None:
                    try:
                        on_line(line)
                    except Exception:  # pragma: no cover — callback must not kill us
                        log.exception("model_server.pipeline.on_line_failed")
        if timeout_seconds is not None and timeout_seconds > 0:
            proc.wait(timeout=timeout_seconds)
        else:
            proc.wait()
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    return proc.returncode


def _load_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(
            "model_server.pipeline.json_load_failed",
            extra={"event": "json_load_failed", "path": str(path), "err": str(exc)},
        )
        return None


def _layer3_report_json(layer2: dict | None, summary: dict | None, output_dir: Path) -> dict:
    layer2 = layer2 or {}
    criteria = layer2.get("criteria_ratings", {}) if isinstance(layer2, dict) else {}
    overall = layer2.get("overall_weighted_score", 0)
    strengths: list[str] = []
    weaknesses: list[str] = []
    actions: list[str] = []

    for criterion, info in criteria.items():
        if not isinstance(info, dict):
            continue
        label = criterion.replace("_", " ").title()
        score = info.get("score", 0) or 0
        summary_text = (info.get("summary") or "").strip()
        line = f"{label} ({score}/100): {summary_text or 'No summary returned.'}"
        if score >= 70:
            strengths.append(line)
        else:
            weaknesses.append(line)
        rec = (info.get("recommendation") or info.get("recommended_action") or "").strip()
        if rec:
            actions.append(f"{label}: {rec}")

    outputs = []
    if isinstance(summary, dict):
        outputs = summary.get("layer3", {}).get("outputs", []) or []
    if not outputs:
        outputs = [p.name for p in sorted(output_dir.glob("*report.*"))]

    return {
        "summary": (
            f"Layer 3 report generated for a call scoring {overall}/100. "
            f"Artifacts: {', '.join(outputs) if outputs else 'none'}."
        ),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommended_actions": actions or ["Review the lowest scoring dimensions with the agent."],
        "artifacts": outputs,
    }


def load_result_json(output_dir: Path) -> dict | None:
    """Collect the files that ``run_full_pipeline.py`` wrote into *output_dir*
    and bundle them for the backend.

    Returns ``{"layer1": ..., "layer2": ..., "summary": ..., "call_rating": ...}``
    or ``None`` if neither an L2 nor a ``call_rating.json`` file is present.

    Supports two pipeline shapes:
      * real pipeline → ``*_diarized_with_emotions.json`` + ``layer2_ratings.json``
      * test stub     → ``call_rating.json``
    """
    bundle: dict[str, object] = {}

    l1_candidates = sorted(output_dir.glob("*_diarized_with_emotions.json"))
    if not l1_candidates:
        l1_candidates = sorted(output_dir.glob("*_diarized.json"))
    if l1_candidates:
        bundle["layer1"] = _load_json(l1_candidates[0])

    l2 = output_dir / "layer2_ratings.json"
    if l2.is_file():
        bundle["layer2"] = _load_json(l2)

    summary = output_dir / "pipeline_summary.json"
    summary_obj = _load_json(summary) if summary.is_file() else None
    if summary_obj is not None:
        bundle["summary"] = summary_obj

    # Fallback path (tests): a single ``call_rating.json`` with the whole report.
    cr = output_dir / "call_rating.json"
    if cr.is_file():
        bundle["call_rating"] = _load_json(cr)

    layer2_obj = bundle.get("layer2")
    layer3_outputs = []
    if isinstance(summary_obj, dict):
        layer3_outputs = summary_obj.get("layer3", {}).get("outputs", []) or []
    report_files = [p.name for p in sorted(output_dir.glob("*report.*"))]
    if layer3_outputs or report_files:
        bundle["layer3"] = {
            "outputs": layer3_outputs or report_files,
            "report_json": _layer3_report_json(
                layer2_obj if isinstance(layer2_obj, dict) else None,
                summary_obj,
                output_dir,
            ),
        }

    return bundle or None
