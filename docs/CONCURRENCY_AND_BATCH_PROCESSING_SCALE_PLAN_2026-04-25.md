# CallTone Concurrency and Batch Processing Scale Plan

Date: 2026-04-25

Purpose: make CallTone accept many calls at the same time, process them reliably in batches or queue waves, and use the GPU efficiently without corrupting QA results.

## Current verified state

Stress test result on the live deployment:

| Concurrent uploads | Completed | Failed/rejected | Main observed reason |
|---:|---:|---:|---|
| 5 | 1 | 4 | model server busy, HTTP 409 |
| 10 | 2 | 8 | model server busy, HTTP 409 |
| 20 | 1 | 19 | upload SSL EOF/reset |
| 50 | 0 | 50 | write timeout / SSL EOF/reset |

The completed calls were valid: score 80.3, 7 QA dimensions, 21 evidence items, narrative report present.

The failure is capacity architecture, not scoring correctness.

## Why it failed

### 1. Backend upload path reads the whole file into memory

`backend/app/main.py` currently does:

```python
content = await file.read()
```

For the 89 MB test file:

- 5 concurrent uploads means about 445 MB request body pressure before pipeline work.
- 20 concurrent uploads means about 1.8 GB request body pressure.
- 50 concurrent uploads means about 4.45 GB request body pressure, before TLS buffers, reverse proxy buffering, Python memory, DB sessions, and upload writes.

This explains the SSL EOF/reset and write timeout behavior in the 20 and 50 wave.

### 2. Model server has an explicit single-slot guard

`model_server/jobs.py` says one GPU runs one pipeline at a time. `JobStore.acquire_slot()` returns `None` when `_active_id` is set.

`model_server/endpoints.py` then returns:

```json
{"detail": "another job is in flight", "retry_after_seconds": 30}
```

with HTTP 409.

That behavior is safe, but it is not a batch/queue design. It rejects load instead of absorbing it.

### 3. Each pipeline is a full subprocess

`model_server/pipeline_adapter.py` launches `models/run_full_pipeline.py` as a subprocess. This gives crash isolation and clean VRAM release, but it also means every accepted call pays cold-start/reload overhead for several models unless the process keeps them resident.

### 4. The workload is multi-stage, not one model call

One call includes:

- upload and disk write
- optional denoise
- pyannote diarization
- faster-whisper or SenseVoice ASR
- role identification
- emotion model
- Layer 2 seven skill scoring
- Layer 3 narrative report

Some stages are GPU-capable. Some are CPU-bound or partly CPU-bound. For example, pyannote states that the neural inference part can run on GPU, but clustering remains CPU-side.

## Target behavior

The system should:

1. Accept many uploads concurrently without HTTP/TLS resets.
2. Persist every accepted call as a durable job.
3. Show queue position and ETA in the UI.
4. Process calls by controlled worker capacity instead of rejecting with 409.
5. Use batching where the underlying model supports batching.
6. Scale to multiple GPU servers when one A100 is not enough.
7. Preserve security, context binding, and report correctness.

## Important distinction

"At the exact same time" can mean three different things:

1. Concurrent upload acceptance: many users upload files at once.
2. Concurrent queued jobs: many calls are waiting or running under a scheduler.
3. True simultaneous GPU inference: multiple model inferences share the GPU at the same time.

CallTone needs all three, but they require different changes.

## Recommended architecture

```text
Frontend
  |
  | 1. upload audio directly or streaming
  v
Backend API
  |
  | 2. create Call row + enqueue Job
  v
Durable Queue (Redis/RQ or Celery)
  |
  | 3. GPU workers pull jobs by capacity
  v
GPU Scheduler / Model Server
  |
  | 4. stage pipeline work
  v
ASR batcher / diarization worker / vLLM scorer / report worker
  |
  | 5. write transcript, QA scores, evidence, report
  v
PostgreSQL + object storage
```

## Phase 1 - Fix upload ingestion first

Goal: 50 users can upload the 89 MB test call without resetting connections.

### Changes

1. Stop reading full upload body into RAM.

Current:

