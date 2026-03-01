# LAYER 2 — QA Scoring Engine

Scores customer service calls on four quality dimensions using an LLM skill.

## How It Works

1. Reads LAYER 1 JSON output (transcript + emotions + signals)
2. Condenses transcript to ~3 KB compact text
3. Runs `score-call-quality` skill (Llama 3.1 8B, deterministic)
4. Computes weighted overall score (0–100)
5. Flags calls for review when dimension confidence < 0.7

## Usage

```bash
python LAYER_2/qa_scorer.py <layer1_json_path>

# Example
python LAYER_2/qa_scorer.py Test_audio/bad_cs_results/bad_cs_denoised_diarized_with_emotions.json
```

Output: `<input_name>_qa_report.json` written next to the input file.

## Dimensions (Sprint 1)

| Dimension | Weight | Scale | Good Score |
|-----------|--------|-------|------------|
| Politeness & Tone | 15% | 1.0–5.0 | 4+ |
| Empathy | 10% | 1.0–5.0 | 4+ |
| Conflict Detection | 15% | 0 or 1 | 0 (no conflict) |
| Issue Resolution | 5% | 0 or 1 | 1 (resolved) |

## Overall Score Normalization

- Politeness/Empathy: `(score - 1) / 4` → 0.0–1.0
- Conflict: inverted (`1 - score`, so 0=good→1.0)
- Resolution: as-is (1=good→1.0)
- Final: weighted sum × 100

## Determinism Test

```bash
python LAYER_2/test_determinism.py
```

Runs scoring 3 times, verifies byte-identical output.
