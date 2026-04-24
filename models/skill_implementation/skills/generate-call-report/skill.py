"""
Skill: generate-call-report

PROMPT-ONLY skill - contains NO logic, loops, classes, or conditionals.
Only returns a SkillBundle dict with prompts and configuration.

This skill receives the complete Layer 2 rating output (all 7 criteria with
their evidence, violations, summaries, and score justifications) and synthesizes
it into a per-criterion narrative report that speaks directly to the agent —
explaining WHY each rating was given with reference to specific transcript
moments and company policy requirements.
"""
from pathlib import Path


def get_generate_call_report_skill_bundle():
    """
    Return the skill bundle that generates a narrative quality report.
    """

    return {
        "name": "generate-call-report",

        "model_dir": str(Path(__file__).parent.parent.parent / "models" / "Qwen3-8B-Q4_K_M.gguf"),

        "system_prompt": """You are a senior call center quality assurance coach writing a detailed feedback report for a customer service agent.

You have received the complete quality analysis of a call, including scores, evidence, violations, and justifications for 7 rating criteria.

Your task is to synthesize this data into clear, professional, actionable narrative feedback for each criterion.

WRITING GUIDELINES:
1. Speak directly to the agent in second person ("You received...", "When you said...", "You failed to...")
2. Reference specific transcript quotes or behaviors mentioned in the evidence
3. Explain WHY each action was a violation or strength — link it to the company policy or expected standard
4. Be honest but constructive — the goal is coaching, not punishment
5. For high scores: acknowledge what was done well and why it matters
6. For low scores: be specific about what went wrong and what should have been done instead

OUTPUT RULES:
1. Output MUST be valid JSON only — no markdown, no preamble
2. Every narrative field must be a complete paragraph (3-5 sentences minimum)
3. Do not invent evidence not provided in the input data
4. key_strengths and areas_for_improvement must each have 2-4 items
5. coaching_recommendation must be a single actionable paragraph

Output the JSON immediately with no preamble.""",

        "user_prompt_template": """Write a narrative quality report based on the following call rating analysis.

COMPLETE RATING ANALYSIS:
{input_text}

OUTPUT SCHEMA (return valid JSON matching this structure exactly):
{{
  "executive_summary": "3-4 sentence overall assessment of the call quality, mentioning the overall score and the most significant strengths and weaknesses",
  "criteria_narratives": {{
    "script_compliance": "3-5 sentence paragraph explaining the script compliance score — what the agent did or failed to do, citing specific evidence and referencing company policy requirements",
    "factual_accuracy": "3-5 sentence paragraph explaining the factual accuracy score",
    "politeness_tone": "3-5 sentence paragraph explaining the politeness and tone score",
    "empathy": "3-5 sentence paragraph explaining the empathy score",
    "conflict_detection": "3-5 sentence paragraph explaining the conflict handling score",
    "issue_resolution": "3-5 sentence paragraph explaining the issue resolution score",
    "overall_severity": "3-5 sentence paragraph explaining the overall severity classification"
  }},
  "key_strengths": [
    "specific strength with brief explanation",
    "specific strength with brief explanation"
  ],
  "areas_for_improvement": [
    "specific improvement needed with concrete suggestion",
    "specific improvement needed with concrete suggestion"
  ],
  "coaching_recommendation": "A single actionable paragraph summarizing what the agent should focus on in their next coaching session, referencing the most impactful areas"
}}

Return ONLY the JSON object:

/no_think""",

        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "seed": 42,
            "do_sample": False,
            "stop": ["\n\n\n\n"],
        },

        "output_schema": {
            "type": "object",
            "required": [
                "executive_summary",
                "criteria_narratives",
                "key_strengths",
                "areas_for_improvement",
                "coaching_recommendation",
            ],
            "properties": {
                "executive_summary": {"type": "string"},
                "criteria_narratives": {
                    "type": "object",
                    "required": [
                        "script_compliance",
                        "factual_accuracy",
                        "politeness_tone",
                        "empathy",
                        "conflict_detection",
                        "issue_resolution",
                        "overall_severity",
                    ],
                    "properties": {
                        "script_compliance":  {"type": "string"},
                        "factual_accuracy":   {"type": "string"},
                        "politeness_tone":    {"type": "string"},
                        "empathy":            {"type": "string"},
                        "conflict_detection": {"type": "string"},
                        "issue_resolution":   {"type": "string"},
                        "overall_severity":   {"type": "string"},
                    },
                },
                "key_strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "areas_for_improvement": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "coaching_recommendation": {"type": "string"},
            },
        },
    }
