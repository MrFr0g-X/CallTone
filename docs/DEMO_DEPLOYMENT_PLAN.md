# CallTone — Demo Deployment Plan (two-server, on-demand GPU)

> Companion to `DEMO_DEPLOYMENT_STUDY.md`. This document is the *how*;
> the study is the *why*. Every step D-N here is the implementation of
> the identically-numbered decision in the study.
>
> **Author:** NasrEldin (Nanonumous) · **Operator:** Hothifa
>
> **Target state:** `https://calltone.tech` serves the SPA,
> `https://api.calltone.tech` serves the backend, the backend forwards
> pipeline jobs to a Vast.ai RTX 4090 instance that is booted on demand
> and destroyed after each demo session.

## 0. Scope

| Dimension             | In                                          | Out                               |
| --------------------- | ------------------------------------------- | --------------------------------- |
| Environments          | single "demo" env                           | staging, canary, multi-region     |
| GPU                   | 1 × Vast.ai RTX 4090 on demand              | persistent GPU, GPU pool          |
| Audio store           | local disk on Tier 2 (uploads/)             | S3/R2, CDN                        |
| Model server          | FastAPI wrapping `models/run_full_pipeline` | Triton, vLLM, TGI                 |
| Database              | Postgres on Tier 2                          | managed Postgres, read replicas   |
| Observability         | JSON logs + `/health/detailed`              | Prometheus, Grafana, alerting     |

## 1. Controls catalogue (mapped to study)

| ID   | Control                                             | File(s) touched                                       | Study §   |
| ---- | --------------------------------------------------- | ----------------------------------------------------- | --------- |
| D-1  | Architecture study committed                        | `docs/DEMO_DEPLOYMENT_STUDY.md`                       | all       |
| D-2  | This plan committed                                 | `docs/DEMO_DEPLOYMENT_PLAN.md`                        | all       |
| D-3  | `model_server/` package skeleton                    | `model_server/{main.py,requirements.txt,README.md,Dockerfile,.env.example}` | §2.3, §3 |
| D-4  | `/v1/analyze` + `/v1/jobs/{id}` endpoints           | `model_server/main.py`, `model_server/jobs.py`        | §3, §4    |
| D-5  | Shared bearer-token auth                            | `model_server/auth.py`                                | §5        |
| D-6  | `backend/app/model_client.py`                       | `backend/app/model_client.py`                         | §3        |
| D-7  | Wire backend upload → model server                  | `backend/app/main.py` (upload + worker subproc)       | §3, §6    |
| D-8  | `setup_vast_instance.sh` — idempotent bootstrap     | `model_server/setup_vast_instance.sh`                 | §2.3, §6  |
| D-9  | Tests (mocked pipeline) + httpx-mock client tests   | `model_server/tests/`, `backend/tests/test_model_client.py` | §6    |
| D-10 | Verify + commit                                     | —                                                     | all       |

## 2. Per-step implementation

### D-3. `model_server/` skeleton

Create a new top-level package `model_server/` that is *completely
separate* from `backend/app/`. Layout:

```
model_server/
  __init__.py
  main.py              # FastAPI app + lifespan
  jobs.py              # in-memory job store (UUID -> JobState)
  pipeline_adapter.py  # calls models/run_full_pipeline on a worker thread
  auth.py              # bearer token + IP allowlist middleware
  requirements.txt     # pinned deps (fastapi, httpx, python-multipart, llama-cpp-python[cuda], …)
  .env.example         # MODEL_SERVER_TOKEN, HF_TOKEN, ALLOWED_IPS, CUDA_VISIBLE_DEVICES
  Dockerfile           # nvidia/cuda:12.1.1-runtime-ubuntu22.04 base
  setup_vast_instance.sh  # the bootstrap script (D-8)
  README.md            # the 30-minute boot runbook
  tests/
    conftest.py
    test_auth.py
    test_analyze.py    # pipeline is mocked
```

