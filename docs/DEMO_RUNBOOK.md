# CallTone — Demo Runbook (laptop UI + Vast GPU)

Five commands from cold to "open the browser and upload a call."

## Prereqs (one-time)

- Vast.ai instance running, SSH-reachable. You have its port + IP.
- Rotated `HF_TOKEN` with read access to the gated `pyannote/*` repos.
  (The one you pasted into chat earlier **must be revoked** — it's
  public now.)
- Local conda env `calltone` with backend deps; `node` + `npm` on PATH.
- The git remote is pushed to the Vast side (setup script does `git pull`).

## 1. Bootstrap Tier 3 (Vast GPU)

```bash
# On your laptop — SSH in.
ssh -p 44049 root@185.65.93.114

# On the Vast box.
cd /opt/calltone 2>/dev/null || git clone <your-repo-url> /opt/calltone
cd /opt/calltone
export HF_TOKEN=<your rotated token>
bash model_server/setup_vast_instance.sh
```

The script runs for ~20 min the first time (pip installs + model downloads).
At the end it prints:

```
[setup_vast] generated new MODEL_SERVER_TOKEN — copy this to the backend:
<64-char hex string>
```

**Copy that hex string.** You'll paste it into `.env.demo` on your laptop
in step 3.

Sanity: `curl -sf http://127.0.0.1:8080/v1/health | jq` should return
`{"ok": true, "gpu_available": true, ...}`. Exit the SSH session — the
systemd unit keeps running.

## 2. Open the SSH tunnel (laptop)

Open a **new terminal** and keep it running for the whole demo:

```bash
ssh -L 8090:localhost:8080 -p 44049 root@185.65.93.114
```

This forwards your laptop's `127.0.0.1:8090` to Vast's `127.0.0.1:8080`.
We use `:8090` locally so it doesn't collide with the UI dev server on
`:8080`. Leave the session open — closing it kills the tunnel.

## 3. Configure the laptop-side env

```bash
cd "D:\Zewail_DC\YEAR_4\GRADUATION PROJECT\PART 2\grad-project-main"
copy .env.demo.example .env.demo
# Edit .env.demo — paste the MODEL_SERVER_TOKEN from step 1.
```

## 4. Launch backend + frontend

```cmd
run_demo.bat
```

This wrapper:
1. Loads `MODEL_SERVER_URL` + `MODEL_SERVER_TOKEN` from `.env.demo`.
2. Probes `http://127.0.0.1:8090/v1/health` (fast-fail if the tunnel is down).
3. Delegates to `run_local.bat` which starts:
   - Backend at `http://localhost:8000`
   - Frontend at `http://localhost:8080`

Two new terminal windows appear — keep them open.

## 5. Go / no-go check

```cmd
python scripts\demo_ready.py
```

A successful run ends with:

```
GO. Open:
    http://127.0.0.1:8080
```

If any row shows `[FAIL]`, the script prints the exact fix.

## 6. Test from the UI

1. Open `http://localhost:8080` in Chrome/Firefox.
2. Log in as `admin@calltone.ai` / `Admin123!` (seed user).
3. **Calls → Upload** → pick a sample WAV/MP3 (try
   `Test_audio/bad_cs.mp3` from this repo).
4. Watch the status column transition:
   `queued` → `transcribing` → `scoring` → `completed` (≈ 3 min).
5. Click the call row to see scores, evidence quotes, and severity.

## Tearing it down

- Stop the backend/frontend: `run_local.bat --stop`
- Close the SSH tunnel terminal (Ctrl-C).
- Stop Vast from its dashboard to halt billing.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Tier 3 /v1/health [FAIL]` | Tunnel terminal died. Re-open it. |
| `Tier 3 auth [FAIL]` with HTTP 401 | `MODEL_SERVER_TOKEN` in `.env.demo` ≠ value on Vast. `grep MODEL_SERVER_TOKEN /opt/calltone/model_server/.env` on Vast, copy again. |
| `Tier 3 auth [FAIL]` with HTTP 403 | `ALLOWED_IPS` on Vast doesn't include `127.0.0.1`. Edit `/opt/calltone/model_server/.env`, `systemctl restart calltone-model`. |
| UI status stuck at `queued` | Backend never reached model server. Check the backend terminal for `ModelServerError`. |
| UI status flips to `failed` with `pipeline exited with code 1` | Check `journalctl -u calltone-model -n 100` on Vast — usually a missing model weight or CUDA OOM. |
| Slow first upload (~3 min) | Expected — first run loads the 8 GB Llama model into VRAM. Subsequent runs reuse the cache. |

## What "done" looks like

- Run `python scripts\demo_ready.py` at any point during the demo — it
  always gives you a current GO/NO-GO. Use it before showing a supervisor.
- If Tier 3 is down but Tier 2 is up, the backend still runs the local
  pipeline (if models are present) or writes a clear error to the Call
  record. The UI never 500s.
