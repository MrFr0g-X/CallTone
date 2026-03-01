#!/usr/bin/env python3
"""
LAYER 2 QA Scorer — Scores customer service calls using the score-call-quality skill.

Takes a LAYER 1 JSON output file and produces a qa_report.json with:
- 7 dimension scores (Script Compliance, Factual Accuracy, Politeness, Empathy,
  Conflict, Resolution, Overall Severity)
- Overall weighted score (0-100)
- Flag for review when confidence is low
- Evidence quotes from the transcript

Usage:
    python LAYER_2/qa_scorer.py <layer1_json_path>
    python LAYER_2/qa_scorer.py Test_audio/bad_cs_results/bad_cs_denoised_diarized_with_emotions.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# Add repo root and skill_implementation to path
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "skill_implementation"))

from skill_runtime import load_skill, run_skill, validate_skill


def condense_transcript_for_scoring(l1_data: dict) -> str:
    """Condense LAYER 1 JSON into compact text for the LLM.

    Keeps: speaker, text, signals, audio_emotion, audio_emotion_confidence.
    Drops: id, start, end, event, full audio_emotion_scores distribution.

    Args:
        l1_data: Parsed LAYER 1 JSON output.

    Returns:
        Condensed text representation (~2-3KB for a typical call).
    """
    lines = []

    # Call metadata summary
    meta = l1_data.get("call_metadata", {})
    lines.append(
        f"CALL: {meta.get('file', 'unknown')} | "
        f"Duration: {meta.get('duration_seconds', 0):.0f}s | "
        f"Speakers: {meta.get('num_speakers', 0)}"
    )

    # Speaker summary
    lines.append("\nSPEAKER SUMMARY:")
    for speaker, summary in l1_data.get("speaker_summary", {}).items():
        talk_pct = summary.get("talk_time_pct", 0)
        signals = summary.get("behavioral_signals", {})
        signals_str = (
            ", ".join(f"{k}:{v}" for k, v in signals.items() if v > 0)
            if signals
            else "none"
        )
        lines.append(f"  {speaker}: talk={talk_pct}%, signals=[{signals_str}]")

    # Transcript
    lines.append("\nTRANSCRIPT:")
    for seg in l1_data.get("transcript", []):
        speaker = seg.get("speaker", seg.get("role", "UNKNOWN"))
        text = seg.get("text", "").strip()
        if not text:
            continue

        signals = seg.get("signals", [])
        emotion = seg.get("audio_emotion", "")
        confidence = seg.get("audio_emotion_confidence", 0)

        parts = [f"  {speaker}: {text}"]
        if signals:
            parts.append(f" [{','.join(signals)}]")
        if emotion:
            parts.append(f" (emotion:{emotion} conf:{confidence:.2f})")

        lines.append("".join(parts))

    return "\n".join(lines)


def compute_overall_score(dimensions: list) -> float:
    """Compute weighted overall score normalized to 0-100.

    Normalization (all mapped to 0.0–1.0 where 1.0 = best):
    - Script Compliance (binary 0/1): 1=compliant=good, keep as-is
    - Factual Accuracy (1-5 scale): (score - 1) / 4
    - Politeness/Empathy (1-5 scale): (score - 1) / 4
    - Conflict Detection (binary 0/1): invert → (1 - score), 0=good
    - Issue Resolution (binary 0/1): 1=resolved=good, keep as-is
    - Overall Severity (1-4 scale): invert → (4 - score) / 3, 1=minor=best

    Args:
        dimensions: List of dimension dicts with name, weight, score.

    Returns:
        Overall score as float (0-100).
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for dim in dimensions:
        name = dim["name"]
        score = dim["score"]
        weight = dim["weight"]

        if name in ("Politeness & Tone", "Empathy", "Factual Accuracy"):
            # 1-5 scale → normalize to 0-1
            normalized = (score - 1.0) / 4.0
        elif name == "Conflict Detection":
            # 0=no conflict (good), 1=conflict (bad) → invert
            normalized = 1.0 - score
        elif name in ("Issue Resolution", "Script Compliance"):
            # 0=bad, 1=good → keep as-is
            normalized = float(score)
        elif name == "Overall Severity":
            # 1=minor (best), 4=critical (worst) → invert
            normalized = (4.0 - score) / 3.0
        else:
            normalized = score

        normalized = max(0.0, min(1.0, normalized))
        weighted_sum += weight * normalized
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return round((weighted_sum / total_weight) * 100, 1)