```python
content = await file.read()
dest.write_bytes(content)
```

Replace with streaming chunk copy:

```python
with dest.open("wb") as out:
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(...)
        out.write(chunk)
```

2. Increase backend max file size if 85 to 100 MB WAV is expected to be normal.

Current backend cap is 100 MB. Model server cap is 200 MB. They should match a documented product limit, for example 250 MB or 500 MB.

3. Add upload status:

- `UPLOADING`
- `UPLOADED`
- `QUEUED`
- `RUNNING`
- `COMPLETED`
- `FAILED`

4. Add reverse-proxy settings for large uploads:

- larger `client_max_body_size`
- longer `client_body_timeout`
- sane temp path with enough disk
- no arbitrary 20 min processing timeout

5. Prefer direct-to-object-storage for production.

Best production path:

- Backend creates upload session.
- Frontend uploads audio directly to object storage.
- Backend receives `object_key`.
- Job worker downloads/streams from storage.

This prevents the API server from being the data pipe for 50 x 89 MB.

### Acceptance test

Run 50 concurrent uploads and require:

- 50 HTTP 202 responses
- 0 SSL EOF/reset
- 0 write timeout
- all calls created in DB
- all calls show queue position

## Phase 2 - Replace model-server 409 with a durable queue

Goal: accepted calls never fail just because the GPU is busy.

### Recommended queue

Use Redis + RQ for the first production version.

Why RQ first:

- simpler than Celery
- good enough for one or a few GPU workers
- jobs are visible in Redis
- easy retry/cancel/requeue semantics

Use Celery later if you need:

- complex routing
- distributed autoscaling
- scheduled jobs
- task chains/chords
- strict per-queue rate control

### Queue design

Queues:

- `ingest`: file validation, metadata, duration detection
- `gpu`: full pipeline or GPU-heavy stages
- `report`: final report/render/email/export
- `failed`: dead-letter jobs after max retries

Job record fields:

- `job_id`
- `call_id`
- `company_name`
- `asr_engine`
- `report_mode`
- `priority`
- `status`
- `queue_position`
- `attempts`
- `max_attempts`
- `created_at`
- `started_at`
- `finished_at`
- `worker_id`
- `gpu_server_id`
- `error_class`
- `error_message`

### Backend behavior

`POST /calls/upload` should return immediately:

```json
{
  "callId": "...",
  "jobId": "...",
  "status": "QUEUED",
  "queuePosition": 7,
  "etaSeconds": 620
}
```

The frontend should poll:

```text
GET /calls/{call_id}/status
```

and show:

- queued position
- estimated wait
- current stage
- retry count if failed once

### Model server behavior

Remove hard rejection:

- no HTTP 409 for normal user uploads
- scheduler accepts job metadata
- workers pull when capacity is available

Keep 409 only for direct debug endpoint misuse, not production uploads.

### Acceptance test

Run 50 concurrent uploads and require:

- all 50 become `QUEUED`
- no user-facing pipeline failures
- GPU processes jobs in order or by priority
- failed jobs retry once, then move to dead-letter with clear reason

## Phase 3 - Add controlled GPU worker concurrency

Goal: use one A100 safely without OOM or CUDA contention.

### Worker model

Start with:

- 1 GPU worker process for full pipeline jobs
- queue depth unlimited but controlled
- no parallel full-pipeline subprocesses yet

Then benchmark:

- 1 worker
- 2 workers
- 3 workers

For each:

- peak VRAM
- peak GPU utilization
- median runtime
- p95 runtime
- failure rate
- transcript WER
- diarization quality
- QA score stability

Do not assume more workers means faster. A100 can host several models, but pyannote, CTranslate2, llama-cpp/vLLM, and ONNX Runtime can fight for memory and streams.

### NVIDIA MPS option

Enable CUDA MPS only after single-worker queueing is stable. MPS can let multiple CUDA processes cooperate on one GPU, but it does not magically batch the pipeline. It helps when several processes have idle gaps or small kernels.

Test plan:

- baseline without MPS
- MPS enabled with 2 pipeline workers
- MPS enabled with 3 pipeline workers
- compare throughput and failures

