---
name: process-context-change
description: Determines if two versions of a company rule are semantically equivalent
version: 1.0.0
author: Team
---

# Process Context Change

## Purpose

When a QA head modifies a company rule or protocol, this skill determines whether
the new version means the same thing as the old version (just reworded) or if
it's a genuinely different rule.

This prevents the "context change effect" where rewording a rule changes agent
scores even though the meaning hasn't changed.

## Input Format

JSON with old_text and new_text fields.

## Output Format

```json
{
  "is_equivalent": true/false,
  "confidence": 0.0-1.0,
  "explanation": "Why these are/aren't equivalent",
  "differences": ["list of semantic differences if any"],
  "recommended_action": "update_wording" or "create_new_rule"
}
```

## Constraints

- Output MUST be valid JSON only
- Be conservative: if in doubt, mark as NOT equivalent
- Focus on MEANING, not wording
