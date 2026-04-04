"""
Text Ingestion Module — lets the QA head write company context as plain text.

The QA head writes a free-form .txt file describing the company's policies,
scripts, products, and behavioral expectations. This module uses the LLM to:

1. Parse the text into the structured CompanyContextSchema fields
2. Validate completeness — flag anything the QA forgot to include
3. Save the result as JSON for the rest of LAYER 2

Architecture:
    Plain text file (.txt)
         │
    Pass 1: Extract script_compliance fields
    Pass 2: Extract factual_accuracy fields
    Pass 3: Extract behavioral fields
         │
    Assemble into CompanyContextSchema
         │
    Pass 4: Validate — check every field, report missing/incomplete
         │
    Save as JSON → ready for LAYER 2 pipeline

Usage:
    from text_ingestion import ingest_text_context

    result = ingest_text_context(
        text_path="/path/to/company_policy.txt",
        company_name="MetroBoost",
    )
    # result = {"json_path": "...", "validation": {...}}
"""

import json
import sys
from pathlib import Path
from typing import Optional
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skill_implementation"))

from .schema import CompanyContextSchema
from .context_store import ContextStore


# ---------------------------------------------------------------------------
# Prompts for each extraction pass
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a precise JSON extraction assistant. You read company policy documents written in plain text by a QA head, and you extract specific fields into structured JSON.

CRITICAL RULES:
1. Output MUST be valid JSON only — no markdown, no explanations, no preamble.
2. Extract ONLY what is explicitly stated in the text. Do NOT invent or assume information.
3. If a field is not mentioned at all in the text, set it to an empty string "".
4. Preserve the original meaning exactly. Do not paraphrase in a way that changes the intent.
5. Include all relevant details — plan prices, specific phrases, step-by-step procedures.
6. Output the JSON object immediately."""


PASS_SCRIPT_PROMPT = """Read the following company policy document and extract ONLY the script compliance fields.

COMPANY POLICY DOCUMENT:
{input_text}

Extract these fields from the text above. If a field is not mentioned, use "".
IMPORTANT: Be concise. Capture the KEY rules, exact scripts, and numbered steps. Do NOT copy entire paragraphs — summarize into clear, actionable rules.

Return this exact JSON structure:
{{
  "greeting_script": "The exact greeting the agent must use when answering calls",
  "closing_script": "The exact closing the agent must use when ending calls",
  "required_verification_steps": "Steps the agent must follow to verify customer identity",
  "hold_procedure": "What the agent must say before and after putting a customer on hold",
  "transfer_procedure": "What the agent must say and do when transferring a call",
  "escalation_procedure": "When and how the agent should escalate to a supervisor",
  "mandatory_disclosures": "Legal or regulatory statements the agent must read",
  "prohibited_phrases": "Words or phrases the agent must NEVER use"
}}

Return ONLY the JSON:"""


PASS_FACTUAL_PROMPT = """Read the following company policy document and extract ONLY the factual accuracy fields.

COMPANY POLICY DOCUMENT:
{input_text}

Extract these fields from the text above. If a field is not mentioned, use "".
IMPORTANT: Be concise. List products with name, price, and key features in a compact format. Summarize policies as numbered rules. Do NOT copy entire paragraphs verbatim.

Return this exact JSON structure:
{{
  "products_and_services": "List of ALL products/services with exact names, prices, and features",
  "current_promotions": "ALL active promotions, discounts, and offers with their exact terms and conditions",
  "policies": "Company policies: billing, refunds, cancellation, porting, etc.",
  "common_troubleshooting": "Standard troubleshooting steps for common issues",
  "contact_information": "Department phone numbers, emails, hours of operation",
  "frequently_asked_questions": "Common questions and their correct answers"
}}

Return ONLY the JSON:"""


PASS_BEHAVIORAL_PROMPT = """Read the following company policy document and extract ONLY the behavioral guideline fields.

COMPANY POLICY DOCUMENT:
{input_text}

Extract these fields from the text above. If a field is not mentioned, use "".
IMPORTANT: Keep each field value CONCISE — summarize key rules as a numbered list, do NOT copy paragraphs verbatim. Maximum 3-4 sentences per field.

