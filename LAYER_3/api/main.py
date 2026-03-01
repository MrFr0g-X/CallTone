"""
CallTone LAYER 3 — REST API for QA scoring.

Endpoints:
    POST /analyze       Score a call (from pre-processed JSON or raw audio)
    GET  /health        Health check
    GET  /reports/{id}  Retrieve a stored report
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from LAYER_2.qa_scorer import score_call
from LAYER_3.api.models import ErrorResponse, HealthResponse, QAReport

app = FastAPI(
    title="CallTone QA API",
    description="AI-powered quality assurance scoring for customer service calls",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory report store (keyed by call_id)
_reports: dict[str, dict] = {}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/analyze", response_model=QAReport, responses={400: {"model": ErrorResponse}})
async def analyze(
    json_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """Score a customer service call.

    Two modes:
        - **json_path**: Path to a pre-processed LAYER 1 JSON (fast, for demo).
        - **file**: Raw audio upload — runs full LAYER 1 pipeline then LAYER 2 (slow).

    At least one of json_path or file must be provided.
    """
    if json_path is None and file is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'json_path' (path to LAYER 1 JSON) or 'file' (audio upload).",
        )

    l1_json_path: str

    if json_path is not None:
        # Fast path: score pre-processed LAYER 1 JSON directly
        resolved = Path(json_path)
        if not resolved.is_absolute():
            resolved = REPO_ROOT / json_path
        if not resolved.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {resolved}")
        l1_json_path = str(resolved)
    else:
        # Slow path: run full LAYER 1 pipeline on uploaded audio
        l1_json_path = await _run_layer1_pipeline(file)

    try:
        report = score_call(l1_json_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Store report for later retrieval
    _reports[report["call_id"]] = report

    return report


@app.get(
    "/reports/{call_id}",
    response_model=QAReport,
    responses={404: {"model": ErrorResponse}},
)
async def get_report(call_id: str):
    """Retrieve a previously scored QA report by call_id."""
    if call_id not in _reports:
        raise HTTPException(status_code=404, detail=f"Report not found: {call_id}")
    return _reports[call_id]


async def _run_layer1_pipeline(file: UploadFile) -> str:
    """Run the full LAYER 1 pipeline on an uploaded audio file.

    Saves the upload to a temp directory, runs pipeline.py as a subprocess,
    then locates the output JSON.

    Returns:
        Path to the LAYER 1 output JSON.
    """
    suffix = Path(file.filename).suffix if file.filename else ".wav"
    tmp_dir = Path(tempfile.mkdtemp(prefix="calltone_"))
    tmp_audio = tmp_dir / f"upload{suffix}"

    try:
        # Save uploaded file
        with open(tmp_audio, "wb") as f:
            content = await file.read()
            f.write(content)

        # Run LAYER 1 pipeline
        pipeline_script = REPO_ROOT / "LAYER_1" / "pipeline.py"
        result = subprocess.run(
            [sys.executable, str(pipeline_script), str(tmp_audio)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
            cwd=str(REPO_ROOT / "LAYER_1"),
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"LAYER 1 pipeline failed: {result.stderr[:500]}",
            )

        # Find the output JSON — pipeline produces <base>_diarized_with_emotions.json
        stem = tmp_audio.stem
        candidates = [
            tmp_dir / f"{stem}_diarized_with_emotions.json",
            tmp_dir / f"{stem}_enhanced_diarized_with_emotions.json",
            tmp_dir / f"{stem}_diarized.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        # Fallback: find any JSON in tmp_dir
        jsons = list(tmp_dir.glob("*.json"))
        if jsons:
            return str(jsons[0])

        raise HTTPException(
            status_code=500,
            detail="LAYER 1 pipeline completed but no output JSON found.",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="LAYER 1 pipeline timed out (>10 min).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
