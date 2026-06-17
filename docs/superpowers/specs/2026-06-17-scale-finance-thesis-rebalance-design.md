# CallTone — Scale, Finance & Thesis-Rebalance Design Spec

> Created 2026-06-17. Defense June 21–22 (submission before June 20). Author: pairing w/ Hothifa.
> Decisions locked by user (2026-06-17): (1) implement a **bounded** real concurrency upgrade + demo (no full autoscaler); (2) **hybrid** SaaS-cloud-default + on-prem option; (3) **tiered per-agent/month + usage caps** pricing; (4) content into **both** thesis + defense guide.

---

## 0. Problem statement
Three gaps threaten an A at defense:
1. **Thesis is AI-heavy.** Software engineering, system architecture, and security are *built* but *under-narrated* — they read as summaries while AI gets chapters.
2. **Finance is qualitative only.** `02_market_business.tex` has a qualitative competitor table + "tens–low-hundreds $/agent/mo" and nothing numerical: no cost-per-call, unit economics, margin, 4090-vs-A100 math, or multi-company projection.
3. **Scalability is unproven.** The pipeline queue is **strictly serialized** (one worker thread, one `running` job, one GPU, one backend) — no answer to "50 companies × 100–500 agents."

## 1. Current state (grounded in code)
- **Queue:** `backend/app/main.py` — `PipelineJob` table already has `priority`, `attempts/max_attempts`, `locked_at`. Worker = single `_PIPELINE_WORKER_THREAD`; `_pipeline_queue_snapshot`/`_queued_pipeline_jobs` assume one active job (`running ... .first()`). **Built multi-worker-ready; runs single-worker.**
- **Multi-tenancy:** data model tenant-scoped (`Client → User/Employee/Call`, `company_name` on jobs). Isolation at data layer exists; **concurrent per-tenant throughput + fairness do not.**
- **Model server:** separate tier (`model_server/`), reached over SSH tunnel; backend talks to ONE endpoint (`model_client.py`). No pool.
- **DB:** Postgres in prod (supports `FOR UPDATE SKIP LOCKED`); SQLite likely in local dev.