Return this exact JSON structure:
{{
  "tone_guidelines": "Guidelines for how the agent should speak and behave on calls",
  "empathy_guidelines": "How the agent should handle emotional or upset customers",
  "conflict_resolution_guidelines": "How the agent should handle conflicts and angry customers",
  "resolution_expectations": "What counts as resolving an issue and when to follow up"
}}

Return ONLY the JSON:"""


# Pass 5 prompts — one per section to avoid output truncation.
# Each call takes only the relevant extracted fields and produces atomic nodes
# with LLM-generated semantic_tags and declared cross_refs.

_PASS_ATOMIC_SYSTEM = """You are a knowledge graph builder. You convert structured policy fields into atomic knowledge nodes — one independent fact per node. Output ONLY valid JSON."""

_PASS_ATOMIC_TEMPLATE = """Convert these {section_name} policy fields into atomic knowledge nodes.

FIELDS:
{input_text}

Break each field into ATOMIC FACTS. One self-contained rule, procedure, or statement per node.

For each atomic fact return:
- "field": the source field name (exact name from the list above)
- "content": the fact as one clear, complete sentence
- "semantic_tags": 5-8 SPECIFIC search tags. Use words an agent would SAY or a customer would USE.
  Include synonyms and common phrasings.
  BAD (too generic): ["procedure", "policy", "agent", "rule", "required"]
  GOOD (specific):   ["greeting-script", "opening-phrase", "your-wireless-specialist", "thank-you-for-calling"]
  BAD: ["discount", "promotion", "billing"]
  GOOD: ["autopay-discount", "5-dollar-off", "automatic-payment", "next-billing-cycle", "monthly-credit"]
- "cross_refs": list of OTHER field names (from ALL 18 fields) where this fact is also relevant, or []

Valid field names for cross_refs: greeting_script, closing_script, required_verification_steps, hold_procedure, transfer_procedure, escalation_procedure, mandatory_disclosures, prohibited_phrases, products_and_services, current_promotions, policies, common_troubleshooting, contact_information, frequently_asked_questions, tone_guidelines, empathy_guidelines, conflict_resolution_guidelines, resolution_expectations

Return ONLY this JSON:
{{
  "atomic_nodes": [
    {{"field": "...", "content": "...", "semantic_tags": [...], "cross_refs": [...]}}
  ]
}}"""


VALIDATION_PROMPT = """You are a QA validation assistant. A company policy document was parsed into structured fields. Check each field and report what is MISSING or INCOMPLETE.

Here are the extracted fields:
{input_text}

For each field, report:
- "ok" if the field has sufficient content for evaluating a customer service agent
- "missing" if the field is empty
- "incomplete" if the field exists but is missing critical details (e.g., prices without amounts, procedures without steps)

Return this JSON:
{{
  "fields": {{
    "greeting_script": {{"status": "ok|missing|incomplete", "note": "what is missing or why incomplete"}},
    "closing_script": {{"status": "...", "note": "..."}},
    "required_verification_steps": {{"status": "...", "note": "..."}},
    "hold_procedure": {{"status": "...", "note": "..."}},
    "transfer_procedure": {{"status": "...", "note": "..."}},
    "escalation_procedure": {{"status": "...", "note": "..."}},
    "mandatory_disclosures": {{"status": "...", "note": "..."}},
    "prohibited_phrases": {{"status": "...", "note": "..."}},
    "products_and_services": {{"status": "...", "note": "..."}},
    "current_promotions": {{"status": "...", "note": "..."}},
    "policies": {{"status": "...", "note": "..."}},
    "common_troubleshooting": {{"status": "...", "note": "..."}},
    "contact_information": {{"status": "...", "note": "..."}},
    "frequently_asked_questions": {{"status": "...", "note": "..."}},
    "tone_guidelines": {{"status": "...", "note": "..."}},
    "empathy_guidelines": {{"status": "...", "note": "..."}},
    "conflict_resolution_guidelines": {{"status": "...", "note": "..."}},
    "resolution_expectations": {{"status": "...", "note": "..."}}
  }},
  "overall_completeness": "percentage estimate of how complete the policy is",
  "critical_missing": ["list of fields that are REQUIRED but missing or empty"]
}}

