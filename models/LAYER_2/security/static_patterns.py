"""
Static prompt-injection pattern scanner.

First line of defense — pure regex, zero LLM, zero injection risk.
Runs in milliseconds before any LLM sees the transcript.

Design principle: flag suspicious patterns, not normal speech.
  - Prefer false negatives over false positives at LOW/MEDIUM.
  - At CRITICAL we want high precision — only flag unmistakable injection.
"""

import re
from dataclasses import dataclass, field


@dataclass
class PatternMatch:
    pattern_name: str
    matched_text: str
    context: str          # surrounding text for review
    severity: str         # low / medium / high / critical
    location: str         # speaker label if extractable, else "unknown"


# ── Pattern definitions ───────────────────────────────────────────────────────
# Each tuple: (name, compiled_regex, severity)
# Patterns are case-insensitive (flag set at compile time).
#
# Severity rationale:
#   critical — clear, targeted LLM instruction (should block)
#   high     — likely injection, needs LLM confirmation
#   medium   — suspicious, could be innocent speech — LLM confirms
#   low      — weak signal, log only

_PATTERNS: list[tuple[str, re.Pattern, str]] = []


def _p(name: str, pattern: str, severity: str) -> None:
    _PATTERNS.append((name, re.compile(pattern, re.IGNORECASE | re.MULTILINE), severity))


# ── CRITICAL — unambiguous LLM instruction attempts ───────────────────────────
_p("score_override_explicit",
   r"\b(give|assign|set|output|return)\b.{0,30}\b(score|rating|mark|grade)\b.{0,20}\b(100|perfect|full|maximum|highest|10[0\s]*out[0\s]*of)\b",
   "critical")

_p("score_override_pre_qualifier",
   r"\b(give|assign|set|output|return|provide)\b.{0,20}\b(perfect|full|maximum|highest|100)\b.{0,20}\b(score|rating|mark|grade|point)s?\b",
   "critical")

_p("score_to_this_agent",
   r"\b(give|assign|rate|grade|score|mark)\b.{0,40}\b(this\s+agent|the\s+agent|this\s+call|this\s+conversation)\b.{0,40}\b(100|perfect|full|maximum|high|excellent|top)\b",
   "critical")

_p("ignore_instructions",
   r"\b(ignore|disregard|forget|bypass|override|skip)\b.{0,30}\b(previous|prior|above|all|your|these|the)\b.{0,20}\b(instruction|prompt|rule|guideline|constraint|context|system|directive)\b",
   "critical")

_p("instruction_injection_marker",
   r"(^|\n)\s*\[\s*(system|sys|assistant|user|inst|instruction|override)\s*\]",
   "critical")

_p("role_instruction_marker",
   r"(^|\n)\s*(system|assistant|user)\s*:\s*(ignore|you must|you should|give|rate|score|output)",
   "critical")

_p("direct_score_command",
   r"\b(you must|you should|please|make sure to)\b.{0,40}\b(give|assign|output|return|provide)\b.{0,30}\b(100|perfect|full|maximum|high|top)\b.{0,20}\b(score|rating|mark|grade|point)\b",
   "critical")

_p("pretend_no_evaluation",
   r"\b(pretend|act as if|behave as if|imagine)\b.{0,50}\b(there\s*(are|were|is)\s*no\s*(rule|policy|guideline|criterion|rating|evaluation))",
   "critical")

# ── HIGH — strong signals, need LLM confirmation ──────────────────────────────
_p("ai_identity_acknowledgment",
   r"\b(you are|you'?re|as)\b.{0,20}\b(an?\s*)?(ai|llm|language model|gpt|llama|chatbot|bot|neural network)\b",
   "high")

_p("if_you_are_ai",
   r"\b(if|when)\b.{0,15}\byou\b.{0,10}\b(are|'re)\b.{0,15}\b(an?\s*)?(ai|llm|language model|bot|model|robot)\b",
   "high")

_p("override_score",
   r"\b(override|change|modify|alter|adjust|fix|force)\b.{0,30}\b(score|rating|grade|mark|evaluation|result)\b",
   "high")