def check_flag_for_review(dimensions: list) -> Tuple[bool, str]:
    """Flag call for review if any dimension confidence < 0.7.

    Args:
        dimensions: List of dimension dicts with name and confidence.

    Returns:
        Tuple of (should_flag, reason_string).
    """
    low_conf = []
    for dim in dimensions:
        if dim["confidence"] < 0.7:
            low_conf.append(f"{dim['name']} ({dim['confidence']:.2f})")

    if low_conf:
        return True, f"Low confidence on: {', '.join(low_conf)}"
    return False, ""


def extract_layer1_summary(l1_data: dict) -> dict:
    """Extract summary statistics from LAYER 1 data for the QA report.

    Handles both role-identified transcripts (speaker names contain 'agent'/
    'service') and raw speaker labels (SPEAKER_A/B). For raw labels, the
    speaker with the lower talk_time_pct is assumed to be the agent.

    Emotion stats are computed from transcript segments (audio_emotion field)
    rather than the speaker_summary.emotion_distribution, which may be stale.

    Args:
        l1_data: Parsed LAYER 1 JSON.

    Returns:
        Summary dict with key metrics.
    """
    summary = {
        "agent_talk_time_pct": 0.0,
        "customer_dominant_emotion": "unknown",
        "customer_anger_pct": 0.0,
        "escalation_signals_detected": 0,
        "frustrated_signals_detected": 0,
    }

    speaker_summary = l1_data.get("speaker_summary", {})

    # Determine agent vs customer speaker
    agent_speaker = None
    customer_speaker = None

    for speaker, data in speaker_summary.items():
        role = data.get("role", speaker)
        if "agent" in role.lower() or "service" in role.lower():
            agent_speaker = speaker
        elif "customer" in role.lower() or "caller" in role.lower():
            customer_speaker = speaker

    # Fallback: if roles not identified, agent = lower talk_time_pct
    if agent_speaker is None and len(speaker_summary) == 2:
        speakers = list(speaker_summary.items())
        if speakers[0][1].get("talk_time_pct", 0) <= speakers[1][1].get("talk_time_pct", 0):
            agent_speaker, customer_speaker = speakers[0][0], speakers[1][0]
        else:
            agent_speaker, customer_speaker = speakers[1][0], speakers[0][0]

    # Agent talk time
    if agent_speaker and agent_speaker in speaker_summary:
        summary["agent_talk_time_pct"] = speaker_summary[agent_speaker].get(
            "talk_time_pct", 0.0
        )

    # Customer signals from speaker_summary
    if customer_speaker and customer_speaker in speaker_summary:
        signals = speaker_summary[customer_speaker].get("behavioral_signals", {})
        summary["escalation_signals_detected"] = signals.get("ESCALATION", 0)
        summary["frustrated_signals_detected"] = signals.get("FRUSTRATED", 0)

    # Compute emotion stats from transcript segments (more accurate)
    emotion_counts: dict[str, int] = {}
    for seg in l1_data.get("transcript", []):
        seg_speaker = seg.get("speaker", seg.get("role", ""))
        if customer_speaker and seg_speaker != customer_speaker:
            continue
        emo = seg.get("audio_emotion", "")
        if emo:
            emotion_counts[emo] = emotion_counts.get(emo, 0) + 1

    total_emotions = sum(emotion_counts.values())
    if total_emotions > 0:
        anger_count = emotion_counts.get("anger", 0)
        summary["customer_anger_pct"] = round(
            (anger_count / total_emotions) * 100, 1
        )
        dominant = max(emotion_counts, key=emotion_counts.get)
        summary["customer_dominant_emotion"] = dominant.lower()

    return summary


