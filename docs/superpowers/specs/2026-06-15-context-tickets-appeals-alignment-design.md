# Design — Context-Ticket AI Pipeline + Agent Appeals + Role Alignment (2026-06-15)

Status: **DRAFT for review.** No code until approved. Most work is GPU-independent;
GPU is re-rented once at the end for the live pipeline tests (items A, D).

Roles: agent, qa, admin (+ manager/viewer tenant-scoped), owner/super_admin (platform).
Live tenant for testing: **MetroBoost Telecom** (calltonetesting_{admin,qa,agent}@spamok.com / As112233@@).

---

## A. Context-ticket AI auto-apply/decline  ← restore teammate's original (CONFIRMED: pure AI, no human)

**Problem.** Batch-4 turned context-change tickets into a *human admin approve/reject*
flow, and "approve" never actually writes the context. The original design = QA
submits a change → an AI gate screens it → it is **auto-applied or auto-declined**
to the company context, no human.

**Building blocks that already exist (reuse, don't rebuild):**
- `LAYER_2/security/injection_scanner.scan(text, use_llm=…)` → `ScanResult{verdict, severity, recommended_action}` (static patterns + LLM detector). The security/injection gate.
- `LAYER_2/company_context/text_ingestion.ingest_text_context()` → builds the grouped context + atomic nodes and saves it. The "apply" engine.
- Model-server context store + `PUT /v1/contexts/{name}` push (already used during scoring).

**New flow (backend, on `POST /context/tickets`):**
1. QA submits `{field_name, proposed_text, reason}` (company auto = their tenant).
2. **Sanitize + injection scan** `proposed_text` (static always; LLM detector when model server up).
   - `recommended_action == block` (or `hold_for_human_review` with high severity) → ticket `status=declined`, `decision="ai_blocked"`, store `ai_verdict`, `ai_reasoning`. STOP.
3. **Validity check** (lightweight LLM/skill): is the field a real context field, is the text a coherent policy for that field, not empty/contradictory? Fail → `status=declined`, `decision="ai_invalid"`, reasoning. STOP.
4. **Apply (targeted, NOT full re-ingest):** update that one field in the company
   context JSON (grouped schema), regenerate atomic nodes for the affected section
   only, bump `context_version`, save, and `PUT /v1/contexts/{name}` to the model
   server. Ticket `status=applied`, store `decision="ai_applied"`, `applied_at`, a
   before/after `diff`, and `ai_reasoning`.
5. Notify the submitting QA of the outcome (existing email service).

**Decisions needing your confirmation:**
- **D-A1 Apply granularity:** targeted single-field update (recommended — fast, safe, no full 5-pass) vs full re-ingest of a merged doc. → *recommend targeted.*
- **D-A2 Escape hatch:** keep the admin "Replace Context" full-upload + a **read-only** ticket audit list (who changed what, AI verdicts). Admins no longer approve (AI does) but can see history + still do a full replace. → *recommend keep as audit + manual replace.*
- **D-A3 Borderline (`suspicious`/`hold`)**: with "pure AI", treat hold-for-review as **decline** (no human) and tell QA to rephrase/resubmit. → *recommend decline-and-explain.*

**RBAC:** QA gets `canSubmitContextTickets` (triggers the AI flow). Admin keeps
`canManageContext` (Replace Context full upload + audit). Server-enforced.

**Needs GPU** (LLM detector + atomic-node regen). Static scan + field write work GPU-free as a fallback.

---

## B. Company-context "all fields show X" (display bug, scoring is fine)

**Root cause (verified):** real context JSON is **grouped** — top-level keys
`script_compliance, factual_accuracy, behavioral, atomic_nodes, company_name,
context_version, last_updated`. The UI (`CompanyContext.tsx` `CONTEXT_FIELDS`)
checks **flat** legacy keys (`greeting_script`, …) that don't exist at top level →
every field renders ✗.

**Fix:** render the real schema — iterate the grouped sections and their sub-fields
(+ show atomic-node count), mark filled/empty against actual keys; fix the
"N fields filled" count to match. Backward-compatible: if a flat-schema context is
seen, still render it.

---

## C. QA "Companies" tab — wrong mental model for single-company users

QA/admin are bound to ONE company; a plural "Companies" list implies multi-tenant.
**Fix:** tenant scope → no list; show the single company's context directly, tabs =
`Context` + `Change Tickets` (+ `Replace Context` for admin). Keep the multi-company
list ONLY for platform scope (owner/super_admin). De-slop the copy.

---

## D. Hard-coded / spurious transcript signal tags (e.g. QUESTIONING on the agent greeting)

Frontend renders `line.signals` (real data), so the bad tag originates **upstream**
in LAYER 1 (role-ID / signal tagging) or seed data. **Plan:** read the LAYER-1
signal-assignment step (`role_identification` / pipeline adapter), find where
signals are attached, remove any default/hard-coded signal, keep only
genuinely-detected ones; also audit the frontend `line.profile` fallback tag.
**Verify on a real re-processed call** (needs GPU).

---

## E. Admin "Company Context" → `/qa/context` + Upload showing for admin (route/RBAC/UX conflict)

Admin sidebar links to the QA URL and shows a QA-flavored page incl. top-nav
"Upload". **Fix:** add a proper **`/admin/context`** route rendering the context
view inside `AdminLayout` (admin sidebar, no QA `Navbar`, no "Upload" item). Admin
context view = single-company Context + **Replace Context** + Change-ticket audit.
Sidebar "Company Context" → `/admin/context`. Remove the QA-only Upload affordance
for admins. Verify URLs per role.

---

## F. NEW FEATURE — Agent appeal on a flagged call (full-stack, kept simple)

**Goal.** When a call is flagged / scored badly, the agent can appeal; a QA sees the
appeal **on that call** and re-reviews it as a human (uphold or overturn), with the
outcome recorded on the call.

**Data (new DB table `call_appeals`):** `id, call_id, client_id, agent_employee_id,
status[open|under_review|upheld|overturned], agent_reason, qa_id, qa_response,
corrected_score (nullable), created_at, resolved_at`.

**Backend:**
- `POST /api/calls/{id}/appeal` — agent, **own** call only, only if flagged/low; one open appeal per call. Body `{reason}`.
- `GET /api/appeals` — QA/admin see appeals for **their company**; agent sees own.
- `PATCH /api/appeals/{id}` — QA/admin: set `under_review` → `upheld`/`overturned` + `qa_response` (+ optional `corrected_score`). Server-enforced scope.

**Frontend (CallDetail):**
- Agent + flagged + own call → "Appeal this review" button → reason modal → creates appeal; shows status badge.
- QA/admin viewing that call → "Appeal" panel: agent's reason + actions (Uphold / Overturn + note, optional corrected score). Resolution shown to the agent.

**Decisions needing confirmation:**
- **D-F1 Overturn effect:** record a human decision + `qa_response` and show a
  "Human-reviewed" badge; **corrected_score optional** and displayed alongside the
  AI score (AI score not overwritten — audit trail). → *recommend this (simple, honest).*
- **D-F2 Eligibility:** appealable only when `flag_for_review` true OR grade ≤ D / severity Major+. → *recommend yes.*

**Out of scope (YAGNI):** multi-message threads, re-running the AI, notifications beyond existing email.

---

## G. Full cross-role alignment audit (team-lead pass) + 100% verification

Build a **role × surface matrix** (agent / qa / admin / manager / viewer /
owner+super_admin) × (every route, nav item, capability, action) → expected vs
actual; fix every mismatch (naming, URL, RBAC gate, validation, AI-slop copy).
Then browser-test each role end-to-end (Playwright) with 0 console errors, plus
backend RBAC tests. Items B/C/E feed this; this pass catches the rest.

**Verification gates (per the standing rule "100% confirmation"):**
- `tsc -p tsconfig.app.json` 0, `vitest` green, backend `pytest` green.
- Per-role Playwright walkthrough on staging, 0 console errors.
- Live pipeline re-test on the re-rented GPU for A + D.
- Then one staged → prod cutover (backups + rollback), as before.

---

## Sequencing (GPU-cost-aware)
1. **GPU-free now:** B, C, E, F (frontend + backend + DB), A's non-LLM parts, G audit + fixes.
2. **Re-rent GPU once** at the end → implement/verify A (injection+ingest apply) and D (signal fix) on real calls, full per-role smoke, then prod cutover.

## Open decisions to confirm: D-A1, D-A2, D-A3, D-F1, D-F2 (recommendations marked).
