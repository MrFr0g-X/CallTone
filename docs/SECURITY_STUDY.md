# CallTone — Security Study

**Author:** NasrEldin Khaled (IT) · **Date:** 2026-04-19 · **Audience:** project supervisor + jury

This document is a comparative analysis of the security posture CallTone
needs in production. It is paired with `SECURITY_PLAN.md`, which commits
to a specific control set, sequences the implementation, and lists the
verification commands.

The scope is the same shape as `DEPLOYMENT_STUDY.md`: a graduation project,
single-box on-prem, ten concurrent QA reviewers — not a public SaaS.
Security work is sized accordingly.

---

## 1. What we are protecting

| Asset                                 | Where it lives                          | Sensitivity |
|---------------------------------------|-----------------------------------------|-------------|
| Customer-service **call recordings**  | `backend/uploads/*.{wav,mp3,flac}`      | High — PII, voice biometrics |
| **Transcripts** (verbatim speech)     | `transcripts` table + `Transcript` model | High — PII content |
| **QA reports** (scores, evidence)     | `qa_reports` table                      | Medium — internal eval |
| **User accounts** (admin/qa/agent)    | `users` table — `password_hash` column  | High — bcrypt cost-12 |
| **JWT signing key** (`SECRET_KEY`)    | `.env.prod` on the GPU box              | Critical    |
| **HF_TOKEN** (pyannote weights)       | `.env.prod`                             | Medium — re-issuable |
| **Database dump backups**             | `/srv/backups/calltone/` on the NAS     | High — full PII |
| **Pipeline binaries / model weights** | `models/**` (gitignored)                | Low — public weights |

All seven are real and present today. The first three are the reason
this is a security-bearing project rather than a demo: if a transcript
leaks, a real customer was harmed.

---

## 2. Threat model

### 2.1 Actors and motivations

| Actor                          | Capability                              | Likely goal                           |
|--------------------------------|------------------------------------------|---------------------------------------|
| Curious teammate (insider)     | Has a valid `agent` JWT                 | Read another agent's calls            |
| Disgruntled QA reviewer        | Has a valid `qa` JWT                    | Tamper with a score, hide a bad call  |
| External script kiddie         | Knows the demo URL, no creds            | Brute-force `/auth/login`, pop a shell |
| Malicious **caller**           | Speaks into a customer-service line     | Inject prompts into the QA scorer     |
| Compromised dev laptop         | Has the dev `.env` file                 | Read prod by reusing a leaked secret  |
| GitHub repo crawler / bot      | Reads public commits                    | Steal secrets accidentally pushed     |

The middle two — **brute-force on login** and **prompt injection via
transcript** — are the threats specific to this product. A
customer-service caller has a microphone and an unlimited budget of
words; if they can convince the LLM to give itself a perfect score,
the entire QA contract is broken. That is why LAYER 2's
`injection_scanner.py` exists and is exercised by 13 adversarial test
cases (`models/LAYER_2/security/tests/`).

### 2.2 Out-of-scope threats (and why)

- **Nation-state APT.** Academic deployment, no high-value target,
  reasonable response is "use HTTPS and don't get clever."
- **DDoS at the network layer.** The on-prem deploy sits behind a
  single nginx; a real flood is the GPU box owner's problem, not the
  application's.
- **Supply-chain attack on Llama 3.1 weights.** Mitigated by
  SHA-256-pinning every model in `download_models.py` and downloading
  once on the deploy host (cf. `DEPLOYMENT_PLAN.md` §10).
- **Side-channel timing attack on bcrypt.** `passlib`'s `verify` is
  constant-time; we do not hand-roll string comparisons.
- **TLS 1.0/1.1 downgrade.** Cert-bot defaults to 1.2+ already;
  Mozilla "intermediate" config will be applied at the nginx layer.

### 2.3 Attack surface inventory

Counted from the actual codebase (matches `AUDIT_2026-04-18.md` §1):

