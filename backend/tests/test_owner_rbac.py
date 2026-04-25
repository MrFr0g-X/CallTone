import secrets

from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(email: str, role_name: str, password: str = "OwnerTest123!") -> int:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        assert role is not None, f"Missing role {role_name}"
        user = User(
            full_name=f"{role.display_name} Test User",
            email=email,
            password_hash=hash_password(password),
            role_id=role.id,
            client_id=None,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _login(client, email: str, password: str = "OwnerTest123!") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_owner_can_invite_super_admin(client):
    owner_email = f"owner_invite_{secrets.token_hex(4)}@calltone.ai"
    _create_user(owner_email, "owner")
    owner_token = _login(client, owner_email)

    invite_email = f"new_super_{secrets.token_hex(4)}@calltone.ai"
    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(owner_token),
        json={"name": "Promoted Super Admin", "email": invite_email, "role": "super_admin"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "super_admin"


def test_super_admin_cannot_invite_super_admin(client, admin_token):
    invite_email = f"blocked_super_{secrets.token_hex(4)}@calltone.ai"
    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(admin_token),
        json={"name": "Blocked Super Admin", "email": invite_email, "role": "super_admin"},
    )

    assert response.status_code == 400, response.text
    assert "Allowed roles" in response.json()["detail"]


def test_super_admin_cannot_mutate_owner(client, admin_token):
    owner_email = f"protected_owner_{secrets.token_hex(4)}@calltone.ai"
    owner_id = _create_user(owner_email, "owner")

    role_response = client.patch(
        f"/api/admin/users/{owner_id}/role",
        headers=_auth(admin_token),
        json={"role": "admin"},
    )
    assert role_response.status_code == 403, role_response.text

    status_response = client.patch(
        f"/api/admin/users/{owner_id}/status",
        headers=_auth(admin_token),
        json={"status": "disabled"},
    )
    assert status_response.status_code == 403, status_response.text

    delete_response = client.delete(
        f"/api/admin/users/{owner_id}",
        headers=_auth(admin_token),
    )
    assert delete_response.status_code == 403, delete_response.text


def test_owner_can_demote_and_delete_super_admin(client):
    owner_email = f"owner_mutate_{secrets.token_hex(4)}@calltone.ai"
    _create_user(owner_email, "owner")
    owner_token = _login(client, owner_email)

    target_email = f"temp_super_{secrets.token_hex(4)}@calltone.ai"
    target_id = _create_user(target_email, "super_admin")

    role_response = client.patch(
        f"/api/admin/users/{target_id}/role",
        headers=_auth(owner_token),
        json={"role": "admin"},
    )
    assert role_response.status_code == 200, role_response.text
    assert role_response.json()["user"]["role"] == "admin"

    delete_response = client.delete(
        f"/api/admin/users/{target_id}",
        headers=_auth(owner_token),
    )
    assert delete_response.status_code == 200, delete_response.text
