"""Invite-flow happy-path test (audit action item A-01).

Covers:
  admin invites a teammate → token returned →
  GET /auth/invite/{token} reveals the invited user →
  POST /auth/invite/accept activates the account →
  the new user can log in with the chosen password.
"""

import secrets

from app.database import SessionLocal
from app.models import Employee, User


def test_admin_can_invite_qa_who_then_logs_in(client, admin_token):
    new_email = f"inviteflow_{secrets.token_hex(4)}@calltone.ai"

    # 1. Admin sends invite
    invite = client.post(
        "/api/admin/users/invite",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Invite Flow QA", "email": new_email, "role": "qa"},
    )
    assert invite.status_code == 200, invite.text
    body = invite.json()
    assert "inviteUrl" in body
    token = body["inviteUrl"].rsplit("token=", 1)[-1]
    assert token, "invite URL did not contain a token"

    # 2. Public invite-details endpoint resolves the token
    details = client.get(f"/api/auth/invite/{token}")
    assert details.status_code == 200, (
        f"GET /auth/invite/{{token}} returned {details.status_code}; "
        f"inviteUrl was {body['inviteUrl']!r}; extracted token {token!r}"
    )
    assert details.json()["email"] == new_email
    assert details.json()["role"] == "qa"

    # 3. Accept invite with a password
    accept = client.post(
        "/api/auth/invite/accept",
        json={
            "token": token,
            "password": "InvitePass123!",
            "confirmPassword": "InvitePass123!",
        },
    )
    assert accept.status_code == 200, accept.text

    # 4. The new user can now log in
    login = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "InvitePass123!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == "qa"


def test_invite_token_cannot_be_reused(client, admin_token):
    """Once an invite is accepted, the token must be invalidated."""
    new_email = f"reuse_{secrets.token_hex(4)}@calltone.ai"

    invite = client.post(
        "/api/admin/users/invite",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Reuse Test", "email": new_email, "role": "agent"},
    )
    token = invite.json()["inviteUrl"].rsplit("token=", 1)[-1]

    # First accept succeeds
    first = client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": "FirstPass123!", "confirmPassword": "FirstPass123!"},
    )
    assert first.status_code == 200

    # Second accept must fail (404 — token was cleared)
    second = client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": "OtherPass123!", "confirmPassword": "OtherPass123!"},
    )
    assert second.status_code == 404


def test_invite_requires_admin_role(client, qa_token):
    """A QA user must not be able to invite teammates."""
    r = client.post(
        "/api/admin/users/invite",
        headers={"Authorization": f"Bearer {qa_token}"},
        json={"name": "Should Fail", "email": "fail@calltone.ai", "role": "agent"},
    )
    assert r.status_code == 403


def test_delete_user_detaches_employee_link(client, admin_token):
    """Deleting a user must preserve employee/call history by unlinking Employee.user_id."""
    new_email = f"delete_linked_{secrets.token_hex(4)}@calltone.ai"

    invite = client.post(
        "/api/admin/users/invite",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Linked Agent", "email": new_email, "role": "agent"},
    )
    assert invite.status_code == 200, invite.text
    user_id = invite.json()["user"]["id"]

    db = SessionLocal()
    try:
        employee = Employee(
            employee_code=f"DEL-{secrets.token_hex(3)}",
            full_name="Linked Agent",
            role="AGENT",
            user_id=user_id,
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        employee_id = employee.id
    finally:
        db.close()

    delete_response = client.delete(
        f"/api/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["deletedType"] == "invitation"

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == user_id).first() is None
        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        assert employee is not None
        assert employee.user_id is None
    finally:
        db.close()
