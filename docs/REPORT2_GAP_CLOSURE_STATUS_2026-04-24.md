# Report 2 Gap Closure Status — 2026-04-24

This file records what was closed after comparing the project against:

- `Implementation & Testing Report 2-Template-v2.docx.pdf`
- `Grading Rubric- Testing Report 2.docx.pdf`
- `minimum requirements that determine the maturity of your graduation project.txt`

## Closed In This Pass

| Gap | Status | Evidence |
|---|---|---|
| Security review before screenshots | Closed | `docs/SECURITY_PIPELINE_REVIEW_2026-04-24.md` |
| Direct Layer 2 injection-bypass test | Closed | `scripts/security/layer2_injection_bypass_probe.py` |
| Automated regression for bypass attack | Closed | `models/LAYER_2/security/tests/test_layer2_bypass_injection.py` |
| Project-wide unit testing study plan | Closed | `docs/PROJECT_UNIT_TESTING_STUDY_PLAN_2026-04-24.md` |
| Vault test count stale | Closed | `obsidian-vault/600-Testing/Test-Matrix.md` |
| Vault security evidence missing | Closed | `obsidian-vault/600-Testing/Security-Review-2026-04-24.md` |
| Tracked mock DB password | Closed | `backend/app/mock_call_loader.py` now requires env vars |
| Final report stale GPU/model/runtime claims | Partially closed | `docs/Final_Report_v2.tex` patched and PDF recompiles |
| Readiness plan lacked security evidence | Closed | `ALL_DOCS/.../Final/CallTone_Final_Optimization_and_Screenshot_Readiness_Plan.md` |
| Load/concurrency evidence | Closed | 10-call server-side stress passed: `10/10 COMPLETED`, 0 failures, `ALL_DOCS/.../stress_20260425_server_side_10/CallTone_10_Call_Stress_Report.pdf` |
| GPU backup/restore evidence | Closed | `gdrive:hothifa-full-gpu-20260425-005615-queue-ready`, 20 GPU restore files / 23 total with vault evidence pack, 38.839 GiB, vault runbook updated |

## Verified Commands

```powershell
python scripts/security/layer2_injection_bypass_probe.py --output-json tmp_layer2_injection_bypass_probe_result.json
python -m pytest models/LAYER_2/security/tests/test_static_scanner.py models/LAYER_2/security/tests/test_layer2_bypass_injection.py backend/tests/test_security.py backend/tests/test_rbac.py model_server/tests/test_auth.py model_server/tests/test_endpoints.py -q
python -m py_compile backend/app/mock_call_loader.py backend/app/main.py scripts/security/layer2_injection_bypass_probe.py
cd calltone-UI
npm test -- --run
cd ../docs
pdflatex -interaction=nonstopmode -halt-on-error Final_Report_v2.tex
```

Observed:

- Security/backend/model-server/Layer 2 subset: `44 passed`.
- Frontend suite: `22 passed`.
- Backend suite after queue work: `65 passed`.
- Model-server suite after capacity endpoint: `22 passed`.
- Layer 2 bypass probe: blocked, `severity=critical`, no rating file created.
- `Final_Report_v2.pdf` regenerated successfully.
- Focused secret scan found no real leaked HF token, server password, SSH private key, or removed DB password.

## Still Remaining Before Final Screenshots

| Remaining item | Why it matters | Next action |
|---|---|---|
| Final screenshot bank | Required for evidence-based report | Capture 14 screenshots from readiness plan |
| Full Report 2 document in official template | Current `Final_Report_v2` is broader than the Week 12 template | Copy final facts/evidence into the required Report 2 structure |
| Individual contribution table | 15% rubric item | Add student, program, contribution, evidence, percentage |
| Load/concurrency evidence | Maturity checklist asks for multiple users/RPS/p95 | Closed for current scope with 10-call server-side stress; optional 20/50 remains future |
| Swagger/OpenAPI evidence | API design checklist | Screenshot `/docs` or exported OpenAPI JSON |
| PII retention/deletion policy | AI governance/security checklist | Add retention, deletion, and access policy section |
| Failure simulation evidence | Demo readiness checklist | Capture tunnel/model-server-down behavior and recovery explanation |
| Final GitHub evidence | Rubric requires commits/PRs | Commit/push final code/docs state, excluding secrets/artifacts |

## Current Remaining Items After 2026-04-25 Closeout

| Remaining item | Status | Action |
|---|---|---|
| Official Report 2 template document | Still required | Transfer final evidence into the exact provided template |
| Screenshot bank | Still required | Capture UI, health, queue, report, context, Drive backup, GitHub evidence |
| Individual contribution table | Still required | Add member-by-member contribution/evidence/percentage |
| PII retention/deletion policy | Still required | Add concise policy section to report |
| Failure simulation screenshot | Still required | Capture controlled model-server/tunnel-down and recovery behavior |
| Final GitHub commit hash | Pending this push | Include hash in final report after push |

## Current Judgment

The system is technically demo-capable. The remaining work is packaging and proof discipline: screenshots, official Report 2 formatting, load/API/failure evidence, and final Git history alignment.
