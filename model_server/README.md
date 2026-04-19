# CallTone Model Server (Tier 3)

FastAPI service that runs the LAYER 1 → LAYER 2 → LAYER 3 pipeline on GPU.

- **Deploy target**: On-demand Vast.ai instance (RTX 4090, CUDA 12.1).
- **Client**: the Tier-2 backend (`api.calltone.tech`). No other callers.
- **Security**: bearer token (`MODEL_SERVER_TOKEN`) + IP allowlist
  (`ALLOWED_IPS`). `/v1/health` is public for platform probes only.

## Endpoints (planned — see `docs/DEMO_DEPLOYMENT_PLAN.md`)

| Method | Path                            | Purpose                                  |
|--------|---------------------------------|------------------------------------------|
| GET    | `/v1/health`                    | Liveness + GPU / cache probe (public)    |
| POST   | `/v1/analyze`                   | Multipart audio upload → `{job_id, ...}` |
| GET    | `/v1/jobs/{job_id}`             | Status, step, progress                   |
| GET    | `/v1/jobs/{job_id}/result`      | Full QA report (only when `status=done`) |

Concurrency: one job at a time. `/v1/analyze` returns 409 while busy.

## Local dev (no GPU, pipeline mocked)

```bash
cd "PART 2/grad-project-main"
pip install -r model_server/requirements.txt
export MODEL_SERVER_TOKEN=dev-token
export ALLOWED_IPS=127.0.0.1
uvicorn model_server.main:app --reload --port 8080
curl http://127.0.0.1:8080/v1/health
```

Unit tests mock `pipeline_adapter.run_pipeline_blocking` so you don't need
the ML stack on your laptop:

```bash
pytest model_server/tests/ -v
```

## 30-minute boot runbook (Vast)

Full walkthrough is in `docs/DEMO_DEPLOYMENT_PLAN.md` §7. Short form:

```bash
ssh -p 44049 root@185.65.93.114
git clone https://github.com/<owner>/grad-project.git /opt/calltone
cd /opt/calltone
bash model_server/setup_vast_instance.sh   # D-8 — builds once, ~25 min
# → prints MODEL_SERVER_TOKEN; copy to app server's .env
curl -H "Authorization: Bearer $MODEL_SERVER_TOKEN" \
     http://127.0.0.1:8080/v1/health
```

## Layout

```
model_server/
  __init__.py
  main.py              # FastAPI app + /v1/health
  auth.py              # bearer + IP allowlist middleware
  jobs.py              # in-memory job store (single-slot)
  pipeline_adapter.py  # subprocess wrapper around models/run_full_pipeline.py
  requirements.txt     # server deps (ml deps listed as comments)
  Dockerfile           # nvidia/cuda:12.1.1-runtime base
  .env.example         # all runtime knobs
  tests/
    conftest.py
    test_auth.py       # D-9
    test_analyze.py    # D-9 — pipeline mocked
```
