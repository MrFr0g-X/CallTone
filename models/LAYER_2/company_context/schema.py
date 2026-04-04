"""
Company Context Schema - defines the structured fields the QA head fills out.

Each field has a name, description, data type, and whether it's required.
The QA head fills these fields to define company-specific rules, protocols,
scripts, offers, and factual information that the agent must follow.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextField:
    """A single field in the company context form."""
    name: str
    description: str
    field_type: str  # "text", "list", "structured"
    required: bool
    category: str  # which criterion this feeds into
    example: str


# The fields the QA head must fill out
CONTEXT_FIELDS = [
    # --- Script Compliance fields ---
    ContextField(
        name="greeting_script",
        description="The exact greeting the agent must use when answering a call",
        field_type="text",
        required=True,
        category="script_compliance",
        example="Thank you for calling [Company Name], my name is [Agent Name]. How may I assist you today?"
    ),
    ContextField(
        name="closing_script",
        description="The exact closing the agent must use when ending a call",
        field_type="text",
        required=True,
        category="script_compliance",
        example="Is there anything else I can help you with? Thank you for calling [Company Name]. Have a great day!"
    ),
    ContextField(
        name="required_verification_steps",
        description="Steps the agent must follow to verify customer identity",
        field_type="list",
        required=True,
        category="script_compliance",
        example="1. Ask for full name\n2. Ask for account number or phone number\n3. Ask security question"
    ),
    ContextField(
        name="hold_procedure",
        description="What the agent must say before and after putting a customer on hold",
        field_type="text",
        required=True,
        category="script_compliance",
        example="Before: 'May I place you on a brief hold while I look into this?' After: 'Thank you for holding.'"
    ),
    ContextField(
        name="transfer_procedure",
        description="What the agent must say and do when transferring a call",
        field_type="text",
        required=True,
        category="script_compliance",
        example="Agent must explain the reason for transfer and provide the department name before transferring."
    ),
    ContextField(
        name="escalation_procedure",
        description="When and how the agent should escalate a call to a supervisor",
        field_type="text",
        required=True,
        category="script_compliance",
        example="Escalate if customer requests supervisor, threatens legal action, or issue cannot be resolved in 2 attempts."
    ),
    ContextField(
        name="mandatory_disclosures",
        description="Legal or regulatory statements the agent must read in certain situations",
        field_type="list",
        required=False,
        category="script_compliance",
        example="1. Recording disclosure: 'This call may be recorded for quality assurance.'\n2. Fee disclosure before processing payments"
    ),
    ContextField(
        name="prohibited_phrases",
        description="Words or phrases the agent must NEVER use",
        field_type="list",
        required=False,
        category="script_compliance",
        example="1. 'That's not my department'\n2. 'I don't know'\n3. 'You should have...'\n4. 'Calm down'"
    ),

    # --- Factual Accuracy fields ---
    ContextField(
        name="products_and_services",
        description="List of products/services with correct names, prices, and descriptions",
        field_type="structured",
        required=True,
        category="factual_accuracy",
        example="Product: Basic Plan - $9.99/month - 100GB storage, email support\nProduct: Pro Plan - $29.99/month - 1TB storage, phone + email support"
    ),
    ContextField(
        name="current_promotions",
        description="Active promotions, discounts, and special offers with their terms",
        field_type="list",
        required=False,
        category="factual_accuracy",
        example="1. Summer Sale: 20% off Pro Plan for new customers (valid until Sept 30)\n2. Referral bonus: $10 credit per referral"
    ),
    ContextField(
        name="policies",
        description="Company policies (return, refund, warranty, cancellation, etc.)",
        field_type="structured",
        required=True,
        category="factual_accuracy",
        example="Return Policy: 30-day return window, item must be unused, refund processed within 5-7 business days"
    ),
    ContextField(
        name="common_troubleshooting",
        description="Standard troubleshooting steps for common issues",
        field_type="structured",
        required=False,
        category="factual_accuracy",
        example="Issue: Can't login\nSteps: 1. Clear browser cache 2. Try password reset 3. Check if account is locked"
    ),
    ContextField(
        name="contact_information",
        description="Correct department phone numbers, emails, hours of operation",
        field_type="structured",
        required=True,
        category="factual_accuracy",
        example="Billing: billing@company.com, 1-800-123-4567\nTech Support: techsupport@company.com, available 24/7"
    ),
    ContextField(
        name="frequently_asked_questions",
        description="Common questions and their correct answers",
        field_type="structured",
        required=False,
        category="factual_accuracy",
        example="Q: How long does shipping take? A: Standard 5-7 business days, Express 2-3 business days"
    ),

    # --- General behavior fields ---
    ContextField(
        name="tone_guidelines",
        description="Guidelines for how the agent should speak and behave",
        field_type="text",
        required=False,
        category="politeness_tone",
        example="Always use the customer's name. Maintain a warm, professional tone. Avoid jargon."
    ),
    ContextField(
        name="empathy_guidelines",
        description="How the agent should handle emotional customers",
        field_type="text",
        required=False,
        category="empathy",
        example="Acknowledge the customer's frustration before offering solutions. Use phrases like 'I understand how frustrating this must be.'"
    ),
    ContextField(
        name="conflict_resolution_guidelines",
        description="How the agent should handle conflicts and angry customers",
        field_type="text",
        required=False,
        category="conflict_detection",
        example="Stay calm. Do not argue. Offer solutions. If customer becomes abusive, warn once then escalate."
    ),
    ContextField(
        name="resolution_expectations",
        description="What counts as resolving an issue and when to follow up",
        field_type="text",
        required=False,
        category="issue_resolution",
        example="Issue is resolved when customer confirms satisfaction. If not resolved, create a ticket and provide reference number."
    ),
]


@dataclass
class CompanyContextSchema:
    """The complete company context filled by the QA head."""
    company_name: str
    context_version: str
    last_updated: str

    # Script Compliance
    greeting_script: str = ""
    closing_script: str = ""
    required_verification_steps: str = ""
    hold_procedure: str = ""
    transfer_procedure: str = ""
    escalation_procedure: str = ""
    mandatory_disclosures: str = ""
    prohibited_phrases: str = ""

    # Factual Accuracy
    products_and_services: str = ""
    current_promotions: str = ""
    policies: str = ""
    common_troubleshooting: str = ""
    contact_information: str = ""
    frequently_asked_questions: str = ""

    # Behavioral
    tone_guidelines: str = ""
    empathy_guidelines: str = ""
    conflict_resolution_guidelines: str = ""
    resolution_expectations: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "company_name": self.company_name,
            "context_version": self.context_version,
            "last_updated": self.last_updated,
            "script_compliance": {
                "greeting_script": self.greeting_script,
                "closing_script": self.closing_script,
                "required_verification_steps": self.required_verification_steps,
                "hold_procedure": self.hold_procedure,
                "transfer_procedure": self.transfer_procedure,
                "escalation_procedure": self.escalation_procedure,
                "mandatory_disclosures": self.mandatory_disclosures,
                "prohibited_phrases": self.prohibited_phrases,
            },
            "factual_accuracy": {
                "products_and_services": self.products_and_services,
                "current_promotions": self.current_promotions,
                "policies": self.policies,
                "common_troubleshooting": self.common_troubleshooting,
                "contact_information": self.contact_information,
                "frequently_asked_questions": self.frequently_asked_questions,
            },
            "behavioral": {
                "tone_guidelines": self.tone_guidelines,
                "empathy_guidelines": self.empathy_guidelines,
                "conflict_resolution_guidelines": self.conflict_resolution_guidelines,
                "resolution_expectations": self.resolution_expectations,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyContextSchema":
        """Create from dictionary."""
        sc = data.get("script_compliance", {})
        fa = data.get("factual_accuracy", {})
        bh = data.get("behavioral", {})
        return cls(
            company_name=data.get("company_name", ""),
            context_version=data.get("context_version", "1.0.0"),
            last_updated=data.get("last_updated", ""),
            greeting_script=sc.get("greeting_script", ""),
            closing_script=sc.get("closing_script", ""),
            required_verification_steps=sc.get("required_verification_steps", ""),
            hold_procedure=sc.get("hold_procedure", ""),
            transfer_procedure=sc.get("transfer_procedure", ""),
            escalation_procedure=sc.get("escalation_procedure", ""),
            mandatory_disclosures=sc.get("mandatory_disclosures", ""),
            prohibited_phrases=sc.get("prohibited_phrases", ""),
            products_and_services=fa.get("products_and_services", ""),
            current_promotions=fa.get("current_promotions", ""),
            policies=fa.get("policies", ""),
            common_troubleshooting=fa.get("common_troubleshooting", ""),
            contact_information=fa.get("contact_information", ""),
            frequently_asked_questions=fa.get("frequently_asked_questions", ""),
            tone_guidelines=bh.get("tone_guidelines", ""),
            empathy_guidelines=bh.get("empathy_guidelines", ""),
            conflict_resolution_guidelines=bh.get("conflict_resolution_guidelines", ""),
            resolution_expectations=bh.get("resolution_expectations", ""),
        )
