"""
Skill validator - ensures skills follow prompt-only constraints.
"""

import re
from pathlib import Path
from typing import List, Tuple
from .types import SkillBundle


# Keywords that violate prompt-only constraint
FORBIDDEN_KEYWORDS = [
    "for ",
    "while ",
    "class ",
    "if ",
    "elif ",
    "else:",
    "try:",
    "except:",
    "except ",
]


def validate_skill(skill_name: str, bundle: SkillBundle, skills_dir: Path = None) -> Tuple[bool, List[str]]:
    """
    Validate that a skill follows all requirements.
    
    Args:
        skill_name: Name of the skill
        bundle: The loaded SkillBundle
        skills_dir: Optional custom skills directory
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent / "skills"
    
    skill_path = Path(skills_dir) / skill_name
    skill_md = skill_path / "SKILL.md"
    skill_py = skill_path / "skill.py"
    
    # Check SKILL.md exists
    if not skill_md.exists():
        errors.append(f"SKILL.md not found in {skill_path}")
    else:
        # Check for YAML frontmatter
        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            errors.append("SKILL.md must start with YAML frontmatter (---)")
        else:
            # Check for required fields in frontmatter
            frontmatter_end = content.find("---", 3)
            if frontmatter_end == -1:
                errors.append("SKILL.md frontmatter not properly closed with ---")
            else:
                frontmatter = content[3:frontmatter_end]
                if "name:" not in frontmatter:
                    errors.append("SKILL.md frontmatter missing 'name' field")
                if "description:" not in frontmatter:
                    errors.append("SKILL.md frontmatter missing 'description' field")
    
    # Check skill.py exists
    if not skill_py.exists():
        errors.append(f"skill.py not found in {skill_path}")
    else:
        # Validate prompt-only constraints
        py_content = skill_py.read_text(encoding="utf-8")
        
        # Check for forbidden keywords (only in code lines, not inside string literals)
        lines = py_content.split('\n')
        in_triple_quote = False
        triple_char = None
        code_lines = []  # (line_number, line_content) for lines that are actual code

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if in_triple_quote:
                # Check if this line closes the triple quote
                if triple_char in line:
                    in_triple_quote = False
                continue  # Skip lines inside triple-quoted strings
            # Check if this line opens a triple quote
            if '"""' in stripped or "'''" in stripped:
                tq = '"""' if '"""' in stripped else "'''"
                count = stripped.count(tq)
                if count == 1:
                    # Opens but doesn't close on same line
                    in_triple_quote = True
                    triple_char = tq
                # If count >= 2, it opens and closes on same line (string literal)
                continue  # Skip lines with triple quotes
            code_lines.append((i, line))

        for keyword in FORBIDDEN_KEYWORDS:
            for i, line in code_lines:
                stripped = line.strip()
                if keyword in line and not stripped.startswith('#'):
                    # Make sure keyword is not inside an inline string or after a comment
                    if '#' not in line.split(keyword)[0]:
                        errors.append(
                            f"skill.py line {i} contains forbidden keyword '{keyword.strip()}'. "
                            f"Skills must be prompt-only (no loops, classes, conditionals)."
                        )
                        break
        
        # Check for get_*_skill_bundle function
        if not re.search(r'def get_\w+_skill_bundle\(\)', py_content):
            errors.append("skill.py must contain a function named get_*_skill_bundle()")
    
    # Validate bundle structure
    required_keys = ['name', 'model_dir', 'system_prompt', 'user_prompt_template', 'decoding', 'output_schema']
    for key in required_keys:
        if key not in bundle:
            errors.append(f"SkillBundle missing required key: '{key}'")
    
    # Validate decoding parameters for determinism
    if 'decoding' in bundle:
        decoding = bundle['decoding']
        
        if decoding.get('temperature', 1.0) != 0.0:
            errors.append("Decoding temperature must be 0.0 for determinism")
        
        if decoding.get('top_p', 0.0) != 1.0:
            errors.append("Decoding top_p must be 1.0 for determinism")
        
        if decoding.get('do_sample', True) is not False:
            errors.append("Decoding do_sample must be False for determinism")
    
    # Validate output_schema exists
    if 'output_schema' in bundle:
        if not isinstance(bundle['output_schema'], dict):
            errors.append("output_schema must be a dict")
    
    return (len(errors) == 0, errors)


def validate_prompt_stability(system_prompt: str, user_prompt_template: str) -> Tuple[bool, List[str]]:
    """
    Check if prompts are stable (no timestamps, randomness indicators).
    
    Returns:
        Tuple of (is_stable, list_of_warnings)
    """
    warnings = []
    
    # Check for timestamp indicators
    timestamp_patterns = [
        r'\{.*time.*\}',
        r'\{.*date.*\}',
        r'random',
        r'rand\(',
    ]
    
    combined = system_prompt + " " + user_prompt_template
    
    for pattern in timestamp_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            warnings.append(f"Prompt may contain dynamic content: {pattern}")
    
    return (len(warnings) == 0, warnings)