If MPS gives higher throughput without transcript/report degradation, keep it. If not, disable it.

### Acceptance test

For the 89 MB test call:

- 10 queued jobs complete without failure
- p95 latency is predictable
- no OOM
- no zombie processes
- no stuck job

## Phase 4 - Real batching inside pipeline stages

Goal: make the GPU process more work per second, not just queue more work.

### ASR batching

faster-whisper supports batched inference and shows major speedups in its own benchmark. The published benchmark shows `faster-whisper (batch_size=8)` reducing a large-v2 GPU run from 1m03s to 17s, with VRAM rising from 4525 MB to 6090 MB.

Plan:

1. Replace sequential faster-whisper transcription with `BatchedInferencePipeline`.
2. Batch chunks inside one long call first.
3. Then add cross-call micro-batching:
   - collect ASR segments for up to 250-500 ms
   - group by model/language/beam settings
   - run batch
   - return segments to original jobs

Suggested A100 starting point:

- `batch_size=16` for faster-whisper-large-v3
- increase to 24/32 only after monitoring VRAM

### Diarization batching

pyannote is less batch-friendly. It can run neural inference on GPU, but clustering is CPU-side. The first practical improvement is not true batching; it is:

- preload pipeline once
- keep it resident
- use known `num_speakers=2`
- pass waveform from memory
- cap CPU thread pools
- run 1 or 2 diarization workers max

Future improvement:

- split diarization into segmentation/embedding services
- batch segmentation across calls with Triton if exported
- keep clustering on CPU worker pool

### Layer 2 LLM batching

Current Layer 2 already runs seven skill prompts in parallel inside one call. That helps one call, but it does not give good multi-call serving.

Recommended upgrade:

- move Qwen3-8B scoring from llama-cpp subprocess calls to vLLM server
- expose OpenAI-compatible local endpoint
- send every skill prompt as a normal chat/completion request
- let vLLM continuous batching combine requests across calls

This is the biggest throughput upgrade for scoring.

Recommended service split:

```text
Pipeline worker
  |
  | HTTP/OpenAI-compatible requests
  v
vLLM Qwen3-8B scoring server
```

Settings to benchmark:

- Qwen3-8B AWQ or FP16/BF16 depending VRAM
- max model len 4096 or 8192
- max concurrent sequences tuned by vLLM
- prefix caching on if prompts share rubric/context structure
- structured output parser retained

### Layer 3 batching

Layer 3 narrative report should also use the same vLLM server. It is less latency-critical than Layer 2 and can be lower priority in the LLM scheduler.

## Phase 5 - Multi-GPU / multi-server scale-out

Goal: 20 to 50 calls finish in a reasonable wall-clock window, not just queue.

One A100 cannot process 50 full calls truly simultaneously if each call runs diarization, ASR, scoring, and report. The production design should support adding GPU servers.

### Scheduler model

Create a `gpu_workers` table:

- `worker_id`
- `host`
- `status`
- `gpu_name`
- `vram_total`
- `vram_free`
- `active_jobs`
- `max_jobs`
- `last_heartbeat`
- `version`
- `queue_tags`

Dispatch policy:

- shortest queue first
- reject unhealthy workers
- pin calls to one worker for all artifacts
- retry on another worker if worker dies before stage start

### Scale math

If one call takes about 90 seconds end-to-end:

- one worker serial: 40 calls/hour
- two workers serial: 80 calls/hour
- four workers serial: 160 calls/hour

If stage batching reduces average processing to 45 seconds:

- one worker: 80 calls/hour
- four workers: 320 calls/hour

Batching improves throughput. More GPU workers improves wall-clock queue drain. Use both.

## Phase 6 - Batch upload UX

Goal: QA users can upload a folder/list of calls and track a batch.

Add:

- `POST /batches`
- `POST /batches/{batch_id}/files`
- `GET /batches/{batch_id}`
- `GET /batches/{batch_id}/calls`
- `POST /batches/{batch_id}/cancel`
- `POST /batches/{batch_id}/retry-failed`

