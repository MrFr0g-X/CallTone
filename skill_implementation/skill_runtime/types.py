"""
Type definitions for the prompt-only skills system.
"""

from typing import TypedDict, Optional, List, Any
from dataclasses import dataclass


class DecodingParams(TypedDict, total=False):
    """Parameters for deterministic decoding."""
    temperature: float
    top_p: float
    max_tokens: int
    seed: int
    stop: Optional[List[str]]
    do_sample: bool


class SkillBundle(TypedDict):
    """Complete skill bundle containing all required components."""
    name: str
    model_dir: str
    system_prompt: str
    user_prompt_template: str
    decoding: DecodingParams
    output_schema: dict


@dataclass
class SkillMetadata:
    """Metadata parsed from SKILL.md frontmatter."""
    name: str
    description: str
    version: Optional[str] = None
    author: Optional[str] = None
