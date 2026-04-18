# CallTone — Deployment Study

**Author:** Hothifa Hamdan (DSAI) · **Date:** 2026-04-18 · **Audience:** project supervisor + jury

This document is a comparative analysis of how CallTone could be deployed in
production. It is paired with `DEPLOYMENT_PLAN.md`, which commits to a
specific path and lays out the CI/CD pipeline and rollout.

---

## 1. What we are deploying

CallTone is a 3-layer system, not a single service. Any deployment story has
to cover all three plus the shared support surface:

| Component                       | Tech                              | GPU? | Stateful? |
|---------------------------------|-----------------------------------|------|-----------|
| **Frontend** (React/Vite SPA)   | Static bundle (HTML/CSS/JS)       | No   | No        |
| **Backend API** (FastAPI)       | Python 3.11, SQLAlchemy, JWT      | No   | Yes (DB)  |
| **LAYER 1** — audio pipeline    | resemble-enhance + pyannote + SenseVoice + Audio2Emotion | **Yes** | No (per-call) |
| **LAYER 2** — QA scorer (skill) | Llama 3.1 8B GGUF via llama-cpp   | **Yes** | No        |
| **LAYER 3** — LaTeX reporter    | Jinja2 templates                  | No   | No        |
| **Database**                    | SQLite (dev) / PostgreSQL (prod)  | No   | **Yes**   |
| **Object storage**              | Local FS (dev) / S3 / blob (prod) | No   | **Yes**   |

Total weight on disk: ≈ 12.5 GB of model weights (Llama 8 GB, SenseVoice
0.9 GB, Audio2Emotion 1.2 GB, pyannote 1.0 GB, resemble-enhance 0.7 GB).

Pipeline cost per 10-min call (measured on RTX 3060 6 GB):
`~3 min` enhancement + `~30 s` diarisation + `~20 s` transcription +
`~10 s` emotion + `~25 s` role ID + `~60 s` QA scoring ≈ **~5 min total**,
matching the MVP target in CLAUDE.md.

---

## 2. Constraints that drive the decision

1. **Single-tenant academic deployment.** This is a graduation project for
   one supervisor and one jury — not a multi-tenant SaaS. Ten thousand
   concurrent users is fiction; ten concurrent QA reviewers is realistic.
2. **GPU is the long pole.** Every option below either requires owning or
   renting an Nvidia GPU. CPU-only inference of Llama 8 B + SenseVoice is
   technically possible but would push the per-call latency from 5 min to
   30+ min — unusable.
3. **Privacy of call recordings.** Customer-service audio often contains
   PII. A self-hosted box keeps audio out of third-party clouds, which is
   what the supervisor and the original Fall-2025 brief asked for.
4. **Determinism contract.** The skill framework guarantees identical
   QA scores across runs (`temperature=0`, `seed=12345`). Any deployment
   that auto-scales across heterogeneous GPUs (different drivers / CUDA
   versions) risks breaking bit-exact reproducibility — relevant for
   appeal/audit workflows.
5. **Budget = 0 €.** No cloud spend. The team has access to two local
   GPUs (RTX 3060 6 GB and RTX 5060 Ti 16 GB).

---

## 3. Deployment options compared

### Option A — Single-box on-prem (recommended for v1)

```
┌──────────────────────────────────────────────────┐
│  RTX 5060 Ti box                                 │
│  ┌─────────────┐  ┌────────────────────────────┐ │
│  │ Nginx :443  │──│ uvicorn FastAPI :8000      │ │
│  └─────────────┘  │   ↳ /api/*  + /static/*    │ │
│                   │   ↳ pipeline workers       │ │
│                   └─────────┬──────────────────┘ │
│                             │ in-process import  │
│                             ▼                    │
│  ┌────────────────────────────────────────────┐  │
│  │  models/ on disk  (mounted in container)   │  │
│  └────────────────────────────────────────────┘  │
│  PostgreSQL :5432 ← persistent volume            │
│  /uploads ← persistent volume                    │
└──────────────────────────────────────────────────┘
```

| Pros | Cons |
|------|------|
| Cheapest path to v1 — uses existing hardware. | Single point of failure; box reboot = downtime. |
| Audio never leaves the LAN — privacy-friendly. | No horizontal scaling for concurrent calls. |
| Determinism preserved (one GPU, one driver). | Manual disaster recovery. |
| Already containerised (Dockerfile + compose).  | We own monitoring + backups. |

