#!/usr/bin/env bash
# ─── rollback.sh ───────────────────────────────────────────────────────────
# Manual rollback to a previous tag. Use when CI rollback didn't fire
# (e.g. a runner died) or when a regression is found post-deploy.
#
# Usage:
#   sudo ./scripts/rollback.sh prod v0.3.1
#   sudo ./scripts/rollback.sh staging <sha-or-ref>
#
# Volumes (uploads, database, context) survive the rollback because
# they live outside the container image.
# ───────────────────────────────────────────────────────────────────────────

set -euo pipefail

ENV="${1:-}"
TARGET="${2:-}"

usage() {
  echo "Usage: $0 <staging|prod> <git-ref>"
  echo "Example: $0 prod v0.3.1"
  exit 2
}

[ -n "$ENV" ] && [ -n "$TARGET" ] || usage
case "$ENV" in
  staging|prod) ;;
  *) usage ;;
esac

ROOT="/opt/calltone/${ENV}"
ENV_FILE="${ROOT}/.env.${ENV}"
COMPOSE="docker compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.${ENV}.yml"

[ -d "$ROOT" ]      || { echo "missing $ROOT"; exit 1; }
[ -f "$ENV_FILE" ]  || { echo "missing $ENV_FILE"; exit 1; }

cd "$ROOT"

# Capture current ref so we can re-roll forward if needed
CURRENT=$(git rev-parse --short HEAD)
echo "current ref: ${CURRENT}"
echo "rolling back to: ${TARGET}"
read -r -p "proceed? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "aborted"; exit 0; }

git fetch --quiet --tags origin
git checkout --quiet "$TARGET"

$COMPOSE up -d --build --remove-orphans

# Wait for healthcheck (max 90s)
for i in $(seq 1 45); do
  if curl -fsS "http://localhost:$([ "$ENV" = "prod" ] && echo 8000 || echo 8001)/api/health" >/dev/null 2>&1; then
    echo "rollback healthy after ${i}s"
    echo "you rolled back from ${CURRENT} to $(git rev-parse --short HEAD)"
    exit 0
  fi
  sleep 2
done

echo "rollback container did not become healthy in 90s — manual investigation required" >&2
exit 1
