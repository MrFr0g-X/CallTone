"""
CallTone LAYER 3 — REST API serving demo data + real LAYER 1 call detail.

All endpoints live under the /api prefix to match the calltone-UI frontend.
Auth is mock (email-based role resolution). Dashboards serve realistic mock
data. CallDetail for "call-bad-cs" serves real LAYER 1 transcript data.
"""

import sys
from pathlib import Path

from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from LAYER_3.api.demo_data import (
    AGENTS,
    AGENT_CALLS,
    AGENT_CALLS_MAP,
    TREND_DATA,
    get_call_detail,
)

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

router = APIRouter(prefix="/api")


# ── Auth (mock) ──────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str = ""


@router.post("/auth/login")
async def login(body: LoginRequest):
    name = body.email.split("@")[0]
    display = name[0].upper() + name[1:] if name else "User"
    role = "agent"
    if "admin" in body.email:
        role = "admin"
    elif "qa" in body.email:
        role = "qa"
    return {"token": f"demo-token-{role}", "user": {"name": display, "role": role}}


@router.post("/auth/logout")
async def logout():
    return {"message": "ok"}


@router.get("/auth/me")
async def me():
    return {"name": "Demo User", "role": "qa", "email": "demo@calltone.tech"}


# ── Agent Dashboard ──────────────────────────────────────────────────────────


@router.get("/agent/dashboard")
async def agent_dashboard(range: str = "Weekly"):
    calls = AGENT_CALLS
    n = len(calls) or 1
    avg = round(sum(c["overallScore"] for c in calls) / n)
    pol = round(sum(c["politeness"] for c in calls) / n, 1)
    emp = round(sum(c["empathy"] for c in calls) / n, 1)
    conflict_pct = round(sum(1 for c in calls if c["conflict"]) / n * 100)
    resolution_pct = round(sum(1 for c in calls if c["resolution"]) / n * 100)

    return {
        "scores": {
            "overall": avg,
            "politeness": pol,
            "empathy": emp,
            "conflictRate": conflict_pct,
            "resolutionRate": resolution_pct,
        },
        "trend": TREND_DATA,
    }


@router.get("/agent/calls")
async def agent_calls(range: str = "Weekly", sortBy: str = "time", page: int = 1):
    calls = list(AGENT_CALLS)
    if sortBy == "rating":
        calls.sort(key=lambda c: c["overallScore"], reverse=True)
    return {"calls": calls, "total": len(calls)}


# ── QA Dashboard ─────────────────────────────────────────────────────────────


@router.get("/qa/summary")
async def qa_summary(range: str = "Monthly"):
    total = sum(a["callCount"] for a in AGENTS)
    avg = round(sum(a["overallScore"] for a in AGENTS) / len(AGENTS))
    flagged = sum(
        1 for calls in AGENT_CALLS_MAP.values() for c in calls if c["status"] == "flagged"
    )
    return {"totalCalls": total, "avgScore": avg, "flaggedCalls": flagged}


@router.get("/qa/agents")
async def qa_agents(range: str = "Monthly"):
    return AGENTS


@router.get("/qa/agents/{agent_id}/calls")
async def qa_agent_calls(agent_id: str, range: str = "Monthly", sortBy: str = "time"):
    calls = list(AGENT_CALLS_MAP.get(agent_id, []))
    if sortBy == "rating":
        calls.sort(key=lambda c: c["overallScore"], reverse=True)
    return calls


@router.get("/qa/calls/{call_id}")
async def qa_call_detail(call_id: str):
    detail = get_call_detail(call_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Call not found: {call_id}")
    return detail


# ── Health ───────────────────────────────────────────────────────────────────


@router.get("/health")
async def health():
    return {"status": "healthy", "layer1": "available", "layer2": "demo_mode"}


# ── Analyze (stub) ───────────────────────────────────────────────────────────


@router.post("/analyze")
async def analyze():
    detail = get_call_detail("call-bad-cs")
    if not detail:
        raise HTTPException(status_code=503, detail="Demo data not available")
    return detail


# ── Mount & root ─────────────────────────────────────────────────────────────

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "CallTone API", "docs": "/docs"}
