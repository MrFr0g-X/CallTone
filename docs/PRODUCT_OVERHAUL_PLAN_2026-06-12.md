# CallTone Product Overhaul — Plan & Investigation (2026-06-12)

Scope: frontend + backend + behavior changes across Admin, QA, Agent roles, plus
SenseVoice removal and thesis follow-on. The live product (calltone.tech /
api.calltone.tech, branch `integration/release-2026-04-25`) is what users see, so every
change is staged → tested → deployed surgically (same method as the security hotfix).

Legend: ✅ verified in code · ❓ needs deeper investigation · 🔴 security/correctness ·
🟡 UX/cosmetic · 🟢 net-new feature.

---

## A. ADMIN role

### A1. Activity Log — too noisy 🟡
- Shows every company event; unusable at 500-agent scale.
- **Fix:** paginate + filter by category (auth / uploads / scoring / team / settings) +
  default to last 7 days + collapse repetitive rows. Frontend `pages/AdminActivity.tsx`;
  backend activity endpoint must accept `category`, `since`, `page`, `page_size`.

### A2. Team tab — no pagination/categorization 🟡
- Lists all members at once. **Fix:** server-side pagination (10/page) + role tabs +
  search. `pages/AdminTeam.tsx` + team endpoint params.

### A3. Role filters expose owner/super_admin to company admins 🔴 (info-leak/UX)
- ✅ Filter options come from `lib/roles.ts` / `data/adminRoleConfig.ts`. Company admins
  must only see/assign: **agent, QA, viewer, manager, admin**. owner/super_admin are
  CallTone-internal (platform) roles and must be hidden for tenant admins.

### A4. Overview dashboard is generic, not admin-focused 🟡
- `pages/AdminDashboard.tsx`. Rebuild KPIs for an admin: team size by role, calls
  processed (company), avg score trend, flagged-for-review count, queue health,
  context freshness — not QA/agent-style cards.

