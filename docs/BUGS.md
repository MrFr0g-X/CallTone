# CallTone — Bug Log

This document tracks defects discovered and resolved during Spring 2026
implementation of CallTone. Each entry links to the commit that fixed
the bug (or, for open items, points to the file that still carries the
problem). Severity follows the convention used in our project plan:

- **P0** — system-down / blocks core flow / security
- **P1** — major feature broken or visibly degraded
- **P2** — quality-of-life, hardening, or refactor

---

## B-01 — Frontend used hard-coded mock data instead of real API

- **Severity:** P1
- **Status:** Fixed
- **Fix commit:** `3798ca0` — *fix(ui): replace all mock data in admin and agent pages with real API data*
- **Symptom:** Admin and Agent dashboards rendered the same five
  fictitious calls regardless of which user was logged in. Demo
  reviewers could not verify that uploads actually reached the backend.
- **Root cause:** Pages were stubbed during early UI work and the TODO
  to wire them to `services/api.ts` was never closed.
- **Fix:** Replaced the inline fixtures with `useEffect` calls into
  `callsApi.list()` / `callsApi.detail()` and surfaced loading + error
  states. The mock arrays were deleted entirely so they cannot be
  re-imported by mistake.

## B-02 — API client lacked upload and status-polling endpoints

- **Severity:** P1
- **Status:** Fixed
- **Fix commit:** `9573ef2` — *fix(ui): clean up API client and add upload/status endpoints*
- **Symptom:** Drag-and-drop upload page existed in the UI but had no
  way to actually POST a file or check pipeline progress.
- **Root cause:** `services/api.ts` was scaffolded for auth only; the
  upload path was added to the backend (`268079c`) before the matching
  client method existed.
- **Fix:** Added `callsApi.upload(file)` (multipart/form-data) and
  `callsApi.status(callId)` (polled every 2 s by the upload page).
  Centralised the axios base URL in one place so prod and dev only
  differ by `.env`.

## B-03 — Pipeline stage hand-off stalled between Layer 1 modules

- **Severity:** P1
- **Status:** Fixed
- **Fix commit:** `ef72a0d` — *optimization for pipeline (i just had enough)*
- **Symptom:** Long calls (>3 min) would hit transcription, then sit
  for tens of seconds before role-ID started, then again before the
  emotion stage. End-to-end runtime exceeded the 5-minute MVP target.
- **Root cause:** Each stage re-loaded its model from disk because the
  previous run held GPU memory and wouldn't release until the Python
  process exited. Sub-process boundaries were unnecessary.
- **Fix:** Folded the three stages into a single Python process,
  loaded models once, and added explicit `torch.cuda.empty_cache()`
  between stages. Total runtime on a 10-minute call dropped from
  ~7 min to ~3.5 min.

## B-04 — Backend missing auth, admin management, and invite flow

- **Severity:** P0
- **Status:** Fixed
- **Fix commit:** `80de8a9` — *Add backend auth, admin management, QA call display, and invite flow*
- **Symptom:** The original FastAPI service exposed `/analyze` with no
  authentication. Anyone with the URL could upload audio and read any
  user's call list.
- **Root cause:** Original scaffold treated auth as out-of-scope for
  the proof-of-concept; we discovered during the QA-team handover that
  the report was being sent to multiple roles and we could not prove
  separation of duties.
- **Fix:** Added bcrypt-hashed passwords, JWT bearer tokens with a
  short expiry, role-based access control (agent / qa / admin /
  super_admin), an invite flow with one-time tokens, and per-user
  call listing. RBAC is now covered by `backend/tests/test_rbac.py`.

## B-05 — QA scoring covered only 4 of 7 dimensions

- **Severity:** P0
- **Status:** Fixed
- **Fix commit:** `3a19772` — *feat(scoring): expand QA scoring from 4 to all 7 dimensions*
- **Symptom:** QA report lacked Script Compliance, Factual Accuracy,
  and Severity, so the overall score was capped at 65% of true weight.
  Calls that failed scripted disclosures still scored "good."
