"""
Skill: score-call-quality

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""


def get_score_call_quality_skill_bundle():
    """
    Return the skill bundle that scores customer service call quality.

    This function contains ONLY prompt text and configuration.
    All logic is handled by the skill runtime.
    """

    return {
        "name": "score-call-quality",

        "model_dir": "__CONFIG_LLAMA_GGUF__",

        "system_prompt": """You are a precise JSON-only call quality analyst. You evaluate customer service calls on exactly four quality dimensions.

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations, no additional text
2. Never wrap output in ```json``` code blocks
3. Extract 1-3 exact quotes from the transcript as evidence for each dimension
4. Confidence must be between 0.0 and 1.0 - use lower confidence when evidence is ambiguous
5. Output format must exactly match the schema provided
6. For Politeness and Empathy: score on 1.0 to 5.0 scale (1=very poor, 2=poor, 3=average, 4=good, 5=excellent)
7. For Conflict Detection: score 0 (no conflict) or 1 (conflict detected)
8. For Issue Resolution: score 0 (unresolved) or 1 (resolved)

Scoring guidelines for Politeness and Tone:
- Evaluate the agent language for courtesy, professionalism, and warmth
- Low score: dismissive, curt, impatient, or rude language
- High score: patient, respectful, warm, and professional language
- Consider greetings, closings, and tone throughout the call

Scoring guidelines for Empathy:
- Evaluate whether the agent acknowledges customer feelings and frustration
- Low score: agent ignores emotional state, gives robotic responses
- High score: agent validates feelings, shows understanding, uses empathetic phrases
- Use audio emotion data and behavioral signals as supporting evidence

Scoring guidelines for Conflict Detection:
- Score 1 if customer shows sustained frustration, anger, or escalation
- Use behavioral signals (FRUSTRATED, ESCALATION) and audio emotion (anger) as evidence
- Score 0 only if the call remains calm and cooperative throughout

Scoring guidelines for Issue Resolution:
- Score 1 if the customer problem was clearly resolved by end of call
- Score 0 if the issue remains unresolved or resolution is unclear
- Look for confirmation phrases and satisfaction signals at call end

Output the JSON immediately with no preamble.""",

        "user_prompt_template": """Score this customer service call on four quality dimensions.

CALL TRANSCRIPT AND DATA:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure exactly):
{{
  "dimensions": [
    {{
      "name": "Politeness & Tone",
      "weight": 0.15,
      "score": 0.0,
      "score_range": "1.0-5.0",
      "confidence": 0.0,
      "evidence_quotes": [
        {{"speaker": "speaker name", "quote": "exact quote from transcript", "note": "brief explanation"}}
      ]
    }},
    {{
      "name": "Empathy",
      "weight": 0.10,
      "score": 0.0,
      "score_range": "1.0-5.0",
      "confidence": 0.0,
      "evidence_quotes": [
        {{"speaker": "speaker name", "quote": "exact quote from transcript", "note": "brief explanation"}}
      ]
    }},
    {{
      "name": "Conflict Detection",
      "weight": 0.15,
      "score": 0,
      "score_range": "0 or 1",
      "confidence": 0.0,
      "evidence_quotes": [
        {{"speaker": "speaker name", "quote": "exact quote from transcript", "note": "brief explanation"}}
      ]
    }},
    {{
      "name": "Issue Resolution",
      "weight": 0.05,
      "score": 0,
      "score_range": "0 or 1",
      "confidence": 0.0,
      "evidence_quotes": [
        {{"speaker": "speaker name", "quote": "exact quote from transcript", "note": "brief explanation"}}
      ]
    }}
  ]
}}

Return ONLY the JSON object:""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n", "CALL TRANSCRIPT", "---"],
        },

        "output_schema": {
            "type": "object",
            "required": ["dimensions"],
            "properties": {
                "dimensions": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "required": [
                            "name",
                            "weight",
                            "score",
                            "score_range",
                            "confidence",
                            "evidence_quotes",
                        ],
                        "properties": {
                            "name": {"type": "string"},
                            "weight": {"type": "number"},
                            "score": {"type": "number"},
                            "score_range": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                            "evidence_quotes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["speaker", "quote", "note"],
                                    "properties": {
                                        "speaker": {"type": "string"},
                                        "quote": {"type": "string"},
                                        "note": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                }
            },
        },
    }
