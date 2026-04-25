# CallTone Branching, CI/CD, and Deployment Plan — 2026-04-25

This note records the recommended production workflow after the queue, frontend RBAC, model-server capacity, backup, and Report 2 evidence work.

## Current Branch State

Observed on 2026-04-25:

| Branch | Current role | State |
|---|---|---|
| `feat/test-suite-and-evidence` | Current integration branch | Contains the latest production queue, frontend RBAC, docs, tests, security probes, and stress tooling. Pushed at commit `aaebf6e`. |
| `main` | Intended stable trunk | Behind the current integration branch by 27 commits. |
| `backend` | Old backend feature branch | No unique commits missing from the current integration branch. Can be archived after merge to `main`. |
| `server` | GPU/server experiment branch | Has 2 unique commits: B200 quickstart fixes, `.gitattributes`, SPA route, BankServ context, and an SVG update. Needs selective merge/review. |
| `deploy` | Deployment experiment branch | Has 2 unique commits: rsync deployment workflow and SPA `.htaccess`. Needs selective merge/review because workflow conflicts with current CI/CD files. |

Dry-run merge findings:

- `origin/deploy` conflicts with current branch in `.github/workflows/deploy.yml` and `calltone-UI/public/.htaccess`.
- `origin/server` conflicts in `backend/app/main.py` and `models/LAYER_2/company_context/contexts/bankserv_global.json`.
- `origin/backend` has no unique missing work relative to the current branch.

## Recommendation

Do **not** merge the current branch blindly into `deploy`.

The best route is:

1. Treat `main` as the protected trunk.
2. Treat `feat/test-suite-and-evidence` as the current release candidate.
3. Create one short-lived integration branch from it.
4. Selectively merge or cherry-pick the useful `server` and `deploy` branch commits.
5. Run full CI locally and in GitHub.
6. Open a pull request into `main`.
7. Let `main` represent the exact deployable source state.
8. Deploy from `main` to staging automatically.
9. Deploy production only from a version tag after smoke tests.

Recommended commands:

```bash
git checkout feat/test-suite-and-evidence
git pull origin feat/test-suite-and-evidence
git checkout -b integration/release-2026-04-25

# Bring only reviewed work from the older branches.
git cherry-pick a59cd56   # deploy rsync workflow, if still useful after review
git cherry-pick 52a2786   # server quickstart/context fixes, resolve conflicts manually

# Resolve conflicts by preserving current queue/backend behavior.
pytest backend/tests/ model_server/tests/ models/LAYER_2/security/tests/ -q
cd calltone-UI && npm ci && npm test -- --run && npm run build

git push origin integration/release-2026-04-25
```

Then open a PR:

```text
integration/release-2026-04-25 -> main
```

## Branch Policy Going Forward

| Branch type | Naming | Allowed content | Deployment effect |
|---|---|---|---|
| Stable trunk | `main` | Reviewed, tested, deployable code only | Auto-deploy to staging after CI. |
| Feature branches | `feat/<area>-<summary>` | One bounded feature or fix | CI only; no deployment. |
| Hotfix branches | `fix/<area>-<summary>` | Production bug fix | CI only; PR to `main`; tag if production fix. |
| Release branches | `release/<date-or-version>` | Short-lived stabilization branch | Optional staging deploy. |
| Production tags | `vX.Y.Z` | Immutable production release | Production deploy after manual approval. |

Retire these after the final merge:

- `backend`, because its useful work is already in the current integration branch.
- `server`, after its unique useful files are merged/cherry-picked.
- `deploy`, after its useful deployment workflow changes are merged/cherry-picked.

## CI Strategy

CI should not require the live A100 or model downloads on every PR.

Mandatory CI for every PR:

- backend unit/integration tests with mocked model server,
- model-server endpoint/job tests using tiny fixtures,
- Layer 2 security scanner and bypass tests,
- frontend Vitest suite,
- frontend production build,
- secret scan,
- lint/security checks that do not require secrets.

Current GitHub Actions already cover:

- backend tests,
- skill/security tests,
- frontend Vitest + build,
- Bandit,
- npm audit,
- gitleaks.

