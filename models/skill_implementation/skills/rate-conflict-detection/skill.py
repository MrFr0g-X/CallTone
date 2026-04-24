"""
Skill: rate-conflict-detection

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_conflict_detection_skill_bundle():
    """
    Return the skill bundle that rates conflict detection and handling.
    """

    return {
        "name": "rate-conflict-detection",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to detect conflicts or escalations in the call and rate how the agent handled them.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Read the transcript and identify any conflict indicators
2. SECOND: Classify the severity of any conflicts found
3. THIRD: Evaluate how the agent responded to each conflict
4. FOURTH: Check if the agent followed escalation procedures (if provided)
5. FIFTH: Based on the evidence, assign a score from the rubric

CONFLICT INDICATORS:
- Customer raising voice (indicated by caps, exclamation marks, or emotion data)
- Customer threatening (legal action, complaints, cancellation)
- Customer requesting supervisor/manager
- Agent arguing back or being defensive
- Repeated failed attempts to resolve
- Customer using profanity or aggressive language

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = No conflicts present, OR agent expertly de-escalated all tensions
  75 = Minor tension present but handled well, prevented escalation
  50 = Conflict present and partially managed, some de-escalation attempts
  25 = Conflict poorly handled, escalation occurred or was not properly managed
  0 = Agent caused, provoked, or significantly worsened a conflict

CRITICAL RULES:
1. Output MUST be valid JSON only
2. Use behavioral signals and audio emotion data if available
3. Score MUST be exactly one of: 0, 25, 50, 75, 100
4. A call with NO conflicts should score 100

Output the JSON immediately with no preamble.

/think""",

        "user_prompt_template": """Detect conflicts and rate how the agent handled them in this call.

TRANSCRIPT AND CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "conflicts_detected": [
    {{
      "description": "what the conflict was about",
      "severity": "none" or "minor" or "moderate" or "severe",
      "customer_quote": "triggering customer statement",
      "agent_response": "how the agent responded",
      "handled_well": true or false
    }}
  ],
  "escalation_occurred": true or false,
  "agent_caused_conflict": true or false,
  "summary": "2-3 sentence summary of conflict handling",
  "score_justification": "why this exact score level was chosen"
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
            "required": ["score", "conflicts_detected", "escalation_occurred", "agent_caused_conflict", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "conflicts_detected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description", "severity", "customer_quote", "agent_response", "handled_well"],
                        "properties": {
                            "description": {"type": "string"},
                            "severity": {"type": "string", "enum": ["none", "minor", "moderate", "severe"]},
                            "customer_quote": {"type": "string"},
                            "agent_response": {"type": "string"},
                            "handled_well": {"type": "boolean"}
                        }
                    }
                },
                "escalation_occurred": {"type": "boolean"},
                "agent_caused_conflict": {"type": "boolean"},
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
