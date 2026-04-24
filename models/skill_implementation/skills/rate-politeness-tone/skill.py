"""
Skill: rate-politeness-tone

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_politeness_tone_skill_bundle():
    """
    Return the skill bundle that rates the agent's politeness and tone.
    """

    return {
        "name": "rate-politeness-tone",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to rate the agent's politeness, professionalism, and communication tone.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Read any tone guidelines from the company context
2. SECOND: Read the transcript and identify the agent's tone throughout
3. THIRD: Note specific examples of good and bad tone
4. FOURTH: Consider the overall pattern, not just isolated moments
5. FIFTH: Based on the evidence, assign a score from the rubric

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = Consistently professional, warm, and courteous throughout the entire call
  75 = Generally polite with only minor lapses (e.g., one slightly abrupt response)
  50 = Mixed tone - professional at times but notable unprofessional moments
  25 = Frequently unprofessional, curt, or discourteous
  0 = Rude, dismissive, hostile, or actively disrespectful

WHAT TO EVALUATE:
- Use of customer's name
- Please/thank you/you're welcome
- Active listening indicators
- Patience with repetition or confusion
- Avoiding condescending language
- Maintaining composure under pressure
- Professional vocabulary (no slang unless appropriate)

CRITICAL RULES:
1. Output MUST be valid JSON only
2. Cite exact quotes as evidence
3. Score MUST be exactly one of: 0, 25, 50, 75, 100
4. Consider emotional context from audio emotions if provided

Output the JSON immediately with no preamble.

/no_think""",

        "user_prompt_template": """Rate the agent's politeness and tone in this call.

TRANSCRIPT AND CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "evidence": [
    {{
      "quote": "exact quote from transcript",
      "assessment": "positive" or "negative" or "neutral",
      "note": "why this is good or bad tone"
    }}
  ],
  "positive_examples": ["specific good tone examples"],
  "negative_examples": ["specific bad tone examples"],
  "summary": "2-3 sentence summary of tone quality",
  "score_justification": "why this exact score level was chosen"
}}

Return ONLY the JSON object:""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 500,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n"],
        },

        "output_schema": {
            "type": "object",
            "required": ["score", "evidence", "positive_examples", "negative_examples", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["quote", "assessment", "note"],
                        "properties": {
                            "quote": {"type": "string"},
                            "assessment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                            "note": {"type": "string"}
                        }
                    }
                },
                "positive_examples": {"type": "array", "items": {"type": "string"}},
                "negative_examples": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
