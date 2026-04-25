"""
Skill: identify-call-roles

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.
"""
from pathlib import Path


def get_identify_call_roles_skill_bundle():
    """
    Return the skill bundle that identifies agent vs customer in call transcripts.
    
    This function contains ONLY prompt text and configuration.
    All logic is handled by the skill runtime.
    """
    
    return {
        "name": "identify-call-roles",
        
        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),
        
        "system_prompt": """You are a precise JSON-only assistant that analyzes call center transcripts.

Your ONLY job is to identify which speaker is the agent/representative and which is the customer.

CRITICAL RULES:
1. Output MUST be valid JSON only - no markdown, no explanations, no additional text
2. Never wrap output in ```json``` code blocks
3. Extract 1-3 exact quotes from the transcript as evidence
4. Keep reason_short to 25 words maximum
5. Output format must exactly match the schema provided

Key indicators to consider:
- Agent: professional greeting, offers help, asks questions, provides solutions, uses company language
- Customer: describes problems, asks help, expresses frustration or satisfaction

Output the JSON immediately with no preamble.

/no_think""",
        
        "user_prompt_template": """Analyze this call transcript and identify speaker roles.

TRANSCRIPT:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure):
{{
  "agent_speaker": "SPEAKER_A" or "SPEAKER_B" or "UNKNOWN",
  "customer_speaker": "SPEAKER_A" or "SPEAKER_B" or "UNKNOWN",
  "confidence": 0.0 to 1.0,
  "evidence": [
    {{"speaker": "SPEAKER_X", "quote": "exact quote from transcript"}},
    {{"speaker": "SPEAKER_Y", "quote": "exact quote from transcript"}}
  ],
  "reason_short": "explanation in 25 words or less"
}}

Return ONLY the JSON object:""",
        
        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 1024,
            "seed": 12345,
            "do_sample": False,
            "stop": ["\n\n\n", "TRANSCRIPT:", "---"],
        },
        
        "output_schema": {
            "type": "object",
            "required": ["agent_speaker", "customer_speaker", "confidence", "evidence", "reason_short"],
            "properties": {
                "agent_speaker": {
                    "type": "string",
                    "enum": ["SPEAKER_A", "SPEAKER_B", "SPEAKER_C", "SPEAKER_D", "UNKNOWN"]
                },
                "customer_speaker": {
                    "type": "string",
                    "enum": ["SPEAKER_A", "SPEAKER_B", "SPEAKER_C", "SPEAKER_D", "UNKNOWN"]
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "evidence": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "required": ["speaker", "quote"],
                        "properties": {
                            "speaker": {"type": "string"},
                            "quote": {"type": "string"}
                        }
                    }
                },
                "reason_short": {
                    "type": "string",
                    "maxLength": 200
                }
            }
        }
    }
