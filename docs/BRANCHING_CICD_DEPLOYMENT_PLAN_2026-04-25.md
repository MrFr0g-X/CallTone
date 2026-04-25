# CallTone Branching, CI/CD, and Deployment Plan — 2026-04-25

This is the release plan implemented on `integration/release-2026-04-25`.

## Final Branch Route

| Branch | Purpose | Current decision |
|---|---|---|
| `main` | Protected trunk. Only reviewed, tested, deployable code lands here. | Keep as the only long-lived trunk. |
| `integration/release-2026-04-25` | Release integration branch created from `feat/test-suite-and-evidence`. | Use for PR into `main`. |
| `feat/test-suite-and-evidence` | Previous release-candidate branch containing queue, tests, evidence, RBAC, stress tooling, and report docs. | Source branch for integration. |
| `server` | Experimental GPU/server branch. | Selectively ported useful files only. Do not merge blindly. |
| `deploy` | Experimental frontend deployment branch. | Not merged. Its old deploy model was replaced by the 3-tier workflow. |
| `backend` | Old backend feature branch. | No unique required work. Archive after `main` is updated. |

Backup branch created before integration work:

```text
backup/pre-cicd-20260425-050520
```

## Cherry-Pick / Porting Decisions

Useful `server` work was ported:

- `.gitattributes` to normalize line endings and protect binary/model formats.
- `models/LAYER_2/company_context/contexts/bankserv_global.json` expanded context.
- `models/LAYER_2/company_context/contexts/bankserv_global_graph.json`.
- `models/audio_transcription_pipeline.svg` update.
- Backend `/` static-index fallback for all-in-one server mode.
- `VAST_AI_QUICKSTART.sh`, rewritten to match the current 3-server architecture.

Rejected/rewritten work:

- `server_setup.sh` from `server` was removed because it was an old all-in-one deployment script and contained a hardcoded token. It is not safe or correct for the current architecture.
- `deploy` branch workflow was not cherry-picked because it deploys only the frontend from the `deploy` branch. The final workflow deploys from `main`/tags and handles frontend + backend + smoke checks.

## Required Branch Policy

Use this policy in GitHub branch protection:

- Protect `main`.
- Require pull request before merge.
- Require at least one approving review.
- Require conversation resolution.
- Require status checks:
  - `backend (pytest + OpenAPI)`
  - `model-server (pytest)`
  - `Layer 2 skills/security (pytest)`
  - `frontend (vitest + build)`
- Require branches to be up to date before merge.
- Do not allow force pushes to `main`.
- Do not allow deletion of `main`.

Feature work should use:

```text
feat/<area>-<short-summary>
fix/<area>-<short-summary>
```

Production releases should use immutable tags:

```text
v1.0.0
v1.0.1
```

## CI Workflow

File:

```text
.github/workflows/ci.yml
```

Triggers:

- push to `main`,
- push to `integration/**`,
- push to `release/**`,
- push to `feat/**`,
- push to `fix/**`,
- pull request into `main`,
- manual `workflow_dispatch`.

Jobs:

| Job | What it validates | A100 required? |
|---|---|---|
| `backend (pytest + OpenAPI)` | Backend API, RBAC, upload settings, queue behavior, remote pipeline client, OpenAPI export. | No |
| `model-server (pytest)` | Model-server auth, endpoints, job lifecycle with mocked subprocess. | No |
| `Layer 2 skills/security (pytest)` | Skill validation and transcript-bypass prompt-injection blocking. | No |
| `frontend (vitest + build)` | Frontend unit tests and production Vite build. | No |

CI intentionally does not download Qwen, pyannote, Whisper, or Audio2Emotion. Live model tests are expensive and tied to short-lived GPU infrastructure, so they run only as deployment/demo smoke tests.

## Deployment Workflow

File:

```text
.github/workflows/deploy.yml
```

### Staging

Trigger:

- CI success on `main`,
- or manual dispatch with `target=staging`.

Actions:

- Build frontend with `VITE_API_BASE_URL=${{ vars.STAGING_API_BASE_URL }}`.
- Rsync `calltone-UI/dist/` to staging webspace.
- Rsync repository source to staging backend VPS while excluding secrets, uploads, model weights, caches, and generated files.
- Run the configured backend restart command.
- Smoke-test frontend and backend health URLs.

### Production

Trigger:

- push tag `v*.*.*`,
- or manual dispatch with `target=production`.

Guardrails:

- Requires successful CI for the same commit SHA.
- Uses GitHub `production` environment.
- Production environment should require manual approval in repository settings.

Actions:

- Build frontend with `VITE_API_BASE_URL=${{ vars.PROD_API_BASE_URL }}`.
- Rsync frontend to production webspace.
- Rsync backend/source to production VPS with strict excludes.
- Restart backend through the configured command.
- Smoke-test public frontend and backend health.

