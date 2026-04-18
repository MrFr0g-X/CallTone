import io


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_upload_rejects_non_audio_content_type(client, qa_token):
    files = {
        "file": (
            "evil.exe",
            io.BytesIO(b"MZ\x90\x00"),
            "application/x-msdownload",
        )
    }
    r = client.post("/api/calls/upload", files=files, headers=_auth(qa_token))
    assert r.status_code in (400, 415, 422)


def test_pipeline_settings_admin_only(client, admin_token, agent_token):
    r1 = client.get("/api/settings/pipeline", headers=_auth(admin_token))
    assert r1.status_code == 200
    r2 = client.put(
        "/api/settings/pipeline",
        json={
            "audioMode": "denoise",
            "injectionScan": "static",
            "reportMode": "simple",
            "useConsensus": False,
            "companyName": "BankServ Global",
        },
        headers=_auth(agent_token),
    )
    assert r2.status_code in (401, 403)


def test_status_polling_unknown_call_returns_404(client, qa_token):
    r = client.get(
        "/api/calls/00000000-0000-0000-0000-000000000000/status",
        headers=_auth(qa_token),
    )
    assert r.status_code == 404