### A5. Settings → "Tenant Company Control Service / you cannot create platform clients" 🔴 UX/AI-tell
- ✅ Copy lives in `pages/AdminSettings.tsx` + `pages/AdminClients.tsx`. This is the
  worst AI-slop tell. **Fix:** remove the entire platform-scope notice; tenant admins
  should simply not see platform-client controls at all (not be told they can't).

### A6. Company Access Policy must actually work 🔴
- ✅ Backend `client_policy` endpoints exist (`main.py`). Audit every toggle end-to-end:
  confirm each policy field persists AND is enforced in the relevant code path (not just
  stored). Fix any hardcoded/no-op toggles.

### A7. Admin can view + change Company Context 🟢 (core idea)
- Today context editing/replace lives under QA (`pages/CompanyContext.tsx`). Add an
  admin Settings section that shows the saved company context and lets the admin
  replace/update it. Backend context endpoints exist; wire admin RBAC.

### A8. "Company AI Pipeline Defaults" (audio processing, injection scan, speaker count) 🔴 ownership
- These are **CallTone-developer** controls, not tenant-admin. **Fix:** remove from the
  tenant admin Settings UI (keep them platform-only / config-level). `AdminSettings.tsx`
  + `pipeline_settings` exposure.

### A9. Company Processing Queue in admin settings — useless 🟡
- Either remove from tenant admin, or make it a filtered, useful per-company view
  (active/queued/failed counts + retry). Recommend: remove from admin Settings; keep an
  ops-only view.

---

## B. QA role

### B1. QA dashboard — decent, minor refinement 🟡
- `pages/QADashboard.tsx`. Keep; polish KPIs/sorting.

### B2. Call rows show "Agent 1" + raw `.wav` filename 🟡
- Present agent name + a clean, human call title (date/time + agent), not the raw upload
  filename. Frontend formatting + ensure backend returns a display name.

### B3. Call detail — overall score → gauge/speedometer 🟡
- Replace the big number with a colored radial gauge (color by score band). `CallDetail.tsx`.

### B4. Call detail — sectioned/tabbed layout 🟡
- AI quality report + evidence are buried at the bottom. Convert to tabs/sections:
  Overview · Transcript · QA Scores · AI Report · Evidence. `CallDetail.tsx`.

### B5. Context tab — replace-context must move to admin; QA gets tickets 🔴🟢
- ✅ Today QA can directly **replace context** (`CompanyContext.tsx`). Wrong. QA should
  only **submit change-request tickets**; admins manage them.
- ❓ **No ticket system exists** in backend (no `/api/.../tickets` route, no ticket
  table). This is net-new: DB table `context_ticket`, CRUD endpoints, QA submit + status
  view, admin manage/reply tab (ties to A-side new "Tickets" tab).

---

## C. AGENT role

### C1. Dashboard — minor refinement 🟡 (`pages/AgentDashboard.tsx`).
### C2. Call page URL says `/qa/call/...` for agents 🔴 routing/UX
- ✅ `App.tsx:53` — single route `/qa/call/:callId` shared by qa+agent+owner+admin+
  super_admin. Backend authorizes per-call via `_ensure_call_visible_to_user` (verified
  in the security audit), so **not an open IDOR** — but the URL is wrong and leaks a
  role-implying path. **Fix:** add role-neutral route `/call/:callId` (or `/agent/call/`)
  and route each role to its own path; keep backend authz.
### C3. Call page card layout — same tabbed treatment as B4.

---

## D. PLATFORM / PIPELINE

### D1. Remove SenseVoice as a selectable ASR option 🔴 product + thesis
- ✅ References in `UploadCall.tsx`, `services/api.ts`, backend, `models/`. Remove the
  toggle and any UI/option; faster-whisper is the only engine. Keep code path dormant if
  cheap, but no user-facing option.
- **Thesis:** reframe SenseVoice as "evaluated and rejected" (already partly done in the
  ASR section); ensure no remaining "switchable engine" claims imply it is live.

### D2. Per-company auto-ingestion API ❓ (investigate, do NOT build yet)
- ❓ Schema has no `ApiKey` table (Client/User/Role/Employee/Customer/Call/Transcript/
  QaReport/PipelineJob/PipelineSettings/ClientPolicy). Strong signal: **no per-company
  API-key auto-upload exists** — upload is manual via the UI only. Confirm, then decide
  if it's future-work (likely yes; out of scope before defense).

### D3. System-wide alignment / AI-slop sweep 🟡
- Remove remaining "made by AI"-sounding copy across all dashboards; consistent
  terminology, empty states, and role-correct visibility everywhere.

---

## Sequencing (safe order; defense ~June 20)
1. **Low-risk, high-impact, copy/visibility (no behavior risk):** A3, A5, A8, A9, D1, D3.
2. **Frontend UX with backend params:** A1, A2, A4, B1, B2, B3, B4, C1, C3.
3. **Routing fix:** C2 (add new routes, keep old redirecting).
4. **Net-new features (most work/risk):** A7 (admin context edit), A6 (policy enforcement
   audit), B5 + admin Tickets tab.
5. **Investigation-only (no code):** D2.

Each batch: branch off `integration/release-2026-04-25` → build/test locally → deploy to
staging → smoke → prod. Never via CI-from-`main` (main is 44 commits stale).

## Decisions (LOCKED 2026-06-12)
1. Tenant-admin role set: **agent, QA, viewer, manager, admin** (owner + super_admin
   hidden = CallTone-internal only).
2. Ticket system: **minimal** — QA submits subject+body, sees status (open/approved/
   rejected); admin views/replies/applies. One table + basic endpoints + 2 UI surfaces.
3. Company Processing Queue: **remove from tenant admin Settings** (ops-only internally).
4. Deploy cadence: **stage everything, ONE vetted prod deploy before defense.** All work
   on branch `feature/product-overhaul-2026-06-12`; continuous staging; no prod churn
   until the final go.
</content>
