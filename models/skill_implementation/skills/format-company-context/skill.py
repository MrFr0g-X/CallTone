"""
Skill: format-company-context

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_format_company_context_skill_bundle():
    """
    Return the skill bundle that formats raw company context into
    optimized LLM-readable rules and protocols.
    """

    return {
        "name": "format-company-context",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a precise JSON-only assistant that reformats company rules and protocols.

Your job is to take raw company context fields (written by a QA head) and rewrite them
into clear, unambiguous, LLM-optimized text that can be used to evaluate customer service agents.

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations
2. PRESERVE ALL MEANING from the original text - do not add or remove requirements
3. Use RFC 2119 language: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY
4. Make implicit rules explicit
5. Break compound rules into individual, atomic rules
6. Remove ambiguity - if something could be interpreted multiple ways, choose the strictest interpretation
7. Add clear keywords for each rule to aid in search and retrieval

Output the JSON immediately with no preamble.""",

        "user_prompt_template": """Reformat the following company context fields into clear, unambiguous rules.

RAW CONTEXT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "formatted_rules": [
    {{
      "field": "field_name_from_input",
      "original": "the original text exactly as provided",
      "formatted": "RULE: Clear, atomic, unambiguous rule using MUST/MUST NOT/SHOULD language",
      "keywords": ["keyword1", "keyword2"]
    }}
  ],
  "validation_notes": "any issues, ambiguities, or missing information found in the input"
}}

Return ONLY the JSON object:

/no_think""",

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
            "required": ["formatted_rules", "validation_notes"],
            "properties": {
                "formatted_rules": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["field", "original", "formatted", "keywords"],
                        "properties": {
                            "field": {"type": "string"},
                            "original": {"type": "string"},
                            "formatted": {"type": "string"},
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        }
                    }
                },
                "validation_notes": {"type": "string"}
            }
        }
    }