Return ONLY the JSON:"""


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _load_llm(n_ctx: int = 8192):
    """Load the Llama model for text ingestion."""
    from llama_cpp import Llama

    model_path = str(
        Path(__file__).parent.parent.parent
        / "skill_implementation"
        / "models"
        / "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"
    )

    return Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=8,
        n_gpu_layers=-1,
        seed=12345,
        verbose=False,
    )


def _run_llm(llm, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    """Run a single LLM call and return the generated text."""
    full_prompt = (
        f"<|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )

    response = llm(
        full_prompt,
        temperature=0.0,
        top_p=1.0,
        max_tokens=max_tokens,
        stop=["<|eot_id|>", "<|end_of_text|>"],
        echo=False,
        seed=12345,
    )

    return response["choices"][0]["text"].strip()


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM output, handling common quirks and truncation."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON within the text (model sometimes adds text around it)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Handle truncated JSON (output hit max_tokens) — try to close open strings/braces
    if start >= 0:
        fragment = text[start:]
        # Close any open string
        if fragment.count('"') % 2 == 1:
            fragment += '"'
        # Close open braces
        open_braces = fragment.count("{") - fragment.count("}")
        fragment += "}" * max(0, open_braces)
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM output:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Chunk the input text if it's too long for one pass
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def _truncate_for_context(text: str, max_input_tokens: int = 3500) -> str:
    """Truncate text to fit within the context window for one pass."""
    estimated = _estimate_tokens(text)
    if estimated <= max_input_tokens:
        return text
    # Truncate conservatively
    max_chars = max_input_tokens * 4
    return text[:max_chars] + "\n\n[... document truncated for this pass ...]"


# ---------------------------------------------------------------------------
# Main ingestion flow
# ---------------------------------------------------------------------------

def ingest_text_context(
    text_path: str,
    company_name: str,
    context_version: str = "1.0.0",
    contexts_dir: Optional[str] = None,
    skip_validation: bool = False,
) -> dict:
    """
    Ingest a plain-text company policy document and convert it to structured JSON.

    Args:
        text_path: Path to the .txt file written by the QA head
        company_name: Company name (used for saving)
        context_version: Version string for the context
        contexts_dir: Optional custom directory for saving JSON
        skip_validation: If True, skip the validation pass

    Returns:
        dict with:
            json_path: Path to the saved JSON file
            validation: Validation results (or None if skipped)
            schema: The extracted CompanyContextSchema as dict
    """
    # Read the text file
    text_path = Path(text_path)
    if not text_path.exists():
        raise FileNotFoundError(f"Text file not found: {text_path}")

    raw_text = text_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(f"Text file is empty: {text_path}")

    print(f"\n{'='*80}")
    print(f"TEXT INGESTION: {company_name}")
    print(f"{'='*80}")
    print(f"Source:  {text_path}")
    print(f"Length:  {len(raw_text)} chars (~{_estimate_tokens(raw_text)} tokens)")

    # Load model once, reuse for all passes
    print(f"\nLoading LLM...")
    llm = _load_llm(n_ctx=16384)

    # Truncate if needed for each pass (leave room for prompt + output)
    text_for_prompt = _truncate_for_context(raw_text, max_input_tokens=5000)

    # --- Pass 1: Script Compliance ---
    print(f"\nPass 1/4: Extracting script compliance fields...")
    prompt1 = PASS_SCRIPT_PROMPT.format(input_text=text_for_prompt)
    raw1 = _run_llm(llm, SYSTEM_PROMPT, prompt1)
    script_fields = _parse_json_response(raw1)
    print(f"  Extracted {sum(1 for v in script_fields.values() if v)} / {len(script_fields)} fields")

    # --- Pass 2: Factual Accuracy ---
    print(f"Pass 2/4: Extracting factual accuracy fields...")
    prompt2 = PASS_FACTUAL_PROMPT.format(input_text=text_for_prompt)
    raw2 = _run_llm(llm, SYSTEM_PROMPT, prompt2)
    factual_fields = _parse_json_response(raw2)
    print(f"  Extracted {sum(1 for v in factual_fields.values() if v)} / {len(factual_fields)} fields")

    # --- Pass 3: Behavioral ---
    print(f"Pass 3/4: Extracting behavioral fields...")
    prompt3 = PASS_BEHAVIORAL_PROMPT.format(input_text=text_for_prompt)
    raw3 = _run_llm(llm, SYSTEM_PROMPT, prompt3)
    behavioral_fields = _parse_json_response(raw3)
    print(f"  Extracted {sum(1 for v in behavioral_fields.values() if v)} / {len(behavioral_fields)} fields")

    # --- Flatten any nested dicts to strings (model sometimes returns structured dicts) ---
    def _flatten(val):
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            parts = []
            for k, v in val.items():
                if isinstance(v, dict):
                    details = ", ".join(f"{dk}: {dv}" for dk, dv in v.items())
                    parts.append(f"{k}: {details}")
                else:
                    parts.append(f"{k}: {v}")
            return "\n".join(parts)
        if isinstance(val, list):
            return "\n".join(str(item) for item in val)
        return str(val)

    script_fields = {k: _flatten(v) for k, v in script_fields.items()}
    factual_fields = {k: _flatten(v) for k, v in factual_fields.items()}
    behavioral_fields = {k: _flatten(v) for k, v in behavioral_fields.items()}

    # --- Assemble into schema ---
    context = CompanyContextSchema(
        company_name=company_name,
        context_version=context_version,
        last_updated=str(date.today()),
        # Script compliance
        greeting_script=script_fields.get("greeting_script", ""),
        closing_script=script_fields.get("closing_script", ""),
        required_verification_steps=script_fields.get("required_verification_steps", ""),
        hold_procedure=script_fields.get("hold_procedure", ""),
        transfer_procedure=script_fields.get("transfer_procedure", ""),
        escalation_procedure=script_fields.get("escalation_procedure", ""),
        mandatory_disclosures=script_fields.get("mandatory_disclosures", ""),
        prohibited_phrases=script_fields.get("prohibited_phrases", ""),
        # Factual accuracy
        products_and_services=factual_fields.get("products_and_services", ""),
        current_promotions=factual_fields.get("current_promotions", ""),
        policies=factual_fields.get("policies", ""),
        common_troubleshooting=factual_fields.get("common_troubleshooting", ""),
        contact_information=factual_fields.get("contact_information", ""),
        frequently_asked_questions=factual_fields.get("frequently_asked_questions", ""),
        # Behavioral
        tone_guidelines=behavioral_fields.get("tone_guidelines", ""),
        empathy_guidelines=behavioral_fields.get("empathy_guidelines", ""),
        conflict_resolution_guidelines=behavioral_fields.get("conflict_resolution_guidelines", ""),
        resolution_expectations=behavioral_fields.get("resolution_expectations", ""),
    )

    # --- Pass 4: Validation ---
    validation = None
    if not skip_validation:
        print(f"Pass 4/4: Validating completeness...")
        context_summary = json.dumps(context.to_dict(), indent=2)
        # Truncate the summary if too long for the validation prompt
        context_summary_truncated = _truncate_for_context(context_summary, max_input_tokens=4500)
        prompt4 = VALIDATION_PROMPT.format(input_text=context_summary_truncated)
        raw4 = _run_llm(llm, SYSTEM_PROMPT, prompt4)
        try:
            validation = _parse_json_response(raw4)
        except ValueError:
            validation = {"error": "Could not parse validation output", "raw": raw4[:500]}

        _print_validation_report(validation)

    # --- Pass 5a/5b/5c: Atomic Node Generation (Zettelkasten semantic tags) ---
    # Run in 3 focused sub-calls (one per section) to avoid output truncation.
    # Each call takes only the relevant extracted fields as input.
    atomic_nodes = []

    def _format_fields(fields: dict) -> str:
        return "\n".join(
            f"{k}: {v}" for k, v in fields.items() if v
        )

    pass5_sections = [
        ("Script Compliance", script_fields),
        ("Factual Accuracy", factual_fields),
        ("Behavioral", behavioral_fields),
    ]

    print(f"\nPass 5/5: Generating semantic tags for Zettelkasten graph...")
    for section_name, fields in pass5_sections:
        fields_text = _format_fields(fields)
        if not fields_text.strip():
            continue
        prompt5 = _PASS_ATOMIC_TEMPLATE.format(
            section_name=section_name,
            input_text=fields_text,
        )
        try:
            raw5 = _run_llm(llm, _PASS_ATOMIC_SYSTEM, prompt5, max_tokens=6144)
            result5 = _parse_json_response(raw5)
            section_nodes = result5.get("atomic_nodes", [])
            atomic_nodes.extend(section_nodes)
            print(f"  {section_name}: {len(section_nodes)} atomic nodes")
        except (ValueError, KeyError) as e:
            print(f"  WARNING: Pass 5 failed for {section_name}: {e}. "
                  f"Graph will use legacy keyword-based builder for this section.")

    # --- Save ---
    store = ContextStore(contexts_dir)
    json_path = store.save(context)

    # Augment the saved JSON with atomic_nodes (raw re-save preserves extra keys
    # that CompanyContextSchema.to_dict() would otherwise drop)
    if atomic_nodes:
        with open(json_path, "r", encoding="utf-8") as f:
            saved_raw = json.load(f)
        saved_raw["atomic_nodes"] = atomic_nodes
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(saved_raw, f, indent=2, ensure_ascii=False)
        print(f"  Total atomic nodes saved: {len(atomic_nodes)}")

    print(f"\nSaved to: {json_path}")

    return {
        "json_path": str(json_path),
        "validation": validation,
        "schema": context.to_dict(),
        "atomic_nodes_count": len(atomic_nodes),
    }


def _print_validation_report(validation: dict):
    """Print a human-readable validation report."""
    print(f"\n{'─'*80}")
    print(f"  VALIDATION REPORT")
    print(f"{'─'*80}")

    if "error" in validation:
        print(f"\n  WARNING: Validation parse failed: {validation['error']}")
        return

    fields = validation.get("fields", {})
    ok_count = 0
    missing_count = 0
    incomplete_count = 0

    for field_name, info in fields.items():
        status = info.get("status", "unknown")
        note = info.get("note", "")
        if status == "ok":
            ok_count += 1
            icon = "OK"
        elif status == "missing":
            missing_count += 1
            icon = "MISSING"
        elif status == "incomplete":
            incomplete_count += 1
            icon = "INCOMPLETE"
        else:
            icon = "???"

        display_name = field_name.replace("_", " ").title()
        if status == "ok":
            print(f"  [{icon}]         {display_name}")
        else:
            print(f"  [{icon}]    {display_name}")
            if note:
                print(f"              -> {note}")

    total = ok_count + missing_count + incomplete_count
    print(f"\n  Summary: {ok_count}/{total} OK, {missing_count} missing, {incomplete_count} incomplete")

    completeness = validation.get("overall_completeness", "unknown")
    print(f"  Completeness: {completeness}")

    critical = validation.get("critical_missing", [])
    if critical:
        print(f"\n  CRITICAL — These required fields are missing:")
        for field in critical:
            print(f"    - {field}")

    print(f"{'─'*80}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert a plain-text company policy document into structured JSON for LAYER 2"
    )
    parser.add_argument("text_file", help="Path to the .txt file written by the QA head")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--version", default="1.0.0", help="Context version (default: 1.0.0)")
    parser.add_argument("--output-dir", help="Custom output directory for the JSON file")
    parser.add_argument("--skip-validation", action="store_true", help="Skip the validation pass")

    args = parser.parse_args()

    result = ingest_text_context(
        text_path=args.text_file,
        company_name=args.company,
        context_version=args.version,
        contexts_dir=args.output_dir,
        skip_validation=args.skip_validation,
    )

    print(f"\nDone. JSON saved to: {result['json_path']}")
