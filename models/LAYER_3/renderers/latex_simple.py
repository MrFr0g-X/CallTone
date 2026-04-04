"""
LAYER 3 — Simple LaTeX Renderer (Mode 1)

Fills the simple_report.tex template with scores from Layer 2.
No LLM inference — pure data formatting.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "simple_report.tex"

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
    """Escape a plain-text string for safe inclusion in LaTeX."""
    if not isinstance(text, str):
        text = str(text)
    # Order matters: backslash must come first
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
    """Return the LaTeX color name for a given score."""
    if score >= 100:
        return "score100"
    if score >= 75:
        return "score75"
    if score >= 50:
        return "score50"
    if score >= 25:
        return "score25"
    return "score0"


def _score_label(score: float) -> str:
    """Return the human-readable label for an overall score."""
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 25:
        return "Poor"
    return "Critical"


def _get_summary(criterion_data: dict) -> str:
    """Extract a short summary from a criterion result."""
    summary = criterion_data.get("summary", "")
    if not summary:
        summary = criterion_data.get("score_justification", "No summary available.")
    # Truncate for the table cell — keep it to ~120 chars
    if len(summary) > 120:
        summary = summary[:117].rstrip() + "..."
    return _tex(summary)


# ── Main Renderer ────────────────────────────────────────────────────────────

def render_simple_latex(
    layer2_result: dict,
    output_path: str,
    report_date: Optional[str] = None,
) -> str:
    """
    Fill the simple_report.tex template with Layer 2 ratings and write to disk.

    Args:
        layer2_result: The dict returned by run_layer2_pipeline().
        output_path:   Where to write the .tex file.
        report_date:   Optional date string; defaults to today.

    Returns:
        Absolute path to the written .tex file.
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # ── Header fields ────────────────────────────────────────────────────────
    company_name  = _tex(layer2_result.get("company_name", "Unknown Company"))
    report_date   = report_date or datetime.now().strftime("%Y-%m-%d")
    overall_score = round(layer2_result.get("overall_weighted_score", 0), 1)
    score_label   = _score_label(overall_score)
    score_color   = _score_color(int(overall_score))

    meta      = layer2_result.get("call_metadata", {})
    audio_file = _tex(str(meta.get("audio_file", "N/A")))
    duration   = str(round(meta.get("duration_seconds", 0)))

    # ── Substitutions dict ───────────────────────────────────────────────────
    subs = {
        "<<COMPANY_NAME>>":  company_name,
        "<<REPORT_DATE>>":   report_date,
        "<<OVERALL_SCORE>>": str(int(overall_score)),
        "<<SCORE_LABEL>>":   score_label,
        "<<SCORE_COLOR>>":   score_color,
        "<<AUDIO_FILE>>":    audio_file,
        "<<DURATION>>":      duration,
    }

    # ── Per-criterion fields ─────────────────────────────────────────────────
    criteria_ratings = layer2_result.get("criteria_ratings", {})
    for criterion in CRITERIA:
        data   = criteria_ratings.get(criterion, {})
        score  = int(data.get("score", 0))
        weight = CRITERION_WEIGHTS.get(criterion, 0.0)
        contrib = round(score * weight, 2)
        color  = _score_color(score)
        summary = _get_summary(data)

        subs[f"<<SCORE_{criterion}>>"]  = str(score)
        subs[f"<<COLOR_{criterion}>>"]  = color
        subs[f"<<CONTRIB_{criterion}>>"] = f"{contrib:.2f}"
        subs[f"<<SUMMARY_{criterion}>>"] = summary

    # ── Fill template ────────────────────────────────────────────────────────
    filled = template
    for placeholder, value in subs.items():
        filled = filled.replace(placeholder, value)

    # ── Write output ─────────────────────────────────────────────────────────
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(filled, encoding="utf-8")

    return str(out.resolve())
