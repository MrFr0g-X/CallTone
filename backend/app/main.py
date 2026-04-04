from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import secrets
import uuid

from fastapi import FastAPI, HTTPException, status, Depends, Body, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import Base, engine, get_db, settings, SessionLocal
from app.models import (
    User, Client, Role,
    Employee, Customer, Call, Transcript, QaReport,
    _compute_grade,
)
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_password, hash_password
import app.models  # noqa

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


@app.get("/")
def root():
    return {"message": "CallTone API is running"}


@app.post(f"{settings.API_V1_PREFIX}/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role.name,
            "clientId": user.client_id,
        },
    }


@app.get(f"{settings.API_V1_PREFIX}/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role.name,
        "clientId": current_user.client_id,
        "isActive": current_user.is_active,
        "lastLoginAt": current_user.last_login_at,
    }

@app.get(f"{settings.API_V1_PREFIX}/admin/dashboard")
def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin", "manager", "viewer"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    active_clients = db.query(Client).filter(Client.status == "active").count()
    trial_clients = db.query(Client).filter(Client.status == "trial").count()
    total_clients = db.query(Client).count()

    total_agents = (
        db.query(User)
        .join(User.role)
        .filter(User.role.has(name="agent"))
        .count()
    )

    # Compute real stats from call data
    total_calls = db.query(Call).count()
    completed_calls = db.query(Call).filter(Call.status == "COMPLETED").count()

    avg_score_row = db.query(func.avg(QaReport.overall_score)).first()
    avg_quality_score = round(avg_score_row[0], 1) if avg_score_row and avg_score_row[0] else 0

    # Build monthly call trend from actual data
    calls_by_month = (
        db.query(
            func.extract("month", Call.call_time).label("m"),
            func.count(Call.id).label("cnt"),
        )
        .filter(Call.call_time.isnot(None))
        .group_by("m")
        .all()
    )
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_map = {int(r.m): r.cnt for r in calls_by_month} if calls_by_month else {}

    # Show last 7 months of data
    now = datetime.now(timezone.utc)
    calls_trend = []
    for offset in range(6, -1, -1):
        m = ((now.month - 1 - offset) % 12) + 1
        calls_trend.append({"month": month_names[m - 1], "calls": month_map.get(m, 0)})

    return {
        "kpis": {
            "activeClients": active_clients,
            "trialClients": trial_clients,
            "totalClients": total_clients,
            "totalAgents": total_agents,
            "callsThisMonth": total_calls,
            "monthlyRevenue": 0,
        },
        "health": {
            "avgQualityScore": avg_quality_score,
            "activeClients": active_clients,
            "completedCalls": completed_calls,
            "totalCalls": total_calls,
            "uptime": 99.9,
        },
        "trends": {
            "revenue": [],
            "calls": calls_trend,
        },
    }

@app.get(f"{settings.API_V1_PREFIX}/admin/clients")
def get_admin_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin", "manager", "viewer"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    clients = db.query(Client).order_by(Client.name.asc()).all()

    result = []
    for client in clients:
        agent_count = (
            db.query(User)
            .join(User.role)
            .filter(User.client_id == client.id, User.role.has(name="agent"))
            .count()
        )

        qa_count = (
            db.query(User)
            .join(User.role)
            .filter(User.client_id == client.id, User.role.has(name="qa"))
            .count()
        )

        result.append(
            {
                "id": client.id,
                "name": client.name,
                "industry": client.industry or "Unknown",
                "status": client.status,
                "plan": client.plan,
                "agents": agent_count,
                "qaCount": qa_count,
                "callsThisMonth": 0,
                "mrr": 0,
                "avgScore": 0,
            }
        )

    active_clients = len([c for c in result if c["status"] == "active"])
    trial_clients = len([c for c in result if c["status"] == "trial"])
    total_agents = sum(c["agents"] for c in result)
    total_calls = sum(c["callsThisMonth"] for c in result)
    total_mrr = sum(c["mrr"] for c in result)

    return {
        "summary": {
            "totalClients": len(result),
            "activeClients": active_clients,
            "trialClients": trial_clients,
            "totalAgents": total_agents,
            "totalCalls": total_calls,
            "totalMRR": total_mrr,
        },
        "clients": result,
    }


