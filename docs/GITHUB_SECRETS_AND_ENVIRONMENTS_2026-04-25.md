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
| `production` | Production deploy from `vX.Y.Z` tags. | Require at least one reviewer before deployment. |

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
| `PROD_BACKEND_RESTART_CMD` | `sudo systemctl restart calltone-backend` |

Optional staging variables, if a staging domain/VPS is created:

| Variable | Example |
|---|---|
| `STAGING_API_BASE_URL` | `https://api-staging.calltone.tech` |
| `STAGING_FRONTEND_URL` | `https://staging.calltone.tech` |
| `STAGING_BACKEND_HEALTH_URL` | `https://api-staging.calltone.tech/api/health/detailed` |
| `STAGING_BACKEND_RESTART_CMD` | `sudo systemctl restart calltone-backend` |

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

These deploy backend/source code to the Hetzner VPS. The workflow preserves remote `.env`, PostgreSQL data, uploads, and model-server secrets.

| Secret | Meaning |
|---|---|
| `PROD_BACKEND_HOST` | Production backend VPS host. |
| `PROD_BACKEND_USER` | Production backend SSH user. |
| `PROD_BACKEND_PORT` | Production backend SSH port, usually `22`. |
| `PROD_BACKEND_PATH` | Remote CallTone repo/source path. |
| `PROD_BACKEND_SSH_KEY` | Private deploy key with backend SSH access. |

### Staging

Only add staging secrets after a separate staging webspace/VPS is provisioned.

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
| `STAGING_BACKEND_PATH` | Staging backend source path. |
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

The production deploy workflow will start from the tag and wait for approval in the GitHub `production` environment.

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