UI:

- batch name
- company context
- ASR engine
- agent mapping mode
- priority
- progress bar
- per-call status table
- failed-only filter
- export CSV/PDF

Batch status:

- `CREATED`
- `UPLOADING`
- `QUEUED`
- `RUNNING`
- `PARTIAL_FAILED`
- `COMPLETED`
- `CANCELLED`

## Phase 7 - Observability and evidence

For every job, persist:

- upload latency
- queue wait time
- stage start/end times
- GPU worker id
- ASR engine
- model versions
- context version
- prompt/rubric version
- score and evidence counts
- failure class

Metrics:

- queue depth
- oldest queued age
- jobs completed/minute
- p50/p95/p99 end-to-end latency
- GPU utilization
- GPU memory
- backend disk free
- upload failure rate
- HTTP 409 count, should become zero for user uploads
- retry count

Alerts:

- queue age > target
- GPU worker heartbeat missing
- disk free below 20 GB
- upload error rate > 2%
- job failure rate > 2%
- no completed jobs for 10 minutes while queue is non-empty

## Implementation order

## Detailed execution task board

Status legend:

- `[x]` completed in this working session.
- `[~]` in progress / partially implemented.
- `[ ]` planned and not implemented yet.

### Track A - Upload ingestion and API stability

- `[x]` A1. Identify upload bottleneck from stress-test evidence.
- `[x]` A2. Locate backend memory-risk code path: `backend/app/main.py` uses `await file.read()`.
- `[x]` A3. Replace full-body upload read with chunked streaming to disk.
- `[x]` A4. Compute SHA-256 while streaming, not after buffering the whole file.
- `[x]` A5. Delete partial upload file if request exceeds max size.
- `[x]` A6. Align backend max upload cap with model-server cap.
- `[x]` A7. Add tests proving upload code uses bounded chunk reads and cleans partial files.
- `[ ]` A8. Add reverse-proxy deployment notes for large upload body/timeouts.
- `[ ]` A9. Re-run 20/50 upload stress after deployment.

### Track B - Queue semantics

- `[x]` B1. Add persistent job fields or a dedicated pipeline jobs table.
- `[x]` B2. Change upload response from "processing started" to "queued" once queue exists.
- `[x]` B3. Add queue position and ETA to `GET /calls/{call_id}/status`.
- `[~]` B4. Add retry and dead-letter state.
- `[x]` B5. Update frontend upload page to display queued/running state.
- `[x]` B6. Stop normal upload bursts from submitting all jobs to the model server at once.

Current Track B implementation note:

- Implemented a durable database-backed `pipeline_jobs` table with queued/running/completed/failed states. This serializes GPU submissions and prevents normal concurrent uploads from all hitting the single-slot model server at once.
- Queued jobs now survive backend restarts. Startup recovery moves interrupted `running` jobs back to `queued`.
- Retry state is partially complete: failed jobs are retried up to `max_attempts` before terminal `failed`. A manual dead-letter/retry UI endpoint is still pending.

### Track C - Model-server scheduler

- `[~]` C1. Replace `JobStore.acquire_slot()` hard rejection with queued jobs.
- `[ ]` C2. Keep direct debug endpoint 409 behavior only for manual/debug mode.
- `[ ]` C3. Add worker heartbeat and active job metadata.
- `[ ]` C4. Add `/v1/queue` or `/v1/capacity` for observability.
- `[ ]` C5. Add `/tmp/calltone_job_*` cleanup on terminal state and startup.

Current Track C implementation note:

- The model server still has the safe single-slot guard.
- The backend now serializes submissions before they reach the model server, so ordinary user uploads should no longer create a wave of `HTTP 409 another job is in flight` failures.
- The final model-server-native scheduler is still pending.

### Track D - GPU throughput optimization

- `[ ]` D1. Benchmark single full-pipeline worker after upload fix.
- `[ ]` D2. Test two full-pipeline workers without MPS.
- `[ ]` D3. Test two full-pipeline workers with NVIDIA MPS.
- `[ ]` D4. Add faster-whisper batched inference inside one call.
- `[ ]` D5. Add cross-call ASR micro-batching if intra-call batching is stable.
- `[ ]` D6. Move Layer 2/3 LLM serving to vLLM for continuous batching.

