def test_login_success(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@calltone.ai", "password": "Admin123!"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "super_admin"


def test_login_wrong_password_returns_401(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@calltone.ai", "password": "wrong"},
    )
    assert r.status_code == 401


def test_me_requires_valid_token(client, admin_token):
    r = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "admin@calltone.ai"