**Why a new package instead of merging into `backend/`?** Deploy
target is different (GPU VM vs app server), dependency set is
different (`llama-cpp-python[cuda]`, `torch+cu121`, `pyannote.audio`,
`funasr`, `resemble-enhance` vs `fastapi`, `sqlalchemy`, `passlib`),
and the security surface is different (internal API vs internet-facing
with JWT + RBAC). Keeping them physically separate lets us ship much
smaller Docker images for each.

### D-4. `/v1/analyze` + `/v1/jobs/{id}`

**Endpoints**:

```
GET  /v1/health                     → {ok, gpu_available, model_cache_warm}
POST /v1/analyze                    → multipart audio → {job_id, eta_seconds}
GET  /v1/jobs/{job_id}              → {status, step, progress_pct, error?, result?}
GET  /v1/jobs/{job_id}/result       → full QA report JSON (only when done)
```

**Status machine**: `queued → denoising → diarising → transcribing →
role_ident → emotion → scoring → rendering → done | failed`.

**Concurrency model**: single-threaded pipeline. `POST /v1/analyze`
rejects with 409 if a job is already in-flight (GPU can do one thing
at a time). In-memory dict keyed by `job_id` (UUIDv4). Old jobs
garbage-collected after 5 minutes.

**Pipeline dispatch**: use `asyncio.to_thread` to run the blocking
`run_full_pipeline.*` calls off the event loop. The async endpoint
returns immediately; the thread updates the job state as it
progresses.

### D-5. Shared bearer-token auth + IP allowlist

`model_server/auth.py` adds a middleware:

```python
# Pseudocode
if request.url.path == "/v1/health":
    return await call_next(request)
if request.client.host not in ALLOWED_IPS:
    return Response(status_code=403)
if request.headers.get("Authorization") != f"Bearer {MODEL_SERVER_TOKEN}":
    return Response(status_code=401)
return await call_next(request)
```

- `MODEL_SERVER_TOKEN` ← `openssl rand -hex 32`, set at bootstrap time.
- `ALLOWED_IPS` ← `91.99.208.254` (the app server). Comma-separated.
- Health is public so Vast's own probes can hit it.

### D-6. `backend/app/model_client.py`

Thin `httpx.AsyncClient` wrapper:

```python
# Public surface, ~80 LOC total
async def submit(audio_bytes, filename, company=None) -> str:  # returns job_id
async def poll(job_id) -> dict                                 # returns {status, step, …}
async def fetch_result(job_id) -> dict                         # returns QA report JSON
```

- Bearer auth via `MODEL_SERVER_TOKEN` env var on the backend side.
- `MODEL_SERVER_URL` env var controls the base URL.
- Timeouts: `connect=10s, read=600s` (full pipeline can take 3 min +
  cold-start).
- Retries: 3× on connection errors with exponential backoff (1s, 2s,
  4s); no retry on 4xx/5xx bodies (those indicate real failures).

### D-7. Wire backend upload → model server

The existing `upload_call` route in `backend/app/main.py:1278` already
spawns a subprocess via `multiprocessing.get_context("spawn")` to run
`_run_pipeline(call_id, dest)`. The only change is inside
`_run_pipeline`:

```python
# Pseudocode
if os.environ.get("MODEL_SERVER_URL"):
    _run_remote_pipeline(call_id, dest)     # NEW — forwards to Tier 3
else:
    _run_local_pipeline(call_id, dest)      # existing behaviour
```

`_run_remote_pipeline` uses `model_client` to submit + poll, and
writes `current_step`, transcript, and QA report back to Postgres
exactly as the local worker does. The DB schema and the
`/api/calls/{id}/status` polling contract do not change.

**Key property**: when `MODEL_SERVER_URL` is *unset*, behaviour is
identical to today. This means deploying the remote path is a
feature flag, not a breaking change.

### D-8. `setup_vast_instance.sh`

