# CallTone Full Unit Testing Study Plan — 2026-04-24

Purpose: define the complete test strategy needed to make CallTone defensible for Implementation & Testing Report 2 and future production hardening.

This plan covers frontend, backend, model server, Layer 1, Layer 2, Layer 3, deployment scripts, security, and AI behavior.

## Current Test Baseline

| Area | Existing tests | Current evidence |
|---|---:|---|
| Backend auth/RBAC/security subset | 23 passing | `python -m pytest backend/tests/test_security.py backend/tests/test_rbac.py -q` |
| Model server auth/endpoints subset | 17 passing | `python -m pytest model_server/tests/test_auth.py model_server/tests/test_endpoints.py -q` |
| Layer 2 prompt-injection security subset | 4 passing | `python -m pytest models/LAYER_2/security/tests/test_static_scanner.py models/LAYER_2/security/tests/test_layer2_bypass_injection.py -q` |
| Frontend suite | 22 passing | `npm test -- --run` |
| Frontend lint/build | Passing with known Fast Refresh warnings | `npm run lint`, `npm run build` |
| Backend syntax | Passing | `python -m py_compile backend/app/main.py` |

## Testing Goals

| Goal | Target |
|---|---|
| No silent score-zero reports | Remote pipeline result must fail loudly if Layer 2 output is missing |
| No unauthorized data exposure | Every role-restricted endpoint has positive and negative tests |
| No transcript injection bypass | Layer 2 blocks critical prompt injection even when Layer 1 is skipped |
| No broken UI actions | Every visible button has a tested route, API call, or disabled state |
| No hardcoded production secrets | Secret scan and `.gitignore` validation in CI |
| Reproducible GPU recovery | Restore scripts tested with dry-run/static checks plus one manual restore log |
| Measured AI behavior | ASR WER and QA evidence checks preserved as regression artifacts |

## Test Pyramid

| Level | What belongs here | Why |
|---|---|---|
| Unit | Pure functions, role helpers, parsers, mappers, scoring extractors | Fast and deterministic |
| Component | React pages/components with mocked API | Catches UI regressions without live servers |
| Integration | FastAPI endpoints + DB test session, model-server mocked subprocess | Verifies contracts |
| Security | RBAC, upload validation, prompt injection, secrets scan | Required maturity evidence |
| AI behavior | ASR WER fixtures, Layer 2 JSON schema/evidence checks | Shows quality is measured |
| E2E/manual | One live upload through `calltone.tech` | Screenshot/demo proof |

## Backend Unit Test Plan

### Auth and user lifecycle

| Test | Priority | Expected |
|---|---|---|
| Login succeeds with active user | P0 | JWT returned |
| Login fails with wrong password | P0 | 401 |
| Inactive user cannot login | P0 | 403 or 401 |
| `/auth/me` rejects missing/invalid token | P0 | 401 |
| Invite accept rejects expired token | P1 | 410 |
| Invite accept rejects reused token | P1 | 400/409 |
| Role update logs security event | P1 | structured log emitted |

### RBAC and data visibility

| Test | Priority | Expected |
|---|---|---|
| Agent cannot access admin endpoints | P0 | 403 |
| Agent cannot upload calls | P0 | 403 |
| Agent sees only own calls | P0 | foreign call returns 403/404 |
| QA can access QA dashboard/upload/context | P0 | 200 |
| Viewer can read admin dashboard but cannot mutate users/settings | P0 | read 200, write 403 |
| Admin can manage users/settings | P0 | 200 |
| Super admin cannot delete self | P1 | 400 |

### Upload and pipeline settings

| Test | Priority | Expected |
|---|---|---|
| Non-audio upload rejected | P0 | 400 |
| Oversized upload rejected or configured limit enforced | P0 | 413/400 |
| Dangerous filename sanitized | P0 | no slash/backslash/null |
| Missing agent falls back safely or returns explicit 400 | P1 | deterministic behavior |
| ASR engine validates only `fasterwhisper` or `sensevoice` | P0 | invalid value rejected |
| Pipeline settings reject invalid `injectionScan` | P0 | 400 |
| Timeout env parser handles blank/zero/invalid values | P1 | deterministic |

### Result extraction and reporting

| Test | Priority | Expected |
|---|---|---|
| Missing Layer 2 output raises explicit failure | P0 | no fake zero report |
| Evidence extractor supports all Layer 2 evidence schemas | P0 | non-empty normalized rows |
| Layer 3 report JSON maps to UI fields | P0 | summary/strengths/weaknesses/actions |
| Duration metadata reads real audio duration | P1 | non-zero seconds |
| Grade calculation boundaries are correct | P1 | A/B/C/D/F thresholds |

