---
name: format-company-context
description: Formats raw company context fields into optimized LLM-readable rules and protocols
version: 1.0.0
author: Team
---

# Format Company Context

## Purpose

Takes raw company context fields (as filled by the QA head) and reformats them
into clear, unambiguous, LLM-optimized text. This ensures the model understands
the rules precisely regardless of how the QA head worded them.

## Input Format

JSON with the raw context fields from the QA head's input form.

## Output Format

JSON with reformatted fields optimized for LLM consumption:

```json
{
  "formatted_rules": [
    {
      "field": "greeting_script",
      "original": "...",
      "formatted": "RULE: Agent MUST begin every call with: '...'",
      "keywords": ["greeting", "opening"]
    }
  ],
  "validation_notes": "Any issues found in the input"
}
```

## Constraints

- Output MUST be valid JSON only
- Preserve ALL meaning from the original
- Make rules explicit and unambiguous
- Use MUST/MUST NOT/SHOULD/SHOULD NOT language
