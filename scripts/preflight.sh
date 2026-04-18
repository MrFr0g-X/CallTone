#!/usr/bin/env bash
# ─── preflight.sh ──────────────────────────────────────────────────────────
# Pre-release checklist runner. Mirrors §9 of DEPLOYMENT_PLAN.md.
# Run before tagging a release:
#
#   ./scripts/preflight.sh
#
# Exits non-zero on the first hard failure. Soft warnings keep going.
# ───────────────────────────────────────────────────────────────────────────

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
WARN=0
FAIL=0

check() {  # check "name" "command"
  local name="$1" cmd="$2"
  printf "  ▸ %-55s " "$name"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "OK"
    PASS=$((PASS+1))
  else
    echo "FAIL"
    FAIL=$((FAIL+1))
  fi
}

soft() {   # soft "name" "command"
  local name="$1" cmd="$2"
  printf "  ▸ %-55s " "$name"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "OK"
    PASS=$((PASS+1))
  else
    echo "WARN"
    WARN=$((WARN+1))
  fi
}

echo "[1] Repository state"
check "clean working tree"             "git diff --quiet && git diff --cached --quiet"
check "on main or release branch"      "[[ \$(git branch --show-current) =~ ^(main|release/.*)$ ]]"

echo
echo "[2] Backend tests"
check "pytest backend/tests/ green"    "cd backend && python -m pytest tests/ -q --no-cov"
check "pytest skill tests green"       "python -m pytest models/skill_implementation/tests/ -q --no-cov"
check "pytest security tests green"    "python -m pytest models/LAYER_2/security/tests/ -q --no-cov"

echo
echo "[3] Frontend"
check "vitest green"                   "cd calltone-UI && npm test -- --run"
check "production build succeeds"      "cd calltone-UI && npm run build"

echo
echo "[4] Models"
soft  "Llama GGUF present"             "test -f models/skill_implementation/models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"
soft  "SenseVoice present"             "test -d models/LAYER_1/models/sensevoice"
soft  "pyannote present"               "test -d models/LAYER_1/models/pyannote"
soft  "resemble-enhance present"       "test -d models/LAYER_1/resemble-enhance"

echo
echo "[5] Secrets / env"
check "no .env tracked in git"         "! git ls-files | grep -E '^\\.env(\\..*)?$'"
soft  ".env.example exists"            "test -f .env.example"

echo
echo "[6] Docs"
check "audit doc present"              "ls docs/AUDIT_*.md >/dev/null"
check "deployment plan present"        "test -f docs/DEPLOYMENT_PLAN.md"
check "deployment study present"       "test -f docs/DEPLOYMENT_STUDY.md"

echo
echo "─────────────────────────────────────────"
printf "  PASS=%d  WARN=%d  FAIL=%d\n" "$PASS" "$WARN" "$FAIL"
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ] || exit 1
echo "preflight OK — safe to tag."
