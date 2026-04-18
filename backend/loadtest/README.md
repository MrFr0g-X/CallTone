# Load testing CallTone

Locust scenarios for the read-side (auth, dashboard, call list/detail,
health). GPU-bound endpoints (upload, scoring) are excluded — they
need a different harness.

## Run

```bash
pip install locust   # already in backend/requirements.txt
uvicorn app.main:app --port 8000

# Interactive UI (recommended first run):
locust -f backend/loadtest/locustfile.py --host http://localhost:8000
# → http://localhost:8089

# Headless smoke test (60 s, 50 users):
locust -f backend/loadtest/locustfile.py \
    --host http://localhost:8000 \
    --headless -u 50 -r 5 -t 60s \
    --csv reports/load_smoke
```

## Targets

The MVP target documented in CLAUDE.md is "<5 minutes per 10-minute
call" for the *full pipeline*. The HTTP read-side targets we set
ourselves for the QA portal:

| Endpoint              | p95 target | Hard fail |
|-----------------------|-----------:|----------:|
| `/api/health`         |     50 ms  |   500 ms  |
| `/api/v1/auth/me`     |    150 ms  |   1000 ms |
| `/api/v1/qa/calls`    |    300 ms  |   2000 ms |
| `/api/v1/qa/calls/:id`|    400 ms  |   2000 ms |

## Credentials

Defaults to the seed user `qa@calltone.ai / QApass123!`. Override via
`LOAD_QA_EMAIL` / `LOAD_QA_PASSWORD` env vars before invoking locust.

## Output

`--csv reports/load_smoke` writes:

- `load_smoke_stats.csv` — per-endpoint p50/p95/p99
- `load_smoke_failures.csv` — error breakdown
- `load_smoke_history.csv` — time series (for graphs in the report)
