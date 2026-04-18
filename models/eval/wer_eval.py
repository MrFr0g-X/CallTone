"""Layer 1 evaluation: word-error-rate of SenseVoice transcripts vs reference.

Usage:
    python -m models.eval.wer_eval \
        --transcripts <dir> --refs <dir> \
        [--out models/eval/results/eval_results.json]

Each reference file (``*.txt`` in ``--refs``) is compared to a
hypothesis file of the same name in ``--transcripts``. Output is a JSON
report with per-file WER/CER plus session-wide means. ``jiwer`` is the
reference implementation; ``pip install jiwer``.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from jiwer import wer, cer
except ImportError as exc:
    raise SystemExit("pip install jiwer  # required for wer_eval") from exc


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().lower()


def evaluate(transcript_dir: Path, ref_dir: Path) -> dict:
    results = []
    for ref in sorted(ref_dir.glob("*.txt")):
        hyp = transcript_dir / ref.name
        if not hyp.exists():
            results.append({"file": ref.name, "skipped": "no_hypothesis"})
            continue
        r, h = _load(ref), _load(hyp)
        if not r:
            results.append({"file": ref.name, "skipped": "empty_reference"})
            continue
        results.append({
            "file": ref.name,
            "wer": round(wer(r, h), 4),
            "cer": round(cer(r, h), 4),
            "ref_chars": len(r),
            "hyp_chars": len(h),
        })

    scored = [r for r in results if "wer" in r]
    n = max(1, len(scored))
    summary = {
        "files_evaluated": len(scored),
        "files_skipped": len(results) - len(scored),
        "mean_wer": round(sum(r["wer"] for r in scored) / n, 4),
        "mean_cer": round(sum(r["cer"] for r in scored) / n, 4),
    }
    return {"per_file": results, "summary": summary}


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcripts", required=True, type=Path,
                    help="Directory of hypothesis transcripts (*.txt)")
    ap.add_argument("--refs", required=True, type=Path,
                    help="Directory of reference transcripts (*.txt)")
    ap.add_argument("--out", default=Path("models/eval/results/eval_results.json"),
                    type=Path)
    args = ap.parse_args(argv)

    if not args.refs.exists():
        print(f"error: refs dir not found: {args.refs}", file=sys.stderr)
        return 2
    if not args.transcripts.exists():
        print(f"error: transcripts dir not found: {args.transcripts}", file=sys.stderr)
        return 2

    report = evaluate(args.transcripts, args.refs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