| Surface                                  | Endpoints | Auth required | Notes |
|------------------------------------------|-----------|---------------|-------|
| Public — health + login + invite-accept  | 5         | No            | `/`, `/api/health`, `/api/health/detailed`, `/api/v1/auth/login`, `/api/v1/auth/invite/{token}`, `/api/v1/auth/invite/accept` |
| Authenticated — read                     | 11        | JWT           | calls list, dashboards, ticket reads, etc. |
| Authenticated — write                    | 7         | JWT + role    | upload, settings PUT, ingest POST |
| Authenticated — admin                    | 7         | super_admin / admin role | invite, role/status patch, delete |
| **Total**                                | **30**    |               | (all in `backend/app/main.py`) |

The public surface is intentionally small. Every byte the unauthenticated
internet can poke is on the first row of the table, and that row is the
priority target for hardening.

---

## 3. Control catalog — what we could implement

For each control we list the option, the cost, and a recommendation.
Selected items become rows in `SECURITY_PLAN.md`.

### 3.1 Authentication strength

| Option                                  | Cost          | Verdict                  |
|------------------------------------------|---------------|--------------------------|
| Bcrypt (current, cost-12 default)        | already paid  | **KEEP**                 |
| Argon2id                                 | low (passlib) | defer — bcrypt fine for our threat model |
| 2FA / TOTP                               | medium        | defer — no-one demos a graduation project with TOTP |
| WebAuthn / passkeys                      | high          | defer — overkill for ten reviewers |
| Min-length password (≥ 8) on accept      | already paid  | **KEEP**                 |
| Reject passwords > 72 bytes (bcrypt cap) | trivial       | **ADD** — `bcrypt<4.1` pin still truncates silently, `≥5.0` raises. Make the rejection explicit so the UX is predictable across versions. |
| Reject the dev `SECRET_KEY` at startup when `DEBUG=false` | trivial | **ADD** — single biggest "oops" that a single-box deploy can ship |

### 3.2 Brute-force / abuse protection

| Option                              | Cost           | Verdict                        |
|--------------------------------------|----------------|--------------------------------|
| `slowapi` / `limits` (Redis-backed) | medium — adds Redis | defer — Redis is overkill for v1 |
| In-process token bucket on `/auth/login` | low — pure-Python, no deps | **ADD** — 10 attempts/IP/min is plenty |
| In-process token bucket on `/auth/invite/accept` | low | **ADD** — same risk, fewer requests |
| nginx `limit_req` zone               | low — nginx config | defer to deploy phase |
| CAPTCHA on the login page            | medium — UX cost | defer — not warranted at our scale |

The point of in-process limiting is to defang automated credential
stuffing. A determined attacker can rotate IPs; a script kiddie cannot.

### 3.3 HTTP transport hardening

| Header                            | Default | Recommendation |
|-----------------------------------|---------|----------------|
| `Strict-Transport-Security`       | none    | **ADD** at nginx (deploy phase) |
| `X-Content-Type-Options: nosniff` | none    | **ADD** in middleware |
| `X-Frame-Options: DENY`           | none    | **ADD** — we never embed |
| `Referrer-Policy: no-referrer`    | none    | **ADD** — we have no analytics |
| `Permissions-Policy`              | none    | **ADD** — disable mic/camera/geo by default |
| `Content-Security-Policy`         | none    | **ADD** — `default-src 'self'`; SPA-friendly; tightens XSS blast radius |
| `Cross-Origin-Opener-Policy: same-origin` | none | nice-to-have, low cost — **ADD** |
| `Cross-Origin-Resource-Policy: same-site` | none | **ADD** for the API — assets stay first-party |

Cost is one middleware function (~30 lines). Reward is meaningful:
the JWT lives in `localStorage`, so any persistent XSS could exfiltrate
it. CSP + `X-Content-Type-Options` is the cheap version of the
"defense in depth" we owe the user.

### 3.4 Input validation at the edge

