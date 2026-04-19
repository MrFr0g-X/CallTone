# CallTone — Security Plan

**Author:** NasrEldin Khaled (IT) · **Date:** 2026-04-19

This is the executable counterpart to `SECURITY_STUDY.md`. It commits
to the eight controls (C-1 … C-8) selected in §4 of the study, lays
out the file layout, the verification commands, the rollback path,
and the incident-response runbook.

The structure mirrors `DEPLOYMENT_PLAN.md` so a reviewer can read both
documents the same way.

---

## 1. Scope summary

| #   | Control                                              | Layer       | Files touched (planned)                         |
|-----|-------------------------------------------------------|-------------|--------------------------------------------------|
| C-1 | Login / invite-accept rate limit                      | Backend     | `backend/app/rate_limit.py` (new), `main.py`     |
| C-2 | HTTP security-headers middleware                      | Backend     | `backend/app/security_headers.py` (new), `main.py` |
| C-3 | Production `SECRET_KEY` startup guard                 | Backend     | `backend/app/database.py`                        |
| C-4 | Upload filename sanitization                          | Backend     | `backend/app/main.py` (upload handler)           |
| C-5 | Password length window 8–72 bytes                     | Backend     | `backend/app/main.py` (invite-accept)            |
| C-6 | Structured security-event log lines                   | Backend     | `backend/app/main.py` (login, role, status, delete) |
| C-7 | `.gitleaks.toml` allowlist                            | Repo root   | `.gitleaks.toml` (new)                           |
| C-8 | Public security policy                                | Repo root   | `SECURITY.md` (new)                              |
| —   | Test coverage for C-1..C-6                            | Tests       | `backend/tests/test_security.py` (new)           |

Total planned diff: ~250 lines added, 0 lines removed (purely additive).

---

## 2. Implementation details — per control

### C-1 — Login / invite-accept rate limit

**Goal.** Stop credential-stuffing scripts without adding Redis.

**Design.** In-process token bucket keyed on client IP. 10 attempts
per minute per IP per endpoint. Bucket lives in module state
(thread-safe via `threading.Lock`). Sufficient because:
- single-box deploy → single uvicorn process
- ten reviewers → bucket cardinality is tiny
- if we ever go multi-instance, swap the storage for Redis without
  changing the call-site

**Files.** `backend/app/rate_limit.py` (new, ~50 lines):
- `class RateLimiter` with `(key, max, window_seconds)` constructor
- `def check(key) -> None` raises `HTTPException(429)` on overflow
- one shared instance per limited endpoint, declared at module top

`backend/app/main.py`: import the limiter, call `check(request.client.host)`
at the top of `/auth/login` and `/auth/invite/accept`.

**Why not `slowapi`.** `slowapi` is a fine library, but pulling it in
means a new dep + a global limiter object that ties our middleware
order to its `Request.state` contract. A 50-line bucket is easier to
audit and has zero supply-chain surface.

**Configurable.** Limits read from env: `RATE_LIMIT_LOGIN_PER_MINUTE`
(default 10), `RATE_LIMIT_INVITE_ACCEPT_PER_MINUTE` (default 5).
Tests force the limits to 3 to keep them fast.

### C-2 — HTTP security-headers middleware

**Goal.** Shrink XSS / clickjacking / MIME-sniff blast radius cheaply.

**Design.** A single `BaseHTTPMiddleware` that injects, on every
response:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-site
```

`'unsafe-inline'` for styles is required by Tailwind's runtime utility
classes; we accept it. Scripts stay strict.

**HSTS gating.** Only set HSTS when `DEBUG=false` so local development
over `http://localhost` keeps working.

**Files.** `backend/app/security_headers.py` (new, ~40 lines), wired
in `main.py` after the CORS middleware (order matters — security
headers should outermost-wrap responses, after CORS handles its own
preflight).

### C-3 — Production `SECRET_KEY` startup guard

**Goal.** Prevent the most common single-box deploy footgun: shipping
prod with `SECRET_KEY="dev-secret-key-change-in-production"`.

**Design.** In `database.py::Settings`, after `BaseSettings` resolves
env vars, raise `RuntimeError` if all of:
- `DEBUG is False`
- `SECRET_KEY == "dev-secret-key-change-in-production"`

This is a startup-time check — uvicorn won't even bind a port if the
guard fails. Tests stay green because `conftest.py` sets
`SECRET_KEY="test-secret-key-not-for-production"` (different string).

