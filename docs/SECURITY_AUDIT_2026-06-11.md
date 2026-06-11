# CallTone — Pre-Defense Security Audit (2026-06-11)

Scope: full project — FastAPI backend, React/Vite frontend, GPU model server,
deployment scripts (Hetzner VPS + Vast.ai + SSH tunnel), secrets handling, Docker.
Method: source review of auth, authorization, input handling, subprocess/SQL/file
I/O, crypto, CORS, and committed-secret scan. Confidence threshold for "vuln": >80%.

## Verdict
**No HIGH-confidence, externally exploitable vulnerability found.** The codebase is
genuinely well-hardened. One MEDIUM (privileged path traversal) and a few LOW
hardening items below. Nothing here is a defense blocker.

---

## Findings

### M1 — Path traversal in company-context upload (privileged) — MEDIUM
* **File:** `backend/app/main.py:3673` (`POST /api/context/ingest`)
* **Issue:** `tmp_path = UPLOAD_DIR / f"context_{company_name.lower().replace(' ', '_')}_{uuid}.txt"`.
  `company_name` is validated by `_ensure_company_allowed_for_user` (966) for
  *tenant* users, but **platform/super-admin** users bypass that check
  (`allowed is None`), so the raw value reaches the path. `replace(' ','_')` does
  not strip `/` or `..`.
* **Impact:** An authenticated **platform admin** could write a `.txt` file outside
  `UPLOAD_DIR` (controlled prefix, uuid suffix, fixed `.txt`). Requires the highest
  privilege role and yields only a constrained `.txt` write — not RCE.
* **Fix:** Run `company_name` through `_sanitize_filename()` (already exists, 637)
  before building the path, or resolve and assert the path stays under `UPLOAD_DIR`.

### L1 — `DEBUG` defaults to `True` — LOW (deploy hardening)
* **File:** `backend/app/database.py:10`
* The `SECRET_KEY` boot guard (57) only fires when `DEBUG=false`. If a prod deploy
  forgets to set `DEBUG=false`, the dev default key would be accepted (JWT forgery).
  `.env.example` correctly sets `DEBUG=false`; just confirm it on the live host.
* **Fix:** Default `DEBUG=False`; opt into debug explicitly in dev.

### L2 — Non-constant-time token compare on model server — LOW
* **File:** `model_server/auth.py:77` (`header[...] != expected`)
* Bearer token compared with `!=`. Timing side-channel is largely theoretical over
  the network for a high-entropy hex token, and the server is already IP-allowlisted.
* **Fix:** `hmac.compare_digest(provided, expected)`.

### L3 — `/docs` exposure depends on config — LOW
* `DOCS_ALLOWED_IPS` gates Swagger/OpenAPI. If unset in prod, the schema is public
  (info disclosure only). Confirm it is set on the live host.

---

## Verified secure (no action)
* **SQL:** all queries parametrized (`mock_call_loader.py`, ORM elsewhere) — no injection.
* **Subprocess:** `model_server/pipeline_adapter.py` builds an **argv list** (no
  `shell=True`); `company`/`asr_engine` cannot inject commands.
* **AuthN:** bcrypt (`security.py`), JWT alg pinned to HS256 (no `alg=none`/confusion).
* **AuthZ:** tenant isolation enforced via `client_id` scoping + explicit cross-tenant
  check on call access (`_ensure_call_visible_to_user`, 981); agent/QA/admin RBAC.
* **CORS:** `main.py:495` — wildcard origins only when credentials are **disabled**;
  avoids the dangerous `*`+credentials combo.
* **Upload:** `_sanitize_filename` (637) strips path separators, leading dots, caps length.
* **Model server:** bearer token **+ IP allowlist** middleware; health-only public path.
* **Secrets:** `SECRET_KEY` boot guard for prod; `.env`/`.env.prod`/`.env.demo`
  gitignored; **no hardcoded secrets or private keys in tracked source**; `.gitleaks.toml`,
  Dependabot, and a `security.yml` CI workflow are present.
* **Frontend:** React (auto-escaping); no `dangerouslySetInnerHTML`/eval on user input.

## Operational notes (not code vulns)
* GPU server reached over SSH tunnel from the backend tier only — keep the Vast port
  off the public internet; rely on the tunnel + token + IP allowlist.
* Rotate `MODEL_SERVER_TOKEN` and `SECRET_KEY` after the defense if any laptop/Vast
  instance that held them is shared or recycled.
