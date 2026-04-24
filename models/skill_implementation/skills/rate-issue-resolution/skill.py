"""
Skill: rate-issue-resolution

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_issue_resolution_skill_bundle():
    """
    Return the skill bundle that rates issue resolution.
    """

    return {
        "name": "rate-issue-resolution",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to determine if the customer's problem was actually resolved during the call.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Identify what the customer's issue/question was
2. SECOND: Track what steps the agent took to resolve it
3. THIRD: Check if the customer confirmed the issue was resolved
4. FOURTH: Look for follow-up indicators (ticket created, callback promised, etc.)
5. FIFTH: Based on the evidence, assign a score from the rubric

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = Issue fully resolved - customer explicitly confirmed satisfaction or problem was demonstrably fixed
  75 = Issue likely resolved - agent took all reasonable steps, customer seemed satisfied
  50 = Partially resolved - some aspects addressed but others left open
  25 = Mostly unresolved - minimal progress, customer still has the problem
  0 = Not addressed - agent failed to even attempt resolution

RESOLUTION INDICATORS:
- Customer says "thank you" or "that works" or "great"
- Agent provides a clear solution and customer accepts
- Ticket/reference number provided for follow-up
- Callback or follow-up scheduled

NON-RESOLUTION INDICATORS:
- Customer still asking the same question at end
- "I'll try that" without confidence
- Agent unable to provide answer
- Call ended abruptly

CRITICAL RULES:
1. Output MUST be valid JSON only
2. Score MUST be exactly one of: 0, 25, 50, 75, 100
3. Consider customer's final emotional state as a resolution indicator

Output the JSON immediately with no preamble.

/no_think""",

        "user_prompt_template": """Rate the issue resolution in this call.

TRANSCRIPT AND CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "customer_issue": "description of what the customer's problem/question was",
  "resolution_steps": ["step 1 the agent took", "step 2"],
  "resolution_status": "fully_resolved" or "likely_resolved" or "partially_resolved" or "unresolved" or "not_addressed",
  "customer_confirmed": true or false,
  "follow_up_arranged": true or false,
  "summary": "2-3 sentence summary of resolution outcome",
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
            "required": ["score", "customer_issue", "resolution_steps", "resolution_status", "customer_confirmed", "follow_up_arranged", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "customer_issue": {"type": "string"},
                "resolution_steps": {"type": "array", "items": {"type": "string"}},
                "resolution_status": {
                    "type": "string",
                    "enum": ["fully_resolved", "likely_resolved", "partially_resolved", "unresolved", "not_addressed"]
                },
                "customer_confirmed": {"type": "boolean"},
                "follow_up_arranged": {"type": "boolean"},
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