- **Root cause:** Sprint 1 scope explicitly deferred the heavy three.
  When the supervisor asked to see a real end-to-end demo, the report
  shape no longer matched the spec.
- **Fix:** Added the three missing dimension prompts to the QA skill,
  re-weighted to the documented 15/10/15/5/25/25/5 split, and updated
  the report schema. Determinism contract preserved
  (temperature=0, seed=12345).

## B-06 — Models tracked as a git submodule (broken on clone)

- **Severity:** P2
- **Status:** Fixed
- **Fix commit:** `124a0da` — *convert models from submodule to regular folder*
- **Symptom:** `git clone` produced an empty `models/` directory.
  New collaborators could not run anything until they ran a separate
  `git submodule update --init`, which they never knew to do.
- **Root cause:** Early in the project we kept models in a private repo
  to avoid pushing weights to the main repo. We later moved the actual
  weights to `download_models.py` but the submodule pointer remained.
- **Fix:** Removed the submodule pointer, committed the model code
  directly, and documented `python download_models.py` as the only
  step needed to get weights.

## B-07 — Hard-coded `/home/mazen/...` paths across Layer 1

- **Severity:** P2
- **Status:** Open (workaround in place)
- **Files affected:**
  - `models/LAYER_1/audio_emotion_detection_enhanced/download_model.py:10`
  - `models/LAYER_1/test_full_pipeline.py` (lines 14, 20, 26)
  - `models/LAYER_1/pipeline/transcribe_diarize.py:567` (runtime patch)
- **Symptom:** Layer 1 only runs on the original developer's machine
  unless the absolute paths are edited.
- **Workaround:** `transcribe_diarize.py` rewrites the offending paths
  in `config.yaml` at runtime, so the production pipeline works.
- **Planned fix:** Introduce `models/LAYER_1/config.py` that resolves
  every path via `Path(__file__).parent`. Tracked in the plan as
  Sprint 1 Track A; deliberately deferred to keep this sprint focused
  on test coverage and reporting.

## B-08 — SenseVoice text-emotion output unreliable

- **Severity:** P1
- **Status:** Fixed (mitigation, not source-side fix)
- **Evidence in code:**
  `models/LAYER_1/pipeline/transcribe_diarize.py:430` and `:488`
  (`# Emotion detection disabled`)
- **Symptom:** SenseVoice's built-in text-emotion field returned
  `NEUTRAL` on >85% of utterances even when the audio was clearly
  angry, defeating the whole point of the emotion signal.
- **Root cause:** SenseVoice's text-emotion head is trained on short,
  clean clips and degrades on telephony-quality audio.
- **Fix:** Disabled the SenseVoice emotion field and routed all
  emotion through the audio-only Audio2Emotion v3 model
  (`models/LAYER_1/emotion_integration.py`). Per-utterance accuracy
  improved subjectively from "always neutral" to a usable signal,
  with the documented caveat that segments under 0.6 s are skipped.

---

## Summary

| ID   | Severity | Status               | Fix commit / location |
|------|----------|----------------------|-----------------------|
| B-01 | P1       | Fixed                | `3798ca0`             |
| B-02 | P1       | Fixed                | `9573ef2`             |
| B-03 | P1       | Fixed                | `ef72a0d`             |
| B-04 | P0       | Fixed                | `80de8a9`             |
| B-05 | P0       | Fixed                | `3a19772`             |
| B-06 | P2       | Fixed                | `124a0da`             |
| B-07 | P2       | Open (workaround)    | LAYER_1 config        |
| B-08 | P1       | Fixed (mitigation)   | `transcribe_diarize.py:430` |

All fix commits are in `feat/test-suite-and-evidence` history and on
`main`. Verify any hash with:

```
git log --all --oneline | grep <hash>
```
