# CallTone Frontend Authority And Functionality Audit

Date: 2026-04-24

Scope: active frontend in `calltone-UI/`, backend API access checks in `backend/app/main.py`, and the production deployment split across:

- Tier 1 UI: `https://calltone.tech` static Vite bundle on Hetzner shared hosting.
- Tier 2 API: `https://api.calltone.tech` FastAPI backend on Hetzner VPS.
- Tier 3 model server: private Vast.ai GPU reached through the Tier 2 SSH tunnel.

## Current Route Authority

| Route | Access | Page | Status |
|---|---|---|---|
| `/` | Public; authenticated users redirect to role home | `Home` | Added. Replaces the previous direct redirect to login. |
| `/login` | Public | `Login` | Uses centralized role redirect after login. |
| `/accept-invite` | Public with token | `AcceptInvite` | Functional invite acceptance. |
| `/not-authorized` | Public | `NotAuthorized` | Uses centralized role home links. |
| `/agent/dashboard` | `agent` only | `AgentDashboard` | Agent-only dashboard. |
| `/qa/dashboard` | `qa` only | `QADashboard` | QA-only overview. |
| `/qa/upload` | `qa`, `admin`, `super_admin` | `UploadCall` | Upload and ASR selection available to QA/admin roles only. |
| `/qa/context` | `qa`, `admin`, `super_admin` | `CompanyContext` | Context upload/tickets available to QA/admin roles. |
| `/qa/call/:callId` | `qa`, `agent`, `admin`, `super_admin` | `CallDetail` | Backend enforces agent can only see own calls. |
| `/admin/dashboard` | `admin`, `super_admin`, `manager`, `viewer` | `AdminDashboard` | Read/dashboard access for admin-family roles. |
| `/admin/clients` | `admin`, `super_admin`, `manager`, `viewer` | `AdminClients` | Added read-only client directory. |
| `/admin/team` | `admin`, `super_admin`, `manager`, `viewer` | `AdminTeam` | Mutating controls hidden unless admin/super_admin. |
| `/admin/activity` | `admin`, `super_admin`, `manager`, `viewer` | `AdminActivity` | Read-only activity/team overview. |
| `/admin/settings` | `admin`, `super_admin` only | `AdminSettings` | Restricted to roles that can mutate pipeline settings. |

## Endpoint Flow Map

| Frontend area | API client | Backend endpoints | Notes |
|---|---|---|---|
| Login/logout/session | `authApi` | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | Logout now clears client state immediately and navigates to login without requiring refresh. |
| Invite flow | `authApi` | `GET /api/auth/invite/{token}`, `POST /api/auth/invite/accept` | Public token flow. |
| QA dashboard | `callsApi` | `GET /api/qa/calls` | Dashboard time tabs now actually filter calls and summary KPIs. |
| Call detail | `callsApi` | `GET /api/qa/calls/{id}`, `GET /api/qa/calls/{id}/audio` | Backend now checks QA/admin or owning agent. |
| Upload analysis | `callsApi` | `POST /api/calls/upload`, `GET /api/calls/{id}/status` | Upload validates audio type/size before submit. |
| Pipeline settings | `pipelineApi` | `GET /api/settings/pipeline`, `PUT /api/settings/pipeline` | Fake UI-only settings were removed; page now edits real backend-backed AI pipeline settings only. |
| Company context | `contextApi` | `GET /api/context/companies`, `GET /api/context/companies/{name}`, `POST /api/context/ingest`, `GET /api/context/ingest/{job_id}/status` | Restricted to QA/admin roles. |
| Context tickets | `contextApi` | `GET /api/context/tickets`, `POST /api/context/tickets`, `PUT /api/context/tickets/{id}` | Admin/super_admin can approve/reject tickets from UI. |
| Admin dashboard | `adminApi` | `GET /api/admin/dashboard` | Admin-family read surface. |
| Admin clients | `adminApi` | `GET /api/admin/clients` | Added missing frontend page for existing backend endpoint. |
| Admin team | `adminApi` | `GET /api/admin/users`, invite/role/status/delete endpoints | Mutation buttons are hidden for manager/viewer to match backend rules. |
| Agent dashboard | `agentApi` | `GET /api/agent/dashboard`, `GET /api/agent/calls` | Backend now requires agent role explicitly. |

## Main Fixes Made

- Added a proper public home page at `/` so the project no longer looks like an empty login-only template.
- Fixed `ProtectedRoute` so it waits for auth initialization before redirecting.
- Fixed logout behavior by clearing auth state immediately and using `navigate("/login", { replace: true })`.
- Centralized role routing in `src/lib/roles.ts` to prevent inconsistent redirects.
- Added actual date-range filtering for weekly/monthly/quarterly/yearly dashboard tabs.
- Added backend visibility checks so agents can only open their own calls.
- Restricted settings/context/pipeline endpoints to roles that should access them.
- Removed fake settings controls from Admin Settings; the page now only exposes functional pipeline controls.
- Added Admin Clients page for the existing clients endpoint.
- Added context-ticket approve/reject UI for admin/super_admin.
- Added SPA `.htaccess` into `public/` so deep routes survive browser refresh after deployment.
- Cleaned lint violations caused by empty interfaces and `any` usage.

## Verification Completed

Local frontend:

- `npm test -- --run`: 7 files, 22 tests passed.
- `npm run lint`: 0 errors, 9 pre-existing Fast Refresh warnings.
- `npm run build`: production build passed.
- `calltone-UI/dist-deploy.tgz`: fresh deploy artifact created from `dist/`.
- `calltone-UI/dist/.htaccess`: present in build output.

Backend:

- `python -m py_compile backend/app/main.py`: passed.
- Deployed `backend/app/main.py` to Tier 2 Hetzner VPS.
- Restarted `calltone-backend`.
- Verified `https://api.calltone.tech/api/health`: `{"status":"ok"}`.
- Verified detailed health: database OK, model server OK, GPU available.

## Deployment Status

Backend API authorization fixes are live on `api.calltone.tech`.

Frontend fixes are built and packaged locally but are not confirmed live on `calltone.tech` yet because the repository does not contain the Tier 1 shared-hosting SSH/SFTP account for `public_html`. The deploy-ready artifact is:

`calltone-UI/dist-deploy.tgz`

To make the frontend changes live, upload the contents of `calltone-UI/dist/` into the Hetzner shared-hosting `public_html/` directory while preserving `.htaccess`.

## Remaining Manual Smoke Checks After Frontend Deploy

- Public home loads at `https://calltone.tech/`.
- Login as QA redirects to `/qa/dashboard`; logout returns immediately to `/login`.
- Login as Agent redirects to `/agent/dashboard`; agent cannot access `/qa/upload`, `/qa/context`, or `/admin`.
- Agent call detail opens only for own calls.
- Login as Admin/Super Admin can access admin pages, upload, context, settings.
- Login as Manager/Viewer can read admin dashboard/team/activity/clients but cannot see settings or mutation buttons.
- Upload page accepts audio, rejects non-audio and oversized files, and polling reaches completed/failed state.
- Context page lists companies, uploads context, shows ingest status, creates tickets, and admin can approve/reject.
- QA dashboard search, rating sort, and date ranges update visible rows and KPIs.
- Admin settings save real pipeline settings and reload persisted values.
