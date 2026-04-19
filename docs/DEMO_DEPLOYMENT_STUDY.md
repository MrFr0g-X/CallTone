# CallTone — Demo Deployment Study (two-server, on-demand GPU)

> **Status:** supersedes the demo/defence portion of `DEPLOYMENT_STUDY.md`
> (2026-04-18), which compared on-prem vs split vs cloud at the
> architectural level and chose on-prem. This document scopes the
> *concrete* deployment for supervisor review and graduation defence:
> two servers, on-demand GPU, real domain.
>
> **Companion:** `DEMO_DEPLOYMENT_PLAN.md` — the step-by-step build
> sequence. Keep them in sync: every decision labelled D-N here maps
> to an implementation block in the plan.

## 0. Purpose

We are splitting CallTone across three hosts instead of one so that the
heavy GPU pipeline only costs money when a reviewer is actually asking
for it. The split has consequences: a network boundary audio must
cross, a new credential surface, and a deployment workflow that has to
be drilled before supervisor review.

Scope: the on-demand demo configuration (supervisor showcase +
graduation defence). "Company scale" (1000+ calls/day, persistent GPU,
queue workers) is an orthogonal future project and is explicitly out of
scope in §8.

## 1. Three-tier architecture

```
┌──────────────────────────────────────────┐
│ Tier 1 — Static frontend                 │
│ calltone.tech  (Hetzner shared hosting)  │
│ Serves the built Vite SPA from public_   │
│ html/. No backend logic. Varnish cache,  │
│ free TLS via konsoleH.                   │
└────────────────────┬─────────────────────┘
                     │ fetch() — HTTPS — JWT bearer
                     ▼
┌──────────────────────────────────────────┐
│ Tier 2 — App server (always on)          │
│ 91.99.208.254  (Hetzner Cloud CPX31)     │
│ 4 vCPU · 8 GB RAM · 80 GB SSD · 20 TB/mo │
│ FastAPI backend · Postgres · Nginx · TLS │
│ Holds users, roles, calls, transcripts,  │
│ QA reports. NO model code runs here.     │
└────────────────────┬─────────────────────┘
                     │ httpx + bearer token (private)
                     │ Model server URL set via env var;
                     │ absent → backend falls back to local
                     │ subprocess pipeline (dev mode).
                     ▼
┌──────────────────────────────────────────┐
│ Tier 3 — GPU model server (on-demand)    │
│ Vast.ai — RTX 4090, Ubuntu 22.04 + CUDA  │
│ Started manually before a demo,          │
│ destroyed after. Exposes /v1/analyze and │
│ /v1/jobs/{id}. Models download on boot.  │
└──────────────────────────────────────────┘
```

This is the minimum three-tier split that both (a) keeps the always-on
cost under $15/mo and (b) lets us destroy the expensive machine between
demos without breaking the reviewer-facing website.

## 2. Server inventory

### 2.1 Tier 1 — `calltone.tech` (shared hosting, Hetzner konsoleH)

| Attribute         | Value                                             |
| ----------------- | ------------------------------------------------- |
| Host              | `www686.your-server.de`                           |
| Domain            | `calltone.tech` (customer-owned)                  |
| Storage           | 100 GB                                            |
| Memory limit      | 384 MB per process                                |
| Supported runtime | PHP-FPM + Node.js managed processes + static HTML |
| TLS               | free via konsoleH                                 |
| Databases         | 20 × MySQL (unused)                               |

**Role**: serves the compiled Vite bundle from `public_html/`. Nothing
else. Does not run backend code; does not proxy. The SPA points its
`VITE_API_BASE_URL` at `https://api.calltone.tech`, which DNS-resolves
to Tier 2.

**Why not run the backend here?** 384 MB per-process RAM is not enough
to hold FastAPI + SQLAlchemy + bcrypt + 10 reviewer sessions. Shared
hosting also forbids arbitrary long-running daemons (only PHP-FPM and
managed Node processes). No `systemd`, no Docker, no root — verified
from the package description.

### 2.2 Tier 2 — Hetzner Cloud CPX31 app server

