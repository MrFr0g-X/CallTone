"""
Skill: rate-script-compliance

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_script_compliance_skill_bundle():
    """
    Return the skill bundle that rates the agent's script compliance.
    """

    return {
        "name": "rate-script-compliance",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to rate how well the agent followed required scripts, protocols, and procedures.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Read the company rules/protocols provided
2. SECOND: Read the transcript carefully
3. THIRD: For EACH rule, find evidence in the transcript of compliance or violation
4. FOURTH: List all violations found
5. FIFTH: Based on the evidence, assign a score from the rubric

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = Fully compliant - all required scripts and protocols followed perfectly
  75 = Mostly compliant - minor deviations only (e.g., slightly paraphrased but conveyed same meaning)
  50 = Partially compliant - some protocols followed, some missed entirely
  25 = Poorly compliant - significant gaps, most protocols not followed
  0 = Not compliant at all - agent ignored required scripts entirely

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations
2. You MUST cite exact quotes from the transcript as evidence
3. You MUST check EVERY rule provided in the context
4. Score MUST be exactly one of: 0, 25, 50, 75, 100
5. If no company context is provided, score based on general call center best practices

Output the JSON immediately with no preamble.

/think""",

        "user_prompt_template": """Rate the agent's script compliance in this call.

COMPANY RULES AND PROTOCOLS:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "evidence": [
    {{
      "rule": "the specific rule being checked",
      "quote": "exact quote from transcript showing compliance or violation",
      "met": true or false
    }}
  ],
  "violations": ["specific violation 1", "specific violation 2"],
  "summary": "2-3 sentence summary of overall script compliance",
  "score_justification": "why this exact score level was chosen based on the evidence"
}}

Return ONLY the JSON object:""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 800,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n"],
        },

        "output_schema": {
            "type": "object",
            "required": ["score", "evidence", "violations", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["rule", "quote", "met"],
                        "properties": {
                            "rule": {"type": "string"},
                            "quote": {"type": "string"},
                            "met": {"type": "boolean"}
                        }
                    }
                },
                "violations": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
