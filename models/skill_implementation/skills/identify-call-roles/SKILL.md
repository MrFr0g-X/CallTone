---
name: identify-call-roles
description: Identify which transcript speaker is customer vs agent in call center conversations
version: 1.0.0
author: Team
---

# Identify Call Roles

## Purpose

This skill analyzes a call transcript with speaker labels (e.g., SPEAKER_A, SPEAKER_B) and determines which speaker is the customer and which is the agent/representative.

## Input Format

A text transcript with speaker labels:

```
SPEAKER_A: Hello, thank you for calling...
SPEAKER_B: Hi, I need help with...
```

## Output Format

Strict JSON with the following structure:

```json
{
  "agent_speaker": "SPEAKER_A"|"SPEAKER_B"|"UNKNOWN",
  "customer_speaker": "SPEAKER_A"|"SPEAKER_B"|"UNKNOWN",
  "confidence": 0.0-1.0,
  "evidence": [
    {"speaker": "SPEAKER_A", "quote": "exact quote from transcript"},
    {"speaker": "SPEAKER_B", "quote": "exact quote from transcript"}
  ],
  "reason_short": "Brief explanation in 25 words or less"
}
```

## Constraints

- Output MUST be valid JSON only (no markdown, no additional text)
- `evidence` must contain 1-3 exact quotes from the transcript
- `reason_short` must be 25 words or less
- `confidence` must be between 0.0 and 1.0
- If unable to determine roles, set both to "UNKNOWN" with confidence < 0.5

## Example

Input:
```
SPEAKER_A: Thank you for calling XYZ Support. How may I assist you today?
SPEAKER_B: Hi, I'm having issues with my account login.
```

Output:
```json
{
  "agent_speaker": "SPEAKER_A",
  "customer_speaker": "SPEAKER_B",
  "confidence": 0.95,
  "evidence": [
    {"speaker": "SPEAKER_A", "quote": "Thank you for calling XYZ Support. How may I assist you today?"},
    {"speaker": "SPEAKER_B", "quote": "I'm having issues with my account login."}
  ],
  "reason_short": "SPEAKER_A uses formal greeting and offers assistance; SPEAKER_B describes a problem."
}
```