### Track E - Batch UX and production ops

- `[ ]` E1. Add batch upload API.
- `[ ]` E2. Add batch progress page/table.
- `[ ]` E3. Add retry failed calls action.
- `[~]` E4. Add Prometheus-style metrics or JSON metrics endpoint.
- `[ ]` E5. Add alert thresholds for queue age, disk, GPU worker health, and failure rate.

Current Track E implementation note:

- Added protected `GET /api/pipeline/queue` JSON endpoint for super-admin/admin/QA users. It reports active call id, queued call ids, queue depth, per-job ETA, and estimated drain time. This is useful for screenshots and operational visibility, but it is not a full Prometheus metrics endpoint yet.

### Verification log

2026-04-25 local verification after Track A changes:

```text
python -m py_compile backend/app/main.py backend/tests/test_upload_settings.py
python -m pytest backend/tests/test_upload_settings.py backend/tests/test_remote_pipeline.py -q
14 passed

python -m pytest backend/tests -q
64 passed

npm test -- --run
22 passed

npm run build
passed

npm run lint
0 errors, 9 pre-existing Fast Refresh warnings
```

Track A result: backend upload ingestion is now bounded-memory. This should remove the Python-side RAM amplification from 20/50 concurrent large uploads. It does not yet solve GPU queueing; Track B/C are still required to stop HTTP 409 model-server busy failures.

Track B result: concurrent uploads now return `QUEUED`, get a queue position/ETA, and are submitted through a database-backed queue worker instead of one process per upload. This should remove the model-server 409 wave for normal uploads and survive backend restart. Redis/RQ is still a future scale option, but the current implementation now has durable job records.

### A. Immediate fixes, 0.5-1 day

1. Stream backend upload to disk instead of `await file.read()`.
2. Match backend/model-server max file sizes.
3. Add explicit error classification in status UI.
4. Keep current single-slot model server, but show "queued/busy" correctly.

Expected result: 20/50 upload waves stop crashing at TLS/write layer.

### B. Queue MVP, 1-2 days

1. Add Redis.
2. Add RQ worker or Celery worker.
3. Backend upload creates DB row and enqueues job.
4. GPU worker pulls and calls model server.
5. UI shows queue position.

Expected result: 50 uploads become 50 queued jobs, not 50 failures.

### C. GPU worker scheduler, 2-3 days

1. Replace model server `acquire_slot()` rejection with worker-owned dequeue.
2. Add heartbeat and active job tracking.
3. Add retry/dead-letter handling.
4. Add cleanup for `/tmp/calltone_job_*`.

Expected result: stable batch processing on one GPU.

### D. ASR batching, 1-2 days

1. Add faster-whisper batched mode.
2. Benchmark batch sizes 8, 16, 24, 32.
3. Compare WER against `test_eng.txt`.
4. Lock best speed/accuracy profile.

Expected result: lower per-call ASR time with controlled VRAM use.

### E. vLLM scoring server, 2-4 days

1. Start Qwen3-8B under vLLM.
2. Replace llama-cpp backend calls with OpenAI-compatible HTTP client.
3. Keep structured JSON validation.
4. Batch/concurrently send Layer 2 skill prompts across calls.
5. Add separate priority for Layer 3 report.

Expected result: Layer 2/3 throughput improves under concurrent calls.

### F. Multi-GPU scale, 2-4 days

1. Add worker registry.
2. Add multiple Vast GPU workers.
3. Add routing/heartbeat/failover.
4. Run 5/10/20/50 stress again.

Expected result: 20/50 call batches drain in parallel across GPUs.

## What not to do

Do not just raise uvicorn workers. Each worker can duplicate model memory and break GPU isolation.

Do not run 50 full pipeline subprocesses on one A100. That will cause OOM, CUDA contention, and unpredictable results.

Do not keep accepting uploads through API RAM. Stream to disk or direct-to-object-storage.

