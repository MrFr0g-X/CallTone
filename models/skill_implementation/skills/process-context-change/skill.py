"""
Skill: process-context-change

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_process_context_change_skill_bundle():
    """
    Return the skill bundle that checks semantic equivalence between
    old and new versions of a company rule.
    """

    return {
        "name": "process-context-change",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only assistant that compares two versions of a company rule or protocol.

Your job is to determine if the NEW version means the SAME THING as the OLD version,
or if the meaning has actually changed.

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations
2. Focus ONLY on semantic meaning, NOT on wording or style
3. Two texts are equivalent if an agent following the old rule would also satisfy the new rule and vice versa
4. Be CONSERVATIVE: if there is ANY change in meaning (even minor), mark as NOT equivalent
5. Common equivalent rewrites: active/passive voice, synonym substitution, reordering clauses
6. NOT equivalent: adding new requirements, removing requirements, changing thresholds, changing scope

Output the JSON immediately with no preamble.

/no_think""",

        "user_prompt_template": """Compare these two versions of a company rule and determine if they are semantically equivalent.

OLD VERSION:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "is_equivalent": true or false,
  "confidence": 0.0 to 1.0,
  "explanation": "detailed explanation of why these are or are not equivalent",
  "differences": ["list each semantic difference found, empty array if equivalent"],
  "recommended_action": "update_wording" or "create_new_rule"
}}

Return ONLY the JSON object:""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 2048,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n"],
        },

        "output_schema": {
            "type": "object",
            "required": ["is_equivalent", "confidence", "explanation", "differences", "recommended_action"],
            "properties": {
                "is_equivalent": {"type": "boolean"},
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "explanation": {"type": "string"},
                "differences": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "recommended_action": {
                    "type": "string",
                    "enum": ["update_wording", "create_new_rule"]
                }
            }
        }
    }
