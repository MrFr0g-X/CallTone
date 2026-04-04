"""
Context Store - reads, writes, and manages company context files.

Company contexts are stored as JSON files in the contexts/ directory.
Each file represents one company's complete set of rules and protocols.
"""

import json
from pathlib import Path
from typing import Optional
from .schema import CompanyContextSchema


class ContextStore:
    """Manages company context files on disk."""

    def __init__(self, contexts_dir: Optional[str] = None):
        if contexts_dir is None:
            self.contexts_dir = Path(__file__).parent / "contexts"
        else:
            self.contexts_dir = Path(contexts_dir)
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

    def save(self, context: CompanyContextSchema) -> Path:
        """Save a company context to disk."""
        filename = context.company_name.lower().replace(" ", "_") + ".json"
        filepath = self.contexts_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(context.to_dict(), f, indent=2, ensure_ascii=False)
        return filepath

    def load(self, company_name: str) -> CompanyContextSchema:
        """Load a company context from disk."""
        filename = company_name.lower().replace(" ", "_") + ".json"
        filepath = self.contexts_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"No context found for company: {company_name} at {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CompanyContextSchema.from_dict(data)

    def list_companies(self) -> list:
        """List all available company contexts."""
        return [
            p.stem.replace("_", " ").title()
            for p in self.contexts_dir.glob("*.json")
        ]

    def load_raw(self, company_name: str) -> dict:
        """Load raw dict without schema conversion."""
        filename = company_name.lower().replace(" ", "_") + ".json"
        filepath = self.contexts_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"No context found for company: {company_name}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_context_for_criterion(self, company_name: str, criterion: str) -> dict:
        """
        Extract only the context fields relevant to a specific criterion.

        Args:
            company_name: Company name
            criterion: One of "script_compliance", "factual_accuracy",
                       "politeness_tone", "empathy", "conflict_detection",
                       "issue_resolution"

        Returns:
            Dict with relevant context fields
        """
        raw = self.load_raw(company_name)
        result = {"company_name": raw.get("company_name", "")}

        criterion_map = {
            "script_compliance": "script_compliance",
            "factual_accuracy": "factual_accuracy",
            "politeness_tone": "behavioral",
            "empathy": "behavioral",
            "conflict_detection": "behavioral",
            "issue_resolution": "behavioral",
        }

        section = criterion_map.get(criterion)
        if section and section in raw:
            result[section] = raw[section]

        return result