Do not hide 409 as generic failure. It should become queue position, not "FAILED".

Do not batch calls without preserving company context version, ASR engine, and prompt version per call.

## Final target

For the same 89 MB `test.wav`:

### Single A100 MVP target

- 50 concurrent uploads accepted.
- 50 jobs queued.
- 0 upload SSL reset.
- 0 HTTP 409 visible to user.
- calls processed sequentially or with safe limited concurrency.
- queue ETA visible.

### Optimized one-A100 target

- 50 concurrent uploads accepted.
- 2-4 calls can be in active staged processing where safe.
- ASR and LLM stages use batching.
- GPU utilization stays high during ASR/LLM phases.
- no OOM.

### Multi-GPU production target

- 50 concurrent uploads accepted.
- 50 jobs distributed across workers.
- completed reports returned predictably.
- UI shows batch progress and failed-only retry.

## Research sources

- FastAPI `UploadFile` uses a spooled temporary file and exposes async chunk reads: https://fastapi.tiangolo.com/tutorial/request-files/
- Celery workers support queues, routing, autoscale, and worker concurrency controls: https://docs.celeryq.dev/en/main/userguide/workers.html
- RQ is a simple Redis-backed Python job queue: https://python-rq.org/docs/
- NVIDIA MPS enables cooperative multi-process CUDA use: https://docs.nvidia.com/deploy/mps/index.html
- NVIDIA Triton supports dynamic batching and concurrent model execution: https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2600/user-guide/docs/tutorials/Conceptual_Guide/Part_2-improving_resource_utilization/README.html
- vLLM supports continuous batching, prefix caching, quantization, and OpenAI-compatible serving: https://docs.vllm.ai/en/latest/
- Hugging Face TGI documents continuous batching as a production LLM serving optimization: https://huggingface.co/docs/text-generation-inference/main/index
- faster-whisper benchmark shows significant gains from `batch_size=8`: https://github.com/SYSTRAN/faster-whisper
- pyannote documents GPU execution for neural inference and CPU-side clustering behavior: https://huggingface.co/pyannote/speaker-diarization-3.0

## Implementation report - 2026-04-25 MVP concurrency hardening

### Problem confirmed from stress testing

The first stress test proved the system did not fail because the QA model was bad. It failed because the request/concurrency path was not designed for burst upload traffic:

- 5 parallel uploads: only 1 completed; the rest hit model-server busy responses.
- 10 parallel uploads: only 2 completed; the rest hit model-server busy responses.
- 20 parallel uploads: most failed at upload/network layer with SSL EOF/reset behavior.
- 50 parallel uploads: no calls completed; failures were write timeouts and SSL EOF/reset.
- Completed calls were valid: score around 80.3, all 7 dimensions present, evidence present, report present.

The conclusion is architectural: the single A100 worker can process calls, but the backend must not let many uploaded calls attack the model server at once. The system needs upload streaming and queue semantics before true batch/GPU scaling.

### Implemented now

#### Backend upload ingestion

File: `backend/app/main.py`

Implemented:

- Replaced full upload buffering with chunked streaming to disk via `_stream_upload_to_disk()`.
- Uploads are read in `UPLOAD_CHUNK_SIZE = 1 MB` chunks.
- SHA-256 is computed while streaming, so there is no second memory-heavy file read.
- Partial files are removed if the upload exceeds the configured limit or if streaming fails.
- Empty uploads are rejected.
- Backend upload cap is now `200 MB`, aligned with the model-server path and the real 89 MB stress-test WAV.

Why this matters:

- Previous behavior used `await file.read()`, which could hold many full WAV files in RAM during a stress wave.
- With 20 or 50 concurrent 89 MB uploads, that design caused memory pressure and TLS/write instability before jobs reached the GPU.
- Streaming makes memory usage bounded by chunk size rather than file size.

#### Backend queue MVP

File: `backend/app/main.py`

Implemented:

