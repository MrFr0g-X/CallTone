# LAYER 3 — REST API

FastAPI server exposing CallTone QA scoring as HTTP endpoints.

## Quick Start

```bash
cd LAYER_3/api
pip install -r requirements.txt
uvicorn main:app --reload
```

Server runs at `http://localhost:8000`. Interactive docs at `/docs`.

## Endpoints

### `GET /health`

Returns system status.

```bash
curl http://localhost:8000/health
```

### `POST /analyze`

Score a call. Two modes:

**Fast path** — pre-processed LAYER 1 JSON:

```bash
curl -X POST http://localhost:8000/analyze \
  -F "json_path=Test_audio/bad_cs_results/bad_cs_denoised_diarized_with_emotions.json"
```

**Slow path** — raw audio upload (runs full pipeline):

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@path/to/call.mp3"
```

### `GET /reports/{call_id}`

Retrieve a previously scored report.

```bash
curl http://localhost:8000/reports/bad_cs_denoised_diarized_with_emotions
```

## Response Format

See `LAYER_2/README.md` for the QA report schema.
