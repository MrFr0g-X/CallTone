# CallTone — Deployment Plan & CI/CD

**Author:** Hothifa Hamdan (DSAI) · **Date:** 2026-04-18

This is the executable counterpart to `DEPLOYMENT_STUDY.md`. It commits
to **Option A (single-box on-prem)** and lays out the environments, the
CI/CD pipeline, the release ritual, and the rollback path.

---

## 1. Environments

| Env       | Purpose                              | Where                          | URL                                  | Auto-deploys from     |
|-----------|--------------------------------------|--------------------------------|--------------------------------------|-----------------------|
| **local** | Daily development                    | Each contributor's laptop      | `http://localhost:8080`              | n/a (use `run_local.bat`) |
| **staging** | Integration testing + demo rehearsal | Staging container on the GPU box | `https://stage.calltone.local`     | every push to `main`  |
| **prod**  | Supervisor demo + jury defense       | Production container, same box | `https://calltone.local`             | every git tag `v*.*.*` |

Staging and prod share the GPU box but live in **separate Docker
networks** with separate Postgres volumes, so a staging seed dump can
never overwrite the demo data. The Nginx reverse proxy multiplexes by
hostname.

---

## 2. Branching model

```
main      ← always green (CI passes), deploys to staging on merge
└── feat/*  ← short-lived feature branches, PR into main
└── fix/*   ← bug-fix branches
└── chore/* ← infra/tooling
```

Tags `v*.*.*` deploy to prod. Hotfix path: branch off the prod tag,
PR straight to `main`, then re-tag.

---

## 3. CI pipeline (already implemented)

**File:** `.github/workflows/ci.yml`

Three parallel jobs run on every push and PR:

```yaml
jobs:
  backend:    # Python 3.11, pip install + pytest -v
  skills:     # skill_implementation/tests/ — determinism + validator
  frontend:   # Node 20, npm ci + vitest run + npm run build
```

Each job:
- runs in < 90 s on GitHub-hosted runners
- uses **concurrency cancellation** — pushing a new commit cancels the
  in-flight run for the same ref, saving CI minutes
- caches `~/.cache/pip` and `node_modules` keyed on lockfile hashes

**Required checks** for merge to `main`: all three jobs green.

### What CI does NOT do (and why)

- **Does not run the audio pipeline.** No GPU on GitHub runners; the
  pipeline is exercised by `models/LAYER_1/test_pipeline.py` on the
  GPU box manually before each tag.
- **Does not download model weights.** 12.5 GB pull on every build is
  wasteful; weights are pinned via SHA-256 in `download_models.py`
  and cached on the deploy host.
- **Does not push images.** Single-box deploy uses `docker compose up
  --build` on the host; no registry needed for v1.

### Future additions (post-defense)

- Coverage gate (fail if backend coverage drops below 60 %).
- Trivy scan of the built image.
- Lighthouse CI on the built frontend.

---

## 4. CD pipeline

### 4.1 Staging (continuous on push to `main`)

A self-hosted runner on the GPU box listens on the `gpu-stage` label.
On every merge:

```yaml
deploy-staging:
  runs-on: [self-hosted, gpu-stage]
  needs: [backend, skills, frontend]
  steps:
    - uses: actions/checkout@v4
    - run: |
        cd /opt/calltone/staging
        git pull --ff-only
        docker compose --env-file .env.staging up -d --build
        sleep 15
        curl -fsS http://localhost:8001/api/health/detailed || exit 1
```

Verifies health, then a Discord webhook posts the staging URL + the
git SHA to the team channel.

### 4.2 Production (manual, on tag)

Tagging is deliberate:

```bash
git tag v0.4.0
git push origin v0.4.0
```

The tag triggers:

```yaml
deploy-prod:
  if: startsWith(github.ref, 'refs/tags/v')
  runs-on: [self-hosted, gpu-prod]
  environment:
    name: production         # GitHub-protected: requires manual approval
  steps:
    - uses: actions/checkout@v4
    - run: |
        cd /opt/calltone/prod
        git fetch --tags
        git checkout ${{ github.ref_name }}
        docker compose --env-file .env.prod up -d --build
        ./scripts/post_deploy_smoke.sh
```

**`scripts/post_deploy_smoke.sh`** (5 checks, exit on first failure):
1. `curl /api/health` → 200
2. `curl /api/health/detailed` → DB up, free disk > 10 GB, GPU visible
3. login as seeded admin → JWT issued
4. GET `/api/admin/users` with that JWT → list returned
5. POST a tiny `test.wav` → status `processing` within 2 s

Failure aborts the deploy and leaves the previous container running
because the new container only swaps in after `--up -d --build`
succeeds atomically.

---

## 5. Secrets management

| Secret                  | Where it lives               | Rotation           |
|-------------------------|------------------------------|---------------------|
| `SECRET_KEY` (JWT sign) | GitHub Environments + `.env.prod` (mode 600) | Per release, generated `openssl rand -hex 32` |
| `HF_TOKEN`              | `.env.prod` only             | When HF rotates    |
| `POSTGRES_PASSWORD`     | `.env.prod` only             | Quarterly          |
| Let's Encrypt cert      | `/etc/letsencrypt/`          | Auto, certbot timer |
| GitHub deploy SSH key   | The runner box `~/.ssh/`     | Yearly              |

**Never** commit a `.env*` file. `.gitignore` already covers `.env`,
`.env.local`, `.env.prod`, `.env.staging`.

---

## 6. Rollout cadence

