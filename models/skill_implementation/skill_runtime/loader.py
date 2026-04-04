"""
Dynamic skill loader - discovers and imports skill bundles.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List
from .types import SkillBundle


def discover_all_skills(skills_dir: Path = None) -> List[str]:
    """
    Discover all available skills by scanning the skills/ directory.
    
    Returns:
        List of skill names (folder names).
    """
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent / "skills"
    
    skills_dir = Path(skills_dir)
    
    if not skills_dir.exists():
        return []
    
    skill_names = []
    for item in skills_dir.iterdir():
        if item.is_dir() and (item / "skill.py").exists():
            skill_names.append(item.name)
    
    return sorted(skill_names)


def load_skill(skill_name: str, skills_dir: Path = None) -> SkillBundle:
    """
    Load a skill bundle by dynamically importing its skill.py module.
    
    Args:
        skill_name: Name of the skill (folder name in skills/)
        skills_dir: Optional custom skills directory
        
    Returns:
        SkillBundle dict containing all skill configuration
        
    Raises:
        FileNotFoundError: If skill folder or skill.py doesn't exist
        ImportError: If skill module can't be imported
        AttributeError: If get_*_skill_bundle function not found
    """
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent / "skills"
    
    skills_dir = Path(skills_dir)
    skill_path = skills_dir / skill_name
    skill_file = skill_path / "skill.py"
    
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill folder not found: {skill_path}")
    
    if not skill_file.exists():
        raise FileNotFoundError(f"skill.py not found in: {skill_path}")
    
    # Dynamic import
    module_name = f"skills.{skill_name}.skill"
    spec = importlib.util.spec_from_file_location(module_name, skill_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from: {skill_file}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    
    # Find the get_*_skill_bundle function
    bundle_func = None
    for attr_name in dir(module):
        if attr_name.startswith("get_") and attr_name.endswith("_skill_bundle"):
            bundle_func = getattr(module, attr_name)
            break
    
    if bundle_func is None:
        raise AttributeError(
            f"No get_*_skill_bundle() function found in {skill_file}. "
            f"Expected function like: get_{skill_name.replace('-', '_')}_skill_bundle()"
        )
    
    # Call the function to get the bundle
    bundle = bundle_func()
    
    if not isinstance(bundle, dict):
        raise TypeError(f"Skill bundle must be a dict, got {type(bundle)}")
    
    return bundle


def get_skill_info(skill_name: str, skills_dir: Path = None) -> Dict[str, str]:
    """
    Get basic information about a skill without loading it fully.
    
    Returns:
        Dict with 'name' and 'path' keys
    """
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent / "skills"
    
    skills_dir = Path(skills_dir)
    skill_path = skills_dir / skill_name
    
    return {
        "name": skill_name,
        "path": str(skill_path),
        "exists": skill_path.exists(),
        "has_skill_py": (skill_path / "skill.py").exists(),
        "has_skill_md": (skill_path / "SKILL.md").exists(),
    }
