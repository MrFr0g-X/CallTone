"""
Pydantic v2 models for the CallTone QA API.

Matches the qa_report.json schema produced by LAYER 2.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class EvidenceQuote(BaseModel):
    speaker: str
    quote: str
    note: str


class QADimension(BaseModel):
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    score: float
    score_range: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quotes: List[EvidenceQuote] = []


class Layer1Summary(BaseModel):
    agent_talk_time_pct: float = 0.0
    customer_dominant_emotion: str = "unknown"
    customer_anger_pct: float = 0.0
    escalation_signals_detected: int = 0
    frustrated_signals_detected: int = 0


class ScorerMetadata(BaseModel):
    scorer_model: str
    skill_version: str
    scored_at: str


class QAReport(BaseModel):
    call_id: str
    file: str
    duration_seconds: float
    overall_score: float = Field(ge=0.0, le=100.0)
    flag_for_review: bool
    flag_reason: Optional[str] = None
    dimensions: List[QADimension]
    layer1_summary: Layer1Summary
    metadata: ScorerMetadata


class AnalyzeRequest(BaseModel):
    json_path: str = Field(
        description="Path to a pre-processed LAYER 1 JSON file"
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    layer1: str = "ready"
    layer2: str = "ready"


class ErrorResponse(BaseModel):
    detail: str