- Added durable DB queue table: `pipeline_jobs`.
- Added queue worker thread: `_pipeline_queue_worker_loop()`.
- Upload endpoint now creates the call row with `current_step="queued"`.
- Upload endpoint returns `status="QUEUED"` instead of implying immediate GPU execution.
- Upload endpoint returns `queuePosition` and `etaSeconds`.
- Status endpoint now includes queue metadata:
  - `queuePosition`
  - `queuedCount`
  - `etaSeconds`
- Normal upload bursts are serialized before reaching the model server.
- Backend startup recovery requeues jobs that were `running` during a backend restart.
- Failed jobs retry until `max_attempts`, then become terminal `failed`.

Why this matters:

- The model server still has a safe single-slot guard.
- Before this change, concurrent uploads spawned concurrent backend pipeline processes, and each process tried to submit to the single-slot GPU model server.
- That produced `HTTP 409 another job is in flight` failures.
- With this MVP, the backend accepts uploads, queues them, and sends only one job at a time to the GPU path.

Limitations:

- This is durable in the backend database, not only process memory.
- If the backend process restarts, queued jobs remain in `pipeline_jobs`.
- If the backend dies while a job is `running`, startup recovery moves it back to `queued`.
- This is still a single-worker GPU queue. Multiple backend processes should not each run their own queue worker unless a DB lock/Redis worker ownership layer is added.

#### Queue observability endpoint

File: `backend/app/main.py`

Implemented:

- Added protected endpoint: `GET /api/pipeline/queue`.
- Allowed roles: `super_admin`, `admin`, `qa`.
- Denied role: `agent`.
- Response includes:
  - `activeCallId`
  - `queuedCount`
  - `queuedCallIds`
  - `etaSecondsPerJob`
  - `estimatedDrainSeconds`

Why this matters:

- QA/admin users and developers can inspect queue state without guessing from one call status page.
- This gives useful evidence for screenshots and operational review.
- This is not a full Prometheus metrics endpoint yet.

#### Frontend upload UX

Files:

- `calltone-UI/src/pages/UploadCall.tsx`
- `calltone-UI/src/services/api.ts`

Implemented:

- Frontend max upload cap changed to `200 MB`.
- Upload validation message changed to `File too large (max 200 MB)`.
- Upload page now understands the `queued` pipeline step.
- After upload, the UI displays queue position and estimated time when available.
- Status polling refreshes queue metadata.
- API typings now include queue fields in upload and status responses.
- API layer exposes typed `pipelineApi.getQueue()` for future admin/QA queue UI.

Why this matters:

- Users no longer see a burst upload as "failed because GPU busy" when the correct behavior is "accepted and queued".
- The UI and backend now agree on file-size limits.
- Future admin pages can consume queue state through a typed API helper instead of hardcoded fetch calls.

#### Tests added/updated

File: `backend/tests/test_upload_settings.py`

Added tests for:

- Streaming upload writes chunks and computes SHA-256 correctly.
- Oversized streamed uploads delete partial files.
- Upload endpoint enqueues pipeline work instead of starting immediate GPU processing.
- Queue snapshot returns active/queued positions.
- Queue observability endpoint is role-protected and reports active/queued jobs.

Files:

- `calltone-UI/src/test/api-helpers.test.ts`
- `calltone-UI/src/test/upload-validation.test.ts`

Updated tests for:

- 200 MB frontend upload cap.
- Oversized file validation behavior.

### Verification

Commands run from `grad-project-main`:

```text
python -m py_compile backend/app/main.py backend/tests/test_upload_settings.py
```

Result:

```text
passed
```

```text
python -m pytest backend/tests/test_upload_settings.py backend/tests/test_remote_pipeline.py -q
```

Result:

```text
14 passed
```

```text
python -m pytest backend/tests -q
```

Result:

```text
64 passed
```

Commands run from `grad-project-main/calltone-UI`:

```text
npm test -- --run
```

Result:

```text
7 test files passed
22 tests passed
```

```text
npm run build
```

Result:

```text
passed
```

Build warnings:

- `caniuse-lite` database is old.
- Main JS bundle is larger than 500 KB.

These warnings existed as build-quality items; they do not block the queue/upload change.