def score_call(l1_json_path: str) -> dict:
    """Score a customer service call using the score-call-quality skill.

    Args:
        l1_json_path: Path to LAYER 1 JSON output file.

    Returns:
        Complete QA report dict matching qa_report.json schema.

    Raises:
        FileNotFoundError: If l1_json_path does not exist.
        ValueError: If skill output is not valid JSON.
    """
    l1_path = Path(l1_json_path)
    if not l1_path.exists():
        raise FileNotFoundError(f"LAYER 1 JSON not found: {l1_json_path}")

    # 1. Load LAYER 1 JSON
    with open(l1_path, "r", encoding="utf-8") as f:
        l1_data = json.load(f)

    # 2. Condense transcript for LLM
    condensed = condense_transcript_for_scoring(l1_data)

    # 3. Load and validate the scoring skill
    bundle = load_skill("score-call-quality")
    is_valid, errors = validate_skill("score-call-quality", bundle)
    if not is_valid:
        raise ValueError(f"Skill validation failed: {errors}")

    # 4. Run the skill
    print(f"Scoring call: {l1_path.name}")
    print(f"Condensed transcript: {len(condensed)} chars")
    raw_output = run_skill(bundle, condensed)

    # 5. Parse output JSON (with repair fallback)
    try:
        skill_result = json.loads(raw_output)
    except json.JSONDecodeError:
        # Attempt JSON repair: extract between first { and last }
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                skill_result = json.loads(raw_output[start:end])
            except json.JSONDecodeError:
                raise ValueError(
                    f"Skill output is not valid JSON even after repair.\n"
                    f"Raw output:\n{raw_output}"
                )
        else:
            raise ValueError(f"No JSON found in skill output:\n{raw_output}")

    dimensions = skill_result.get("dimensions", [])
    if len(dimensions) != 7:
        raise ValueError(
            f"Expected 7 dimensions, got {len(dimensions)}. "
            f"Raw output:\n{raw_output}"
        )

    # 6. Compute overall score
    overall_score = compute_overall_score(dimensions)

    # 7. Check flag for review
    flag, flag_reason = check_flag_for_review(dimensions)

    # 8. Extract LAYER 1 summary
    l1_summary = extract_layer1_summary(l1_data)

    # 9. Assemble the QA report
    call_id = l1_path.stem
    meta = l1_data.get("call_metadata", {})

    qa_report = {
        "call_id": call_id,
        "file": meta.get("file", l1_path.name),
        "duration_seconds": meta.get("duration_seconds", 0.0),
        "overall_score": overall_score,
        "flag_for_review": flag,
        "flag_reason": flag_reason if flag else None,
        "dimensions": dimensions,
        "layer1_summary": l1_summary,
        "metadata": {
            "scorer_model": "Meta-Llama-3.1-8B-Instruct-Q8_0",
            "skill_version": "1.0.0",
            "scored_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    return qa_report


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python LAYER_2/qa_scorer.py <layer1_json_path>")
        print(
            "Example: python LAYER_2/qa_scorer.py "
            "Test_audio/bad_cs_results/bad_cs_denoised_diarized_with_emotions.json"
        )
        sys.exit(1)

    l1_json_path = sys.argv[1]

    try:
        report = score_call(l1_json_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Write report to file next to input
    input_path = Path(l1_json_path)
    output_path = input_path.parent / f"{input_path.stem}_qa_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nQA Report written to: {output_path}")
    print(f"Overall Score: {report['overall_score']}/100")
    print(f"Flag for Review: {report['flag_for_review']}")
    if report["flag_reason"]:
        print(f"Flag Reason: {report['flag_reason']}")

    print("\nDimension Scores:")
    for dim in report["dimensions"]:
        print(
            f"  {dim['name']}: {dim['score']} ({dim['score_range']}) "
            f"[confidence: {dim['confidence']:.2f}]"
        )


if __name__ == "__main__":
    main()