| Vector                          | Today                                  | Recommendation |
|---------------------------------|-----------------------------------------|----------------|
| Upload content-type             | allowlist of 9 audio MIMEs              | KEEP |
| Upload size                     | 100 MB cap                              | KEEP |
| Upload **filename**             | `f"{call_id}_{file.filename}"` — UUID prefix dampens but does not sanitize | **ADD** — strip path separators, control chars, NUL, force basename |
| JSON body size                  | un-capped (Starlette default)           | defer — every endpoint validates field-by-field, payloads are small |
| Email format                    | `pydantic.EmailStr` on login            | KEEP |
| Invite token format             | 32-byte URL-safe                        | KEEP |
| Password max length             | un-capped                               | **ADD** (see 3.1) |
| Free-text fields (name)         | `.strip()` only                         | acceptable — read-only echo, no eval/exec path |

The filename one is the only one that can plausibly write a file
outside `UPLOAD_DIR`. Even with the UUID prefix, a filename of
`../../../../etc/passwd` becomes `<uuid>_../../../../etc/passwd`,
which `Path.write_bytes` will happily traverse. Fix is one helper.

### 3.5 Secret hygiene

| Control                                      | Today                  | Recommendation |
|----------------------------------------------|------------------------|----------------|
| `.env*` in `.gitignore`                      | yes                    | KEEP |
| `.env.example` template                      | yes (created in CD work) | KEEP |
| `gitleaks` in CI                             | yes (per-PR + weekly)  | KEEP |
| `.gitleaks.toml` allowlist for placeholders  | no                     | **ADD** — silences false positives from `replace-with-...` lines so real leaks are visible |
| Pre-commit hook for secret scanning          | no                     | defer — CI catches it, contributors install hooks inconsistently |
| Secrets in GitHub Actions environments       | implied by deploy plan | covered by `DEPLOYMENT_PLAN.md` §5 |
| Quarterly rotation of `POSTGRES_PASSWORD`    | documented             | covered |

### 3.6 Logging & observability of security events

| Event                              | Today                    | Recommendation |
|------------------------------------|--------------------------|----------------|
| Successful login                   | logged via uvicorn access log | sufficient |
| Failed login                       | logged at WARN level via `logging_config.py` | **ADD** an explicit security log line so a future log-aggregator can grep |
| Privilege change (role PATCH)      | not logged               | **ADD** — one log line per change, attributable to actor |
| User deletion                      | not logged               | **ADD** — same |
| Rate-limit trip                    | n/a (not implemented)    | covered by 3.2 implementation |

Out-of-scope for this round: full audit table in the DB. The plan
explicitly says structured-log first, dedicated table later. A row in
Postgres is more durable but adds schema and migration churn we don't
need before the defense.

### 3.7 Prompt injection (LAYER 2 specific)

This is mostly already implemented. Inventory:

- Static regex scanner (`models/LAYER_2/security/static_patterns.py`)
  — 30+ patterns at low/medium/high/critical.
- LLM-backed detector (escalates on medium+).
- Transcript sandboxing wrapper used by the rating LLM.
- 13 adversarial fixtures (`tests/adversarial.json` + 3 unit tests).

Recommendation: **no new code**, but verify the scanner is on by
default in `PipelineSettings` (it is — `injectionScan="static"`),
and add this as an explicit row in the test plan.

### 3.8 Disclosure policy

| Item                                      | Today | Recommendation |
|-------------------------------------------|-------|----------------|
| Security contact published                | no    | **ADD** `SECURITY.md` at repo root with NasrEldin's address |
| Coordinated disclosure window stated      | no    | **ADD** — 90-day standard |

---

## 4. Selected control set (commits to plan)

Out of the catalog, the implementation round picks:

| #   | Control                                             | Section |
|-----|------------------------------------------------------|---------|
| C-1 | Rate-limit `/auth/login` and `/auth/invite/accept`   | 3.2     |
| C-2 | HTTP security headers middleware                     | 3.3     |
| C-3 | Reject default `SECRET_KEY` when `DEBUG=false`       | 3.1     |
| C-4 | Sanitize uploaded filename                           | 3.4     |
| C-5 | Enforce password length window (8–72 bytes)          | 3.1     |
| C-6 | Structured security-event log lines (login fail, role/status PATCH, user DELETE) | 3.6 |
| C-7 | `.gitleaks.toml` allowlist for `.env.example`        | 3.5     |
| C-8 | `SECURITY.md` disclosure policy at repo root         | 3.8     |