## Model Server Test Plan

| Test | Priority | Expected |
|---|---|---|
| `/v1/health` remains public | P0 | 200 |
| `/v1/analyze` without token returns 401 | P0 | blocked |
| Wrong bearer token returns 401 | P0 | blocked |
| Missing `MODEL_SERVER_TOKEN` returns server misconfigured | P0 | 500 with clear detail |
| Missing company context returns explicit 400 | P0 | no subprocess launched |
| Context PUT rejects invalid payload shape | P1 | 400 |
| Audio upload writes only inside temp job dir | P0 | path traversal impossible |
| Job status lifecycle: queued -> running -> completed | P1 | stable schema |
| Job failure exposes safe error message and pipeline log pointer | P1 | no secret leakage |
| Subprocess timeout disabled by default but env-configurable | P1 | parser test |
| `pipeline.log` is written for failures | P1 | readable evidence |

## Layer 1 Test Plan

Layer 1 is hard to fully unit-test because it uses large models, but the wrappers can be tested with mocks.

| Test | Priority | Expected |
|---|---|---|
| SNR gate skips clean audio | P1 | denoise not called |
| SNR gate denoises noisy audio | P1 | denoise called |
| ASR engine selector accepts faster-whisper | P0 | faster-whisper loader used |
| ASR engine selector accepts SenseVoice | P0 | FunASR loader used |
| Invalid ASR engine falls back or rejects consistently | P1 | documented behavior |
| Word-to-turn alignment handles boundary words | P0 | no dropped first/last words |
| Speaker role ID parser tolerates malformed LLM JSON | P1 | fallback roles |
| Emotion integration falls back if ONNX provider fails | P1 | transcript still produced |
| Duration/sample-rate metadata extracted correctly | P1 | real values |

## Layer 2 Test Plan

| Test | Priority | Expected |
|---|---|---|
| Static injection fixture covers block/flag/safe | P0 | all expected |
| Skip-Layer1 injected transcript is blocked | P0 | `InjectionBlockedError` |
| `injection_scan_mode=off` is explicitly testable but marked unsafe | P1 | no scanner call |
| Transcript sandbox wrapper surrounds raw speech | P0 | delimiters present |
| Missing company context fails before scoring | P0 | explicit error |
| Empty context graph fails before scoring | P0 | explicit error |
| Context graph cache invalidates on version change | P1 | rebuild |
| Retriever returns relevant nodes per criterion | P1 | non-empty for seeded context |
| Scoring bundle appends context rule and thinking directive | P0 | prompt contains rule |
| Qwen think-block stripping leaves valid JSON | P0 | JSON parse passes |
| Parallel scoring falls back to sequential on startup failure | P1 | completed result |
| Overall weighted score excludes `overall_severity` correctly | P0 | math check |
| Evidence count drives confidence consistently | P1 | deterministic |

## Layer 3 Test Plan

| Test | Priority | Expected |
|---|---|---|
| Simple report renders from valid Layer 2 JSON | P1 | file generated |
| Narrative report no-skill mode produces UI JSON | P0 | summary/strengths/weaknesses/actions |
| Missing evidence does not crash renderer | P1 | clear fallback |
| Unsafe LaTeX characters are escaped | P1 | no compile break |
| Report filename is safe | P1 | no path traversal |

## Frontend Test Plan

### Routing and roles

| Test | Priority | Expected |
|---|---|---|
| Unauthenticated protected route redirects to login | P0 | `/login` |
| Agent home route is `/agent/dashboard` | P0 | correct |
| QA home route is `/qa/dashboard` | P0 | correct |
| Admin/super admin home route is `/admin/dashboard` | P0 | correct |
| QA cannot see admin mutation buttons | P0 | hidden/disabled |
| Viewer cannot see user mutation controls | P0 | hidden/disabled |
| Logout clears auth and returns to login without refresh | P0 | immediate redirect |

### Upload and context

| Test | Priority | Expected |
|---|---|---|
| Upload validates file selected | P0 | error toast |
| Upload validates agent selected | P0 | error toast |
| ASR toggle sends selected engine | P0 | form field present |
| Upload progress handles queued/running/completed | P0 | correct UI state |
| Upload failure shows backend error detail | P1 | no silent failure |
| Context company list loads | P0 | companies visible |
| Context ingest sends file/company | P1 | API called |
| Ticket create/update controls match role | P1 | QA create, admin approve |

