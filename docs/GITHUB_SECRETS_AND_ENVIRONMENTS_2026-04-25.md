# GitHub Secrets and Environments — CallTone CI/CD

This file records exactly what must be configured in GitHub for the CI/CD route.

Do not commit `.env`, SSH keys, Hugging Face tokens, Hetzner passwords, Vast keys, Google Drive/rclone configs, or model-server bearer tokens.

## Environments

Create these under:

```text
GitHub repo -> Settings -> Environments
```

| Environment | Purpose | Protection |
|---|---|---|
| `staging` | Automatic deploy after `main` CI passes. | No manual approval required. |
| `production` | Production deploy from `vX.Y.Z` tags. | Manual dispatch is required on the current GitHub plan because reviewer protection is not supported. |

## Repository Variables

Create these under:

```text
GitHub repo -> Settings -> Secrets and variables -> Actions -> Variables
```

| Variable | Production value |
|---|---|
| `PROD_API_BASE_URL` | `https://api.calltone.tech` |
| `PROD_FRONTEND_URL` | `https://calltone.tech` |
| `PROD_BACKEND_HEALTH_URL` | `https://api.calltone.tech/api/health/detailed` |
| `PROD_BACKEND_RESTART_CMD` | `/opt/calltone-backend/venv/bin/pip install -r requirements.txt && systemctl restart calltone-backend` |

Staging variables currently configured:

| Variable | Value |
|---|---|
| `STAGING_API_BASE_URL` | `https://api-staging.calltone.tech` |
| `STAGING_FRONTEND_URL` | `https://staging.calltone.tech` |
| `STAGING_BACKEND_HEALTH_URL` | `https://api-staging.calltone.tech/api/health/detailed` |
| `STAGING_BACKEND_RESTART_CMD` | `/opt/calltone-backend-staging/venv/bin/pip install -r requirements.txt && systemctl restart calltone-backend-staging` |

## Repository Secrets

Create these under:

```text
GitHub repo -> Settings -> Secrets and variables -> Actions -> Secrets
```

### Production frontend webspace

These deploy the React `dist/` build to Hetzner shared webspace.

| Secret | Meaning |
|---|---|
| `PROD_WEBSPACE_HOST` | Production webspace SSH host. |
| `PROD_WEBSPACE_USER` | Production webspace SSH/SFTP user. |
| `PROD_WEBSPACE_PORT` | Production SSH port. |
| `PROD_WEBSPACE_PATH` | Remote document root for `calltone.tech`. |
| `PROD_WEBSPACE_SSH_KEY` | Private deploy key with access to the webspace. |

### Production backend VPS

These deploy the contents of the repository `backend/` directory to the Hetzner VPS backend service path. The workflow preserves the remote `.env`, `venv/`, uploads, local DB files, and runtime data.

| Secret | Meaning |
|---|---|
| `PROD_BACKEND_HOST` | Production backend VPS host. |
| `PROD_BACKEND_USER` | Production backend SSH user. |
| `PROD_BACKEND_PORT` | Production backend SSH port, usually `22`. |
| `PROD_BACKEND_PATH` | Remote backend service path, e.g. `/opt/calltone-backend`. |
| `PROD_BACKEND_SSH_KEY` | Private deploy key with backend SSH access. |

### Staging

Staging is provisioned on the same physical servers as production, but with separate frontend/backend paths, service, port, and database. These secrets are already configured and verified.

| Secret | Meaning |
|---|---|
| `STAGING_WEBSPACE_HOST` | Staging frontend webspace SSH host. |
| `STAGING_WEBSPACE_USER` | Staging frontend SSH user. |
| `STAGING_WEBSPACE_PORT` | Staging frontend SSH port. |
| `STAGING_WEBSPACE_PATH` | Staging frontend document root. |
| `STAGING_WEBSPACE_SSH_KEY` | Staging frontend deploy key. |
| `STAGING_BACKEND_HOST` | Staging backend VPS host. |
| `STAGING_BACKEND_USER` | Staging backend SSH user. |
| `STAGING_BACKEND_PORT` | Staging backend SSH port. |
| `STAGING_BACKEND_PATH` | Staging backend service path, e.g. `/opt/calltone-backend-staging`. |
| `STAGING_BACKEND_SSH_KEY` | Staging backend deploy key. |

