"""
Skill: rate-factual-accuracy

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_factual_accuracy_skill_bundle():
    """
    Return the skill bundle that rates the agent's factual accuracy.
    """

    return {
        "name": "rate-factual-accuracy",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to rate whether the agent provided CORRECT factual information during the call.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Read the company's factual context (products, prices, policies, procedures)
2. SECOND: Read the transcript and identify EVERY factual claim the agent made
3. THIRD: For each claim, check if it matches the company's factual context
4. FOURTH: List all inaccuracies found
5. FIFTH: Based on the evidence, assign a score from the rubric

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = All factual claims were correct, no inaccuracies
  75 = Mostly accurate, only minor/trivial inaccuracies (e.g., rounding a price)
  50 = Mix of correct and incorrect information, some significant errors
  25 = Multiple significant factual errors that could mislead the customer
  0 = Fundamentally wrong information provided, or made up facts not in the context

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations
2. Only check claims that CAN be verified against the provided context
3. If the agent said something not covered by the context, note it but don't penalize
4. Score MUST be exactly one of: 0, 25, 50, 75, 100
5. If no company context is provided, only check for obviously false/impossible claims

Output the JSON immediately with no preamble.

/think""",

        "user_prompt_template": """Rate the agent's factual accuracy in this call.

COMPANY FACTUAL CONTEXT AND TRANSCRIPT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "claims_checked": [
    {{
      "claim": "what the agent stated",
      "quote": "exact quote from transcript",
      "correct": true or false,
      "reference": "the correct information from company context, or 'not in context'"
    }}
  ],
  "inaccuracies": ["specific inaccuracy 1", "specific inaccuracy 2"],
  "summary": "2-3 sentence summary of factual accuracy",
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
            "required": ["score", "claims_checked", "inaccuracies", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "claims_checked": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["claim", "quote", "correct", "reference"],
                        "properties": {
                            "claim": {"type": "string"},
                            "quote": {"type": "string"},
                            "correct": {"type": "boolean"},
                            "reference": {"type": "string"}
                        }
                    }
                },
                "inaccuracies": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