**Why a `RuntimeError` and not a warning.** A warning is a footgun.
The whole point is to make this misconfiguration impossible to ship.

### C-4 — Upload filename sanitization

**Goal.** Defang any path-traversal in `file.filename`. Today the
handler does `dest = UPLOAD_DIR / f"{call_id}_{file.filename}"`. The
UUID prefix happens to make traversal harder, but does not eliminate
it: `f"{uuid}_../../../../etc/passwd"` still resolves outside
`UPLOAD_DIR` on most filesystems.

**Design.** Helper `_sanitize_filename(name: str) -> str`:
- empty / None → `"upload.bin"`
- take basename only (`os.path.basename`) — strip any `/` or `\`
- collapse non-`[A-Za-z0-9._-]` to `_`
- truncate to 80 chars (preserve extension)
- if result is empty after sanitization → `"upload.bin"`

Pure function, lives next to the upload handler in `main.py`. Five
lines of code, zero dependencies.

**Verification.** Adversarial inputs in
`backend/tests/test_security.py::test_filename_sanitization`:
- `"../../../etc/passwd"` → `"etc_passwd"` (no leading dots, no slashes)
- `"normal.wav"` → unchanged
- `""` → `"upload.bin"`
- `"a"*200` → truncated to 80
- `"audio\x00.wav"` → no NUL byte in result

### C-5 — Password length window 8–72 bytes

**Goal.** Make the bcrypt 72-byte cap explicit instead of letting
bcrypt 5.x raise a confusing `ValueError` at hash time.

**Design.** In the `/auth/invite/accept` handler, after the existing
`len(password) < 8` check, add:

```python
if len(password.encode("utf-8")) > 72:
    raise HTTPException(
        status_code=400,
        detail="Password must be at most 72 bytes (UTF-8). "
               "Bcrypt does not store more.",
    )