## Production Values Known From Current Deployment

These are non-secret identifiers only.

| Field | Value |
|---|---|
| Frontend domain | `calltone.tech` |
| Frontend host | `www686.your-server.de` |
| Frontend SSH port | `222` |
| Frontend webspace user | stored outside git |
| Backend public domain | `https://api.calltone.tech` |
| Backend VPS IP | `91.99.208.254` |
| Backend local model tunnel | `127.0.0.1:8090` |
| GPU model-server port | `8081` |

The actual passwords and private keys were intentionally not written here.

## Staging Values Known From Current Deployment

These are non-secret identifiers only.

| Field | Value |
|---|---|
| Frontend domain | `https://staging.calltone.tech` |
| Frontend host | `www686.your-server.de` |
| Frontend SSH port | `222` |
| Frontend path | `/usr/home/gsx8iy/public_html/staging/` |
| Backend public domain | `https://api-staging.calltone.tech` |
| Backend VPS IP | `91.99.208.254` |
| Backend path | `/opt/calltone-backend-staging` |
| Backend service | `calltone-backend-staging` |
| Backend local port | `127.0.0.1:8001` |
| Database | `calltone_staging_db` |
| Uploads path | `/opt/calltone-backend-staging/uploads` |

Staging deploy was verified on 2026-04-25 after SSL activation. GitHub Actions run `24927626622` passed frontend deploy, backend deploy, and smoke checks.

The local Windows DNS resolver may still temporarily fail to resolve `staging.calltone.tech`; public resolvers and the authoritative nameserver resolve it correctly:

```bash
nslookup staging.calltone.tech 1.1.1.1
nslookup staging.calltone.tech 8.8.8.8
nslookup staging.calltone.tech tech-domains.earth.orderbox-dns.com
```

## How To Create Deploy SSH Keys

Preferred method:

```bash
ssh-keygen -t ed25519 -C "github-actions-calltone-prod" -f calltone_prod_deploy_ed25519
```

Then:

1. Add the `.pub` file to `~/.ssh/authorized_keys` on the target server/user.
2. Put the private key content into the matching GitHub secret.
3. Delete local temporary copies after confirming deployment works.

## Production Release Procedure

After PR into `main` is merged and CI is green:

```bash
git switch main
git pull origin main
git tag -a v1.0.0 -m "CallTone v1.0.0 graduation demo release"
git push origin v1.0.0
```

Then manually run:

```text
GitHub -> Actions -> Deploy -> Run workflow
target=production
version_tag=v1.0.0
```

The workflow validates that the tag matches `vX.Y.Z` and that CI passed for that tag's commit before deploying. This manual workflow dispatch is the current production approval gate because GitHub rejected environment reviewer/wait-timer rules on the repository plan.

## Staging Verification Procedure

Staging deploys automatically after `main` CI passes. To verify manually:

```bash
curl -I https://staging.calltone.tech
curl https://api-staging.calltone.tech/api/health/detailed
```

The backend health payload may report `model_server` unreachable when the disposable GPU server is stopped. That is acceptable for CI/CD staging because model execution is not required for every frontend/backend deploy. Live call analysis requires restoring a GPU instance and reconnecting the autossh tunnel.

## What The Workflow Never Uploads

The backend rsync helper excludes:

- `.git/`
- `.github/`
- `deployment/`
- Python caches,
- frontend `node_modules/`,
- frontend `dist/`,
- backend `.env`,
- backend uploads,
- SQLite DB files,
- model-server `.env`,
- GGUF/ONNX/safetensors/PT/PTH/BIN model weights.

This prevents accidental leakage of secrets or huge model binaries.