## GitHub Environments

Create two environments:

```text
staging
production
```

Recommended environment protection:

| Environment | Required reviewers | Deployment branches |
|---|---:|---|
| `staging` | 0 | `main` only |
| `production` | 1+ | tags matching `v*.*.*` only |

## Required GitHub Secrets

Never commit these values.

### Staging

| Secret | Purpose |
|---|---|
| `STAGING_WEBSPACE_HOST` | SSH/SFTP host for staging frontend webspace. |
| `STAGING_WEBSPACE_USER` | SSH username for staging frontend webspace. |
| `STAGING_WEBSPACE_PORT` | SSH port for staging frontend webspace. |
| `STAGING_WEBSPACE_PATH` | Remote directory that receives frontend `dist/`. |
| `STAGING_WEBSPACE_SSH_KEY` | Private key for frontend webspace deploy. |
| `STAGING_BACKEND_HOST` | Staging backend VPS host. |
| `STAGING_BACKEND_USER` | Staging backend SSH user. |
| `STAGING_BACKEND_PORT` | Staging backend SSH port. |
| `STAGING_BACKEND_PATH` | Remote source directory for staging backend. |
| `STAGING_BACKEND_SSH_KEY` | Private key for backend deploy. |

### Production

| Secret | Purpose |
|---|---|
| `PROD_WEBSPACE_HOST` | Production frontend webspace host. |
| `PROD_WEBSPACE_USER` | Production frontend webspace username. |
| `PROD_WEBSPACE_PORT` | Production frontend webspace SSH port. |
| `PROD_WEBSPACE_PATH` | Production frontend remote path. |
| `PROD_WEBSPACE_SSH_KEY` | Private key for frontend deploy. |
| `PROD_BACKEND_HOST` | Production backend VPS host. |
| `PROD_BACKEND_USER` | Production backend SSH user. |
| `PROD_BACKEND_PORT` | Production backend SSH port. |
| `PROD_BACKEND_PATH` | Production backend source path. |
| `PROD_BACKEND_SSH_KEY` | Private key for backend deploy. |

## Required GitHub Variables

### Staging

| Variable | Example |
|---|---|
| `STAGING_API_BASE_URL` | `https://api-staging.calltone.tech` |
| `STAGING_FRONTEND_URL` | `https://staging.calltone.tech` |
| `STAGING_BACKEND_HEALTH_URL` | `https://api-staging.calltone.tech/api/health/detailed` |
| `STAGING_BACKEND_RESTART_CMD` | `sudo systemctl restart calltone-backend` |

### Production

| Variable | Example |
|---|---|
| `PROD_API_BASE_URL` | `https://api.calltone.tech` |
| `PROD_FRONTEND_URL` | `https://calltone.tech` |
| `PROD_BACKEND_HEALTH_URL` | `https://api.calltone.tech/api/health/detailed` |
| `PROD_BACKEND_RESTART_CMD` | `sudo systemctl restart calltone-backend` |

## GPU Server Policy

Do not rebuild or redeploy the A100/B200 GPU server on every commit.

Correct policy:

1. Restore the GPU server from the Google Drive/rclone backup when a new instance is created.
2. Start `model_server` on port `8081`.
3. Update Hetzner autossh tunnel to forward backend `127.0.0.1:8090` to GPU `localhost:8081`.
4. Validate:

```bash
curl http://127.0.0.1:8090/v1/health
curl -H "Authorization: Bearer $MODEL_SERVER_TOKEN" http://127.0.0.1:8090/v1/capacity
curl https://api.calltone.tech/api/health/detailed
```

For fresh Vast instances, the safe bootstrap is:

```bash
export HF_TOKEN=...
export CALLTONE_BRANCH=main
bash VAST_AI_QUICKSTART.sh
```

The script never stores the token in git. It reads `HF_TOKEN` only from the environment.

## Release Sequence

Use this exact sequence:

```bash
git switch integration/release-2026-04-25
git push origin integration/release-2026-04-25
gh pr create --base main --head integration/release-2026-04-25
```

After PR CI passes and review is complete:

```bash
gh pr merge --merge
git switch main
git pull origin main
git tag -a v1.0.0 -m "CallTone v1.0.0 graduation demo release"
git push origin v1.0.0
```

Production deployment starts from the tag and waits for GitHub Environment approval.

## Verification Evidence to Keep

For the graduation implementation/testing report, keep:

- CI run URL showing all four jobs passing.
- OpenAPI artifact from the CI run.
- Screenshot of protected `main` branch settings.
- Screenshot of `staging` and `production` GitHub environments.
- Screenshot of deployment workflow run.
- Screenshot or JSON output from `/api/health/detailed`.
- One live GPU smoke result only when the GPU instance is available.
