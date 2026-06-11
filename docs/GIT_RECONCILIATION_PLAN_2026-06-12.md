# Git Reconciliation Plan — main vs live branch (2026-06-12)

## The situation (verified)
- **Live servers run `integration/release-2026-04-25`** (newest branch, 2026-04-27).
  Live prod `app/main.py` hash matches this branch's `backend/app/main.py` exactly.
- **`main` is stale and DIVERGED**, not just behind:
  - `main` has **7 commits** not in integration (the CI/CD trunk + deploy-pipeline work:
    `deploy.yml`, `rsync_repo.sh`, `smoke_http.sh`, tunnel watchdog, branching docs,
    plus a different lineage of email/models/seed/tests/frontend).
  - integration has **44 commits** not in main (the actual product: multi-tenant,
    client policies, invite flow, etc.).
  - A fast-forward is impossible; a real 3-way merge would touch ~44 files with
    conflict risk across backend + frontend. **Not a defense-week operation.**
- **CI deploys from `main`.** So today, dispatching the deploy workflow would push
  stale code to prod AND wipe the live security hotfix. The pipeline is a loaded gun
  until `main` is reconciled.

## My security fixes — current state
- **Live servers:** M1 + L1 already applied + verified (prod + staging). L2 waits for GPU.
- **Local git (`integration` working tree):** my edits are UNCOMMITTED:
  - `backend/app/main.py`   (M1)
  - `backend/app/database.py` (L1)
  - `model_server/auth.py`  (L2)
  - new: `docs/SECURITY_AUDIT_2026-06-11.md`, `docs/SECURITY_HOTFIX_DEPLOY_RUNBOOK_2026-06-12.md`,
    `docs/GIT_RECONCILIATION_PLAN_2026-06-12.md`, `scripts/security/apply_hotfix_inplace.py`
- **Working-tree caveat:** the branch ALSO carries a pile of *other* uncommitted work
  that is NOT mine (docker/, compose*.yaml, AGENTS.md, `security_headers.py`,
  `test_security.py`, `model_server/main.py`, `setup_vast_container.sh`, `.gitignore`,
  `run_demo.bat`, eval artifacts, tmp files, …). These must NOT be swept into the
  security commit blindly.

## Recommended plan (two phases)

### Phase 1 — NOW (safe, zero merge risk): version the security fix on the live branch
1. Commit ONLY the 6 security files above to `integration/release-2026-04-25`.
2. Push `integration/release-2026-04-25` to origin.
- Result: the fixes are versioned on the branch that actually matches prod. No merge,
  no conflicts, no deploy. CI stays dormant (nobody dispatches deploys during defense).

### Phase 2 — AFTER defense: make `main` the real trunk again
1. Decide the 7 main-only CI/CD commits' fate (keep — they're the deploy pipeline).
2. `git switch main; git merge integration/release-2026-04-25` → resolve conflicts
   (favor integration for product code; keep main's `deploy.yml`/ci-scripts).
3. Run full test suite + a staging deploy dry-run.
4. Fast-forward `main` to the merged result; thereafter CI-from-main is safe.
5. Separately decide what to do with the other uncommitted working-tree work.

## Decisions I need from you
- **Scope:** commit ONLY the 6 security files (recommended), or also some of the
  other uncommitted work?
- **Branch + timing:** Phase 1 now on `integration` (recommended) — or hold entirely?
- **Author identity:** git is currently configured as `PlumHeadd
  <habibamagdysayed7@gmail.com>`. Commit as you (`MrFr0g-X` / Hothifa) instead?
- **Push:** push to origin now, or commit locally and leave the push to you?
