"""
Skill: rate-overall-severity

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_overall_severity_skill_bundle():
    """
    Return the skill bundle that classifies overall call severity.
    """

    return {
        "name": "rate-overall-severity",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to classify the overall severity of quality issues in this call.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Read the transcript and identify ALL quality issues
2. SECOND: Consider the cumulative impact of all issues
3. THIRD: Classify the overall severity based on the worst issues found
4. FOURTH: Provide actionable recommendations

SEVERITY CLASSIFICATION (you MUST pick one of these):
  MINOR (score=100): No significant issues. The call was generally good.
    Any issues are trivial (e.g., slightly informal language, minor paraphrasing of script).
    Action: No action needed, or minor coaching opportunity.

  MODERATE (score=75): Some notable issues that should be addressed through coaching.
    Examples: missed a verification step, forgot closing script, slightly inaccurate info.
    Action: Coaching session recommended.

  MAJOR (score=25): Serious issues that need immediate supervisor attention.
    Examples: provided wrong policy information, failed to de-escalate, significant protocol violations.
    Action: Immediate supervisor review and retraining required.

  CRITICAL (score=0): Severe violations requiring disciplinary action.
    Examples: rude to customer, gave completely false information, hung up on customer,
    violated legal/compliance requirements, discriminatory behavior.
    Action: Immediate escalation to management, possible disciplinary action.

CRITICAL RULES:
1. Output MUST be valid JSON only
2. The severity should reflect the WORST issue found, not the average
3. Score MUST be exactly one of: 0, 25, 75, 100
4. When in doubt between two levels, choose the more severe one

Output the JSON immediately with no preamble.""",

        "user_prompt_template": """Classify the overall severity of quality issues in this call.

TRANSCRIPT AND CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 75 or 100,
  "severity": "MINOR" or "MODERATE" or "MAJOR" or "CRITICAL",
  "issues_found": [
    {{
      "issue": "description of the quality issue",
      "severity_contribution": "minor" or "moderate" or "major" or "critical",
      "evidence": "quote or reference from transcript"
    }}
  ],
  "worst_issue": "the single most severe issue found",
  "recommendations": ["actionable recommendation 1", "recommendation 2"],
  "summary": "2-3 sentence overall assessment",
  "score_justification": "why this severity level was chosen"
}}

Return ONLY the JSON object:""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n"],
        },

        "output_schema": {
            "type": "object",
            "required": ["score", "severity", "issues_found", "worst_issue", "recommendations", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 75, 100]
                },
                "severity": {
                    "type": "string",
                    "enum": ["MINOR", "MODERATE", "MAJOR", "CRITICAL"]
                },
                "issues_found": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["issue", "severity_contribution", "evidence"],
                        "properties": {
                            "issue": {"type": "string"},
                            "severity_contribution": {"type": "string"},
                            "evidence": {"type": "string"}
                        }
                    }
                },
                "worst_issue": {"type": "string"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
