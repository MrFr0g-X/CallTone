"""Pytest fixtures for the CallTone backend.

The strategy: patch ``app.database.engine`` and ``app.database.SessionLocal``
to point at a throwaway SQLite file BEFORE ``app.main`` is imported, so the
dev database (``backend/calltone.db``) is never touched by tests.
"""

import os
import sys
import tempfile
from pathlib import Path

# Force SQLite mode and a deterministic test secret BEFORE importing app
os.environ["DB_HOST"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

# Make ``app`` importable as a top-level package
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

# Create a temp DB file dedicated to the test session
_TMP_DB = tempfile.NamedTemporaryFile(suffix="_calltone_test.db", delete=False)
_TMP_DB.close()
_TEST_DB_PATH = _TMP_DB.name

# Patch the database module's engine + SessionLocal to the temp DB
import app.database as _db  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_test_engine = create_engine(
    f"sqlite:///{_TEST_DB_PATH}",
    future=True,
    connect_args={"check_same_thread": False},
)
_db.engine = _test_engine
_db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Now import the rest (they will pick up the patched engine)
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base  # noqa: E402
from app.seed_data import main as seed_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    Base.metadata.drop_all(bind=_test_engine)
    Base.metadata.create_all(bind=_test_engine)
    seed_database()
    yield
    try:
        os.unlink(_TEST_DB_PATH)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Stop test N's login attempts from poisoning test N+1.

    The rate-limit buckets are module-level state that survives between
    tests, so a test file that exercises /auth/login many times can
    exhaust the limit and 429 the next file's admin_token fixture.
    Resetting before each test keeps every test starting from a clean
    bucket without weakening the limiter behavior under test (each test
    that cares about the limiter resets it again explicitly).
    """
    from app.rate_limit import login_limiter, invite_accept_limiter
    login_limiter.reset()
    invite_accept_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_token(client):
    return _login(client, "admin@calltone.ai", "Admin123!")


@pytest.fixture
def qa_token(client):
    return _login(client, "qa@calltone.ai", "Qa123456!")


@pytest.fixture
def agent_token(client):
    return _login(client, "agent1@calltone.ai", "Agent123!")
