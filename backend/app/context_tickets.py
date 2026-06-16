"""AI decision logic for company-context change tickets.

A QA user submits a proposed single-field change to the company scoring
context. Instead of a human approving it, the system runs an injection scan
and a validity check, then **auto-applies** or **auto-declines** the change.

The decision logic lives here (pure, GPU-free) so it is unit-testable in
isolation: the LLM-backed injection scan is injected as a callable, so tests
pass without a model server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# Grouped schema fields — mirrors calltone-UI/src/lib/contextSchema.ts and the
# grouped JSON contexts in models/LAYER_2/company_context/contexts/*.json.
VALID_CONTEXT_FIELDS = {
    # script_compliance
    "greeting_script", "closing_script", "required_verification_steps", "hold_procedure",
    "transfer_procedure", "escalation_procedure", "mandatory_disclosures", "prohibited_phrases",
    # factual_accuracy
    "products_and_services", "current_promotions", "policies", "common_troubleshooting",
    "contact_information", "frequently_asked_questions",
    # behavioral
    "tone_guidelines", "empathy_guidelines",
    "conflict_resolution_guidelines", "resolution_expectations",
}

# field_name -> owning group, so the apply step knows where to write.
FIELD_TO_GROUP = {
    "greeting_script": "script_compliance",
    "closing_script": "script_compliance",
    "required_verification_steps": "script_compliance",
    "hold_procedure": "script_compliance",
    "transfer_procedure": "script_compliance",
    "escalation_procedure": "script_compliance",
    "mandatory_disclosures": "script_compliance",
    "prohibited_phrases": "script_compliance",
    "products_and_services": "factual_accuracy",
    "current_promotions": "factual_accuracy",
    "policies": "factual_accuracy",
    "common_troubleshooting": "factual_accuracy",
    "contact_information": "factual_accuracy",
    "frequently_asked_questions": "factual_accuracy",
    "tone_guidelines": "behavioral",
    "empathy_guidelines": "behavioral",
    "conflict_resolution_guidelines": "behavioral",
    "resolution_expectations": "behavioral",
}


@dataclass
class TicketDecision:
    status: str                    # applied | declined
    decision: str                  # ai_applied | ai_blocked | ai_invalid
    reasoning: str
    scan: Optional[dict] = None


def default_validate(field_name: str, text: str) -> tuple[bool, str]:
    if field_name not in VALID_CONTEXT_FIELDS:
        return False, f"'{field_name}' is not a known context field."
    if not text or len(text.strip()) < 3:
        return False, "Proposed text is empty or too short."
    return True, ""


def _scan_to_dict(r) -> Optional[dict]:
    if hasattr(r, "to_dict"):
        try:
            return r.to_dict()
        except Exception:
            pass
    return getattr(r, "__dict__", None)


def decide_ticket(
    field_name: str,
    proposed_text: str,
    *,
    scan: Callable,
    validate: Callable[[str, str], tuple[bool, str]] = default_validate,
) -> TicketDecision:
    """Decide a context-ticket: injection scan, then validity, then apply.

    Borderline scan verdicts (hold_for_human_review / proceed_with_warning) are
    auto-declined with a rephrase message — there is no human approver (D-A3).
    """
    r = scan(proposed_text)
    action = getattr(r, "recommended_action", "proceed")

    if action == "block":
        return TicketDecision(
            "declined", "ai_blocked",
            "Declined: the request looks like a prompt injection or unsafe content "
            f"({getattr(r, 'overall_reasoning', '')}). Please rephrase and resubmit.",
            _scan_to_dict(r),
        )

    if action in ("hold_for_human_review", "proceed_with_warning"):  # D-A3: no human -> decline
        return TicketDecision(
            "declined", "ai_blocked",
            "Declined: the request was ambiguous or borderline. "
            "Please rephrase more clearly and resubmit.",
            _scan_to_dict(r),
        )

    ok, why = validate(field_name, proposed_text)
    if not ok:
        return TicketDecision("declined", "ai_invalid", f"Declined: {why}", None)

    return TicketDecision(
        "applied", "ai_applied", "Applied to company context.", _scan_to_dict(r),
    )