**Best for:** the supervisor demo, Spring-2026 defense, and a year-1
internal pilot inside one organisation. This is what `docker-compose.yml`
already targets.

### Option B — Split frontend (Vercel) + backend (on-prem GPU)

```
   Browser ─→ Vercel (static SPA) ─→ XHR to https://api.calltone.example
                                              │
                                              ▼
                                      Cloudflare Tunnel
                                              │
                                              ▼
                                      on-prem FastAPI + GPU
```

| Pros | Cons |
|------|------|
| CDN-cached frontend = sub-second TTI globally. | Two deploy pipelines to maintain. |
| Origin still owns audio + GPU.                | CORS / auth cookies need careful setup. |
| Free Vercel hobby tier covers this.            | Cloudflare tunnel adds a hop + latency. |

**Best for:** when the demo audience is geographically distant and the
on-prem box is on a residential ISP. Otherwise unnecessary complexity.

### Option C — Cloud GPU (RunPod / Lambda / vast.ai)

| Pros | Cons |
|------|------|
| Burstable — pay only when processing calls. | Audio leaves the LAN; PII concern. |
| No hardware to maintain.                     | $0.40–$1.20/hr for an A4000 / 4090 — fast burn rate. |
| Easy to spin up second box for HA.           | Cold start of an 8 GB GGUF model = 30–60 s. |

**Best for:** a future commercial pilot once revenue justifies cloud spend.
Not appropriate for the academic deliverable.

### Option D — Kubernetes cluster (over-engineering)

Microservices for layer-1 / layer-2 / API, autoscaling, GPU operator,
service mesh — explicitly **rejected** for this phase. It would consume
weeks of work and not move any rubric criterion. We may revisit if the
project transitions into a real-world deployment after defense.

---

## 4. Decision

**Adopt Option A (single-box on-prem) for v1.** The Dockerfile and
docker-compose.yml in the repo root are already aligned with this choice.
Migration to Option B is a 1-day swap if the demo room has poor network.

| Decision dimension     | Choice                                                |
|------------------------|-------------------------------------------------------|
| Compute                | Single Linux box, RTX 5060 Ti 16 GB                   |
| OS / runtime           | Ubuntu 22.04 + Docker 26 + nvidia-container-toolkit   |
| Reverse proxy + TLS    | Nginx in a sibling container, Let's Encrypt via certbot |
| Database               | PostgreSQL 16 (Docker volume)                          |
| Object storage         | Local volume `/var/lib/calltone/uploads`              |
| Secrets                | `.env` file outside the repo, mode 600                |
| Backups                | nightly `pg_dump` + rsync of `/uploads` to NAS        |
| Monitoring             | `/api/health/detailed` polled by a uptime-kuma side-car |
| Logging                | JSON to stdout → Docker `json-file` driver → log rotate |

---

## 5. Model deployment specifics

Models are the biggest deployment risk because they are **(a) big**, **(b)
gated** (pyannote needs HF_TOKEN), and **(c)** the slowest piece to
re-download.

### 5.1 Where weights live

- **Not inside the Docker image.** Building a 14 GB image would bloat
  every CI run and every push. The Dockerfile copies *code* only.
- **Mounted as read-only volumes** at `docker compose up`:
  - `./model-weights/LAYER_1/models/` → SenseVoice + pyannote
  - `./model-weights/skill_implementation/models/` → Llama GGUF
  - `./model-weights/LAYER_1/resemble-enhance/` → enhancer checkpoint
- **First-run helper**: `python download_models.py --hf-token $HF_TOKEN`
  populates the host directory; CI does not download weights.

### 5.2 Loading strategy

- **LAYER 1** loads diarisation and transcription models on first
  request, then keeps them resident. Ten-minute idle → unload (memory
  pressure on the 6 GB card). The 16 GB card keeps them resident
  permanently.
- **Llama via llama-cpp-python** loads the GGUF via mmap. Resident
  memory ≈ 2 GB + KV cache; the 8 GB weight file stays in page cache.
  First inference after boot ≈ 8 s warm-up; subsequent calls < 60 s
  for a full QA report.
- **`HF_HUB_OFFLINE=1`** is set in the Dockerfile so the container
  never tries to phone home — important behind a corporate firewall.

### 5.3 Determinism

- Same GPU + same CUDA driver across builds (pinned in Dockerfile to
  `nvidia/cuda:12.4.1`).