_p("jailbreak_pattern",
   r"\b(jailbreak|jail break|DAN|do anything now|developer mode|unrestricted mode|god mode)\b",
   "high")

_p("prompt_reference",
   r"\b(your\s+)?(system\s+)?(prompt|instruction|context|input)\b.{0,20}\b(say|says|tells|tells you|instructs?|orders?)\b",
   "high")

_p("injection_explicit",
   r"\b(prompt\s+injection|inject(ing|ed)?\s+(a\s+)?(prompt|instruction|command))\b",
   "high")

# ── MEDIUM — suspicious but could be innocent ────────────────────────────────
_p("rate_me_command",
   r"\b(rate|score|grade|evaluate|assess)\b.{0,30}\b(me|this\s+call|this\s+conversation|my\s+performance|myself)\b",
   "medium")

_p("output_format_command",
   r"\b(output|return|respond\s+with|answer\s+with|provide)\b.{0,30}\b(json|only|just|score|rating|number|integer)\b",
   "medium")

_p("give_high_score",
   r"\b(give|assign|provide)\b.{0,30}\b(me|this\s+agent|the\s+agent|us)\b.{0,30}\b(high|good|great|perfect|excellent|top)\b.{0,20}\b(score|rating|mark|grade)\b",
   "medium")

_p("forget_context",
   r"\b(forget|discard|ignore|drop|clear)\b.{0,30}\b(everything|all|the\s+above|the\s+previous|the\s+context|what\s+was\s+said)\b",
   "medium")

_p("pretend_roleplay",
   r"\b(pretend|roleplay|role.?play|act as|play the role|simulate|imagine you are)\b.{0,40}\b(evaluator|judge|reviewer|rater|qa|quality)\b",
   "medium")

_p("new_task_redirect",
   r"\b(new\s+task|instead\s+(of|do)|forget\s+the\s+(above|task|evaluation)|your\s+(real|actual|true)\s+(task|job|goal))\b",
   "medium")

# ── LOW — weak signals, log only ─────────────────────────────────────────────
_p("score_mention_in_agent_speech",
   r"\b(score|rating|grade|mark|evaluation)\b.{0,20}\b(100|perfect|maximum|full|excellent)\b",
   "low")

_p("ai_general_mention",
   r"\b(artificial intelligence|machine learning|language model|neural network|ai model)\b",
   "low")

_p("instruction_word",
   r"\b(instruction|guideline|rule|policy|directive|protocol)\b.{0,20}\b(ignore|bypass|override|forget|disregard)\b",
   "low")


# ── Scanner ──────────────────────────────────────────────────────────────────

_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def scan_transcript(transcript_text: str) -> list[PatternMatch]:
    """
    Run all static patterns against a transcript string.
    Returns a list of PatternMatch objects (may be empty).
    """
    matches = []
    for name, pattern, severity in _PATTERNS:
        for m in pattern.finditer(transcript_text):
            start = max(0, m.start() - 60)
            end   = min(len(transcript_text), m.end() + 60)
            context = transcript_text[start:end].replace("\n", " ").strip()

            # Try to find the speaker label in the surrounding context
            location = _extract_speaker(transcript_text, m.start())

            matches.append(PatternMatch(
                pattern_name=name,
                matched_text=m.group(0),
                context=context,
                severity=severity,
                location=location,
            ))

    return matches


def aggregate_severity(matches: list[PatternMatch]) -> str:
    """
    Return the highest severity across all matches.
    If no matches: "none".
    """
    if not matches:
        return "none"
    return max(matches, key=lambda m: _SEVERITY_RANK.get(m.severity, 0)).severity


def _extract_speaker(text: str, pos: int) -> str:
    """Look backwards from pos for a 'SPEAKER_LABEL: ' pattern."""
    snippet = text[max(0, pos - 200):pos]
    # Match patterns like "Agent:", "CUSTOMER:", "SPEAKER_00:", etc.
    m = re.findall(r'([A-Z][A-Za-z0-9_ ]{0,30}):\s*$', snippet, re.MULTILINE)
    return m[-1].strip() if m else "unknown"