@app.get(f"{settings.API_V1_PREFIX}/admin/users")
def get_admin_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin", "manager", "viewer"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    users = (
        db.query(User)
        .join(User.role)
        .order_by(User.created_at.asc())
        .all()
    )

    result = []
    for user in users:
        result.append(
            {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role.name,
            "status": (
                "invited"
                if user.invite_token and not user.is_active
                else ("active" if user.is_active else "disabled")
            ),
           "lastLogin": user.last_login_at.isoformat() if user.last_login_at else None,
            "clientId": user.client_id,
            }
        )

    return {
        "currentUserId": current_user.id,
        "users": result,
    }

@app.post(f"{settings.API_V1_PREFIX}/admin/users/invite")
def invite_admin_user(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to invite users")

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    role_name = (payload.get("role") or "").strip()

    if not name or not email or not role_name:
        raise HTTPException(status_code=400, detail="Name, email, and role are required")

    allowed_roles = ["admin", "manager", "viewer", "qa", "agent"]
    if role_name not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role")

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    invite_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    invited_user = User(
        full_name=name,
        email=email,
        password_hash="INVITED_ACCOUNT_NO_PASSWORD_YET",
        role_id=role.id,
        client_id=None,
        is_active=False,
        invite_token=invite_token,
        invite_expires_at=now + timedelta(days=7),
        invited_at=now,
    )

    db.add(invited_user)
    db.commit()
    db.refresh(invited_user)

    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={invite_token}"

    return {
        "message": "Invitation created successfully",
        "inviteUrl": invite_url,
        "user": {
            "id": invited_user.id,
            "name": invited_user.full_name,
            "email": invited_user.email,
            "role": role.name,
            "status": "invited",
            "lastLogin": None,
            "clientId": invited_user.client_id,
        },
    }


@app.get(f"{settings.API_V1_PREFIX}/auth/invite/{{token}}")
def get_invite_details(token: str, db: Session = Depends(get_db)):
    user = db.query(User).join(User.role).filter(User.invite_token == token).first()

    if not user:
        raise HTTPException(status_code=404, detail="Invalid invitation link")

    if not user.invite_expires_at or user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation link has expired")

    if user.is_active:
        raise HTTPException(status_code=400, detail="Invitation has already been used")

    return {
        "name": user.full_name,
        "email": user.email,
        "role": user.role.name,
        "expiresAt": user.invite_expires_at,
    }


@app.post(f"{settings.API_V1_PREFIX}/auth/invite/accept")
def accept_invite(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    token = (payload.get("token") or "").strip()
    password = (payload.get("password") or "").strip()
    confirm_password = (payload.get("confirmPassword") or "").strip()

    if not token or not password or not confirm_password:
        raise HTTPException(status_code=400, detail="Token, password, and confirm password are required")

    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    user = db.query(User).filter(User.invite_token == token).first()

    if not user:
        raise HTTPException(status_code=404, detail="Invalid invitation link")

    if not user.invite_expires_at or user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation link has expired")

    if user.is_active:
        raise HTTPException(status_code=400, detail="Invitation has already been used")

    user.password_hash = hash_password(password)
    user.is_active = True
    user.activated_at = datetime.now(timezone.utc)
    user.invite_token = None
    user.invite_expires_at = None

    db.commit()
    db.refresh(user)

    return {
        "message": "Account activated successfully"
    }


@app.patch(f"{settings.API_V1_PREFIX}/admin/users/{{user_id}}/role")
def update_user_role(
    user_id: int,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_role_name = (payload.get("role") or "").strip()
    allowed_roles = ["admin", "manager", "viewer", "qa", "agent"]

    if new_role_name not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    role = db.query(Role).filter(Role.name == new_role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    user.role_id = role.id
    db.commit()
    db.refresh(user)

    return {
        "message": "Role updated successfully",
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": role.name,
        },
    }

@app.patch(f"{settings.API_V1_PREFIX}/admin/users/{{user_id}}/status")
def update_user_status(
    user_id: int,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_status = (payload.get("status") or "").strip()

    if new_status not in ["active", "disabled"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    if user.invite_token and not user.is_active:
        raise HTTPException(status_code=400, detail="Invited users cannot be enabled/disabled. They must accept the invitation or be deleted.")

    user.is_active = new_status == "active"
    db.commit()
    db.refresh(user)

    return {
        "message": f"User {new_status} successfully",
        "user": {
            "id": user.id,
            "name": user.full_name,
            "status": "active" if user.is_active else "disabled",
        },
    }


@app.get(f"{settings.API_V1_PREFIX}/admin/users/{{user_id}}/invite-link")
def get_invite_link(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.invite_token or user.is_active:
        raise HTTPException(status_code=400, detail="This user does not have an active invitation")

    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={user.invite_token}"

    return {
        "inviteUrl": invite_url
    }


@app.delete(f"{settings.API_V1_PREFIX}/admin/users/{{user_id}}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    was_invited = bool(user.invite_token and not user.is_active)
    user_name = user.full_name

    db.delete(user)
    db.commit()

    return {
        "message": "Invitation deleted successfully" if was_invited else "User deleted successfully",
        "deletedType": "invitation" if was_invited else "user",
        "name": user_name,
    }

## QA Calls list endpoint

@app.get(f"{settings.API_V1_PREFIX}/qa/calls")
def get_qa_calls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Call, Employee, QaReport)
        .join(Employee, Call.employee_id == Employee.id)
        .outerjoin(QaReport, Call.id == QaReport.call_id)
        .order_by(Call.created_at.desc())
        .all()
    )

    results = []
    for call, emp, report in rows:
        results.append({
            "callId": call.id,
            "filename": call.original_filename,
            "callTime": call.call_time.isoformat() if call.call_time else None,
            "status": call.status,
            "agentName": emp.full_name,
            "overallScore": report.overall_score if report else None,
            "severity": report.severity if report else None,
        })

    return {"calls": results}


## QA Call detail endpoint

@app.get(f"{settings.API_V1_PREFIX}/qa/calls/{{call_id}}")
def get_qa_call_detail(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(Call, Employee, Transcript, QaReport)
        .join(Employee, Call.employee_id == Employee.id)
        .outerjoin(Transcript, Call.id == Transcript.call_id)
        .outerjoin(QaReport, Call.id == QaReport.call_id)
        .filter(Call.id == call_id)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    call, emp, transcript, report = row

    drive_file_id = call.drive_file_id
    drive_preview_url = (
        f"https://drive.google.com/file/d/{drive_file_id}/preview"
        if drive_file_id else None
    )
    drive_download_url = (
        f"https://drive.google.com/uc?export=download&id={drive_file_id}"
        if drive_file_id else None
    )

    return {
        "callId": call.id,
        "filename": call.original_filename,
        "driveFileId": drive_file_id,
        "drivePreviewUrl": drive_preview_url,
        "driveDownloadUrl": drive_download_url,
        "callTime": call.call_time.isoformat() if call.call_time else None,
        "durationSeconds": call.duration_seconds,
        "status": call.status,
        "agentName": emp.full_name,
        "transcript": {
            "fullText": transcript.full_text if transcript else "",
            "speakerTurns": transcript.speaker_turns or [] if transcript else [],
        },
        "report": {
            "overallScore": report.overall_score if report else None,
            "grade": report.grade if report else None,
            "severity": report.severity if report else None,
            "dimensionScores": report.dimension_scores or {} if report else {},
            "dimensionReports": report.dimension_reports or {} if report else {},
            "evidence": report.evidence or [] if report else [],
            "confidenceScores": report.confidence_scores or {} if report else {},
            "reportJson": report.report_json or {} if report else {},
        },
    }


## Agent endpoints

@app.get(f"{settings.API_V1_PREFIX}/agent/dashboard")
def get_agent_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(QaReport)
        .join(Call, QaReport.call_id == Call.id)
        .order_by(Call.created_at.desc())
        .limit(50)
        .all()
    )

    if reports:
        overall_scores = [r.overall_score for r in reports if r.overall_score is not None]
        avg = sum(overall_scores) / len(overall_scores) if overall_scores else 0

        # Compute real averages from dimension_scores stored in JSONB
        dim_totals: dict[str, list[float]] = {}
        for r in reports:
            if r.dimension_scores:
                for key, val in r.dimension_scores.items():
                    dim_totals.setdefault(key, []).append(float(val))

        def _dim_avg(key: str) -> float:
            vals = dim_totals.get(key, [])
            return round(sum(vals) / len(vals), 1) if vals else 0

        politeness = _dim_avg("politeness_tone")
        empathy = _dim_avg("empathy")
        conflict_rate = round(
            100 * len([r for r in reports if r.overall_score and r.overall_score < 60]) / len(reports), 1
        )
        resolution_rate = _dim_avg("issue_resolution")
    else:
        avg = 0
        politeness = 0
        empathy = 0
        conflict_rate = 0
        resolution_rate = 0

    # Build trend from recent reports
    trend = []
    for i, r in enumerate(reversed(reports[:12])):
        trend.append({"name": f"Call {i + 1}", "overall": r.overall_score or 0})

    return {
        "scores": {
            "overall": round(avg, 1),
            "politeness": politeness,
            "empathy": empathy,
            "conflictRate": conflict_rate,
            "resolutionRate": resolution_rate,
        },
        "trend": trend,
    }


@app.get(f"{settings.API_V1_PREFIX}/agent/calls")
def get_agent_calls(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Call, Employee, QaReport)
        .join(Employee, Call.employee_id == Employee.id)
        .outerjoin(QaReport, Call.id == QaReport.call_id)
        .order_by(Call.created_at.desc())
        .limit(50)
        .all()
    )

    results = []
    for call, emp, report in rows:
        results.append({
            "callId": call.id,
            "filename": call.original_filename,
            "callTime": call.call_time.isoformat() if call.call_time else None,
            "status": call.status,
            "agentName": emp.full_name,
            "overallScore": report.overall_score if report else None,
            "severity": report.severity if report else None,
        })

    return {"calls": results, "total": len(results)}


## ── Call Upload endpoint (FR-10) ──────────────────────────────────────

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp3",
    "audio/flac", "audio/ogg", "audio/webm", "audio/mp4",
    "application/octet-stream",
}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"


def _run_real_pipeline(call_id: str, audio_path: str, company: str = "BankServ Global"):
    """
    Background task: run the real 3-layer AI pipeline on an uploaded audio file.

    Layer 1: denoise → transcribe + diarize → role ID → emotion detection
    Layer 2: 7-criterion QA scoring via LLM skills + context graph
    Layer 3: LaTeX report generation

    If the real pipeline fails (models missing, GPU unavailable, etc.), the
    error is stored on the Call record so the status endpoint reports it.
    """
    import sys as _sys
    import json as _json

    # Add model paths so pipeline imports resolve
    for p in [
        MODELS_DIR,
        MODELS_DIR / "LAYER_1",
        MODELS_DIR / "LAYER_1" / "resemble-enhance",
        MODELS_DIR / "LAYER_1" / "pipeline",
        MODELS_DIR / "skill_implementation",
    ]:
        if str(p) not in _sys.path:
            _sys.path.insert(0, str(p))

    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return

        call.status = "PROCESSING"

        # ── Layer 1: Audio → structured transcript JSON ──────────────────
        call.current_step = "denoising"
        db.commit()

        from run_full_pipeline import (
            denoise_audio, transcribe_diarize,
            run_role_identification, run_emotion_detection,
        )

        denoised_path = denoise_audio(audio_path)

        call.current_step = "transcribing"
        db.commit()
        txt_path, json_path = transcribe_diarize(denoised_path, num_speakers=None)

        call.current_step = "role_identification"
        db.commit()
        try:
            run_role_identification(json_path, txt_path)
        except Exception:
            pass  # non-fatal

        call.current_step = "emotion_detection"
        db.commit()
        try:
            txt_path, json_path = run_emotion_detection(denoised_path, json_path)
        except Exception:
            pass  # non-fatal

        # Read the Layer 1 output
        with open(json_path, "r", encoding="utf-8") as f:
            l1_output = _json.load(f)

        # Build transcript for DB
        speaker_turns = l1_output.get("transcript", [])
        full_text = " ".join(seg.get("text", "") for seg in speaker_turns if seg.get("text"))
        duration = l1_output.get("call_metadata", {}).get("duration_seconds", 0)

        transcript = Transcript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            full_text=full_text,
            speaker_turns=speaker_turns,
            asr_engine="SenseVoice",
            asr_model="SenseVoiceSmall",
            avg_confidence=0.91,
        )
        db.add(transcript)
        call.duration_seconds = round(duration, 3) if duration else None
        db.commit()

        # ── Layer 2: Transcript → QA scores ─────────────────────────────
        call.current_step = "scoring"
        db.commit()

        output_dir = UPLOAD_DIR / f"{call_id}_results"
        output_dir.mkdir(exist_ok=True)
        rating_output = str(output_dir / "layer2_ratings.json")

        from run_full_pipeline import run_layer2
        l2_result = run_layer2(
            json_path, company, rating_output, injection_scan_mode="static",
        )

        overall_score = l2_result.get("overall_weighted_score", 0)
        criteria = l2_result.get("criteria_ratings", {})

        dim_scores = {}
        dim_reports = {}
        confidence_scores = {}
        evidence = []
        for crit, info in criteria.items():
            dim_scores[crit] = info.get("score", 0)
            dim_reports[crit] = info.get("summary", "")
            confidence_scores[crit] = info.get("consensus_confidence") or info.get("confidence", 0.0)
            for ev in info.get("evidence", []):
                evidence.append({
                    "dimension": crit,
                    "quote": ev.get("quote", ""),
                    "speaker": ev.get("speaker", ""),
                    "reason": ev.get("reason", ""),
                })

        # Determine severity from score
        if overall_score >= 85:
            severity = "Minor"
        elif overall_score >= 65:
            severity = "Moderate"
        else:
            severity = "Major"

        report_json = l2_result.get("report_json", {})
        if not report_json:
            strengths = []
            weaknesses = []
            for crit, info in criteria.items():
                label = crit.replace("_", " ").title()
                score = info.get("score", 0)
                if score >= 80:
                    strengths.append(f"{label}: {info.get('summary', 'Good performance')}")
                elif score < 65:
                    weaknesses.append(f"{label}: {info.get('summary', 'Needs improvement')}")
            report_json = {
                "summary": f"Call scored {overall_score}/100 overall. "
                           f"Rated by CallTone AI pipeline against {company} quality standards.",
                "strengths": strengths or ["Overall adequate performance"],
                "weaknesses": weaknesses or ["No major issues detected"],
                "recommended_actions": [
                    info.get("recommendation", "")
                    for info in criteria.values() if info.get("recommendation")
                ] or ["Continue monitoring"],
            }

        # Resolve QA employee for report
        qa_emp = db.query(Employee).filter(Employee.role == "QA").first()
        qa_id = qa_emp.id if qa_emp else call.employee_id

        report = QaReport(
            id=str(uuid.uuid4()),
            call_id=call_id,
            qa_id=qa_id,
            overall_score=round(overall_score, 1),
            grade=_compute_grade(overall_score),
            severity=severity,
            dimension_scores=dim_scores,
            dimension_reports=dim_reports,
            evidence=evidence,
            confidence_scores=confidence_scores,
            report_json=report_json,
        )
        db.add(report)

        # ── Layer 3: Generate LaTeX report (non-blocking) ───────────────
        call.current_step = "report_generation"
        db.commit()

        try:
            from run_full_pipeline import run_layer3
            run_layer3(rating_output, str(output_dir), mode="simple", use_skill=False)
        except Exception:
            pass  # Layer 3 is optional; scores already saved

        call.current_step = "completed"
        call.status = "COMPLETED"
        db.commit()

    except Exception as exc:
        db.rollback()
        call = db.query(Call).filter(Call.id == call_id).first()
        if call:
            call.status = "FAILED"
            call.error_message = str(exc)
            call.current_step = "error"
            db.commit()
    finally:
        db.close()


def _run_pipeline(call_id: str, audio_path: str):
    """
    Try the real AI pipeline first. If it fails to import (models not
    installed on this machine), the error is recorded on the Call record.
    """
    try:
        _run_real_pipeline(call_id, audio_path)
    except Exception as exc:
        db = SessionLocal()
        try:
            call = db.query(Call).filter(Call.id == call_id).first()
            if call and call.status != "COMPLETED":
                call.status = "FAILED"
                call.error_message = f"Pipeline error: {exc}"
                call.current_step = "error"
                db.commit()
        finally:
            db.close()


@app.post(f"{settings.API_V1_PREFIX}/calls/upload")
async def upload_call(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    agent_id: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.name not in ["super_admin", "admin", "qa"]:
        raise HTTPException(status_code=403, detail="Not authorized to upload calls")

    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Upload an audio file.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 100 MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    sha256 = hashlib.sha256(content).hexdigest()
    call_id = str(uuid.uuid4())
    safe_filename = file.filename or "upload.wav"

    # Save file to disk
    dest = UPLOAD_DIR / f"{call_id}_{safe_filename}"
    dest.write_bytes(content)

    # Resolve agent employee record — pick first agent if none specified
    employee = None
    if agent_id:
        employee = db.query(Employee).filter(Employee.id == agent_id).first()
    if not employee:
        employee = db.query(Employee).filter(Employee.role == "AGENT").first()
    if not employee:
        raise HTTPException(status_code=400, detail="No agent found in database")

    # Resolve or create customer
    customer = db.query(Customer).first()
    if not customer:
        customer = Customer(
            id=str(uuid.uuid4()),
            display_name="Uploaded Call Customer",
            phone_hash="upload",
        )
        db.add(customer)
        db.flush()

    call = Call(
        id=call_id,
        customer_id=customer.id,
        employee_id=employee.id,
        original_filename=safe_filename,
        size_bytes=len(content),
        sha256=sha256,
        status="PENDING",
        current_step="uploaded",
        call_time=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    # Run the real AI pipeline in background
    background_tasks.add_task(_run_pipeline, call_id, str(dest))

    return {
        "callId": call_id,
        "filename": safe_filename,
        "status": "PENDING",
        "message": "Call uploaded successfully. Processing started.",
    }


@app.get(f"{settings.API_V1_PREFIX}/calls/{{call_id}}/status")
def get_call_status(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    has_transcript = db.query(Transcript).filter(Transcript.call_id == call_id).first() is not None
    has_report = db.query(QaReport).filter(QaReport.call_id == call_id).first() is not None

    return {
        "callId": call.id,
        "status": call.status,
        "currentStep": call.current_step,
        "hasTranscript": has_transcript,
        "hasReport": has_report,
        "error": call.error_message,
    }


@app.post(f"{settings.API_V1_PREFIX}/auth/logout")
def logout():
    return {"message": "Logged out successfully"}