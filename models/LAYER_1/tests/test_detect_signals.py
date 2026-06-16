"""Tests for the sparse, intent-only behavioural signal detector (Task D1).

These run GPU-free: ``detect_signals`` is pure regex and the module's heavy ML
imports (torch / pyannote / faster-whisper) are guarded so it imports without a
model environment.
"""

import importlib.util
import sys
from pathlib import Path

# NOTE on the import path: ``models/LAYER_1/`` contains BOTH a ``pipeline.py``
# module and a ``pipeline/`` directory. The file shadows the directory, so
# ``from LAYER_1.pipeline.transcribe_diarize import detect_signals`` (as written
# in the plan) resolves ``LAYER_1.pipeline`` to the .py file and fails. We load
# the real module from its file path instead — still GPU-free, since the module's
# heavy ML imports (torch / pyannote / faster-whisper) are guarded.
_TD_PATH = Path(__file__).resolve().parents[1] / "pipeline" / "transcribe_diarize.py"
_spec = importlib.util.spec_from_file_location("layer1_transcribe_diarize", _TD_PATH)
_td = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _td
_spec.loader.exec_module(_td)
detect_signals = _td.detect_signals


def test_plain_greeting_has_no_signals():
    assert detect_signals(
        "Thank you for calling MetroBoost. This is Shalene. How can I help you today?"
    ) == []


def test_single_question_mark_is_not_questioning():
    assert "QUESTIONING" not in detect_signals("Can you help me?")


def test_routine_question_has_no_signals():
    assert detect_signals("Could you confirm your account number, please?") == []


def test_strong_frustration_detected():
    assert "FRUSTRATED" in detect_signals(
        "This is absolutely ridiculous and unacceptable, the worst service ever."
    )


def test_escalation_detected():
    assert "ESCALATION" in detect_signals(
        "I want to speak to your manager and file a complaint."
    )


def test_apology_detected():
    assert "APOLOGETIC" in detect_signals("I'm so sorry, I sincerely apologize for the delay.")


def test_plain_thanks_is_not_satisfied():
    # "great" / bare "thanks" used to over-tag SATISFIED; that signal is gone.
    assert detect_signals("Great, thanks!") == []
