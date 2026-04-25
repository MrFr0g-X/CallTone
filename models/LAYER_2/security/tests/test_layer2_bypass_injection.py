"""Regression tests for transcript-bypass prompt injection defense."""

import sys
from pathlib import Path

import pytest


MODELS_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "skill_implementation"))
SCRIPTS_DIR = MODELS_DIR.parent / "scripts" / "security"
sys.path.insert(0, str(SCRIPTS_DIR))

from layer2_injection_bypass_probe import build_attack_payload  # noqa: E402
from LAYER_2.pipeline import InjectionBlockedError, run_layer2_pipeline  # noqa: E402


def test_layer2_blocks_injected_transcript_before_context_or_llm(tmp_path):
    """Critical transcript injection must block even when Layer 1 is skipped."""
    output_path = tmp_path / "layer2_ratings.json"

    with pytest.raises(InjectionBlockedError) as exc_info:
        run_layer2_pipeline(
            layer1_dict=build_attack_payload(),
            company_name="BankServ Global",
            output_path=str(output_path),
            injection_scan_mode="static",
        )

    scan_result = exc_info.value.scan_result
    assert scan_result.is_blocked()
    assert scan_result.severity == "critical"
    assert scan_result.recommended_action == "block"
    match_names = set(scan_result.to_dict()["static_match_names"])
    assert {
        "score_override_pre_qualifier",
        "score_to_this_agent",
    } & match_names
    assert not output_path.exists(), "Blocked calls must not produce QA ratings."