Each picks up at most ~50 lines of code. Total surface is small enough
to verify exhaustively (see `SECURITY_PLAN.md` §6).

Deferred with reason:
- 2FA — UX cost not justified at ten users.
- Argon2id — bcrypt is fine in this threat model.
- Full audit table — structured logs first, table when we move to Postgres.
- nginx `limit_req` zone — covered in deploy phase.
- HSTS preload — academic deployment, not public.

---

## 5. Risk register (post-controls)

| ID  | Risk                                              | Likelihood | Impact | Mitigation                              | Residual |
|-----|---------------------------------------------------|------------|--------|------------------------------------------|----------|
| R-1 | Brute force `/auth/login`                         | M          | H      | C-1 (10/min/IP) + bcrypt cost-12         | Low      |
| R-2 | Stolen JWT via XSS in SPA                         | L          | H      | C-2 (CSP + `X-Content-Type-Options`); JWT lives in localStorage by SPA design | Low-Medium |
| R-3 | Path traversal via uploaded filename              | L          | H      | C-4 (basename + control-char strip)      | Low      |
| R-4 | Prod boots with dev `SECRET_KEY`                  | M          | Critical | C-3 (startup refuses to import)         | Very Low |
| R-5 | bcrypt 5.x raises on >72-byte password (UX bug)   | M          | L      | C-5 (reject early, clear error)          | Very Low |
| R-6 | Insider role-change goes uninvestigated           | L          | M      | C-6 (structured log line per change)     | Low      |
| R-7 | Secret pushed to repo                             | L          | Critical | gitleaks (already CI) + C-7 allowlist; CODEOWNERS gates auth files | Low |
| R-8 | Customer-service caller injects prompts           | M          | H      | LAYER 2 scanner (static + LLM + sandbox); 13 adversarial tests | Low |
| R-9 | Backup at `/srv/backups/calltone/` exfiltrated    | L          | Critical | NAS access list; covered by deploy plan §5 | Medium |
| R-10| TLS misconfiguration                              | L          | M      | nginx + certbot (deploy plan); Mozilla intermediate | Low |

The two residuals worth calling out:
- **R-2 (Medium-residual)**: localStorage-based JWT is intentional (the
  SPA cannot use httpOnly cookies without re-architecting the auth
  flow). CSP shrinks the blast radius from "anyone can pop a token"
  to "only same-origin script can," which is a real reduction.
- **R-9 (Medium-residual)**: backups are out of the application's
  reach. Mitigated by ops (filesystem perms on the NAS), not code.

---

## 6. What this study deliberately does not cover

- **Frontend dependency hygiene** — handled by Dependabot (already
  configured) plus weekly `npm audit` in CI.
- **Container image scanning (Trivy)** — promised in `DEPLOYMENT_PLAN.md`
  §3 future-additions and tracked there, not here.
- **Pen-test report** — would be valuable, is out of student-team budget.
- **Compliance frameworks (SOC 2, ISO 27001)** — single academic
  deployment, no contract requires them.

These remain real items. Listing them here so the reader knows they
were considered and consciously deferred, not forgotten.

---

## 7. Bottom line

The 8-control set in §4 is the minimum that makes the public attack
surface (`/auth/*`, `/api/health*`, `/api/calls/upload`) defensible
and the operational secrets (`SECRET_KEY`, `.env.prod`) non-trivial
to mishandle. Together they close every P0/P1 gap we found in the
inventory pass without expanding the deployment footprint or adding
any infrastructure dependency (no Redis, no auth provider, no WAF).

Implementation, verification, and rollback live in `SECURITY_PLAN.md`.
