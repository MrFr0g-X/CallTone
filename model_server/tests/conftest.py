"""Pytest fixtures for the model_server package.

The key fixture is ``client``: a ``TestClient`` that (a) sets a deterministic
``MODEL_SERVER_TOKEN`` and ``ALLOWED_IPS`` before the app is constructed,
and (b) rebuilds the app per-test so middleware picks up the env. This
mirrors the strategy we use in ``backend/tests/conftest.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make the repo root importable so ``model_server`` resolves without an install.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Deterministic auth config for every test module.
os.environ.setdefault("MODEL_SERVER_TOKEN", "test-token-not-for-production")
os.environ.setdefault("ALLOWED_IPS", "testclient,127.0.0.1")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['MODEL_SERVER_TOKEN']}"}


@pytest.fixture
def client() -> TestClient:
    # Import here so each test session reads the env set above.
    from model_server.main import create_app

    app = create_app()
    return TestClient(app)