```

UTF-8 bytes, not chars — a Cyrillic password of "only" 40 chars can
exceed 72 bytes.

**Why 72 not arbitrary.** 72 is the bcrypt spec's input ceiling, the
exact number `bcrypt<4.1` silently truncates at and `bcrypt>=5.0`
raises on. We adopt the underlying limit instead of inventing a
different one.

### C-6 — Structured security-event log lines

**Goal.** A future log aggregator (Loki, CloudWatch) should be able
to grep `event=login_failed` or `event=role_changed` and get a clean
timeline without parsing free-text English.

**Design.** Use the existing `logging_config.py` formatter (already
emits JSON with `extra=` field merging — see commit `b2564bd`).
Add four call sites:

| Endpoint                                            | Event                | Extras                                              |
|-----------------------------------------------------|----------------------|-----------------------------------------------------|
| `POST /auth/login` (failure path)                   | `login_failed`       | `email`, `client_ip`                                |
| `PATCH /admin/users/{id}/role`                      | `role_changed`       | `actor_id`, `target_user_id`, `old_role`, `new_role` |
| `PATCH /admin/users/{id}/status`                    | `status_changed`     | `actor_id`, `target_user_id`, `old_status`, `new_status` |
| `DELETE /admin/users/{id}`                          | `user_deleted`       | `actor_id`, `target_user_id`, `target_email`        |

Implementation cost: ~3 lines per call site. Zero new dependencies.
The `event=` key is a stable contract for future tooling.

### C-7 — `.gitleaks.toml` allowlist

**Goal.** The `.env.example` file shipped in the CD work uses
placeholders like `replace-with-openssl-rand-hex-32`. Default
gitleaks sometimes flags these because they look like 64-char hex
slots — a false positive that, repeated weekly, trains the team to
ignore alerts.

**Design.** A `.gitleaks.toml` at repo root that:
- inherits the default ruleset
- allowlists paths matching `^\.env\.example$`
- allowlists regex `replace-with-` and `hf_replace_me`

Twenty lines of TOML. The allowlist is intentionally tight so a real
secret committed to a different file still trips.

### C-8 — `SECURITY.md` disclosure policy

**Goal.** GitHub renders this file in the Security tab and on the
"Report a vulnerability" prompt. Without it, a researcher who finds
a bug has no documented contact and falls back to opening a public
issue — which is exactly what we want to avoid.

**Design.** Repo root, ~40 lines:
- supported versions (`main` only — single deployment)
- contact (`s-nasreldin.mohamed@zewailcity.edu.eg`)
- response SLA (best-effort within 5 working days)
- coordinated disclosure window (90 days)
- explicit "do not file public GitHub issues for security bugs"

---

## 3. Build sequence

Run in order. Each step is independent enough that it can be verified
on its own, but the order minimises rework if a step fails.

1. **C-7** `.gitleaks.toml` — pure config, no test impact.
2. **C-8** `SECURITY.md` — pure docs.
3. **C-3** `SECRET_KEY` guard — single-line addition in `database.py`.
4. **C-2** Security headers middleware — additive middleware.
5. **C-4** Filename sanitization helper — pure function.
6. **C-5** Password length cap — single-line addition in invite-accept.
7. **C-6** Security event logs — three-line additions × 4 call sites.
8. **C-1** Rate limiter — new module + two call sites.
9. **Tests** `backend/tests/test_security.py` — covers C-1, C-2, C-4, C-5, C-6.

The tests intentionally come last so they exercise the integrated
state, not a half-written intermediate.

---

## 4. Test plan

New test file: `backend/tests/test_security.py`.

| Test                                          | Verifies | How                                  |
|-----------------------------------------------|----------|---------------------------------------|
| `test_login_returns_security_headers`         | C-2      | GET `/`, assert each header present  |
| `test_csp_header_is_set`                      | C-2      | assert `Content-Security-Policy` value |
| `test_filename_sanitization_strips_traversal` | C-4      | direct call to `_sanitize_filename`  |
| `test_filename_sanitization_caps_length`      | C-4      | direct call, 200-char input          |
| `test_filename_sanitization_handles_empty`    | C-4      | empty + None → `"upload.bin"`        |
| `test_password_too_long_rejected`             | C-5      | invite + accept with 100-char pw → 400 |
| `test_password_too_short_rejected`            | C-5 (regression) | 6-char pw → 400 (existing behaviour) |
| `test_login_rate_limit_trips_at_n+1`          | C-1      | login 3× wrong (limit lowered via env), 4th → 429 |
| `test_failed_login_emits_security_log`        | C-6      | capsys-capture, assert `event=login_failed` |
| `test_role_change_emits_security_log`         | C-6      | PATCH role, assert log line shape    |

C-3 (SECRET_KEY guard) is verified manually because the guard fires
at import time — exercising it inside an already-imported pytest
process is contrived. Manual repro: set `DEBUG=false` and unset
`SECRET_KEY`, confirm uvicorn refuses to start.

C-7 (gitleaks allowlist) is verified by re-running gitleaks in CI
and confirming `.env.example` no longer triggers.

C-8 (SECURITY.md) is verified by GitHub rendering it under the
Security tab — visible on first push.

---

## 5. Verification rituals

### 5.1 Verification pass #1 (pre-commit)

```bash
# Backend unit tests
DB_HOST="" pytest backend/tests/ -v --no-cov

# Skill validator (regression — should still pass)
pytest models/skill_implementation/tests/ -v --no-cov

# Security scanner self-tests (regression)
pytest models/LAYER_2/security/tests/ -v --no-cov

# Frontend (regression)
cd calltone-UI && npm test -- --run

# Boot the app — confirm middleware order doesn't break anything
cd backend && uvicorn app.main:app --port 8001 &
sleep 5
curl -s http://localhost:8001/api/health | grep '"ok"'
curl -sI http://localhost:8001/ | grep -i 'content-security-policy'
curl -sI http://localhost:8001/ | grep -i 'x-frame-options'
kill %1
```

### 5.2 Verification pass #2 (independent re-read)

Same suite, plus:

- `git diff --stat origin/main..HEAD` to confirm only the planned files
  changed
- `git diff backend/app/main.py` re-read line by line for unintended
  side-effects on the 30 existing endpoints
- `bandit -r backend/app -ll` locally — should report **no new** medium+ findings
- `pytest backend/tests/ models/skill_implementation/tests/ models/LAYER_2/security/tests/ -v --no-cov` re-run to confirm idempotence

If any step fails, fix-or-revert before commit. Do not commit on a red
suite.

---

## 6. Rollback

Every control is purely additive. Rollback is a single revert.

| Control | Rollback                                                            |
|---------|----------------------------------------------------------------------|
| C-1     | `git revert <sha>` — middleware vanishes, login goes back to unbounded |
| C-2     | same — headers stop being injected                                   |
| C-3     | same — guard removed, but unset `SECRET_KEY` still falls back to dev default |
| C-4     | same — `file.filename` flows raw again (regression — only revert if it breaks a real upload, then re-fix in place) |
| C-5     | same — bcrypt 5.x's `ValueError` returns to bite users               |
| C-6     | same — log lines stop emitting, no functional impact                 |
| C-7     | `rm .gitleaks.toml` — gitleaks falls back to defaults                |
| C-8     | `git revert` — file disappears, GitHub Security tab returns to default |

There is no schema migration, no env-var rename, no nginx-config
change. Rollback time: under one minute.

---

## 7. Incident response — minimal runbook

**Scope.** A genuine security incident (credential leak, suspected
compromise, rate-limit triggered repeatedly from the same IP).

| Step | What                                                | Owner   | SLA |
|------|------------------------------------------------------|---------|-----|
| 1    | Page NasrEldin via Discord `#calltone-ops`          | Whoever notices | < 5 min |
| 2    | If credential leak: rotate `SECRET_KEY` in `.env.prod` and `docker compose restart backend` (invalidates **all** JWTs) | NasrEldin | < 30 min |
| 3    | If repo leak: rotate the leaked secret, push a revert, run `gitleaks detect --redact` on the affected branch | Hothifa + NasrEldin | < 1 h |
| 4    | If suspected account compromise: PATCH the user's `is_active` to false via the admin endpoint | any admin | < 15 min |
| 5    | Capture logs from `/var/log/calltone-archive/` for the incident window into a private gist | NasrEldin | < 24 h |
| 6    | Post-mortem note appended to `docs/BUGS.md` | NasrEldin | < 7 days |