Idempotent bash script; the operator runs it once after SSH-ing into
a fresh Vast instance. Responsibilities:

1. `unset HISTFILE` and `set -euo pipefail`
2. Ensure CUDA toolkit + Python 3.10 are present (Vast images usually
   have both; check and fail loudly if not)
3. `git clone https://github.com/MrFr0g-X/CallTone.git /root/calltone`
4. `cd /root/calltone/PART\ 2/grad-project-main`
5. `pip install -r model_server/requirements.txt` (with pip cache)
6. `python download_models.py --hf-token "$HF_TOKEN"` (idempotent;
   skips what's already downloaded)
7. Pre-warm by running a 5-second canned audio through the pipeline
   (`assets/warmup.wav`) to force CUDA init + mmap load
8. Generate `MODEL_SERVER_TOKEN` if not provided via env var, print it
9. `systemd-run --unit model-server --scope python -m uvicorn
   model_server.main:app --host 0.0.0.0 --port 8000` (keeps running
   even after SSH session closes)
10. Print the final status block:

```
========================================================================
MODEL SERVER READY

URL:     http://<instance_public_ip>:8000
Token:   <generated_token>
Health:  http://<instance_public_ip>:8000/v1/health
========================================================================

Copy these into the app server's .env:
  MODEL_SERVER_URL=http://<instance_public_ip>:8000
  MODEL_SERVER_TOKEN=<generated_token>

Then restart:  systemctl restart calltone-backend
========================================================================
```

### D-9. Tests

**`model_server/tests/`**: unit tests for auth middleware (401/403
paths), for the job state machine (status transitions), and for
`/v1/analyze` with a *mocked* pipeline so the tests don't need a GPU or
13 GB of model weights.

**`backend/tests/test_model_client.py`**: uses `respx` or `httpx.MockTransport`
to assert:
- submit posts multipart + bearer header
- poll returns parsed JSON
- fetch_result returns the report dict
- 3× retry on connection error, then raises
- No retry on 401/500 (those are real failures)

**Coverage target for new code**: ≥80%.

### D-10. Verify + commit

Two verification passes (same pattern as SEC work):

- **Pass #1**: full pytest suite (backend + model_server); bandit; boot
  backend locally with `MODEL_SERVER_URL` pointing at a stubbed server
  and confirm end-to-end (submit → poll → result) works; confirm that
  unsetting `MODEL_SERVER_URL` still runs the local subprocess
  pipeline; confirm `/api/health/detailed` still green.
- **Pass #2**: re-read diff; re-run full suite; run `model_server`
  unit tests in isolation; confirm no regressions in the 40 existing
  backend tests.

Commit as Nanonumous; push; watch CI.

## 3. Build sequence (ordering)

```
D-1 ─┐
     ├─→ D-3 ─→ D-5 ─┐
D-2 ─┘             ├─→ D-4 ─→ D-8 ─┐
                   │                ├─→ D-9 ─→ D-10
               D-6 ┴─→ D-7 ────────┘
```

D-1 and D-2 are pure docs and can happen in parallel. D-3 (skeleton)
must exist before D-4/D-5 touch real files. D-6 and D-7 happen on the
backend side in parallel with D-4/D-5 on the model-server side because
they live in different packages. D-8 builds on a complete D-4+D-5.
D-9 tests everything, D-10 commits.

## 4. Test plan

| Test                                              | Layer          | What it proves                                    |
| ------------------------------------------------- | -------------- | ------------------------------------------------- |
| `test_auth.py::test_missing_token_returns_401`    | model_server   | Middleware rejects unauthenticated requests       |
| `test_auth.py::test_wrong_ip_returns_403`         | model_server   | IP allowlist enforces private callers             |
| `test_auth.py::test_health_is_public`             | model_server   | Vast probes don't need a token                    |
| `test_analyze.py::test_submit_returns_job_id`     | model_server   | `/v1/analyze` happy path (pipeline mocked)        |
| `test_analyze.py::test_concurrent_rejected_409`   | model_server   | Single-worker constraint enforced                 |
| `test_analyze.py::test_jobs_poll_progress`        | model_server   | Status machine transitions are exposed            |
| `test_analyze.py::test_job_not_found_404`         | model_server   | Wrong UUID → 404                                  |
| `test_model_client.py::test_submit_sends_bearer`  | backend        | httpx request has the Authorization header       |
| `test_model_client.py::test_retries_on_conn_err`  | backend        | 3× backoff on connection error                   |
| `test_model_client.py::test_no_retry_on_401`      | backend        | 401 short-circuits — don't hammer                |
| `test_model_client.py::test_poll_parses_status`   | backend        | JSON parsing round-trip                           |
| `test_upload_remote.py::test_upload_uses_remote`  | backend        | When `MODEL_SERVER_URL` set, client is called     |
| `test_upload_remote.py::test_upload_local_fallback`| backend       | When unset, local subprocess is spawned           |

All 40 existing backend tests must remain green.

## 5. Verification rituals

### Pass #1 — functional

1. `cd backend && pytest tests/ -v` — all 40 + new tests green
2. `cd model_server && pytest tests/ -v` — all new tests green
3. `python -m bandit -r model_server/ backend/app/ -ll` — 0 medium/high
4. Boot a stubbed model server (the tests fixture exports it):
   ```bash
   cd model_server && MODEL_SERVER_TOKEN=test python -m uvicorn stubs.main:app --port 9001 &
   ```
5. Boot backend with `MODEL_SERVER_URL=http://127.0.0.1:9001`
   `MODEL_SERVER_TOKEN=test`
6. Upload a tiny WAV, poll status, confirm the stub's fake report
   flows back into `/api/calls/{id}/report`
7. Kill the stub, unset env var, re-run same upload → confirm local
   fallback works (existing subprocess path)

### Pass #2 — regression + security

1. Re-read `git diff` top-to-bottom
2. `pytest backend/tests/ -q` → 40+ passed
3. `pytest model_server/tests/ -q` → all passed
4. `bandit -r . -ll` → clean
5. `grep -rn 'hf_[A-Za-z0-9]\{20,\}' .` → no HF tokens in source
6. Confirm `.gitleaks.toml` still green against the new code

## 6. Rollback

| Change                                     | Rollback                                                              |
| ------------------------------------------ | --------------------------------------------------------------------- |
| `MODEL_SERVER_URL` misconfigured           | Unset the env var and restart — backend falls back to local subprocess |
| Model server refuses auth                  | Regenerate `MODEL_SERVER_TOKEN` on both sides; restart backend         |
| Bootstrap script fails mid-run             | Script is idempotent; re-run. If catastrophic, destroy + relaunch Vast instance |
| New code breaks existing backend tests     | `git revert` the integration commit (D-7); model_server code stays harmless when `MODEL_SERVER_URL` is unset |
| Model download fails due to HF token       | Rotate the HF token, re-export, re-run bootstrap |

## 7. The 30-minute boot runbook

Exactly what the operator does to go from "cold" to "demo-ready":

| Time    | Action                                                                 | Where          |
| ------- | ---------------------------------------------------------------------- | -------------- |
| T+0:00  | Start Vast.ai instance (RTX 4090 template, Ubuntu 22.04 + CUDA 12.1)   | Vast.ai UI     |
| T+2:00  | SSH: `ssh -p <port> root@<ip>`                                         | Laptop         |
| T+2:30  | `curl -fsSL https://raw.githubusercontent.com/MrFr0g-X/CallTone/feat/test-suite-and-evidence/PART%202/grad-project-main/model_server/setup_vast_instance.sh \| HF_TOKEN=<fresh_token> bash` | Vast instance  |
| T+3:00  | Script installs deps (~3 min), downloads models (~5 min), pre-warms    | Vast instance  |
| T+12:00 | Script prints URL + token. Copy both.                                  | Vast instance  |
| T+12:15 | SSH to app server: `ssh root@91.99.208.254`                            | Laptop         |
| T+12:30 | `echo "MODEL_SERVER_URL=http://<ip>:8000" >> /etc/calltone/backend.env` | App server     |
| T+12:40 | `echo "MODEL_SERVER_TOKEN=<token>" >> /etc/calltone/backend.env`       | App server     |
| T+12:50 | `systemctl restart calltone-backend`                                   | App server     |
| T+13:00 | Open https://calltone.tech in browser                                  | Laptop         |
| T+13:30 | Log in as qa@calltone.ai, upload `Test_audio/bad_cs.mp3`               | Browser        |
| T+16:30 | Report renders. Demo proceeds.                                         | Browser        |
| T+??    | After demo: Vast UI → instance → Destroy                               | Vast.ai UI     |

Target: ≤ 15 min cold, ≤ 5 min if the instance's disk snapshot is kept
warm (`Stop` rather than `Destroy`).

## 8. Secrets matrix

| Secret                  | Where stored                           | Rotation                                                      |
| ----------------------- | -------------------------------------- | ------------------------------------------------------------- |
| SSH private key         | Operator laptop, password-protected    | When laptop lost; public key on both servers                  |
| App server root password| Hetzner UI                             | After initial SSH-key install, disable password auth          |
| `SECRET_KEY` (JWT)      | `/etc/calltone/backend.env` (mode 600) | Annual or on compromise                                        |
| `MODEL_SERVER_TOKEN`    | `/etc/calltone/backend.env` + Vast env | **Per instance boot** (new token each time)                   |
| `HF_TOKEN`              | Vast.ai env-var UI only                | On leak (including any chat exposure); scope to pyannote only |
| Postgres password       | `/etc/calltone/backend.env`            | Every 90 days                                                  |
| Let's Encrypt priv key  | `/etc/letsencrypt/` (root-only)        | Automatic via certbot                                          |

**Never committed** to git: all of the above. `.gitleaks.toml` catches
accidental commits.

## 9. Pre-demo checklist

Run this 30 minutes before any supervisor session:

- [ ] `git status` on app server clean, branch is the expected one
- [ ] `systemctl status calltone-backend` → active
- [ ] `curl -sI https://api.calltone.tech/api/health` → 200 + security headers
- [ ] `curl -sI https://calltone.tech/` → 200 (Tier 1 responding)
- [ ] Vast.ai instance status → Running, GPU utilisation < 5%
- [ ] `curl -H "Authorization: Bearer $TOKEN" http://<ip>:8000/v1/health` → `{"ok":true,"model_cache_warm":true}`
- [ ] Test upload with `bad_cs.mp3` → report renders in ≤ 4 min
- [ ] Browser cache cleared before sharing screen

## 10. Out of scope for this plan

Same list as `DEMO_DEPLOYMENT_STUDY.md §8`. Explicitly deferred:

- TLS on the model server itself (using bearer + IP allowlist instead;
  Vast's public IPs are short-lived enough that a cert would expire
  between demos).
- Reverse tunnel (ngrok / cloudflared) — considered but discarded:
  adds a dep we can't debug and doesn't improve security when the
  allowlist is already one IP.
- Automatic Vast provisioning via their CLI — manual UI start is one
  click and avoids storing yet another credential.
- Horizontal scaling / queue workers — company-scale deployment only.

## 11. Bottom line

Ten implementation tasks (D-1…D-10), two new top-level packages
(`model_server/` + the minor `backend/app/model_client.py` addition),
zero breaking changes when the new env vars are unset, and a 15-minute
warm-boot from Vast instance start to a reviewer clicking "Upload".

All code paths are feature-flagged by `MODEL_SERVER_URL`. Every
credential is out-of-band and rotatable. Cost ceiling holds at
~$15/mo even with a warm snapshot kept between demos.