Recommended additions:

| Gap | Action |
|---|---|
| Backend queue regression | Add CI test that submits multiple fake jobs and verifies queued/running/completed states without the real GPU. |
| Model-server timeout policy | Add endpoint test proving `pipelineTimeoutSeconds=null` is reported when timeout is disabled. |
| OpenAPI evidence | Add CI artifact that exports `openapi.json`. |
| Frontend RBAC evidence | Keep `roles.test.ts`; add route-level smoke tests later with Playwright. |
| Deploy smoke | Keep post-deploy smoke as a separate environment-gated step, not regular PR CI. |

## Deployment Strategy

The live system is not a simple one-container deployment. It is a three-server system:

1. Tier 1 frontend on Hetzner shared webspace.
2. Tier 2 FastAPI backend + PostgreSQL on Hetzner VPS.
3. Tier 3 A100 GPU model server on Vast.ai behind an SSH tunnel.

Therefore deployment must be split by tier.

### Staging

Trigger:

- merge to `main`, after CI passes.

Actions:

- build frontend and upload `dist/` to staging webspace,
- rsync backend source to staging VPS and restart service,
- run `/api/health/detailed`,
- optionally point staging backend to the current GPU tunnel or to a fake model-server stub.

### Production

Trigger:

- tag `vX.Y.Z`,
- manual GitHub environment approval.

Actions:

- deploy frontend build to `calltone.tech`,
- deploy backend to Hetzner,
- preserve backend `.env` and PostgreSQL data,
- verify tunnel to A100,
- run public health check,
- run one small pipeline smoke only when GPU is available.

### GPU Server

Do not deploy the GPU server from every commit.

The GPU server is expensive and often short-lived. Treat it as a replaceable runtime restored from Drive:

- restore from `gdrive:hothifa-full-gpu-20260425-005615-queue-ready`,
- update only model-server source when needed,
- restart uvicorn on port `8081`,
- update Hetzner tunnel if Vast IP/port changes,
- validate `/v1/health` and `/v1/capacity`.

## Live Model Testing Policy

Do not make every GitHub CI run call the real model pipeline.

Use three levels:

| Level | When | What it proves |
|---|---|---|
| PR CI | Every PR | Code correctness without A100. |
| Deployment smoke | After staging/prod deploy | API, frontend, auth, queue, and tunnel health. |
| Live GPU smoke | On demand / before demo | Full Layer 1 -> Layer 2 -> Layer 3 pipeline on one known fixture. |

For Report 2 and demo readiness, the current strongest live evidence is:

- public health endpoint green,
- model-server capacity green,
- `10/10` server-side queued stress completed,
- all completed stress calls produced score, evidence, 7 dimensions, speaker turns, and AI report.

## Required GitHub Secrets

Do not commit secrets to GitHub. Store them in GitHub repository/environment secrets.

Expected secret groups:

| Secret | Environment | Purpose |
|---|---|---|
| `PROD_ADMIN_PASSWORD` | production | Post-deploy backend smoke login. |
| `STAGING_ADMIN_PASSWORD` | staging | Staging smoke login. |
| `HETZNER_HOST` / `HETZNER_USER` / `HETZNER_SSH_KEY` | production or staging | Backend deployment over SSH. |
| `WEBSPACE_HOST` / `WEBSPACE_USER` / `WEBSPACE_SSH_KEY` | production or staging | Frontend upload to Hetzner webspace. |
| `MODEL_SERVER_TOKEN` | production only | Backend-to-model-server bearer auth; never printed in logs. |
| `HF_TOKEN` | GPU setup only | HuggingFace gated model downloads; do not expose in frontend/backend CI. |

## Immediate Next Step

Use this sequence:

1. Keep current branch as release candidate.
2. Create `integration/release-2026-04-25`.
3. Manually port useful `server` and `deploy` branch changes.
4. Run CI and local checks.
5. PR into `main`.
6. Deploy staging from `main`.
7. Tag production only after one final human-checked smoke.

This avoids turning `deploy` into a second trunk and prevents branch drift from becoming unmanageable.
