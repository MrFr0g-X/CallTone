"""
LAYER 3 — Narrative LaTeX Renderer (Mode 2)

Two sub-modes:
  use_skill=True  (default) — runs the generate-call-report skill through the
                              LLM to produce flowing, agent-directed narrative
                              paragraphs, then fills narrative_report.tex.

  use_skill=False           — skips the LLM and formats the existing summary /
                              score_justification / evidence fields from Layer 2
                              directly into the template. Faster; same template.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Make sure the skill runtime is importable
_SKILL_ROOT = Path(__file__).parent.parent.parent / "skill_implementation"
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "narrative_report.tex"

CRITERIA = [
    "script_compliance",
    "factual_accuracy",
    "politeness_tone",
    "empathy",
    "conflict_detection",
    "issue_resolution",
    "overall_severity",
]

CRITERION_WEIGHTS = {
    "script_compliance":  0.25,
    "factual_accuracy":   0.25,
    "politeness_tone":    0.15,
    "empathy":            0.10,
    "conflict_detection": 0.15,
    "issue_resolution":   0.05,
    "overall_severity":   0.05,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tex(text: str) -> str:
    """Escape plain text for LaTeX."""
    if not isinstance(text, str):
        text = str(text)
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&",  r"\&"),
        ("%",  r"\%"),
        ("$",  r"\$"),
        ("#",  r"\#"),
        ("_",  r"\_"),
        ("{",  r"\{"),
        ("}",  r"\}"),
        ("~",  r"\textasciitilde{}"),
        ("^",  r"\textasciicircum{}"),
        ("<",  r"\textless{}"),
        (">",  r"\textgreater{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _score_color(score: int) -> str:
    if score >= 100: return "score100"
    if score >= 75:  return "score75"
    if score >= 50:  return "score50"
    if score >= 25:  return "score25"
    return "score0"


def _score_label(score: float) -> str:
    if score >= 90: return "Excellent"
    if score >= 70: return "Good"
    if score >= 50: return "Fair"
    if score >= 25: return "Poor"
    return "Critical"


def _items_to_latex(items: list) -> str:
    """Convert a list of strings into LaTeX \\item lines."""
    if not items:
        return r"\item None identified."
    return "\n".join(r"\item " + _tex(str(item)) for item in items)


def _extract_evidence_items(criterion: str, data: dict) -> list:
    """
    Return a flat list of evidence strings from a criterion result dict,
    handling the different evidence structures each skill produces.
    """
    items = []

    # script_compliance: evidence = [{rule, quote, met}, ...]
    if criterion == "script_compliance":
        for e in data.get("evidence", []):
            status = "Met" if e.get("met") else "VIOLATED"
            rule   = e.get("rule", "")
            quote  = e.get("quote", "")
            items.append(f"[{status}] Rule: {rule} — \"{quote}\"")

    # factual_accuracy: claims = [{claim, correct, source_quote}, ...]
    elif criterion == "factual_accuracy":
        for c in data.get("claims", []):
            status = "Correct" if c.get("correct") else "INCORRECT"
            claim  = c.get("claim", "")
            quote  = c.get("source_quote", c.get("quote", ""))
            items.append(f"[{status}] {claim}" + (f' — "{quote}"' if quote else ""))
        # fallback to generic evidence list
        if not items:
            for e in data.get("evidence", []):
                items.append(str(e))

    # politeness_tone: positive_examples / negative_examples
    elif criterion == "politeness_tone":
        for ex in data.get("positive_examples", []):
            items.append(f"[Good] {ex}")
        for ex in data.get("negative_examples", []):
            items.append(f"[Issue] {ex}")
        if not items:
            for e in data.get("evidence", []):
                items.append(str(e))

    # empathy: emotional_moments = [{customer_quote, customer_emotion, agent_response, empathy_shown, quality}]
    elif criterion == "empathy":
        for m in data.get("emotional_moments", []):
            shown   = "Shown" if m.get("empathy_shown") else "MISSING"
            quality = m.get("quality", "")
            emotion = m.get("customer_emotion", "")
            cq      = m.get("customer_quote", "")
            ar      = m.get("agent_response", "")
            items.append(
                f"[Empathy {shown}] Customer ({emotion}): \"{cq}\" → Agent ({quality}): \"{ar}\""
            )

    # conflict_detection: conflicts_detected = [{description, severity, customer_quote, agent_response, handled_well}]
    elif criterion == "conflict_detection":
        if not data.get("conflicts_detected"):
            items.append("No conflicts detected in this call.")
        for c in data.get("conflicts_detected", []):
            handled  = "Handled well" if c.get("handled_well") else "POORLY handled"
            sev      = c.get("severity", "")
            desc     = c.get("description", "")
            cq       = c.get("customer_quote", "")
            items.append(f"[{sev.upper()} — {handled}] {desc} — Customer said: \"{cq}\"")
        if data.get("agent_caused_conflict"):
            items.append("[CRITICAL] Agent contributed to or caused a conflict.")
        if data.get("escalation_occurred"):
            items.append("[ESCALATION] Call escalated during interaction.")

    # issue_resolution: steps / resolution_steps
    elif criterion == "issue_resolution":
        for step in data.get("resolution_steps", data.get("steps", [])):
            items.append(str(step))
        customer_issue = data.get("customer_issue", "")
        if customer_issue:
            items.insert(0, f"Customer issue: {customer_issue}")
        resolved = data.get("resolved")
        if resolved is not None:
            items.append("Resolved: Yes" if resolved else "Resolved: No")
        if not items:
            for e in data.get("evidence", []):
                items.append(str(e))

    # overall_severity: issues_found = [{issue, severity_contribution, evidence}]
    elif criterion == "overall_severity":
        severity = data.get("severity", "")
        if severity:
            items.append(f"Overall severity classification: {severity}")
        for issue in data.get("issues_found", []):
            sev   = issue.get("severity_contribution", "")
            desc  = issue.get("issue", "")
            evid  = issue.get("evidence", "")
            items.append(f"[{sev.upper()}] {desc}" + (f' — "{evid}"' if evid else ""))
        worst = data.get("worst_issue", "")
        if worst:
            items.append(f"Most severe issue: {worst}")

    # Generic fallback
    if not items:
        for key in ("evidence", "examples", "observations"):
            for e in data.get(key, []):
                items.append(str(e) if not isinstance(e, dict) else json.dumps(e))
            if items:
                break

    return items


def _extract_violation_items(criterion: str, data: dict) -> list:
    """Return flat list of violation/problem strings for a criterion."""
    items = []

    if criterion == "script_compliance":
        items = list(data.get("violations", []))

    elif criterion == "factual_accuracy":
        items = list(data.get("inaccuracies", data.get("errors", [])))

    elif criterion == "politeness_tone":
        items = list(data.get("negative_examples", data.get("violations", [])))

    elif criterion == "empathy":
        items = list(data.get("missed_opportunities", []))

    elif criterion == "conflict_detection":
        poorly = [
            c.get("description", "")
            for c in data.get("conflicts_detected", [])
            if not c.get("handled_well")
        ]
        items = poorly or []
        if data.get("agent_caused_conflict"):
            items.append("Agent caused or escalated a conflict.")

    elif criterion == "issue_resolution":
        items = list(data.get("unresolved_issues", data.get("gaps", [])))
        if not items and data.get("resolved") is False:
            items.append("Customer issue was not resolved during this call.")

    elif criterion == "overall_severity":
        items = list(data.get("recommendations", []))

    # Generic fallback
    if not items:
        for key in ("violations", "issues", "negatives", "problems", "recommendations"):
            raw = data.get(key, [])
            if raw:
                items = [str(x) for x in raw]
                break

    return items


# ── Layer 2 → skill input formatter ─────────────────────────────────────────

def _format_layer2_for_skill(layer2_result: dict) -> str:
    """
    Convert the Layer 2 result dict into a readable text block that the
    generate-call-report skill can process.
    """
    lines = []
    company = layer2_result.get("company_name", "Unknown")
    overall = layer2_result.get("overall_weighted_score", 0)
    lines.append(f"CALL QUALITY RATING ANALYSIS")
    lines.append(f"Company: {company}")
    lines.append(f"Overall Weighted Score: {overall}/100")
    lines.append("")

    criteria_ratings = layer2_result.get("criteria_ratings", {})
    for criterion in CRITERIA:
        data   = criteria_ratings.get(criterion, {})
        score  = data.get("score", 0)
        weight = CRITERION_WEIGHTS.get(criterion, 0.0)
        label  = criterion.replace("_", " ").upper()
        lines.append(f"=== {label} (Score: {score}/100, Weight: {weight*100:.0f}%) ===")
        lines.append(f"Summary: {data.get('summary', 'N/A')}")
        lines.append(f"Score Justification: {data.get('score_justification', 'N/A')}")

        # Evidence
        evidence_items = _extract_evidence_items(criterion, data)
        if evidence_items:
            lines.append("Evidence:")
            for item in evidence_items[:8]:   # cap to avoid token overflow
                lines.append(f"  - {item}")

        # Violations / problems
        violation_items = _extract_violation_items(criterion, data)
        if violation_items:
            lines.append("Violations / Issues:")
            for item in violation_items[:6]:
                lines.append(f"  - {item}")

        lines.append("")

    return "\n".join(lines)


# ── Fallback formatter (no-skill mode) ───────────────────────────────────────

def _build_fallback_narratives(layer2_result: dict) -> dict:
    """
    Build per-criterion narratives WITHOUT running the LLM.
    Uses the existing summary + score_justification fields as the narrative.
    """
    criteria_ratings = layer2_result.get("criteria_ratings", {})
    narratives = {}
    for criterion in CRITERIA:
        data  = criteria_ratings.get(criterion, {})
        score = data.get("score", 0)
        summary = data.get("summary", "No summary available.")
        justification = data.get("score_justification", "")
        if justification and justification != summary:
            narratives[criterion] = f"{summary} {justification}"
        else:
            narratives[criterion] = summary

    # Build executive summary from overall score + top criteria
    overall = layer2_result.get("overall_weighted_score", 0)
    company = layer2_result.get("company_name", "the company")
    label   = _score_label(overall)
    exec_summary = (
        f"This call received an overall quality score of {overall:.1f}/100, "
        f"classified as \"{label}\" against {company}'s standards. "
        f"The evaluation covered 7 criteria weighted by their compliance risk. "
        f"See the detailed breakdown below for criterion-specific findings."
    )

    # Key strengths = criteria scored 75+
    strengths = [
        f"{c.replace('_', ' ').title()} ({criteria_ratings[c].get('score', 0)}/100)"
        for c in CRITERIA
        if criteria_ratings.get(c, {}).get("score", 0) >= 75
    ] or ["No standout strengths identified — review all criteria for improvement opportunities."]

    # Areas = criteria scored < 75
    improvements = [
        f"{c.replace('_', ' ').title()} ({criteria_ratings[c].get('score', 0)}/100): "
        + criteria_ratings[c].get("summary", "Requires attention.")[:80]
        for c in CRITERIA
        if criteria_ratings.get(c, {}).get("score", 0) < 75
    ] or ["No critical gaps identified — focus on maintaining current performance."]

    # Coaching recommendation
    sev_data = criteria_ratings.get("overall_severity", {})
    recs = sev_data.get("recommendations", [])
    if recs:
        coaching = " ".join(recs[:3])
    else:
        coaching = (
            "Focus coaching on the lowest-scoring criteria, "
            "using the specific evidence highlighted in this report as concrete examples."
        )

    return {
        "executive_summary": exec_summary,
        "criteria_narratives": narratives,
        "key_strengths": strengths,
        "areas_for_improvement": improvements,
        "coaching_recommendation": coaching,
    }


# ── Main Renderer ────────────────────────────────────────────────────────────

def render_narrative_latex(
    layer2_result: dict,
    output_path: str,
    use_skill: bool = True,
    report_date: Optional[str] = None,
) -> str:
    """
    Render Mode 2: narrative report with per-criterion explanations.

    Args:
        layer2_result: Dict returned by run_layer2_pipeline().
        output_path:   Where to write the .tex file.
        use_skill:     If True, runs the generate-call-report LLM skill.
                       If False, formats existing Layer 2 data directly (faster).
        report_date:   Optional date string; defaults to today.

    Returns:
        Absolute path to the written .tex file.
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # ── Get narrative content ────────────────────────────────────────────────
    if use_skill:
        narrative_data = _run_narrative_skill(layer2_result)
    else:
        narrative_data = _build_fallback_narratives(layer2_result)

    # ── Header subs ──────────────────────────────────────────────────────────
    company_name  = _tex(layer2_result.get("company_name", "Unknown Company"))
    report_date   = report_date or datetime.now().strftime("%Y-%m-%d")
    overall_score = round(layer2_result.get("overall_weighted_score", 0), 1)
    score_label   = _score_label(overall_score)
    score_color   = _score_color(int(overall_score))
    meta          = layer2_result.get("call_metadata", {})
    audio_file    = _tex(str(meta.get("audio_file", "N/A")))
    duration      = str(round(meta.get("duration_seconds", 0)))

    subs = {
        "<<COMPANY_NAME>>":  company_name,
        "<<REPORT_DATE>>":   report_date,
        "<<OVERALL_SCORE>>": str(int(overall_score)),
        "<<SCORE_LABEL>>":   score_label,
        "<<SCORE_COLOR>>":   score_color,
        "<<AUDIO_FILE>>":    audio_file,
        "<<DURATION>>":      duration,
    }

    # ── Narrative fields ─────────────────────────────────────────────────────
    subs["<<EXECUTIVE_SUMMARY>>"] = _tex(
        narrative_data.get("executive_summary", "No executive summary available.")
    )

    criteria_narratives = narrative_data.get("criteria_narratives", {})
    criteria_ratings    = layer2_result.get("criteria_ratings", {})

    for criterion in CRITERIA:
        data  = criteria_ratings.get(criterion, {})
        score = int(data.get("score", 0))
        weight = CRITERION_WEIGHTS.get(criterion, 0.0)
        contrib = round(score * weight, 2)
        color   = _score_color(score)

        subs[f"<<SCORE_{criterion}>>"]   = str(score)
        subs[f"<<COLOR_{criterion}>>"]   = color
        subs[f"<<CONTRIB_{criterion}>>"] = f"{contrib:.2f}"

        # Narrative paragraph
        narrative = criteria_narratives.get(criterion, data.get("summary", "No narrative available."))
        subs[f"<<NARRATIVE_{criterion}>>"] = _tex(narrative)

        # Evidence items
        evidence_items = _extract_evidence_items(criterion, data)
        subs[f"<<EVIDENCE_{criterion}>>"] = _items_to_latex(evidence_items)

        # Violation items
        violation_items = _extract_violation_items(criterion, data)
        subs[f"<<VIOLATIONS_{criterion}>>"] = _items_to_latex(violation_items)

    # ── Coaching summary ─────────────────────────────────────────────────────
    strengths = narrative_data.get("key_strengths", [])
    subs["<<KEY_STRENGTHS>>"] = _items_to_latex(strengths)

    improvements = narrative_data.get("areas_for_improvement", [])
    subs["<<AREAS_FOR_IMPROVEMENT>>"] = _items_to_latex(improvements)

    coaching = narrative_data.get("coaching_recommendation", "")
    subs["<<COACHING_RECOMMENDATION>>"] = _tex(coaching)

    # ── Fill and write ───────────────────────────────────────────────────────
    filled = template
    for placeholder, value in subs.items():
        filled = filled.replace(placeholder, value)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(filled, encoding="utf-8")

    return str(out.resolve())


def _run_narrative_skill(layer2_result: dict) -> dict:
    """Run the generate-call-report skill and return the parsed result."""
    from skill_runtime.loader import load_skill
    from LAYER_2.consensus.consensus_runner import ConsensusRunner

    # Format Layer 2 data as skill input
    input_text = _format_layer2_for_skill(layer2_result)

    bundle = load_skill("generate-call-report")
    runner = ConsensusRunner()
    result = runner.run_single(bundle, input_text)

    return result
