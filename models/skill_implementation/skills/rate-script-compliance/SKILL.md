---
name: rate-script-compliance
description: Rates agent's compliance with required scripts, protocols, and procedures (25% weight)
version: 1.0.0
author: Team
---

# Rate Script Compliance

## Purpose

Evaluates whether the customer service agent followed required scripts, protocols,
and procedures during the call. Uses company-specific context to check against
actual requirements.

## Weight

25% of overall score

## Input Format

JSON containing transcript and company context rules for script compliance.

## Output Format

```json
{
  "score": 0|25|50|75|100,
  "evidence": [{"quote": "...", "rule": "...", "met": true/false}],
  "summary": "Brief summary of compliance",
  "violations": ["list of specific violations"],
  "score_justification": "Why this specific score level was chosen"
}
```

## Scoring Rubric

- 100 = Fully compliant - all required scripts and protocols followed perfectly
- 75 = Mostly compliant - minor deviations only (e.g., slightly paraphrased greeting)
- 50 = Partially compliant - some protocols followed, some missed
- 25 = Poorly compliant - significant protocol gaps
- 0 = Not compliant - agent ignored required scripts entirely