### Dashboards and call detail

| Test | Priority | Expected |
|---|---|---|
| QA search filters by agent/file/status | P0 | correct subset |
| QA sort by rating/date/status works | P0 | sorted rows |
| Time range helper computes week/month/quarter/year | P0 | correct dates |
| Agent dashboard only calls agent APIs | P0 | no QA upload links |
| Call detail shows transcript, scores, evidence, report | P0 | all sections render |
| Missing AI report shows clear empty state | P1 | no crash |
| Audio button handles missing audio | P1 | safe error |

## Deployment Script Test Plan

| Script | Test type | Expected |
|---|---|---|
| `restore_gpu_server_from_rclone.sh` | shellcheck/static + documented dry-run | no syntax errors |
| `backup_gpu_server_to_rclone.sh` | shellcheck/static + exclude review | includes env/models/configs as intended |
| `launch_restored_gpu_model_server.sh` | static + command review | sources `.env`, launches port 8081 |
| `update_hetzner_tunnel_to_new_vast.sh` | static + parameter validation | no hardcoded stale host |
| `post_deploy_smoke.sh` | live/manual | health endpoints pass |
| `rollback.sh` | static/manual | restores previous release path |

## Security Test Plan

| Test | Priority | Expected |
|---|---|---|
| Secret scan blocks real HF tokens/private keys/passwords | P0 | no hits |
| `.gitignore` excludes env, keys, backup archives | P0 | tracked-file check passes |
| Backend security headers present | P0 | header tests |
| Rate limiter behavior on repeated login failures | P1 | throttled |
| Prompt injection block path | P0 | no ratings file |
| Prompt injection warning path | P1 | proceeds with warning |
| Model-server wrong token | P0 | 401 |
| Context endpoint role enforcement | P0 | non-QA/admin blocked |

## AI Evaluation Test Plan

| Test | Priority | Expected |
|---|---|---|
| WER benchmark against `test_eng.txt` | P0 | metrics file generated |
| Faster-whisper selected default benchmark | P0 | runtime + WER recorded |
| SenseVoice comparison benchmark | P1 | runtime + WER recorded |
| Speaker-turn count sanity check | P0 | no empty transcript |
| QA result schema validation | P0 | 7 dimensions, score, evidence |
| Evidence quote grounding check | P1 | quote exists in transcript or close match |
| Determinism run for same Layer 1 input | P1 | stable score within tolerance |
| Prompt-injection adversarial transcript | P0 | blocked |

## CI Gate Recommendation

Minimum pre-merge gate:

```powershell
python -m pytest backend/tests -q
python -m pytest model_server/tests -q
python -m pytest models/LAYER_2/security/tests -q
python -m pytest models/skill_implementation/tests -q
cd calltone-UI
npm test -- --run
npm run lint
npm run build
```

Minimum pre-demo gate:

```powershell
python scripts/security/layer2_injection_bypass_probe.py --output-json tmp_layer2_injection_bypass_probe_result.json
curl https://api.calltone.tech/api/health/detailed
```

Manual live gate:

- Upload `test.wav`.
- Confirm status `COMPLETED`.
- Confirm transcript, speaker turns, 7 QA scores, evidence, and AI report.
- Save call page screenshot and pipeline log.

## Coverage Targets

| Area | Target |
|---|---:|
| Backend pure utilities/security/RBAC | 85%+ |
| Model-server API/auth/job adapter | 80%+ |
| Frontend role/upload/dashboard helpers | 80%+ |
| Layer 2 security/context/scoring math | 85%+ |
| Layer 1 wrappers/alignment logic | 60%+ mocked coverage |
| Deployment scripts | static checks + manual restore evidence |

## Report 2 Evidence Mapping

| Rubric section | Evidence from this plan |
|---|---|
| Testing Strategy | Test pyramid + suite list |
| Test Coverage & Results | Commands, pass counts, coverage targets |
| Bug Tracking & Fixing | Security issue fixed in `mock_call_loader.py` |
| AI Checklist | WER, prompt injection, schema/evidence checks |
| Software Maturity | auth, RBAC, deployment, restore, observability tests |

## Next Implementation Order

1. Keep all existing green tests in CI.
2. Add missing backend RBAC negative tests for every admin/context/settings mutation.
3. Add model-server context precondition tests.
4. Add Layer 2 context graph and scoring math unit tests.
5. Add frontend page-level tests for admin team/context/upload/call-detail.
6. Add ASR WER regression script output as a checked evidence artifact, not a normal CI test.
7. Add shell/static checks for restore/deploy scripts.