## 2. Workstream A — Bounded concurrency / parallel batch upgrade (CODE)
Goal: real, testable, demoable multi-call concurrency + per-tenant fairness + multi-GPU-readiness. Backward-compatible (default config = today's behavior).

### A1. Configurable worker pool
- New env `PIPELINE_WORKER_CONCURRENCY` (default `1` → identical to today).
- Replace the single worker thread with a pool of N threads each running the existing loop body.

### A2. Atomic job claim (no double-processing)
- Postgres path: claim via `SELECT id FROM pipeline_jobs WHERE status='queued' ORDER BY <fairness> FOR UPDATE SKIP LOCKED LIMIT 1`, then `UPDATE ... SET status='running', locked_at=now()`.
- SQLite/dev path: reuse `_PIPELINE_QUEUE_LOCK` (process-global) for the claim critical section.
- Recovery: on startup, requeue jobs stuck `running` with stale `locked_at` (lease expiry) — generalize existing recovery.

### A3. Per-tenant fair scheduling
- Replace strict FIFO with **fair selection**: among queued jobs, pick the company with the fewest currently-running jobs (tie → oldest `created_at`); within it, lowest `priority`/oldest. Prevents one tenant monopolizing the GPUs.

### A4. Multi-GPU / model-server pool (the "load balancer", bounded form)
- `MODEL_SERVER_URLS` (comma-separated) → backend keeps a small pool with health checks; each worker leases a healthy endpoint; per-endpoint semaphore caps concurrent jobs per GPU.
- Single-URL config = today's behavior.

### A5. Snapshot/overview for many active jobs
- `_pipeline_queue_snapshot` / `_pipeline_queue_overview` already track running as a list in overview; finish the multi-active handling + ETA based on `ceil(queued / concurrency) × per-job`.

### A6. Tests + demo
- Tests: N jobs across M tenants → assert (a) no double-claim, (b) fair interleaving, (c) all reach terminal, (d) concurrency honored.
- Demo: docker-compose **mock model-server** profile (GPU-free), enqueue ~20 jobs / 4 tenants, show concurrent processing + fairness in the queue UI + load-test numbers.

### A7. Non-goals (state honestly)
- No Kubernetes/autoscaler, no cross-region failover, no real multi-instance backend behind an L7 LB (design documented, not deployed).

## 3. Workstream B — Finance model (NUMERIC, cited)
All figures parameterized + sourced; assumptions labeled. Lives in expanded `02_market_business.tex` (+ appendix table) and the defense guide.

### B1. Inputs (cited, June 2026)
- RTX 4090 rent **$0.40/hr** (RunPod $0.34 community / Vast $0.40). A100 80GB **$1.50/hr** (Jarvis $1.49). → 4090 ≈ **3.75× cheaper/hr**.
- Call center: **~50 calls/agent/day** (52 avg), **AHT ~6 min**.
- Working days **22/mo** → **~1,100 calls/agent/month**.
- Processing time/call on 4090: **PARAMETER `t_proc`** (target <5 min/10-min call). Use scenarios t_proc ∈ {2,3,5} min; flag that the *measured* 4090 number must be plugged before final print (GPU currently de-provisioned to stop billing).

### B2. Core unit economics (serialized, 1×4090, continuous)
- 4090 monthly = $0.40 × 24 × 30 = **$288/GPU/mo**.
- Calls/GPU/mo = (60/t_proc) × 24 × 30. t_proc=3 → 14,400 calls/GPU/mo.
- **Cost/call = $0.40 × t_proc / 60**: t_proc=2 → **$0.013**, 3 → **$0.020**, 5 → **$0.033**.
- Agents/GPU = 14,400 / 1,100 ≈ **13 agents** (t_proc=3).
- **Marginal GPU cost/agent/mo ≈ $22** (t_proc=3); concurrency ×2 or t_proc=2 → **~$11–15**.

### B3. Margin & pricing (per decision: tiered per-agent/mo + caps)
- Proposed tiers (illustrative): Starter $39/agent/mo (1,200 calls incl), Growth $29 (volume), Enterprise custom; overage $0.03/call.
- Gross margin at $29–39 vs marginal $11–22 = **~40–70%**, and the concurrency work is what pushes cost toward $11 → margin up. **Make this the explicit link** between Workstream A and finance.
- Undercut: CallMiner transparent ~$89/user/mo; enterprise tens–low-hundreds. CallTone at $29–39 = **~55–65% cheaper** with 100% coverage.

### B4. Scale projection (the "50 companies" answer)
- 50 companies × avg 250 agents = **12,500 agents** → 12,500 × 1,100 = **13.75M calls/mo**.
- GPUs needed (t_proc=3, 14,400 calls/GPU/mo, 70% utilization headroom) = 13.75M / (14,400×0.7) ≈ **~1,365 GPU-months** → fleet ~**1,365 × $0.40 × 720h**… present as **~$393k/mo GPU** vs revenue 12,500 × $29 = **$362k/mo** → shows we MUST improve t_proc/concurrency (drives margin) OR price/utilization. Present honestly with sensitivity table (t_proc, utilization, price) so the model is defensible, not rosy.
- Own-vs-rent: 4090 ≈ $1,800 capex; breakeven vs $288/mo rent ≈ **6.3 months** → at fleet scale, owning/colo beats renting → roadmap item.

### B5. Deliverable
- New thesis section "Cost Model and Unit Economics" + 2 tables (unit econ; scale sensitivity) + 1 figure (cost/call vs t_proc; cost vs competitors).
- Defense-guide finance cheat-sheet (the numbers to say out loud).

## 4. Workstream C — Real-world ops & privacy model (DESIGN → thesis + guide)
Per decision: **hybrid**.
- **SaaS-cloud (default):** client uploads audio (or API push) → our rented-GPU cloud → tenant-isolated processing → report. Privacy: TLS in transit, per-tenant data isolation, configurable retention/auto-purge of audio after scoring, access control, EU/region GPU option for data residency. Audio optionally deleted post-scoring (store transcript+report only).
- **On-prem / VPC (option):** containerized model server + backend run inside the client's environment / their GPU; only license + updates flow to us; **no call data leaves the client.** For banks/gov/data-sovereignty.
- Integration paths: (a) web upload, (b) REST ingestion API (push call recordings), (c) batch SFTP/bucket drop for overnight bulk.
- "Local vs our servers" answer = **both, as tiers** (SaaS default, on-prem premium).
- Diagram: deployment-topology (SaaS multi-tenant vs on-prem single-tenant).

## 5. Workstream D — Thesis rebalancing (DOCS)
Expand without inflating; add real diagrams/tables.
- **System Architecture:** component + deployment + sequence (upload→queue→GPU pool→report) diagrams; the concurrency/queue design (Workstream A) documented.
- **Software Engineering:** RBAC (capability model), API design/versioning, data model, CI/CD, testing strategy (163 tests breakdown), config/secrets, observability/health, error handling — each a real subsection with evidence.
- **Security:** threat model summary, authn/z, rate limiting, prompt-injection (static+LLM), input validation, transport/secret handling, multi-tenant isolation — promote from `SECURITY_STUDY.md` into a proper chapter section.
- Keep AI chapters as-is (already strong).

## 6. Execution order (4-day plan)
1. **Day 1 (today):** Workstream A code (A1–A5) on a new branch + tests (A6). This is the riskiest; do first while fresh.
2. **Day 2:** Verify A end-to-end on mock profile + (if GPU re-rented) one real run; finalize numbers; write Finance (B) into thesis + guide.
3. **Day 3:** Thesis rebalancing (D) + ops/privacy (C) sections + diagrams; rebuild thesis + defense guide PDFs.
4. **Day 4:** Full proofread, numbers cross-check, demo dry-run, buffer.

## 7. Risks & honesty rules
- Don't break the live serialized path: default config must reproduce today's behavior; concurrency is opt-in via env.
- Plug the **measured** 4090 t_proc before final print; until then label as assumption.
- Finance model presented with a **sensitivity table** (no rosy single number); the 50-company case honestly shows margin pressure → motivates the optimization roadmap.
- Everything claimed in thesis/guide must map to real code/tests (no fabrication).

## 8. Open items needing a quick measurement (not blocking design)
- Real end-to-end t_proc per call on the 4090 (re-rent briefly or pull from a prior logged run, e.g. call 85312252).
- Confirm whether >1 pipeline fits in 24 GB concurrently (sets per-GPU concurrency cap) — likely 1 full pipeline + queued L2; validate empirically.