The runbook deliberately punts a lot to "rotate + restart." A small
single-box deploy can absorb the JWT-invalidation pain (everyone has
to log in again); a larger deployment would need refresh-token-aware
revocation. We don't have that and don't need it for the defense.

---

## 8. Secrets matrix (security view)

Rephrases `DEPLOYMENT_PLAN.md` §5 from a security angle — what each
secret protects and what happens if it leaks.

| Secret              | Protects                              | If leaked, the attacker can …                | Rotation trigger |
|---------------------|----------------------------------------|----------------------------------------------|------------------|
| `SECRET_KEY`        | JWT integrity                          | Forge any user's session — full takeover     | Per release; immediately on suspicion |
| `POSTGRES_PASSWORD` | DB read/write                          | Exfiltrate transcripts, alter scores         | Quarterly; on suspicion |
| `HF_TOKEN`          | pyannote weight download               | Re-download what is already on disk          | When HF rotates; not security-critical |
| `DB_PASSWORD`       | App-side DB connection                 | Same as `POSTGRES_PASSWORD`                  | Same as Postgres |
| Backup NAS creds    | `/srv/backups/calltone/`               | Exfiltrate full DB history                   | Yearly; on departure of any admin |
| Admin user passwords| Admin role inside the app              | Invite arbitrary users, change roles, delete | On user request; on departure |

The "If leaked" column is what threat modelling people call the
**adversary capability**. Useful for prioritising which alarm to
trip first.

---

## 9. Pre-release security checklist

Append to `DEPLOYMENT_PLAN.md` §9 the following extra rows:

- [ ] `SECRET_KEY` in `.env.prod` is **not** the dev default (covered by C-3 startup guard, double-check anyway)
- [ ] `bandit -r backend/app -ll` reports zero medium-or-higher findings on `main`
- [ ] `gitleaks detect --no-git --source .` reports zero leaks (with `.gitleaks.toml` allowlist applied)
- [ ] CI Security workflow last run is green
- [ ] HSTS, CSP, X-Frame-Options headers visible in `curl -I https://stage.calltone.local`
- [ ] Login rate-limit trips on the 11th attempt within a minute (manual smoke)
- [ ] Backup of `calltone-db` volume taken in last 25 h (`/srv/backups/calltone/`)

---

## 10. What remains open (post-defense)

| Item                                              | Owner     | When           |
|---------------------------------------------------|-----------|----------------|
| Move JWT to httpOnly cookie + add CSRF tokens     | NasrEldin | post-defense   |
| Argon2id password upgrade with online rehash      | NasrEldin | post-defense   |
| Audit-log table in Postgres (replace structured-log-only) | NasrEldin | post-defense |
| 2FA / TOTP for admin-role accounts                | NasrEldin | post-defense   |
| nginx `limit_req` zone tuned to match C-1         | Hothifa   | deploy phase   |
| Trivy container scan in CI                        | Hothifa   | deploy phase   |
| Pen-test by a third party                         | (out)     | not in budget  |

These are the items that cost more than they buy at the academic
deliverable scale, and so are tracked here rather than implemented now.
