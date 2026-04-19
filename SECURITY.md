# Security Policy

## Supported versions

CallTone is a single-deployment graduation project. Only the head of
`main` and the most recent tagged release receive security fixes.

| Version          | Supported |
|------------------|-----------|
| `main` (latest)  | yes       |
| Tagged `v*.*.*`  | latest tag only |
| Older tags       | no        |

## Reporting a vulnerability

**Please do not file a public GitHub issue for security bugs.**

Email the project security contact:

- **NasrEldin Khaled** — `s-nasreldin.mohamed@zewailcity.edu.eg`

Include:
- A short description of the issue.
- Steps to reproduce, ideally with a curl command, screenshot, or
  minimal payload.
- The commit SHA you tested against (`git rev-parse HEAD`).
- Your name and how you would like to be credited (or whether you
  prefer to remain anonymous).

## Response targets

| Stage                                       | Target           |
|---------------------------------------------|------------------|
| Acknowledge receipt                         | 5 working days   |
| Initial severity assessment                 | 10 working days  |
| Fix or documented mitigation                | 30 working days  |
| Coordinated public disclosure (with reporter) | 90 days from report |

These are best-effort targets for a four-person student team — they
are not contractual SLAs.

## In scope

- The FastAPI backend in `backend/`.
- The React/Vite frontend in `calltone-UI/`.
- The LAYER 1, LAYER 2, and skill-implementation Python code.
- The CI/CD workflows in `.github/workflows/`.
- Configuration shipped in this repository (`docker-compose*.yml`,
  `.gitleaks.toml`, etc.).

## Out of scope

- Vulnerabilities in third-party model weights downloaded by
  `download_models.py` — report those to the upstream model authors.
- Issues that require physical access to the GPU box on which a
  particular instance is deployed.
- Findings that depend on a default development configuration
  (e.g. `DEBUG=true`, `SECRET_KEY="dev-secret-key-..."`); the
  production startup guard refuses to boot in this state.
- Social-engineering attacks against the maintainers or their
  Zewail City accounts.

## Hall of fame

We will acknowledge reporters who give us a reasonable disclosure
window in a `SECURITY_THANKS.md` file added at the time of fix.
