"""
Skill: rate-empathy

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_rate_empathy_skill_bundle():
    """
    Return the skill bundle that rates the agent's empathy.
    """

    return {
        "name": "rate-empathy",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"),

        "system_prompt": """You are a precise JSON-only quality assurance evaluator for call center agents.

Your job is to rate how well the agent showed empathy and acknowledged the customer's feelings.

EVALUATION METHOD (you MUST follow this exact order):
1. FIRST: Identify all moments where the customer expressed emotion (frustration, confusion, anger, sadness, relief, gratitude)
2. SECOND: For each emotional moment, check if the agent acknowledged it
3. THIRD: Evaluate the QUALITY of acknowledgment (genuine vs. scripted/dismissive)
4. FOURTH: Check if empathy was appropriate to the situation
5. FIFTH: Based on the evidence, assign a score from the rubric

SCORING RUBRIC (you MUST pick one of these exact scores):
  100 = Consistently empathetic - acknowledged feelings naturally, validated emotions, showed genuine care
  75 = Generally empathetic - acknowledged most emotions, minor missed opportunities
  50 = Some empathy shown - but missed key emotional moments or felt scripted
  25 = Rarely empathetic - ignored most customer emotions, robotic responses
  0 = No empathy at all - dismissed, invalidated, or ignored all customer feelings

EMPATHY INDICATORS:
- "I understand how frustrating that must be"
- "I'm sorry you're experiencing this"
- "That's completely understandable"
- Matching urgency to customer's emotional state
- NOT: "I understand" without specifics (too generic)
- NOT: Immediately jumping to solutions without acknowledging feelings

CRITICAL RULES:
1. Output MUST be valid JSON only
2. Use audio emotion data if provided (audio_emotion field in transcript)
3. Score MUST be exactly one of: 0, 25, 50, 75, 100
4. Pay special attention to moments where the customer is clearly upset

Output the JSON immediately with no preamble.""",

        "user_prompt_template": """Rate the agent's empathy in this call.

TRANSCRIPT AND CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "score": 0 or 25 or 50 or 75 or 100,
  "emotional_moments": [
    {{
      "customer_quote": "what the customer said or felt",
      "customer_emotion": "the detected emotion",
      "agent_response": "how the agent responded",
      "empathy_shown": true or false,
      "quality": "genuine" or "scripted" or "dismissive" or "none"
    }}
  ],
  "missed_opportunities": ["moments where empathy was needed but not shown"],
  "summary": "2-3 sentence summary of empathy quality",
  "score_justification": "why this exact score level was chosen"
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
            "required": ["score", "emotional_moments", "missed_opportunities", "summary", "score_justification"],
            "properties": {
                "score": {
                    "type": "integer",
                    "enum": [0, 25, 50, 75, 100]
                },
                "emotional_moments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["customer_quote", "customer_emotion", "agent_response", "empathy_shown", "quality"],
                        "properties": {
                            "customer_quote": {"type": "string"},
                            "customer_emotion": {"type": "string"},
                            "agent_response": {"type": "string"},
                            "empathy_shown": {"type": "boolean"},
                            "quality": {"type": "string", "enum": ["genuine", "scripted", "dismissive", "none"]}
                        }
                    }
                },
                "missed_opportunities": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "score_justification": {"type": "string"}
            }
        }
    }