```text
npm run lint
```

Result:

```text
0 errors
9 warnings
```

Warnings are existing React Fast Refresh warnings in shared component/helper files.

### Expected behavior after deployment

For a burst of uploads from normal website usage:

- Uploads should be accepted if they are valid audio files under 200 MB.
- Calls should enter `PENDING` with `current_step="queued"`.
- Frontend should show queue status instead of failing immediately.
- Backend should submit one call at a time to the model server.
- The previous model-server 409 wave should be eliminated for normal uploads.

For direct abuse or debug calls to the model server:

- The model server can still return busy/409 because its own scheduler has not been replaced yet.
- That is acceptable for this MVP because the public user path now queues at the backend.

### What is still required for full production batch scale

The MVP is enough to stop the immediate 5/10/20/50 burst failure mode, but it is not the final scale architecture. Remaining work:

- Add a manual retry/dead-letter admin action.
- Add explicit DB row-locking or Redis/RQ if multiple backend worker processes are introduced.
- Add model-server-native queue/capacity endpoint and cleanup logic for `/tmp/calltone_job_*`.
- Add batch upload API and batch progress table.
- Benchmark one versus two GPU workers on the A100.
- Add ASR batching inside faster-whisper or move to a batch ASR worker.
- Move LAYER 2/3 to vLLM for continuous prompt batching.
- Re-run live stress tests for 5, 10, 20, and 50 calls after deployment.
- Generate the final LaTeX stress-test report using the new queued behavior.

### Deployment note

This implementation was deployed live to the backend and frontend hosting.

Live backend deployment result:

```text
calltone-backend.service active
uvicorn workers: 1
pipeline_jobs table: present
public /api/health/detailed: database ok, model_server ok, gpu_available true
```

Live frontend deployment result:

```text
https://calltone.tech -> HTTP 200
index.html references deployed build assets index-DQNZ5H9G.js and index-iy9O3cmg.css
```

Live validation:

```text
3 concurrent local-uplink uploads of 89 MB test.wav:
COMPLETED 3/3, FAILED 0, HTTP 409 0, upload reset/timeout 0

5 concurrent server-side uploads using existing Hetzner test.wav fixture:
COMPLETED 5/5, FAILED 0, HTTP 409 0, upload reset/timeout 0
upload time over loopback: ~2.6 seconds per 89 MB call
all completed calls: score 80.3, 7 dimensions, 21 evidence items, 62 speaker turns, AI report present

10 concurrent server-side uploads using existing Hetzner test.wav fixture:
COMPLETED 10/10, FAILED 0, HTTP 409 0, upload reset/timeout 0
upload time over loopback: min 4.768s, avg 5.289s, max 5.483s
total queue drain: 1180.493s (~19m40s)
all completed calls: score 80.3, severity Moderate, 7 dimensions, 21 evidence items, 62 speaker turns, AI report present
PDF evidence report: ALL_DOCS/Imp & Testing Rpt 2/Final/stress-tests/stress_20260425_server_side_10/CallTone_10_Call_Stress_Report.pdf
```

Important testing correction:

The correct way to stress queueing is to keep `test.wav` on Hetzner and run `scripts/stress/server_side_upload_stress.py` from the backend host. Re-uploading the same 89 MB file from the local Windows machine makes upload latency mostly measure local internet bandwidth instead of CallTone backend ingestion.

Final deployed additions beyond the first queue MVP:

- protected `GET /api/pipeline/jobs`
- protected `POST /api/pipeline/jobs/{call_id}/retry`
- protected `POST /api/pipeline/jobs/{call_id}/dead-letter`
- Admin Settings GPU Queue Operations panel
- model-server `GET /v1/capacity`
- safer stress helper credential handling via `CALLTONE_STRESS_PASSWORD`

Current remaining scale work:

- batch upload UI/table
- Redis/RQ/Celery if backend workers are increased above 1 or multiple API nodes are introduced
- ASR batching
- vLLM continuous batching for LAYER 2/3
- optional 20/50 server-side stress runs when there is enough time to keep the single GPU busy for the full drain