| Phase | Trigger | What happens | Owner |
|-------|---------|--------------|-------|
| Code review | PR opened | At least one teammate approves; CI green | reviewer |
| Merge to `main` | PR merged | Staging auto-deploys within 3 min | author |
| Sanity check | After staging deploy | Whoever merged hits the staging URL and clicks through one happy path | author |
| Tag for prod | After 24 h on staging without incident | `git tag vX.Y.Z && git push --tags` | maintainer (Hothifa) |
| Prod approval | Tag pushed | GitHub Environments asks for manual approval → click | maintainer |
| Smoke test | After prod deploy | `post_deploy_smoke.sh` runs automatically; failure rolls back | CI |
| Notify supervisor | After smoke green | Email with release notes + SHA | maintainer |

---

## 7. Rollback

Two layers of safety:

### 7.1 Container-level rollback (seconds)

```bash
cd /opt/calltone/prod
git checkout <previous-tag>
docker compose up -d --build
./scripts/post_deploy_smoke.sh
```

The Docker volumes (`calltone-uploads`, `calltone-db`,
`calltone-context`) survive container replacement, so user data is
preserved across the rollback.

### 7.2 Database rollback (minutes)

Nightly `pg_dump` is rsynced to the team NAS at `/srv/backups/calltone/`.
Restore:

```bash
docker compose stop backend
docker exec -i calltone-postgres psql -U calltone -d calltone < dump_2026-04-18.sql
docker compose start backend
```

**Schema migrations** (when we move from SQLite to Postgres + Alembic
in v0.5) MUST be designed for forward-only safe rollback: additive
columns + dual-write windows, never destructive `DROP COLUMN` in the
same release as the code that stops using it.

---

## 8. Monitoring & alerts

**Liveness vs readiness:**
- `/api/health` → cheap, used by Docker `HEALTHCHECK` every 30 s.
- `/api/health/detailed` → DB ping, disk free, GPU memory, git SHA;
  polled every 60 s by Uptime-Kuma running on the same box.

**Alert channels:**
- Uptime-Kuma → Discord webhook to `#calltone-ops`.
- Disk free < 10 % → email + Discord.
- Failed pipeline run (status `failed` in DB) → Discord.

**Logs:**
- Backend writes JSON lines to stdout (see `backend/app/logging_config.py`).
- Docker captures via `json-file` driver with `max-size=50m`,
  `max-file=10` (configured in `docker-compose.yml` for prod).
- Aggregated weekly into `/var/log/calltone-archive/` for the report.

---

## 9. Pre-release checklist (run before every prod tag)

Adapted from the audit punch list:

- [ ] All three CI jobs green on the head of `main`.
- [ ] `pytest backend/tests/ -v` green on the GPU box (covers what CI cannot — local DB integration).
- [ ] `python download_models.py --list` shows all 6 weight files present + matching SHA-256.
- [ ] `models/LAYER_1/test_pipeline.py` runs end-to-end on `Test_audio/` and emits a `layer2_ratings.json` with score in [0, 100].
- [ ] `npm run build` in `calltone-UI/` succeeds; bundle size < 1.5 MB gz.
- [ ] `docs/AUDIT_*` punch list has no open P0/P1 items.
- [ ] `.env.prod` `SECRET_KEY` differs from the dev default.
- [ ] Latest backup `/srv/backups/calltone/` is < 25 h old.
- [ ] Supervisor / jury have the staging URL and credentials at least 48 h before the demo.

---

## 10. First-deploy bootstrap (one-time, on a fresh GPU box)

```bash
# 1. System prereqs
sudo apt-get update && sudo apt-get install -y \
    docker.io docker-compose-v2 nvidia-container-toolkit git nginx certbot

# 2. Clone repo
sudo mkdir -p /opt/calltone/{prod,staging}
sudo git clone https://github.com/<owner>/calltone /opt/calltone/prod
sudo git clone https://github.com/<owner>/calltone /opt/calltone/staging

# 3. Download model weights (one-off, ~12.5 GB)
cd /opt/calltone/prod
HF_TOKEN=hf_xxxxx python download_models.py
ln -s /opt/calltone/prod/model-weights /opt/calltone/staging/model-weights

# 4. Configure secrets
sudo install -m 600 /dev/stdin /opt/calltone/prod/.env.prod <<EOF
SECRET_KEY=$(openssl rand -hex 32)
DB_HOST=postgres
DB_USER=calltone
DB_PASSWORD=$(openssl rand -hex 24)
HF_TOKEN=hf_xxxxx
CORS_ORIGINS=https://calltone.local
EOF

# 5. Bring up the stack
cd /opt/calltone/prod
docker compose --env-file .env.prod up -d --build

# 6. Provision TLS via certbot
sudo certbot --nginx -d calltone.local -d stage.calltone.local

# 7. Register the GitHub self-hosted runner
sudo ./actions-runner/config.sh --url https://github.com/<owner>/calltone \
    --token <runner-token> --labels gpu-prod,gpu-stage --replace
sudo ./actions-runner/svc.sh install && sudo ./actions-runner/svc.sh start
```

---

## 11. What remains open

| Item | Owner | When |
|------|-------|------|
| Nginx config + Let's Encrypt automation | Hothifa | post-defense |
| Move from SQLite to PostgreSQL + Alembic | NasrEldin | post-defense |
| Self-hosted runner on the GPU box | Hothifa | post-defense |
| Uptime-Kuma side-car compose service | Hothifa | post-defense |
| `scripts/post_deploy_smoke.sh` | Hothifa | post-defense |
| `.github/workflows/deploy.yml` | Hothifa | post-defense |

These are deferred until **after** the supervisor sign-off because none
of them are required for the academic deliverable — the CI workflow
already exists, the Docker stack already exists, and the manual rollout
ritual is documented above. The deferred work converts the manual
rollout into a fully automated one.
