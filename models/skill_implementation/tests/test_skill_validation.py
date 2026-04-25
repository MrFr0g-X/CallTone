"""
Test skill validation - ensures prompt-only constraints are enforced.
"""

import sys
import tempfile
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skill_runtime import validate_skill, load_skill
from skill_runtime.validator import FORBIDDEN_KEYWORDS


def test_valid_skill():
    """Test that a valid skill passes validation."""
    skill_name = "identify-call-roles"
    bundle = load_skill(skill_name)
    
    is_valid, errors = validate_skill(skill_name, bundle)
    
    assert is_valid, f"Valid skill failed validation: {errors}"
    print(f"✓ Valid skill test passed for {skill_name}")


def test_forbidden_keywords_detection():
    """Test that validator detects forbidden keywords."""
    
    # Create a temporary invalid skill
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        skills_dir = tmpdir / "skills"
        skill_dir = skills_dir / "test-invalid"
        skill_dir.mkdir(parents=True)
        
        # Create SKILL.md
        (skill_dir / "SKILL.md").write_text("""---
name: test-invalid
description: Test skill
---
# Test
""")
        
        # Create invalid skill.py with a for loop
        (skill_dir / "skill.py").write_text("""
def get_test_invalid_skill_bundle():
    result = []
    for i in range(10):  # FORBIDDEN
        result.append(i)
    
    return {
        "name": "test-invalid",
        "model_dir": "/path/to/model",
        "system_prompt": "test",
        "user_prompt_template": "test {input_text}",
        "decoding": {"temperature": 0.0, "top_p": 1.0, "do_sample": False},
        "output_schema": {}
    }
""")
        
        # Load and validate
        bundle = load_skill("test-invalid", skills_dir=skills_dir)
        is_valid, errors = validate_skill("test-invalid", bundle, skills_dir=skills_dir)
        
        # Should fail validation
        assert not is_valid, "Skill with for loop should fail validation"
        
        # Check error message mentions the forbidden keyword
        assert any("'for'" in err or "for " in err for err in errors), \
            f"Error should mention 'for' loop: {errors}"
        
        print("✓ Forbidden keyword detection test passed")


def test_missing_required_keys():
    """Test that validator catches missing required keys in bundle."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        skills_dir = tmpdir / "skills"
        skill_dir = skills_dir / "test-incomplete"
        skill_dir.mkdir(parents=True)
        
        # Create SKILL.md
        (skill_dir / "SKILL.md").write_text("""---
name: test-incomplete
description: Test skill
---
# Test
""")
        
        # Create skill.py with incomplete bundle
        (skill_dir / "skill.py").write_text("""
def get_test_incomplete_skill_bundle():
    return {
        "name": "test-incomplete",
        # Missing model_dir, system_prompt, etc.
    }
""")
        
        # Load and validate
        bundle = load_skill("test-incomplete", skills_dir=skills_dir)
        is_valid, errors = validate_skill("test-incomplete", bundle, skills_dir=skills_dir)
        
        # Should fail
        assert not is_valid, "Incomplete skill should fail validation"
        
        # Check for missing key errors
        assert any("missing" in err.lower() for err in errors), f"Should report missing keys: {errors}"
        
        print("✓ Missing required keys test passed")


def test_non_deterministic_decoding():
    """Test that validator catches non-deterministic decoding settings."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        skills_dir = tmpdir / "skills"
        skill_dir = skills_dir / "test-nondeterministic"
        skill_dir.mkdir(parents=True)
        
        # Create SKILL.md
        (skill_dir / "SKILL.md").write_text("""---
name: test-nondeterministic
description: Test skill
---
# Test
""")
        
        # Create skill.py with non-deterministic settings
        (skill_dir / "skill.py").write_text("""
def get_test_nondeterministic_skill_bundle():
    return {
        "name": "test-nondeterministic",
        "model_dir": "/path/to/model",
        "system_prompt": "test",
        "user_prompt_template": "test {input_text}",
        "decoding": {"temperature": 0.7, "top_p": 0.9, "do_sample": True},  # NON-DETERMINISTIC
        "output_schema": {}
    }
""")
        
        # Load and validate
        bundle = load_skill("test-nondeterministic", skills_dir=skills_dir)
        is_valid, errors = validate_skill("test-nondeterministic", bundle, skills_dir=skills_dir)
        
        # Should fail
        assert not is_valid, "Non-deterministic skill should fail validation"
        
        # Check for decoding errors
        assert any("temperature" in err.lower() or "determinism" in err.lower() for err in errors), \
            f"Should report non-deterministic settings: {errors}"
        
        print("✓ Non-deterministic decoding test passed")


if __name__ == "__main__":
    print("Running skill validation tests...\n")
    
    try:
        test_valid_skill()
        print()
        test_forbidden_keywords_detection()
        print()
        test_missing_required_keys()
        print()
        test_non_deterministic_decoding()
        print("\n✓ All validation tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
