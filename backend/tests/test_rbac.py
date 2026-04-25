def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_dashboard_blocks_agent(client, agent_token):
    r = client.get("/api/admin/dashboard", headers=_auth(agent_token))
    assert r.status_code in (401, 403)


def test_admin_dashboard_allows_super_admin(client, admin_token):
    r = client.get("/api/admin/dashboard", headers=_auth(admin_token))
    assert r.status_code == 200


def test_qa_calls_visible_to_qa(client, qa_token):
    r = client.get("/api/qa/calls", headers=_auth(qa_token))
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict))