| Attribute     | Value                              |
| ------------- | ---------------------------------- |
| IPv4          | `91.99.208.254`                    |
| IPv6          | `2a01:4f8:c014:3ca4::/64`          |
| Flavour       | CPX31 (AMD, 4 vCPU, 8 GB, 80 GB)   |
| Traffic       | 20 TB egress/month                 |
| Price         | €9.49/month                        |
| Target OS     | Ubuntu 22.04 LTS                   |
| Public DNS    | `api.calltone.tech`, `app.calltone.tech` (A-record planned) |

**Role**: hosts the CallTone FastAPI backend, Postgres, Nginx reverse
proxy with Let's Encrypt TLS, JWT-authenticated REST surface. When a
user uploads a call, the backend stores the audio in `uploads/` and
either:

- runs the pipeline *locally* in a spawned subprocess (current
  behaviour, kept as a dev-mode fallback), or
- forwards the audio to the Tier 3 model server and polls for results
  (new behaviour when `MODEL_SERVER_URL` env var is set).

**Why this flavour?** 4 vCPU / 8 GB is the cheapest Hetzner SKU that
runs Postgres + uvicorn + ~10 concurrent reviewers without paging. The
next rung down (CPX21, 4 GB) pages under concurrent-login tests in
local measurements. 80 GB disk holds ~500 uploaded calls at 100 MB
apiece with head-room; after that we rotate to object storage.

**Credentials policy**: the root password from the Hetzner dashboard is
used *exactly once* to install the operator's SSH public key. After
the key is in `~/.ssh/authorized_keys`, we disable password auth in
`/etc/ssh/sshd_config` (`PasswordAuthentication no`). From that point
forward, ownership is proved by holding the private key on the
operator's laptop. Rotation = revoke laptop key.

### 2.3 Tier 3 — Vast.ai GPU instance (ephemeral)

| Attribute         | Value                                             |
| ----------------- | ------------------------------------------------- |
| Hypervisor        | Vast.ai community cloud                           |
| GPU               | RTX 4090 (24 GB VRAM) or equivalent ≥16 GB        |
| CPU/RAM           | 8 vCPU / 32 GB recommended                        |
| Disk              | 80 GB / instance (model weights ≈ 13 GB)          |
| OS / image        | Ubuntu 22.04 + CUDA 12.1                          |
| Network           | 1 Gbps+ (Vast reports per-provider)               |
| Price             | $0.30–0.50/hr on-demand                           |
| SSH (ephemeral)   | e.g. `ssh -p 44049 root@185.65.93.114` — rotates per instance |

**Role**: on receiving `POST /v1/analyze` with the audio file, runs the
existing `models/run_full_pipeline.py` chain (LAYER 1 → LAYER 2, with
LAYER 3 optional) and reports progress via `GET /v1/jobs/{id}`.
Returns the QA report JSON that the backend already knows how to
persist.

**Why Vast.ai over the alternatives?**

| Option                     | $/mo @ 20h use | On-demand? | Setup friction | Verdict     |
| -------------------------- | -------------- | ---------- | -------------- | ----------- |
| **Vast.ai RTX 4090**       | ~$7            | yes (sec)  | medium         | **chosen**  |
| RunPod community RTX 4090  | ~$7            | yes (sec)  | medium         | tied; Vast cheaper today |
| Hetzner GEX44 (RTX 4000)   | €184 flat      | no         | low            | rejected — 25× cost |
| Lambda Labs H100 on-demand | ~$30 for 20 h  | yes        | low            | overkill for 8 B model |
| Local RTX 3060 on laptop   | free, 12 GB    | always     | zero           | dev-only; can't host for remote reviewer |

Vast.ai wins on the one axis that matters right now (on-demand,
sub-second billing) while staying well inside the $20–30/mo envelope.

