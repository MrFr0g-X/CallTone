#!/usr/bin/env bash
# ─── post_deploy_smoke.sh ──────────────────────────────────────────────────
# 5-check smoke test that runs after each deploy (staging + prod).
# Exits non-zero on the first failure so the calling workflow can react
# (typically by rolling back).
#
# Required env vars:
#   SMOKE_BASE_URL          e.g. http://localhost:8000
#   SMOKE_ADMIN_EMAIL       seeded admin user
#   SMOKE_ADMIN_PASSWORD    that user's password (passed as a CI secret)
#
# Optional:
#   SMOKE_MIN_FREE_GB       minimum free disk; default 10
# ───────────────────────────────────────────────────────────────────────────

set -euo pipefail

: "${SMOKE_BASE_URL:?SMOKE_BASE_URL is required}"
: "${SMOKE_ADMIN_EMAIL:?SMOKE_ADMIN_EMAIL is required}"
: "${SMOKE_ADMIN_PASSWORD:?SMOKE_ADMIN_PASSWORD is required}"
: "${SMOKE_MIN_FREE_GB:=10}"

GREEN="\033[32m"
RED="\033[31m"
RESET="\033[0m"

ok()   { printf "${GREEN}  ✓ %s${RESET}\n" "$*"; }
fail() { printf "${RED}  ✗ %s${RESET}\n" "$*" >&2; exit 1; }

# ── 1/5 — liveness ────────────────────────────────────────────────────────
echo "[1/5] liveness — GET /api/health"
code=$(curl -s -o /dev/null -w "%{http_code}" "${SMOKE_BASE_URL}/api/health")
[ "$code" = "200" ] || fail "/api/health returned $code (expected 200)"
ok "liveness"

# ── 2/5 — readiness (DB ping, disk, GPU) ─────────────────────────────────
echo "[2/5] readiness — GET /api/health/detailed"
detailed=$(curl -fsS "${SMOKE_BASE_URL}/api/health/detailed") || fail "detailed health failed"

# Tolerate either {"status":"ok"} or {"db":{"status":"ok"},...}
echo "$detailed" | grep -qiE '"(status|db)"\s*:\s*"?ok"?' \
  || fail "detailed health did not report ok: $detailed"

# Free-disk check (best-effort: only if the field exists)
free_gb=$(echo "$detailed" | grep -oE '"free_gb"\s*:\s*[0-9.]+' | grep -oE '[0-9.]+' || echo "")
if [ -n "$free_gb" ]; then
  awk -v f="$free_gb" -v m="$SMOKE_MIN_FREE_GB" \
    'BEGIN { exit (f+0 < m+0) ? 1 : 0 }' \
    || fail "free disk ${free_gb}GB below threshold ${SMOKE_MIN_FREE_GB}GB"
  ok "readiness (free=${free_gb}GB)"
else
  ok "readiness"
fi

# ── 3/5 — auth happy path ────────────────────────────────────────────────
echo "[3/5] auth — POST /api/auth/login"
login_body=$(jq -nc \
  --arg e "$SMOKE_ADMIN_EMAIL" \
  --arg p "$SMOKE_ADMIN_PASSWORD" \
  '{email:$e, password:$p}')

login_resp=$(curl -fsS -X POST \
  -H "Content-Type: application/json" \
  -d "$login_body" \
  "${SMOKE_BASE_URL}/api/auth/login") || fail "login request failed"

token=$(echo "$login_resp" | jq -er '.token // .access_token') \
  || fail "login response had no token field: $login_resp"
ok "auth (token issued)"

# ── 4/5 — RBAC happy path ────────────────────────────────────────────────
echo "[4/5] rbac — GET /api/admin/users with admin token"
admin_resp=$(curl -fsS \
  -H "Authorization: Bearer $token" \
  "${SMOKE_BASE_URL}/api/admin/users") || fail "/api/admin/users failed"

echo "$admin_resp" | jq -e '.users | length > 0' >/dev/null \
  || fail "admin/users returned empty user list"
ok "rbac (users listed)"

# ── 5/5 — upload boundary check (rejects non-audio) ──────────────────────
echo "[5/5] upload boundary — POST /api/calls/upload with text/plain"
not_audio=$(mktemp)
echo "this is not audio" > "$not_audio"
trap 'rm -f "$not_audio"' EXIT

reject_code=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $token" \
  -F "file=@${not_audio};type=text/plain" \
  "${SMOKE_BASE_URL}/api/calls/upload")

# Expect 4xx — anything else means the upload boundary regressed
case "$reject_code" in
  4??) ok "upload boundary (rejected with $reject_code)" ;;
  *)   fail "upload boundary accepted non-audio (got $reject_code, expected 4xx)" ;;
esac

# ── all green ────────────────────────────────────────────────────────────
echo
printf "${GREEN}smoke OK — deploy is healthy${RESET}\n"
