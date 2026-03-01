"""
Test that LAYER 2 QA scoring produces deterministic output.

Runs score_call() 3 times on the same LAYER 1 JSON and verifies
all outputs are byte-identical (excluding scored_at timestamp).

Usage:
    python LAYER_2/test_determinism.py [layer1_json_path]
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from LAYER_2.qa_scorer import score_call

# Default test input
DEFAULT_INPUT = (
    REPO_ROOT
    / "Test_audio"
    / "bad_cs_results"
    / "bad_cs_denoised_diarized_with_emotions.json"
)

NUM_RUNS = 3


def strip_timestamp(report: dict) -> str:
    """Serialize report to JSON, stripping the scored_at timestamp."""
    copy = json.loads(json.dumps(report))
    copy.get("metadata", {}).pop("scored_at", None)
    return json.dumps(copy, indent=2, ensure_ascii=False, sort_keys=True)


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_INPUT)

    if not Path(input_path).exists():
        print(f"Error: Input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running {NUM_RUNS} scoring passes on: {Path(input_path).name}\n")

    outputs = []
    for i in range(NUM_RUNS):
        print(f"  Run {i + 1}/{NUM_RUNS}...", end=" ", flush=True)
        report = score_call(input_path)
        serialized = strip_timestamp(report)
        outputs.append(serialized)
        print(f"score={report['overall_score']}")

    # Compare all runs
    all_match = all(o == outputs[0] for o in outputs[1:])

    if all_match:
        print(f"\nDeterminism test PASSED — all {NUM_RUNS} runs are byte-identical.")
        print(f"  Overall score: {json.loads(outputs[0])['overall_score']}/100")
        print(f"  Output length: {len(outputs[0])} chars")
    else:
        print(f"\nDeterminism test FAILED — outputs differ across runs.")
        for i, o in enumerate(outputs):
            print(f"\n--- Run {i + 1} ---")
            print(o[:500])
        sys.exit(1)


if __name__ == "__main__":
    main()
