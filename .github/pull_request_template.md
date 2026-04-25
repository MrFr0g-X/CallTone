<!--
Thanks for contributing to CallTone. Fill in each section briefly so
the reviewer (per CODEOWNERS) can ack quickly.
-->

## What

<!-- 1–2 sentences. What is changing and why. -->

## Scope

- [ ] Backend (`backend/app/**`)
- [ ] Frontend (`calltone-UI/**`)
- [ ] LAYER 1 / pipeline (`models/LAYER_1/**`)
- [ ] LAYER 2 / scorer (`models/LAYER_2/**`)
- [ ] LAYER 3 / report (`models/LAYER_3/**`)
- [ ] CI/CD or deploy (`.github/**`, `scripts/**`, `docker-compose*.yml`, `Dockerfile`)
- [ ] Docs

## How to test

<!--
Concrete commands. The reviewer should be able to copy-paste these.
e.g.
  cd backend && pytest tests/test_invite_flow.py -v
  cd calltone-UI && npm run dev   then click through /admin/team
-->

## Risk & rollback

<!--
- What's the worst-case impact if this regresses in prod?
- How would you roll back? (e.g. `./scripts/rollback.sh prod v0.3.1`)
- Does this change a database schema? An API contract? A skill version?
-->

## Checklist

- [ ] CI green (`backend`, `frontend` jobs)
- [ ] No new `console.log` / `print(...)` in committed code
- [ ] No secrets committed (gitleaks runs on PR but double-check)
- [ ] If touching `models/skill_implementation/skills/*.py`, the skill
      validator passes (`pytest models/skill_implementation/tests/`)
- [ ] If touching backend endpoints, added/updated a test
- [ ] If a UX-visible change, attached a before/after screenshot below

## Screenshots / evidence

<!-- drag images here or paste a link -->
