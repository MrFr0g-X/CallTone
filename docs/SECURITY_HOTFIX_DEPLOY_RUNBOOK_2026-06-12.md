# Security Hotfix — Surgical Deploy Runbook (2026-06-12)

Applies M1 (`backend/app/main.py`) + L1 (`backend/app/database.py`) to the **live
Tier-2 backend** without disturbing anything else. L2 (`model_server/auth.py`) is
deferred until the GPU/Vast box is next rented.

## Why NOT the CI/`main` path
`origin/main` is **44 commits / ~1,361 backend lines behind** this integration
branch. The live VPS runs the integration-branch code (manually deployed in April).
Pushing through CI deploys from `main`, which would **regress prod to old code**.
Do **not** merge to main / dispatch the deploy workflow for this hotfix.

## Safety facts (verified)
- `rsync_repo.sh` excludes `backend/.env`, `backend/uploads/`, `backend/calltone.db*`
  — secrets/DB/uploads are never touched by any sync.
- L1 cannot break boot: prod runs `DEBUG=false` and the **existing** guard already
  forbids the dev-default key under `DEBUG=false`; since prod is live, its
  `SECRET_KEY` is already real. The new `or not use_sqlite` branch only adds
  coverage; it cannot newly trip.
- Both edits are pure-Python on existing files; **no new dependencies**, no DB
  migration. (`hmac` in L2 is stdlib and not deployed now anyway.)
- Local verification: backend pytest 94 passed, model_server 22, frontend 22;
  4 boot-guard cases correct; traversal inputs collapse to safe basenames.

## Connection (from vault `Deployment.md`)
- Prod backend VPS: `91.99.208.254` (Ubuntu 22.04), code at `/opt/calltone-backend/`,
  service `calltone-backend.service`, also `/opt/calltone-backend-staging/`.
- SSH user/port: confirm from your deploy secrets (PROD_BACKEND_USER/PORT). The CI
  uses key `PROD_BACKEND_SSH_KEY` — that key is in GitHub secrets, not on the laptop.

## Procedure (do staging first, then prod)
Run from the repo root on a machine that can SSH to the VPS. Replace `<USER>`,
`<PORT>`, `<DIR>` (`/opt/calltone-backend-staging` first, then `/opt/calltone-backend`).

```bash
# 1. Copy the two patched files up (scp). Nothing else is touched.
scp -P <PORT> backend/app/main.py     <USER>@91.99.208.254:/tmp/main.py.new
scp -P <PORT> backend/app/database.py <USER>@91.99.208.254:/tmp/database.py.new

# 2. On the VPS: back up, swap in, restart, smoke. Rollback is one mv.
ssh -p <PORT> <USER>@91.99.208.254 'bash -s' <<"EOF"
set -e
DIR=/opt/calltone-backend-staging      # <-- do staging FIRST; then rerun with /opt/calltone-backend
ts=$(date +%Y%m%d-%H%M%S)
cp "$DIR/backend/app/main.py"     "$DIR/backend/app/main.py.bak-$ts"
cp "$DIR/backend/app/database.py" "$DIR/backend/app/database.py.bak-$ts"
cp /tmp/main.py.new     "$DIR/backend/app/main.py"
cp /tmp/database.py.new "$DIR/backend/app/database.py"
# Syntax check with the SAME interpreter the service uses (adjust if not system python3):
python3 -c "import py_compile; py_compile.compile('$DIR/backend/app/main.py', doraise=True); py_compile.compile('$DIR/backend/app/database.py', doraise=True)" && echo "compile OK"
sudo systemctl restart calltone-backend-staging   # prod: calltone-backend
sleep 3
sudo systemctl is-active calltone-backend-staging
echo "backup timestamp: $ts"
EOF

# 3. Smoke (must return 200 / status ok):
curl -fsS https://api-staging.calltone.tech/api/health        # staging
curl -fsS https://api-staging.calltone.tech/api/health/detailed

# 4. Only if staging is green, repeat steps 1-3 with DIR=/opt/calltone-backend
#    and the calltone-backend service + https://api.calltone.tech URLs.
```

## Rollback (instant)
```bash
ssh -p <PORT> <USER>@91.99.208.254 \
  'DIR=/opt/calltone-backend; ts=<the printed timestamp>; \
   mv "$DIR/backend/app/main.py.bak-$ts" "$DIR/backend/app/main.py"; \
   mv "$DIR/backend/app/database.py.bak-$ts" "$DIR/backend/app/database.py"; \
   sudo systemctl restart calltone-backend'
```

## Post-deploy verification
- `curl https://api.calltone.tech/api/health` → 200 `{"status":"ok"}`
- Log in on `calltone.tech`, open a call detail (confirms backend healthy).
- `/docs` from an untrusted IP → still 404 (unchanged).
