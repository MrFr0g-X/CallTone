# Agent Appeals Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let an agent appeal a flagged/bad-scored call; a QA (or admin) sees the appeal on that call and resolves it (uphold / overturn + note + optional corrected score), with the AI score preserved as an audit trail.

**Architecture:** New SQLAlchemy table `call_appeals` (one open appeal per call). Three FastAPI endpoints under the existing `backend/app/main.py` patterns (auth via `get_current_user`, scope via the existing `_is_tenant_user` / `_tenant_client_id` / `_ensure_call_visible_to_user` helpers). Frontend: typed client in `services/api.ts` + an Appeal affordance on `CallDetail.tsx` (agent: "Appeal this review" when eligible+own; QA/admin: an Appeal panel to resolve). GPU-free.

**Tech Stack:** FastAPI + SQLAlchemy + Postgres (prod/staging) / SQLite (tests); React + TS + react-query; pytest + vitest.

**Confirmed decisions (from spec):** D-F1 = record human decision + optional `corrected_score`, DO NOT overwrite the AI score. D-F2 = appeal eligible when `flag_for_review` true OR grade ≤ D OR severity Major/Critical.

**Branch:** `feature/product-overhaul-2026-06-12`. **Backend deploys with the final cutover** (not mid-stream), but staging backend gets it for verification.

---

### Task 1: `CallAppeal` model + capabilities

**Files:** Modify `backend/app/models.py`; Modify `backend/app/main.py` (capabilities dict).

- [ ] **Step 1 — read the existing model patterns first.** Open `backend/app/models.py`; match the existing `Call` / `QaReport` style (PK type — they use string UUIDs or ints; FK names; `Base`; timestamp columns; how tables get created — confirm whether the app uses `Base.metadata.create_all` on startup or Alembic, and follow that exact mechanism).