**Why not persistent GPU?** At 20 hours of demo use per month — a
generous upper bound for defence season — persistent hardware is a
25–30× overspend. If the project later pivots to production ("companies
with 1000+ calls/day"), we revisit this with Hetzner GEX44 and a
proper job queue. That deployment is a different study.

**Credentials policy**: the HF_TOKEN used to pull gated pyannote
weights is set via Vast.ai's environment-variable UI, *never* baked
into the image and *never* committed. The `MODEL_SERVER_TOKEN` used to
authenticate the backend's calls is generated fresh per instance
(`openssl rand -hex 32`) and copied into the app server's `.env`.

## 3. End-to-end data flow

```
Reviewer browser    Tier 1 (SPA)         Tier 2 (backend)              Tier 3 (GPU)
     │                   │                      │                            │
     │── upload audio ──>│                      │                            │
     │                   │── POST /calls/upload>│                            │
     │                   │                      │ write audio to disk        │
     │                   │                      │ create Call row            │
     │                   │                      │ spawn worker subproc ─────>│
     │                   │                      │                            │
     │                   │                      │ if MODEL_SERVER_URL set    │
     │                   │                      │   POST /v1/analyze ───────>│
     │                   │                      │   (multipart audio)        │
     │                   │                      │<── job_id ─────────────────│
     │                   │                      │                            │
     │                   │                      │ poll:                      │
     │                   │                      │   GET /v1/jobs/{id} ──────>│
     │                   │                      │<── {status, step, eta} ────│
     │                   │                      │   persist step to DB       │
     │                   │                      │   sleep 2 s                │
     │                   │                      │   ...                      │
     │                   │                      │<── {status:done, report} ──│
     │                   │                      │ persist report + transcript│
     │                   │                      │                            │
     │<── poll /calls/{id}/status (SPA, 3 s) ───│                            │
     │<── report JSON / UI render ──────────────│                            │
```

The subprocess boundary on the backend is the key detail: the HTTP-
forwarding worker looks identical to the in-process worker from the
DB's point of view. Neither the frontend nor the main backend request
thread ever touches the GPU server directly. Reviewers can keep
polling even if the GPU instance goes down mid-run (we mark the call
FAILED with a reason; the reviewer re-uploads after the instance is
rebooted).

## 4. Time budget: can we hit 3–5 min per 10-min call?

Per-stage timings on RTX 4090, Ubuntu 22.04, CUDA 12.1, 10-minute audio
input (based on measured numbers from `models/LAYER_1/*` dev logs and
community GGUF benchmarks):

| Stage                                    | CPU only   | RTX 4090 FP16 | Notes |
| ---------------------------------------- | ---------- | ------------- | ----- |
| resemble-enhance denoise                 | 3–4 min    | 30–45 s       | GPU-bound |
| pyannote segment + embed                 | 90 s       | 15–20 s       | GPU-bound |
| SenseVoiceSmall transcribe               | 2 min      | 20–30 s       | GPU-bound |
| Audio2Emotion per utterance (ONNX)       | 30 s       | 5–10 s        | GPU or CPU-GPU offload |
| Llama 3.1 8B role-ID (1 prompt)          | 25 s       | 6–8 s         | GGUF Q8 + CUDA llama-cpp |
| Free LAYER 1 VRAM, reload LLM for LAYER 2| 5 s        | 5 s           | essential — see `_free_layer1_vram` in `run_full_pipeline.py` |
| Llama 3.1 8B QA scoring (4 dimensions)   | 3 min      | 30–45 s       | ~1.5K tokens out total |
| LAYER 3 renderer (Jinja + pandoc)        | 5 s        | 5 s           | CPU |
| **Total**                                | **~12 min**| **~2–3 min**  |       |

GPU path hits the 3-minute target for typical calls and clears the
5-minute ceiling with margin on long ones. The CPU path misses on
anything > 6 minutes and is kept only as a dev-mode fallback.

**Cold-start cost**: first call after instance boot adds 30–45 s for
model loading (SenseVoice + pyannote + Audio2Emotion + llama-cpp mmap).
Second call onward is warm. The bootstrap script pre-warms by running
a 5-second canned audio through the pipeline before returning its
"ready" signal.

## 5. Threat model deltas

Compared to the single-server model in `SECURITY_STUDY.md`, the split
introduces three new attack surfaces:

| Delta                              | Mitigation                                                   |
| ---------------------------------- | ------------------------------------------------------------ |
| Audio in flight between tiers      | HTTPS to the model server; TLS terminated by Vast's ingress or a caddy sidecar we bring. No audio over plain HTTP. |
| Model-server public endpoint       | Bearer token (`MODEL_SERVER_TOKEN`) required on every non-health route. Token rotates per instance boot. |
| HF_TOKEN on a third-party VM       | Passed via Vast.ai env-var UI, not baked into image, not in shell history (`unset HISTFILE` in bootstrap). Scope-limited HF token (read-only, pyannote repos only). |
| Credential scrape of shell history | `unset HISTFILE`; secrets piped via `read -s` in bootstrap.   |
| Third-party host compromise        | No user PII stored on the model server; audio files deleted within 5 minutes of analysis. Model server holds *no* database. |

**Net verdict**: the split *reduces* data-at-rest risk on the GPU host
(nothing persists beyond one job) at the cost of one new credential
(`MODEL_SERVER_TOKEN`) we have to manage. Net win.

## 6. Failure modes

| Failure                             | Detection                                  | Response                                                     |
| ----------------------------------- | ------------------------------------------ | ------------------------------------------------------------ |
| GPU OOM during LAYER 2              | Worker exits with CUDA error               | Call marked FAILED with "GPU out of memory"; reviewer retries |
| Vast.ai host revoked mid-run        | httpx connection timeout > 30 s            | Call marked FAILED; reviewer alerted, reboot fresh instance  |
| Model download failed on boot       | Bootstrap script exits non-zero            | Bootstrap halts; operator re-runs (idempotent)               |
| Wrong HF_TOKEN → pyannote 401       | Bootstrap's model-download step errors     | Clear error message; operator fixes env var, re-runs         |
| `MODEL_SERVER_URL` unset on backend | Worker falls back to local subprocess      | Dev mode — intentional; local pipeline still works           |
| Network partition between tiers     | Backend retries 3× with exponential backoff| After 3 failures, mark call FAILED                           |
| Audio exceeds 100 MB                | Backend rejects with 400 before any forward| UI surfaces the limit                                        |

Every failure path writes a row in `calls` with a clear status +
reason so the reviewer sees *something* and doesn't think the UI is
frozen.

## 7. Cost model

Monthly, assuming supervisor-review cadence (2 demos/week × 45 min each
with ~15 min of GPU analysis; rest is demo setup/Q&A on pre-cached
results):

| Line                              | Unit                | Usage/mo      | Cost       |
| --------------------------------- | ------------------- | ------------- | ---------- |
| Hetzner CPX31 app server          | €9.49/mo            | 24/7          | ~$10.20    |
| Vast.ai RTX 4090                  | $0.35/hr avg        | 8 × 45 min    | ~$2.10     |
| Vast.ai storage (snapshot kept)   | $0.10/GB/mo         | 15 GB         | ~$1.50     |
| Domain + TLS (Let's Encrypt)      | amortized           | —             | ~$1.00     |
| **Ephemeral total**               |                     |               | **~$13/mo**|
| **With warm image kept**          |                     |               | **~$15/mo**|

Comfortable inside the $30 ceiling. Buffer absorbs: accidental
forgotten instance (max $8 before Vast's daily cap kicks in),
additional demo days during defence week, or moving from RTX 4090 to
RTX 5090 if community pricing falls below it.

## 8. What we explicitly did NOT build

- **Autoscaling pool of GPUs** — single-instance only. At peak demo
  load (1 reviewer) this is correct.
- **Secondary always-on GPU as hot standby** — the demo tolerates a
  15-minute boot window. Standby doubles cost for no user-visible win.
- **Distributed object storage (S3/R2) for audio** — local disk on each
  tier is sufficient; 20 TB Hetzner egress absorbs traffic.
- **Cross-region failover** — not in scope for a graduation demo.
- **Model serving via Triton / vLLM / TGI** — would be faster but adds
  an abstraction layer the project team cannot debug in a week.
  `run_full_pipeline.py` as-is is good enough.
- **Company-scale deployment** — 1000+ calls/day is a different study
  (persistent GPU + Redis queue + horizontal scaling). Explicitly
  deferred until after defence.

## 9. Bottom line

The deployment that meets all stated constraints is:

- **Tier 1**: static SPA on `calltone.tech` shared hosting.
- **Tier 2**: CallTone FastAPI backend on Hetzner CPX31 `91.99.208.254`
  with DNS `api.calltone.tech` + `app.calltone.tech` (TLS via
  Let's Encrypt).
- **Tier 3**: Vast.ai RTX 4090 instance, brought up per demo, destroyed
  after, communicating with the backend over HTTPS + bearer token.

Total always-on cost: **~$11/mo**. Per-demo variable cost: **~$0.26**.
Fits comfortably inside the $20–30/mo ceiling with headroom.

See `DEMO_DEPLOYMENT_PLAN.md` for the step-by-step build sequence
(tasks D-1 through D-10).
