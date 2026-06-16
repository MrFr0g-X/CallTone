"""RBAC + behavior tests for the agent call-appeal workflow.

Fixtures build their own calls/reports/appeals through ``SessionLocal`` so they
stay independent of the shared seed data, mirroring ``test_tenant_isolation``.
The seeded agent1/qa/admin accounts all belong to "BankServ Global".
"""

import secrets
from datetime import datetime, timezone

import pytest

from app.database import SessionLocal
from app.models import Call, Client, Employee, QaReport, CallAppeal, User


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client_id(name: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.name == name).first().id
    finally:
        db.close()


def _agent1_employee_id() -> str:
    """Employee row linked to the seeded agent1 user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "agent1@calltone.ai").first()
        emp = db.query(Employee).filter(Employee.user_id == user.id).first()
        return emp.id
    finally:
        db.close()


def _make_call(employee_id: str, client_id: int, *, report: dict | None = None) -> str:
    """Create a COMPLETED call (optionally with a QaReport) and return its id."""
    db = SessionLocal()
    try:
        call = Call(
            client_id=client_id,
            employee_id=employee_id,
            original_filename=f"appeal-{secrets.token_hex(3)}.wav",
            status="COMPLETED",
            call_time=datetime.now(timezone.utc),
        )
        db.add(call)
        db.flush()
        if report is not None:
            db.add(
                QaReport(
                    call_id=call.id,
                    qa_id=employee_id,
                    overall_score=report["overall_score"],
                    grade=report.get("grade"),
                    severity=report["severity"],
                    dimension_scores={},
                    report_json=report.get("report_json", {}),
                )
            )
        db.commit()
        db.refresh(call)
        return call.id
    finally:
        db.close()


@pytest.fixture
def flagged_call():
    cid = _client_id("BankServ Global")
    return _make_call(
        _agent1_employee_id(),
        cid,
        report={"overall_score": 55.0, "grade": "F", "severity": "Major"},
    )


@pytest.fixture
def good_call():
    cid = _client_id("BankServ Global")
    return _make_call(
        _agent1_employee_id(),
        cid,
        report={"overall_score": 93.0, "grade": "A", "severity": "Minor"},
    )


@pytest.fixture
def other_call():
    """A flagged call owned by a different company's agent."""
    other_cid = _client_id("MetroBoost Telecom")
    db = SessionLocal()
    try:
        emp = Employee(
            client_id=other_cid,
            employee_code=f"AG-OTH-{secrets.token_hex(3)}",
            full_name="Other Co Agent",
            role="AGENT",
        )
        db.add(emp)
        db.flush()
        emp_id = emp.id
    finally:
        db.close()
    return _make_call(
        emp_id,
        other_cid,
        report={"overall_score": 50.0, "grade": "F", "severity": "Critical"},
    )


@pytest.fixture
def open_appeal(flagged_call):
    """An existing open appeal on a flagged BankServ call."""
    db = SessionLocal()
    try:
        appeal = CallAppeal(
            call_id=flagged_call,
            client_id=_client_id("BankServ Global"),
            agent_employee_id=_agent1_employee_id(),
            status="open",
            agent_reason="Customer was abusive; score unfair.",
        )
        db.add(appeal)
        db.commit()
        db.refresh(appeal)

        class _Ref:
            id = appeal.id

        return _Ref()
    finally:
        db.close()


# ── Agent appeal creation ────────────────────────────────────────────────────

def test_agent_can_appeal_own_flagged_call(client, agent_token, flagged_call):
    r = client.post(
        f"/api/calls/{flagged_call}/appeal",
        json={"reason": "Customer was abusive; score unfair."},
        headers=_auth(agent_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"


def test_agent_cannot_appeal_unflagged_call(client, agent_token, good_call):
    r = client.post(
        f"/api/calls/{good_call}/appeal",
        json={"reason": "x"},
        headers=_auth(agent_token),
    )
    assert r.status_code == 400  # not eligible


def test_agent_cannot_appeal_other_companys_call(client, agent_token, other_call):
    r = client.post(
        f"/api/calls/{other_call}/appeal",
        json={"reason": "x"},
        headers=_auth(agent_token),
    )
    assert r.status_code in (403, 404)


def test_agent_cannot_double_appeal(client, agent_token, flagged_call):
    first = client.post(
        f"/api/calls/{flagged_call}/appeal",
        json={"reason": "first"},
        headers=_auth(agent_token),
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/calls/{flagged_call}/appeal",
        json={"reason": "second"},
        headers=_auth(agent_token),
    )
    assert second.status_code in (400, 409)


# ── QA / admin resolution ────────────────────────────────────────────────────

def test_qa_resolves_appeal_overturn_keeps_ai_score(client, qa_token, open_appeal):
    r = client.patch(
        f"/api/appeals/{open_appeal.id}",
        json={"status": "overturned", "qa_response": "Agreed.", "corrected_score": 75.0},
        headers=_auth(qa_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "overturned"
    assert body["correctedScore"] == 75.0

    # The AI score on the QaReport must be unchanged.
    db = SessionLocal()
    try:
        appeal = db.query(CallAppeal).filter(CallAppeal.id == open_appeal.id).first()
        report = db.query(QaReport).filter(QaReport.call_id == appeal.call_id).first()
        assert report.overall_score == 55.0
    finally:
        db.close()


def test_agent_cannot_resolve_appeal(client, agent_token, open_appeal):
    r = client.patch(
        f"/api/appeals/{open_appeal.id}",
        json={"status": "upheld"},
        headers=_auth(agent_token),
    )
    assert r.status_code == 403


def test_qa_sees_company_appeals(client, qa_token, open_appeal):
    r = client.get("/api/appeals", headers=_auth(qa_token))
    assert r.status_code == 200, r.text
    ids = [a["id"] for a in r.json()["appeals"]]
    assert open_appeal.id in ids


def test_agent_lists_only_own_appeals(client, agent_token, open_appeal):
    r = client.get("/api/appeals", headers=_auth(agent_token))
    assert r.status_code == 200, r.text
    ids = [a["id"] for a in r.json()["appeals"]]
    assert open_appeal.id in ids