- [ ] **Step 2 — add the model** (adapt column types to match the codebase's existing convention, e.g. string-UUID PK + `client_id`/`call_id` FKs exactly as `Call` uses):

```python
class CallAppeal(Base):
    __tablename__ = "call_appeals"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id = Column(String, ForeignKey("calls.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    agent_employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    status = Column(String, nullable=False, default="open")  # open|under_review|upheld|overturned
    agent_reason = Column(Text, nullable=False)
    qa_id = Column(String, ForeignKey("employees.id"), nullable=True)
    qa_response = Column(Text, nullable=True)
    corrected_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3 — capabilities.** In `get_user_capabilities` (or equivalent in `main.py`), add `canAppealCalls` (True for agent role) and `canReviewAppeals` (True for qa + admin/owner/super_admin). Mirror the existing capability style. Add matching fields to the frontend `UserCapabilities` type in Step (Task 3).

- [ ] **Step 4 — verify import/boot.** Run: `cd backend && python -c "import app.main"` → no errors. If `create_all` is used, the table is created on next boot; if Alembic, generate the migration following the existing migrations dir.

- [ ] **Step 5 — commit:** `git add backend/app/models.py backend/app/main.py && git commit -m "feat(appeals): CallAppeal model + capabilities"`

---

### Task 2: backend endpoints + RBAC tests (TDD)

**Files:** Modify `backend/app/main.py`; Test `backend/tests/test_appeals.py`.

- [ ] **Step 1 — write failing tests** mirroring the existing `backend/tests` fixtures (reuse the same app/client/db fixtures + auth-token helper used by `test_rbac.py`):

```python
def test_agent_can_appeal_own_flagged_call(client, agent_token, flagged_call):
    r = client.post(f"/api/calls/{flagged_call.id}/appeal",
                    json={"reason": "Customer was abusive; score unfair."},
                    headers={"Authorization": f"Bearer {agent_token}"})
    assert r.status_code == 201
    assert r.json()["status"] == "open"

def test_agent_cannot_appeal_unflagged_call(client, agent_token, good_call):
    r = client.post(f"/api/calls/{good_call.id}/appeal", json={"reason": "x"},
                    headers={"Authorization": f"Bearer {agent_token}"})
    assert r.status_code == 400  # not eligible

def test_agent_cannot_appeal_other_companys_call(client, agent_token, other_call):
    r = client.post(f"/api/calls/{other_call.id}/appeal", json={"reason": "x"},
                    headers={"Authorization": f"Bearer {agent_token}"})
    assert r.status_code in (403, 404)

def test_qa_resolves_appeal_overturn_keeps_ai_score(client, qa_token, open_appeal, db):
    r = client.patch(f"/api/appeals/{open_appeal.id}",
                     json={"status": "overturned", "qa_response": "Agreed.", "corrected_score": 75.0},
                     headers={"Authorization": f"Bearer {qa_token}"})
    assert r.status_code == 200
    # AI score on the QaReport is unchanged; correction lives on the appeal
    assert r.json()["corrected_score"] == 75.0

def test_agent_cannot_resolve_appeal(client, agent_token, open_appeal):
    r = client.patch(f"/api/appeals/{open_appeal.id}", json={"status": "upheld"},
                     headers={"Authorization": f"Bearer {agent_token}"})
    assert r.status_code == 403
```

(Build the `flagged_call`/`good_call`/`open_appeal` fixtures using the existing seed helpers; "flagged" = `flag_for_review` true OR grade ≤ D OR severity in {Major,Critical}.)

- [ ] **Step 2 — run, expect fail:** `cd backend && python -m pytest tests/test_appeals.py -q` → FAIL (routes missing).

- [ ] **Step 3 — implement endpoints** in `main.py` following existing route style:
  - `POST {API_V1_PREFIX}/calls/{call_id}/appeal` — require `canAppealCalls`; `_ensure_call_visible_to_user`; the caller's employee must equal `call.employee_id`; eligibility check (flagged/D/Major+) else 400; reject if an `open`/`under_review` appeal already exists (409/400); create row `status=open`; return 201 + dict.
  - `GET {API_V1_PREFIX}/appeals` — `canReviewAppeals` → appeals for the user's `client_id`; agent → own appeals only. Return list.
  - `PATCH {API_V1_PREFIX}/appeals/{id}` — require `canReviewAppeals`; scope to same client; set `status` ∈ {under_review,upheld,overturned}, `qa_response`, optional `corrected_score`, `qa_id`=reviewer employee, `resolved_at` when terminal. **Never modify the `QaReport` AI score.** Return updated dict.

- [ ] **Step 4 — run tests, expect pass:** `python -m pytest tests/test_appeals.py -q` → PASS. Then full suite `python -m pytest -q` stays green.

- [ ] **Step 5 — commit:** `git add backend/app/main.py backend/tests/test_appeals.py && git commit -m "feat(appeals): appeal create/list/resolve endpoints + RBAC tests"`

---

### Task 3: frontend API client + types

**Files:** Modify `calltone-UI/src/services/api.ts`.

- [ ] **Step 1 — add types + client** following the existing `contextApi` pattern:

```ts
export interface CallAppeal {
  id: string; callId: string; status: "open"|"under_review"|"upheld"|"overturned";
  agentReason: string; qaResponse?: string|null; correctedScore?: number|null;
  createdAt: string; resolvedAt?: string|null;
}
// extend UserCapabilities:
//   canAppealCalls?: boolean; canReviewAppeals?: boolean;
export const appealsApi = {
  create: (callId: string, reason: string) => api.post(`/calls/${callId}/appeal`, { reason }),
  list: () => api.get<{ appeals: CallAppeal[] }>(`/appeals`),
  resolve: (id: string, body: { status: string; qaResponse?: string; correctedScore?: number }) =>
    api.patch(`/appeals/${id}`, body),
};
```

- [ ] **Step 2 — verify:** `cd calltone-UI && npx tsc -p tsconfig.app.json --noEmit` → 0.
- [ ] **Step 3 — commit:** `git add calltone-UI/src/services/api.ts && git commit -m "feat(appeals): frontend api client + capability types"`

---

### Task 4: CallDetail appeal UI (agent submit + QA/admin resolve)

**Files:** Modify `calltone-UI/src/pages/CallDetail.tsx`.

- [ ] **Step 1 — eligibility helper** (reuse existing flag logic if present): `const eligible = report.flagForReview || ["D","F"].includes(report.grade) || ["Major","Critical"].includes(report.severity)`.

- [ ] **Step 2 — agent affordance:** when `user.capabilities.canAppealCalls` && it's the agent's own call && `eligible` && no existing open appeal → show an "Appeal this review" button → modal with a reason textarea → `appealsApi.create`. Show appeal status badge after submit. Match existing CallDetail card styling (no AI-slop copy).

- [ ] **Step 3 — QA/admin panel:** when `user.capabilities.canReviewAppeals` && an appeal exists for this call → show an "Appeal" panel: agent reason, created date, and actions Uphold / Overturn (+ optional note + optional corrected score) → `appealsApi.resolve`. Show resolution + a "Human-reviewed" badge; if `correctedScore` set, display it alongside the AI score (do not replace the gauge value).

- [ ] **Step 4 — verify:** `npx tsc -p tsconfig.app.json --noEmit && npx vitest run && npm run build` → all green.
- [ ] **Step 5 — commit:** `git add calltone-UI/src/pages/CallDetail.tsx && git commit -m "feat(appeals): agent appeal + QA resolve UI on call detail"`

---

### Task 5: deploy to staging (backend-staging + frontend-staging) + browser verify

**Files:** none.

- [ ] **Step 1** — deploy feature-branch `main.py` + new model to `/opt/calltone-backend-staging` (backup `main.py.bak-*`, `py_compile`, restart `calltone-backend-staging`; confirm the `call_appeals` table created). Build+deploy the staging frontend (existing pattern).
- [ ] **Step 2 — Playwright AGENT** (`staging_calltone_agent@spamok.com`): open the seeded flagged call → "Appeal this review" visible → submit a reason → status badge shows; cannot appeal a non-flagged call; 0 console errors.
- [ ] **Step 3 — Playwright QA** (`staging_calltone_qa@spamok.com`): open the same call → Appeal panel shows the agent's reason → Overturn + note + corrected score → resolves; AI gauge value unchanged, corrected score shown beside it; agent re-opens call → sees resolution. 0 console errors.
- [ ] **Step 4** — record results in the vault `Context-Tickets-Appeals-2026-06-15.md`.

---

## Self-Review
- **Spec F coverage:** table (T1), endpoints+RBAC (T2), api/types (T3), UI submit+resolve (T4), verify (T5). ✓
- **D-F1 honored:** AI score never overwritten; `corrected_score` stored on appeal + shown alongside (T2 step3, T4 step3). ✓
- **D-F2 honored:** eligibility = flagged/D/Major+ (T2, T4). ✓
- **Placeholder note:** column types/PK + table-creation mechanism (create_all vs Alembic) and the exact test fixtures must be matched to the existing codebase by the implementer in T1/T2 (flagged as a read-first step, not a guess). No invented identifiers in cross-task references.
