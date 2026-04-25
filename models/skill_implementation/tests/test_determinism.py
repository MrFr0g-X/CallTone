"""
Test that skills produce deterministic output.
"""

import sys
from pathlib import Path

import pytest

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skill_runtime import load_skill, run_skill

# These tests load the real Llama 3.1 8B GGUF (~8 GB). Skip when the
# weights aren't present (CI, fresh clones) so the suite stays useful
# without forcing a model download.
_QWEN3_GGUF = (
    Path(__file__).parent.parent
    / "models"
    / "Qwen3-8B-Q4_K_M.gguf"
)
pytestmark = pytest.mark.skipif(
    not _QWEN3_GGUF.exists(),
    reason=f"Qwen3 GGUF not present at {_QWEN3_GGUF}; run download_models.py",
)


def test_determinism_identify_call_roles():
    """Test that identify-call-roles produces identical output on repeated runs."""
    
    # Load skill
    skill_name = "identify-call-roles"
    bundle = load_skill(skill_name)
    
    # Sample input
    input_text = """SPEAKER_A: Thank you for calling XYZ Support. How can I help you?
SPEAKER_B: Hi, I need help with my order."""
    
    # Run twice
    output1 = run_skill(bundle, input_text)
    output2 = run_skill(bundle, input_text)
    
    # Assert exact match
    assert output1 == output2, (
        f"Outputs differ!\n"
        f"First run:\n{output1}\n\n"
        f"Second run:\n{output2}"
    )
    
    print(f"✓ Determinism test passed for {skill_name}")
    print(f"  Output length: {len(output1)} chars")
    print(f"  Outputs are byte-identical")


def test_determinism_from_cli():
    """Test determinism using the CLI runner."""
    import subprocess
    import tempfile
    
    # Create temp input file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("SPEAKER_A: Hello, customer service.\nSPEAKER_B: I need help.")
        temp_file = f.name
    
    runner_path = Path(__file__).parent.parent / "runner" / "run_skill.py"
    
    # Run twice via CLI
    result1 = subprocess.run(
        ["python", str(runner_path), "--skill", "identify-call-roles", "--file", temp_file],
        capture_output=True,
        text=True
    )
    
    result2 = subprocess.run(
        ["python", str(runner_path), "--skill", "identify-call-roles", "--file", temp_file],
        capture_output=True,
        text=True
    )
    
    # Clean up
    Path(temp_file).unlink()
    
    # Check both succeeded
    assert result1.returncode == 0, f"First run failed: {result1.stderr}"
    assert result2.returncode == 0, f"Second run failed: {result2.stderr}"
    
    # Assert outputs match
    assert result1.stdout == result2.stdout, (
        f"CLI outputs differ!\n"
        f"First:\n{result1.stdout}\n\n"
        f"Second:\n{result2.stdout}"
    )
    
    print("✓ CLI determinism test passed")


if __name__ == "__main__":
    print("Running determinism tests...\n")
    
    try:
        test_determinism_identify_call_roles()
        print()
        test_determinism_from_cli()
        print("\n✓ All determinism tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
