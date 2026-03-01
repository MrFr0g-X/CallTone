---
name: score-call-quality
description: Score customer service call quality on 4 dimensions using LAYER 1 transcript data
version: 1.0.0
author: CallTone Team
---

# Score Call Quality

## Purpose

Analyzes a condensed customer service call transcript (produced by LAYER 1) and scores the call on four quality dimensions. Uses speaker roles, utterance text, behavioral signals, and audio emotion data to produce evidence-backed scores.

## Input Format

A condensed text representation of the LAYER 1 JSON output, including:

```
CALL: filename.wav | Duration: 91s | Speakers: 2

SPEAKER SUMMARY:
  Customer Service Agent: talk=21.8%, signals=[QUESTIONING:4, SATISFIED:1]
  Customer: talk=78.2%, signals=[QUESTIONING:1]

TRANSCRIPT:
  Customer Service Agent: Hello, how can I help you? (emotion:joy conf:0.79)
  Customer: I'm having a problem with my vacuum. [FRUSTRATED] (emotion:anger conf:0.74)
  ...
```

## Output Format

Strict JSON with scores, confidence, and evidence for each of 4 dimensions:

```json
{
  "dimensions": [
    {
      "name": "Politeness & Tone",
      "weight": 0.15,
      "score": 2.1,
      "score_range": "1.0-5.0",
      "confidence": 0.88,
      "evidence_quotes": [
        {"speaker": "Customer Service Agent", "quote": "exact quote", "note": "brief explanation"}
      ]
    },
    {
      "name": "Empathy",
      "weight": 0.10,
      "score": 1.8,
      "score_range": "1.0-5.0",
      "confidence": 0.75,
      "evidence_quotes": []
    },
    {
      "name": "Conflict Detection",
      "weight": 0.15,
      "score": 1,
      "score_range": "0 or 1",
      "confidence": 0.93,
      "evidence_quotes": [
        {"speaker": "Customer", "quote": "exact quote", "note": "escalation signal"}
      ]
    },
    {
      "name": "Issue Resolution",
      "weight": 0.05,
      "score": 1,
      "score_range": "0 or 1",
      "confidence": 0.85,
      "evidence_quotes": [
        {"speaker": "Customer Service Agent", "quote": "exact quote", "note": "resolution confirmed"}
      ]
    }
  ]
}
```

## Dimensions

| Dimension | Weight | Scale | Description |
|-----------|--------|-------|-------------|
| Politeness & Tone | 15% | 1.0-5.0 | Agent courtesy, professionalism, warmth |
| Empathy | 10% | 1.0-5.0 | Agent acknowledgment of customer feelings |
| Conflict Detection | 15% | 0 or 1 | Whether conflict/frustration was present |
| Issue Resolution | 5% | 0 or 1 | Whether the customer's problem was resolved |

## Constraints

- Output MUST be valid JSON only (no markdown, no extra text)
- Each dimension must include score, confidence (0.0-1.0), and evidence_quotes
- evidence_quotes must contain exact quotes from the transcript
- 1-3 evidence quotes per dimension (can be empty if insufficient evidence)
- Confidence should be lower when evidence is ambiguous or sparse

## Example

See `references/` directory for worked examples with test audio outputs.
