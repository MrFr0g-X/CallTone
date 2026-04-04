"""
LAYER 3 — Reporting Pipeline

Consumes Layer 2 rating output (JSON) and produces LaTeX reports.

Two report modes:
  simple    — fills a clean table-based LaTeX template with scores and
              one-line summaries. No LLM inference needed.

  narrative — runs the generate-call-report skill to produce per-criterion
              narrative paragraphs that explain WHY each rating was given,
              then fills a richer LaTeX template. One LLM call for all 7 criteria.

Usage (Python):
    from LAYER_3.pipeline import run_layer3_pipeline
    run_layer3_pipeline("layer2_ratings.json", "output/", mode="both")

Usage (CLI):
    python -m LAYER_3.pipeline --input layer2_ratings.json --output-dir reports/ --mode both
    python -m LAYER_3.pipeline --input layer2_ratings.json --output-dir reports/ --mode simple
    python -m LAYER_3.pipeline --input layer2_ratings.json --output-dir reports/ --mode narrative --no-skill
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Literal

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).parent.parent
for _p in [
    _PROJECT_ROOT,
    _PROJECT_ROOT / "skill_implementation",
    _PROJECT_ROOT / "LAYER_2",
]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from LAYER_3.renderers.latex_simple import render_simple_latex
from LAYER_3.renderers.narrative_renderer import render_narrative_latex


ReportMode = Literal["simple", "narrative", "both"]


def run_layer3_pipeline(
    layer2_json_path: str,
    output_dir: str,
    mode: ReportMode = "both",
    use_skill: bool = True,
    report_date: str | None = None,
) -> dict:
    """
    Generate LaTeX report(s) from a Layer 2 ratings JSON file.

    Args:
        layer2_json_path: Path to the layer2_ratings.json produced by LAYER 2.
        output_dir:       Directory where .tex files will be written.
        mode:             "simple", "narrative", or "both".
        use_skill:        (narrative mode only) If False, skips the LLM and
                          formats existing Layer 2 data directly. Faster.
        report_date:      Report date string (default: today).

    Returns:
        Dict with keys "simple_tex" and/or "narrative_tex" pointing to output files.
    """
    # Load Layer 2 JSON
    with open(layer2_json_path, "r", encoding="utf-8") as f:
        layer2_result = json.load(f)

    out_dir   = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem      = Path(layer2_json_path).stem   # e.g. "layer2_ratings"
    report_dt = report_date or datetime.now().strftime("%Y-%m-%d")
    outputs   = {}

    print(f"\n{'='*70}")
    print("LAYER 3 — REPORT GENERATION")
    print(f"{'='*70}")
    print(f"Input:       {layer2_json_path}")
    print(f"Output dir:  {out_dir}")
    print(f"Mode:        {mode}")
    print(f"Use skill:   {use_skill if mode != 'simple' else 'N/A (simple mode)'}")
    print(f"Company:     {layer2_result.get('company_name', 'Unknown')}")
    print(f"Score:       {layer2_result.get('overall_weighted_score', '?')} / 100\n")

    # ── Mode 1: Simple ────────────────────────────────────────────────────────
    if mode in ("simple", "both"):
        simple_tex_path = str(out_dir / f"{stem}_simple_report.tex")
        print("Rendering simple report...")
        path = render_simple_latex(
            layer2_result=layer2_result,
            output_path=simple_tex_path,
            report_date=report_dt,
        )
        outputs["simple_tex"] = path
        print(f"  Written: {path}")

    # ── Mode 2: Narrative ─────────────────────────────────────────────────────
    if mode in ("narrative", "both"):
        narrative_tex_path = str(out_dir / f"{stem}_narrative_report.tex")
        skill_label = "LLM skill" if use_skill else "direct formatting (no LLM)"
        print(f"Rendering narrative report using {skill_label}...")
        path = render_narrative_latex(
            layer2_result=layer2_result,
            output_path=narrative_tex_path,
            use_skill=use_skill,
            report_date=report_dt,
        )
        outputs["narrative_tex"] = path
        print(f"  Written: {path}")

    print(f"\n{'='*70}")
    print("LAYER 3 COMPLETE")
    print(f"{'='*70}")
    for label, fpath in outputs.items():
        print(f"  {label}: {fpath}")

    _print_compile_hint(outputs)

    return outputs


def _print_compile_hint(outputs: dict):
    """Print instructions to compile the .tex files into PDFs."""
    if not outputs:
        return
    print("\nTo compile to PDF (requires a LaTeX installation):")
    for label, fpath in outputs.items():
        p = Path(fpath)
        print(f"  pdflatex -output-directory=\"{p.parent}\" \"{p}\"")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="LAYER 3 — Generate LaTeX quality reports from Layer 2 ratings."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to the layer2_ratings.json file."
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for output .tex files. Defaults to same folder as --input."
    )
    parser.add_argument(
        "--mode", choices=["simple", "narrative", "both"], default="both",
        help="Report mode(s) to generate (default: both)."
    )
    parser.add_argument(
        "--no-skill", action="store_true",
        help="(Narrative mode) Skip the LLM and format existing Layer 2 data directly."
    )
    parser.add_argument(
        "--date", default=None,
        help="Report date string, e.g. 2026-04-04 (default: today)."
    )
    args = parser.parse_args()

    out_dir = args.output_dir or str(Path(args.input).parent)

    result = run_layer3_pipeline(
        layer2_json_path=args.input,
        output_dir=out_dir,
        mode=args.mode,
        use_skill=not args.no_skill,
        report_date=args.date,
    )

    print(json.dumps(result, indent=2))