- Skill validator forbids sampling — `temperature=0`, `top_p=1`,
  `seed=12345`. Any deviation breaks audit reproducibility, so an
  upgrade from Llama 3.1 8 B to a future model is a **versioned event**
  that produces a new `skill_version` in the QA report metadata.

### 5.4 Versioning

- **Code**: git SHA (short) baked into `/api/health/detailed`.
- **Skills**: each skill has a `version` field; skills are immutable —
  changes require a new version directory.
- **Weights**: pinned by SHA-256 in `download_models.py` manifest; a
  weights-bump triggers a major version of the QA report schema.

---

## 6. Non-functional concerns

| Concern        | Approach                                                         |
|----------------|------------------------------------------------------------------|
| **Throughput** | One GPU = one pipeline at a time. Queue concurrent uploads via FastAPI BackgroundTasks; reject the 4th queued call with HTTP 429 + retry-after. |
| **Latency**    | 5 min/call is the SLO; UI shows determinate progress via `/calls/{id}/status` polling. |
| **Availability** | 99% within working hours is the realistic target — single box, no HA. Documented, not engineered around. |
| **Security**   | JWT (HS256), bcrypt password hashing, RBAC checked on every admin route, Pydantic validation at the boundary, no `eval`/dynamic-import in skills (validator-enforced). |
| **PII**        | Audio uploads stored under UUIDs, not filenames. `/uploads` not exposed by Nginx. Retention policy: TBD with supervisor. |
| **Observability** | JSON logs (`backend/app/logging_config.py`), `/api/health/detailed` with DB ping + disk free + GPU memory. |
| **Backups**    | nightly `pg_dump` (DB) + rsync of `uploads/` to NAS (audio + reports). |
| **DR**         | Box loss → restore latest dump on a fresh Ubuntu install + `docker compose up`. RPO ≤ 24h, RTO ≤ 4h. |

---

## 7. Cost model

For Option A (the recommendation) the marginal cost is electricity:

- RTX 5060 Ti idle ≈ 25 W; under load ≈ 180 W.
- 24/7 idle + 1 hr/day of inference ≈ ~22 kWh/month ≈ €5/month.
- One-off hardware: already owned (€0 incremental).
- TLS certs: Let's Encrypt (€0).
- Domain (optional): €10/year via Porkbun.

For Option C (cloud GPU, future commercial path):

| Provider | GPU       | $/hr | Per call (5 min) | 1k calls/month |
|----------|-----------|------|------------------|-----------------|
| RunPod   | A4000 16G | 0.34 | $0.028           | $28             |
| Lambda   | A10 24G   | 0.60 | $0.050           | $50             |
| Vast.ai  | 4090 24G  | 0.40 | $0.033           | $33             |

That benchmarks well against the manual QA cost the system replaces
(an internal QA reviewer spends ≈ 10 min on a call → at $20/hr that's
$3.30 per call, 100× the cloud-GPU cost).

---

## 8. Risks and mitigations

| Risk                                              | Likelihood | Impact | Mitigation                                                              |
|---------------------------------------------------|-----------:|-------:|-------------------------------------------------------------------------|
| GPU OOM on a long call                            | M | H | Stream audio in 30-s chunks; queue rejects oversized files at upload boundary. |
| Llama produces non-deterministic output after a CUDA driver update | L | H | Pin the CUDA base image; CI builds against the pinned image only. |
| HF_TOKEN expires / pyannote license change        | L | H | Cache weights on local NAS; document the re-download path.              |
| SQLite `calltone.db` corruption from concurrent writes | M | M | Switch to PostgreSQL in production (already supported via env vars).   |
| Audio file fills disk                             | M | M | `/uploads` on its own volume; alarm when free space < 10 %.            |
| Unauthorised access to `/admin/*`                 | L | H | RBAC enforced server-side; tested by `test_admin_dashboard_blocks_agent`. |
| Demo box reboots during supervisor presentation   | L | H | Run `run_local.bat` 30 min before, sanity-check `/api/health/detailed`. |

---

## 9. Conclusion

Option A — single-box on-prem with the existing Docker setup — is the
right deployment for the academic deliverable and the most realistic
v1 for an internal pilot inside a customer-service organisation. It
preserves audio privacy, GPU determinism, and the team's zero-budget
constraint, and it makes graceful future migration to Option B (split
hosting) trivial. The concrete CI/CD, environments, and rollout that
implement this decision are in `DEPLOYMENT_PLAN.md`.
