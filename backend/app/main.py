from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import os
import secrets
import uuid
import threading

# ── Monkey-patch llama-cpp-python 0.3.x crash in LlamaModel.__del__ ──────────
# When model fails to load (e.g. CUDA OOM), __del__ accesses a non-existent
# 'sampler' attribute.  This patch silences the spurious traceback.
try:
    import llama_cpp._internals as _li
    _orig_close = _li.LlamaModel.close
    def _safe_llama_close(self):
        if not hasattr(self, "sampler"):
            return
        _orig_close(self)
    _li.LlamaModel.close = _safe_llama_close
except Exception:
    pass

from fastapi import FastAPI, HTTPException, status, Depends, Body, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import Base, engine, get_db, settings, SessionLocal
from app.models import (
    User, Client, Role,
    Employee, Customer, Call, Transcript, QaReport,
    PipelineSettings,
    _compute_grade,
)
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_password, hash_password
from app.security_headers import SecurityHeadersMiddleware
from app.rate_limit import login_limiter, invite_accept_limiter, client_key
from app.logging_config import configure_logging, get_logger
import app.models  # noqa

configure_logging()
log = get_logger("calltone.api")

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
REPO_DIR_CANDIDATES = [
    BACKEND_DIR.parent,  # repo root in local dev: <repo>/backend/app/main.py
    BACKEND_DIR,         # deployed backend root: <deploy>/app/main.py
]


def _resolve_models_dir() -> Path:
    for base in REPO_DIR_CANDIDATES:
        candidate = base / "models"
        if candidate.exists():
            return candidate
    # Default to the deployed-backend layout if no models dir exists yet.
    return BACKEND_DIR / "models"


def _env_timeout_seconds(name: str) -> int | None:
    """
    Parse an optional timeout env var.

    Unset, empty, zero, or negative disables the backend-side deadline so the
    remote GPU pipeline can run as long as needed.
    """
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        log.warning("invalid timeout env %s=%r; disabling backend deadline", name, raw)
        return None
    return value if value > 0 else None


UPLOAD_DIR = BACKEND_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MODELS_DIR = _resolve_models_dir()
CONTEXTS_DIR = MODELS_DIR / "LAYER_2" / "company_context" / "contexts"
TICKETS_DIR  = MODELS_DIR / "LAYER_2" / "change_management" / "tickets"
REMOTE_PIPELINE_DEADLINE_SECONDS = _env_timeout_seconds("REMOTE_PIPELINE_DEADLINE_SECONDS")

Base.metadata.create_all(bind=engine)

# ── GPU optimizations ────────────────────────────────────────────────────────
try:
    import torch
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True          # auto-tune cuDNN kernels
        torch.set_float32_matmul_precision("high")     # TF32 on Ampere+ / Blackwell
except Exception:
    pass


def _context_path(company_name: str) -> Path:
    return CONTEXTS_DIR / f"{str(company_name or '').strip().lower().replace(' ', '_')}.json"


def _available_company_contexts() -> list[str]:
    import json as _json

    names: list[str] = []
    if CONTEXTS_DIR.exists():
        for f in sorted(CONTEXTS_DIR.glob("*.json")):
            if f.stem.endswith("_graph") or f.stem.endswith("_backup"):
                continue
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                names.append(str(data.get("company_name") or f.stem))
            except Exception:
                names.append(f.stem)
    return names


def _default_pipeline_company() -> str:
    available = _available_company_contexts()
    for candidate in available:
        if str(candidate).strip().lower() == "metroboost":
            return candidate
    return available[0] if available else "metroboost"


def _ensure_known_company_context(company_name: str) -> str:
    company_name = str(company_name or "").strip()
    if not company_name:
        raise FileNotFoundError("No company context configured for QA scoring.")
    if _context_path(company_name).exists():
        return company_name

    available = _available_company_contexts()
    # In the split 3-server deployment, the authoritative company-context store
    # lives on the GPU model server. The backend may have an empty local
    # contexts dir after a fresh deploy, so do not reject valid uploads just
    # because this host is missing mirrored JSON files.
    if os.getenv("MODEL_SERVER_URL"):
        if available:
            log.warning(
                "Local backend context missing for '%s'; trusting remote model "
                "server context store. Local contexts currently available: %s",
                company_name,
                ", ".join(available),
            )
        else:
            log.warning(
                "Local backend context store is empty; trusting remote model "
                "server to resolve '%s'.",
                company_name,
            )
        return company_name

    if available:
        raise FileNotFoundError(
            "No context found for company: "
            f"{company_name}. Available contexts: {', '.join(available)}"
        )
    raise FileNotFoundError(
        f"No context found for company: {company_name}. No contexts are available."
    )


def _run_startup_migrations():
    """Add columns to existing tables that were added after initial create_all."""
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)
        emp_cols = [c["name"] for c in inspector.get_columns("employees")]
        if "user_id" not in emp_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            conn.commit()

        call_cols = [c["name"] for c in inspector.get_columns("calls")]
        if "storage_path" not in call_cols:
            conn.execute(text("ALTER TABLE calls ADD COLUMN storage_path VARCHAR(512)"))
            conn.commit()

    # Ensure the singleton pipeline settings row exists
    db = SessionLocal()
    try:
        if not db.query(PipelineSettings).filter(PipelineSettings.id == 1).first():
            db.add(PipelineSettings(id=1, company_name=_default_pipeline_company()))
            db.commit()
    finally:
        db.close()


_run_startup_migrations()

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
if settings.CORS_ORIGINS:
    _cors_origins += [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

# CORS: wildcard "*" is incompatible with credentials; use allow_all pattern instead
_allow_all = "*" in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else _cors_origins,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security-headers middleware. Added AFTER CORS so it wraps the outer
# response — Starlette runs middleware in reverse-add order, so the
# last add() runs first on the way out (and last on the way in). CORS
# stays innermost so its preflight handling is unaffected.
app.add_middleware(SecurityHeadersMiddleware)

bearer_scheme = HTTPBearer()


# ── Upload filename sanitization (C-4) ──────────────────────────────────────
# Defangs path-traversal in user-supplied filenames before they reach the
# disk. UUID prefixing alone is not enough — `f"{uuid}_../../etc/passwd"`
# still resolves outside UPLOAD_DIR on most filesystems.
import os as _os_for_sanitize
import re as _re_for_sanitize

_FILENAME_SAFE_RE = _re_for_sanitize.compile(r"[^A-Za-z0-9._-]")
_FILENAME_FALLBACK = "upload.bin"
_FILENAME_MAX_LEN = 80


def _extract_evidence_row(ev: dict, speaker_turns: list[dict]) -> dict:
    """Normalize one Layer-2 evidence dict into the UI's row shape.

    The skill's evidence schema varies per criterion (quote vs customer_quote
    vs agent_quote, reason vs rationale vs assessment, ...). We try every
    known key and, if speaker is still missing, infer it by substring-matching
    the quote against transcript turns.
    """
    quote = (ev.get("quote")
             or ev.get("customer_quote")
             or ev.get("agent_quote")
             or ev.get("agent_utterance")
             or ev.get("statement")
             or ev.get("description", ""))
    speaker = (ev.get("speaker", "")
               or ("Customer" if ev.get("customer_quote") else "")
               or ("Customer Service Agent" if ev.get("agent_quote") or ev.get("agent_utterance") else ""))
    # The L2 skill embeds the speaker as a "Speaker: text" prefix in `quote`.
    # Strip it into the dedicated speaker field so the UI can render both.
    if quote and ":" in quote and not speaker:
        head, sep, rest = quote.partition(":")
        head = head.strip()
        if head in ("Customer Service Agent", "Customer", "Agent"):
            speaker = head
            quote = rest.strip()
    if not speaker and quote and speaker_turns:
        # Substring lookup: cheap O(N) scan; transcripts are <100 turns.
        snippet = quote.strip()[:40]
        for turn in speaker_turns:
            text = turn.get("text", "") or ""
            if snippet and snippet in text:
                speaker = turn.get("role") or turn.get("speaker", "")
                break
    reason = (ev.get("reason")
              or ev.get("rationale")
              or ev.get("explanation")
              or ev.get("justification")
              or ev.get("note")
              or ev.get("assessment")
              or ev.get("severity_contribution", ""))
    # script_compliance evidence carries `rule` + `met` instead of a free-text
    # reason; synthesize a human sentence so the UI has something to show.
    if not reason:
        rule = ev.get("rule") or ev.get("policy") or ev.get("guideline")
        if rule is not None:
            met = ev.get("met")
            if met is True:
                reason = f"Followed: {rule}"
            elif met is False:
                reason = f"Missed: {rule}"
            else:
                reason = str(rule)
    return {"quote": quote, "speaker": speaker, "reason": reason}


def _sanitize_filename(name: str | None) -> str:
    """Return a safe basename suitable for joining with UPLOAD_DIR."""
    if not name:
        return _FILENAME_FALLBACK
    base = _os_for_sanitize.path.basename(name.replace("\\", "/"))
    cleaned = _FILENAME_SAFE_RE.sub("_", base)
    cleaned = cleaned.lstrip(".")  # forbid leading dots (hidden files / traversal)
    if len(cleaned) > _FILENAME_MAX_LEN:
        # Preserve extension when truncating
        stem, dot, ext = cleaned.rpartition(".")
        if dot and len(ext) <= 8:
            keep = _FILENAME_MAX_LEN - len(ext) - 1
            cleaned = (stem[:keep] if keep > 0 else stem[: _FILENAME_MAX_LEN]) + dot + ext
        else:
            cleaned = cleaned[:_FILENAME_MAX_LEN]
    return cleaned or _FILENAME_FALLBACK


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


CALLTONE_VERSION = "0.9.0"
_STARTED_AT = datetime.now(timezone.utc)


@app.get("/api/health")
def health_basic():
    """Liveness probe — cheap, no DB, no disk, used by load balancers."""
    return {"status": "ok"}


@app.get("/api/health/detailed")
def health_detailed():
    """Readiness probe — checks DB, model dir, and disk so ops can see
    *why* the service is unhappy without grepping logs."""
    import shutil

    checks: dict = {}
    overall_ok = True

    # DB connectivity
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        checks["database"] = {"ok": True}
    except Exception as exc:
        overall_ok = False
        checks["database"] = {"ok": False, "error": str(exc)[:200]}

    # Model presence: in split deployments (MODEL_SERVER_URL set) the weights
    # live on a separate GPU host reached via the model_server, so the local
    # /opt/models check is meaningless — skip it. Ping the remote /v1/health
    # if reachable, but treat unreachable as a soft warning, not a failure:
    # the backend should still be ready to serve UI, login, history etc. even
    # when the GPU instance is paused (cost-saving on Vast on-demand).
    if os.getenv("MODEL_SERVER_URL"):
        from app.model_client import model_server_health
        try:
            remote = model_server_health(timeout=2.0)
            checks["model_server"] = {"ok": True, "remote": remote}
        except Exception as exc:
            checks["model_server"] = {
                "ok": False,
                "warning": "remote model server unreachable",
                "error": str(exc)[:200],
            }
            # Intentionally don't flip overall_ok — see comment above.
    else:
        try:
            model_dir_exists = MODELS_DIR.exists()
            checks["models_dir"] = {
                "ok": model_dir_exists,
                "path": str(MODELS_DIR),
            }
            if not model_dir_exists:
                overall_ok = False
        except Exception as exc:
            overall_ok = False
            checks["models_dir"] = {"ok": False, "error": str(exc)[:200]}

    # Upload directory + free disk
    try:
        usage = shutil.disk_usage(UPLOAD_DIR)
        free_gb = round(usage.free / (1024 ** 3), 2)
        # Soft threshold: warn under 1 GB free, fail under 100 MB
        disk_ok = usage.free > 100 * 1024 * 1024
        if not disk_ok:
            overall_ok = False
        checks["disk"] = {
            "ok": disk_ok,
            "free_gb": free_gb,
            "upload_dir": str(UPLOAD_DIR),
        }
    except Exception as exc:
        overall_ok = False
        checks["disk"] = {"ok": False, "error": str(exc)[:200]}

    uptime_s = int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())

    return {
        "status": "ok" if overall_ok else "degraded",
        "version": CALLTONE_VERSION,
        "uptime_seconds": uptime_s,
        "started_at": _STARTED_AT.isoformat(),
        "checks": checks,
    }


@app.post(f"{settings.API_V1_PREFIX}/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # C-1: per-IP rate limit; fires before any DB or bcrypt work so a
    # script cannot exhaust CPU.
    login_limiter.check(client_key(request))

    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        # C-6: structured security event for log aggregators.
        log.warning(
            "login_failed",
            extra={
                "event": "login_failed",
                "email": payload.email,
                "client_ip": client_key(request),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        log.warning(
            "login_inactive_account",
            extra={
                "event": "login_inactive_account",
                "user_id": user.id,
                "email": payload.email,
                "client_ip": client_key(request),
            },
        )
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

    expires_at = user.invite_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or expires_at < datetime.now(timezone.utc):
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
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    # C-1: rate-limit per IP — token is 256-bit URL-safe, but cheap to
    # block automated guessing anyway.
    invite_accept_limiter.check(client_key(request))

    token = (payload.get("token") or "").strip()
    password = (payload.get("password") or "").strip()
    confirm_password = (payload.get("confirmPassword") or "").strip()

    if not token or not password or not confirm_password:
        raise HTTPException(status_code=400, detail="Token, password, and confirm password are required")

    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    # C-5: bcrypt has a hard 72-byte input ceiling. Reject early so the
    # error is predictable; bcrypt 5.x raises ValueError otherwise.
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password must be at most 72 bytes (UTF-8). Bcrypt does not store more.",
        )

    user = db.query(User).filter(User.invite_token == token).first()

    if not user:
        raise HTTPException(status_code=404, detail="Invalid invitation link")

    expires_at = user.invite_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or expires_at < datetime.now(timezone.utc):
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

    old_role_name = user.role.name if user.role else None
    user.role_id = role.id
    db.commit()
    db.refresh(user)

    # C-6: privilege-change audit line.
    log.warning(
        "role_changed",
        extra={
            "event": "role_changed",
            "actor_id": current_user.id,
            "target_user_id": user.id,
            "old_role": old_role_name,
            "new_role": role.name,
        },
    )

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

    old_status = "active" if user.is_active else "disabled"
    user.is_active = new_status == "active"
    db.commit()
    db.refresh(user)

    # C-6: account-status audit line.
    log.warning(
        "status_changed",
        extra={
            "event": "status_changed",
            "actor_id": current_user.id,
            "target_user_id": user.id,
            "old_status": old_status,
            "new_status": new_status,
        },
    )

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
    target_email = user.email
    target_id = user.id

    db.delete(user)
    db.commit()

    # C-6: deletion audit line.
    log.warning(
        "user_deleted",
        extra={
            "event": "user_deleted",
            "actor_id": current_user.id,
            "target_user_id": target_id,
            "target_email": target_email,
            "was_invited": was_invited,
        },
    )

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

@app.get(f"{settings.API_V1_PREFIX}/qa/calls/{{call_id}}/audio")
def get_qa_call_audio(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import FileResponse
    import mimetypes

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if not call.storage_path:
        raise HTTPException(status_code=404, detail="No stored audio for this call")

    path = Path(call.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    media_type, _ = mimetypes.guess_type(str(path))
    if media_type is None:
        media_type = "application/octet-stream"

    return FileResponse(
        str(path),
        media_type=media_type,
        filename=call.original_filename or path.name,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=300"},
    )


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
    audio_url = (
        f"{settings.API_V1_PREFIX}/qa/calls/{call.id}/audio"
        if call.storage_path and Path(call.storage_path).is_file() else None
    )

    return {
        "callId": call.id,
        "filename": call.original_filename,
        "driveFileId": drive_file_id,
        "drivePreviewUrl": drive_preview_url,
        "driveDownloadUrl": drive_download_url,
        "audioUrl": audio_url,
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

def _get_agent_employee(current_user: User, db: Session) -> Employee | None:
    """Return the Employee record linked to this user, or None."""
    return db.query(Employee).filter(Employee.user_id == current_user.id).first()


@app.get(f"{settings.API_V1_PREFIX}/agent/dashboard")
def get_agent_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    employee = _get_agent_employee(current_user, db)
    query = db.query(QaReport).join(Call, QaReport.call_id == Call.id)
    if employee:
        query = query.filter(Call.employee_id == employee.id)
    reports = query.order_by(Call.created_at.desc()).limit(50).all()

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
    employee = _get_agent_employee(current_user, db)
    if not employee:
        return {"calls": [], "total": 0}

    rows = (
        db.query(Call, Employee, QaReport)
        .join(Employee, Call.employee_id == Employee.id)
        .outerjoin(QaReport, Call.id == QaReport.call_id)
        .filter(Call.employee_id == employee.id)
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
VALID_ASR_ENGINES = {"fasterwhisper", "sensevoice"}


def _normalize_asr_engine(asr_engine: str | None) -> str:
    engine = str(asr_engine or "fasterwhisper").strip().lower()
    if engine not in VALID_ASR_ENGINES:
        raise ValueError(
            f"Unsupported ASR engine: {engine}. Expected one of: "
            f"{', '.join(sorted(VALID_ASR_ENGINES))}"
        )
    return engine


def _asr_metadata(asr_engine: str | None) -> tuple[str, str]:
    engine = _normalize_asr_engine(asr_engine)
    if engine == "sensevoice":
        return "sensevoice", "SenseVoiceSmall"
    return "fasterwhisper", "large-v3"


def _run_real_pipeline(
    call_id: str,
    audio_path: str,
    company: str = "BankServ Global",
    asr_engine: str = "fasterwhisper",
):
    """
    Background task: run the real 3-layer AI pipeline on an uploaded audio file.

    Layer 1: denoise → transcribe + diarize → role ID → emotion detection
    Layer 2: 7-criterion QA scoring via LLM skills + context graph
    Layer 3: LaTeX report generation

    If the real pipeline fails (models missing, GPU unavailable, etc.), the
    error is stored on the Call record so the status endpoint reports it.
    """
    import os as _os
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

    # Helper: update DB step (pipeline has its own process + GIL, so
    # db.commit() here does NOT contend with uvicorn's event loop).
    def _set_step(step: str):
        call.current_step = step
        db.commit()

    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return

        # Load pipeline settings (use defaults if row missing)
        ps = db.query(PipelineSettings).filter(PipelineSettings.id == 1).first()
        audio_mode      = ps.audio_mode      if ps else "denoise"
        injection_scan  = ps.injection_scan  if ps else "static"
        num_speakers    = ps.num_speakers    if ps else None
        report_mode     = ps.report_mode     if ps else "simple"
        use_consensus   = ps.use_consensus   if ps else False
        _company        = _ensure_known_company_context(ps.company_name if ps else company)

        asr_engine = _normalize_asr_engine(asr_engine)
        asr_engine_db, asr_model_db = _asr_metadata(asr_engine)

        call.status = "PROCESSING"
        _set_step("denoising")

        # ── Layer 1: Audio → structured transcript JSON ──────────────────
        _os.environ["CALLTONE_ASR"] = asr_engine

        from run_full_pipeline import (
            denoise_audio, transcribe_diarize,
            run_role_identification, run_emotion_detection,
        )

        denoised_path = denoise_audio(audio_path, mode=audio_mode)

        _set_step("transcribing")
        txt_path, json_path = transcribe_diarize(denoised_path, num_speakers=num_speakers)

        _set_step("role_identification")
        try:
            run_role_identification(json_path, txt_path)
        except Exception:
            pass  # non-fatal

        # Free Whisper + pyannote VRAM so Audio2Emotion ONNX can load on GPU
        import gc as _gc_l1
        import torch as _torch_l1
        try:
            import transcribe_diarize as _td
            _td._WHISPER_MODEL     = None
            _td._PYANNOTE_PIPELINE = None
        except Exception:
            pass
        try:
            from resemble_enhance.enhancer.inference import load_enhancer
            load_enhancer.cache_clear()
        except Exception:
            pass
        _gc_l1.collect()
        if _torch_l1.cuda.is_available():
            _torch_l1.cuda.empty_cache()

        _set_step("emotion_detection")
        try:
            txt_path, json_path = run_emotion_detection(denoised_path, json_path)
        except Exception:
            pass  # non-fatal

        # Read the Layer 1 output
        with open(json_path, "r", encoding="utf-8") as f:
            l1_output = _json.load(f)

        # Build transcript for DB — single commit for Layer 1 results
        speaker_turns = l1_output.get("transcript", [])
        full_text = " ".join(seg.get("text", "") for seg in speaker_turns if seg.get("text"))
        duration = l1_output.get("call_metadata", {}).get("duration_seconds", 0)

        transcript = Transcript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            full_text=full_text,
            speaker_turns=speaker_turns,
            asr_engine=asr_engine_db,
            asr_model=asr_model_db,
            # Layer 1 doesn't surface per-word probabilities; leave null rather
            # than fabricate a value. WER eval (T09) is the source of truth.
            avg_confidence=None,
        )
        db.add(transcript)
        call.current_step = "scoring"
        call.duration_seconds = round(duration, 3) if duration else None
        db.commit()

        # ── Free Layer 1 VRAM before loading the Layer 2 LLM ───────────
        # PyTorch / ONNX Runtime hold reserved VRAM blocks invisible to
        # llama.cpp.  Releasing them here lets LLaMA 3.1 8B load without OOM.
        import gc as _gc
        import torch as _torch
        try:
            import transcribe_diarize as _td
            _td._WHISPER_MODEL     = None
            _td._PYANNOTE_PIPELINE = None
        except Exception:
            pass
        try:
            from resemble_enhance.enhancer.inference import load_enhancer
            load_enhancer.cache_clear()
        except Exception:
            pass
        try:
            from emotion_integration import _DETECTOR_CACHE as _edc
            for _det in _edc.values():
                if hasattr(_det, "onnx_session") and _det.onnx_session is not None:
                    del _det.onnx_session
                    _det.onnx_session = None
            _edc.clear()
        except Exception:
            pass
        _gc.collect()
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()

        # ── Layer 2: Transcript → QA scores ─────────────────────────────
        _set_step("scoring")

        output_dir = UPLOAD_DIR / f"{call_id}_results"
        output_dir.mkdir(exist_ok=True)
        rating_output = str(output_dir / "layer2_ratings.json")

        from run_full_pipeline import run_layer2
        l2_result = run_layer2(
            json_path, _company, rating_output, injection_scan_mode=injection_scan,
        )

        overall_score = l2_result.get("overall_weighted_score", 0)
        criteria = l2_result.get("criteria_ratings", {})
        if not criteria:
            raise RuntimeError("Local pipeline completed without Layer 2 QA scores.")

        dim_scores = {}
        dim_reports = {}
        confidence_scores = {}
        evidence = []
        for crit, info in criteria.items():
            dim_scores[crit] = info.get("score", 0)
            dim_reports[crit] = info.get("summary", "")
            cc = info.get("consensus_confidence")
            confidence_scores[crit] = cc if cc is not None else info.get("confidence")
            for ev in info.get("evidence", []):
                row = _extract_evidence_row(ev, speaker_turns)
                evidence.append({"dimension": crit, **row})

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

        # ── Free Layer 2 VRAM (LLaMA) so next pipeline run can load Layer 1 ─
        try:
            from skill_runtime.runner import _BACKEND_CACHE as _bc
            _bc.clear()
        except Exception:
            pass
        _gc.collect()
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()

        # ── Layer 3: Generate LaTeX report (non-blocking) ───────────────
        _set_step("report_generation")

        if report_mode != "none":
            try:
                from run_full_pipeline import run_layer3
                run_layer3(rating_output, str(output_dir), mode=report_mode, use_skill=False)
            except Exception:
                pass  # Layer 3 is optional; scores already saved

        # Single final commit — all results (transcript + report + status)
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


def _run_remote_pipeline(
    call_id: str,
    audio_path: str,
    company: str = "BankServ Global",
    asr_engine: str = "fasterwhisper",
):
    """Delegate pipeline execution to the Tier-3 model server.

    Polls ``/v1/jobs/{id}`` until terminal, then writes Transcript + QaReport
    rows matching the local-pipeline contract. The local worker's DB schema
    is the source of truth — remote path must populate the same columns.
    """
    import time as _time

    from app import model_client

    STATUS_TO_STEP = {
        "queued": "queued",
        "denoising": "denoising",
        "diarising": "transcribing",
        "transcribing": "transcribing",
        "role_ident": "role_identification",
        "emotion": "emotion_detection",
        "scoring": "scoring",
        "rendering": "report_generation",
    }

    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return

        asr_engine = _normalize_asr_engine(asr_engine)
        asr_engine_db, asr_model_db = _asr_metadata(asr_engine)

        ps = db.query(PipelineSettings).filter(PipelineSettings.id == 1).first()
        num_speakers = ps.num_speakers if ps else None
        _company = _ensure_known_company_context(ps.company_name if ps else company)

        call.status = "PROCESSING"
        call.current_step = "queued"
        db.commit()

        job_id = model_client.submit(
            audio_path, company=_company, speakers=num_speakers,
            filename=call.original_filename,
            asr_engine=asr_engine,
        )

        # Poll until terminal. By default there is no backend-side hard cap;
        # long calls should finish instead of being failed at an arbitrary
        # wall-clock limit. Set REMOTE_PIPELINE_DEADLINE_SECONDS>0 to restore
        # a safety deadline if needed during ops/debugging.
        deadline = (
            _time.time() + REMOTE_PIPELINE_DEADLINE_SECONDS
            if REMOTE_PIPELINE_DEADLINE_SECONDS is not None
            else None
        )
        last_step: str | None = None
        while True:
            state = model_client.poll(job_id)
            status = state.get("status", "")
            step = STATUS_TO_STEP.get(status, status)
            if step != last_step:
                call.current_step = step
                db.commit()
                last_step = step
            if status == "done":
                break
            if status == "failed":
                raise RuntimeError(
                    f"model server reported failure: {state.get('error')}"
                )
            if deadline is not None and _time.time() >= deadline:
                raise TimeoutError(
                    "model server did not finish before REMOTE_PIPELINE_DEADLINE_SECONDS elapsed"
                )
            _time.sleep(2)

        bundle = model_client.fetch_result(job_id)
        layer1 = bundle.get("layer1") or {}
        layer2 = bundle.get("layer2") or bundle.get("call_rating") or {}
        criteria = layer2.get("criteria_ratings", {}) if isinstance(layer2, dict) else {}
        if not criteria:
            raise RuntimeError(
                "Remote pipeline completed without Layer 2 QA scores. "
                "Check model-server pipeline.log for the underlying failure."
            )

        # ── Transcript row (mirrors local path) ───────────────────────────
        speaker_turns = layer1.get("transcript", []) if isinstance(layer1, dict) else []
        full_text = " ".join(
            seg.get("text", "") for seg in speaker_turns if seg.get("text")
        )
        duration = (
            layer1.get("call_metadata", {}).get("duration_seconds", 0)
            if isinstance(layer1, dict) else 0
        )

        transcript = Transcript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            full_text=full_text,
            speaker_turns=speaker_turns,
            asr_engine=asr_engine_db,
            asr_model=asr_model_db,
            avg_confidence=None,
        )
        db.add(transcript)
        call.duration_seconds = round(duration, 3) if duration else None
        db.commit()

        # ── QaReport row (mirrors local path) ─────────────────────────────
        overall_score = layer2.get("overall_weighted_score", 0)
        dim_scores: dict[str, object] = {}
        dim_reports: dict[str, object] = {}
        confidence_scores: dict[str, object] = {}
        evidence: list[dict[str, object]] = []
        for crit, info in criteria.items():
            dim_scores[crit] = info.get("score", 0)
            dim_reports[crit] = info.get("summary", "")
            cc = info.get("consensus_confidence")
            confidence_scores[crit] = cc if cc is not None else info.get("confidence")
            for ev in info.get("evidence", []):
                row = _extract_evidence_row(ev, speaker_turns)
                evidence.append({"dimension": crit, **row})

        if overall_score >= 85:
            severity = "Minor"
        elif overall_score >= 65:
            severity = "Moderate"
        else:
            severity = "Major"

        # Prefer LAYER 3's narrative if the model server returned one;
        # otherwise synthesize a passable AI quality report from LAYER 2's
        # per-criterion summaries so the UI never has empty bullets.
        report_json = layer2.get("report_json") or bundle.get("layer3", {}).get("report_json")
        if not report_json:
            _label = lambda k: k.replace("_", " ").title()
            strengths = [
                f"{_label(c)} ({info.get('score', 0)}/100): {(info.get('summary') or '').strip()}"
                for c, info in criteria.items()
                if (info.get("score") or 0) >= 70 and (info.get("summary") or "").strip()
            ]
            weaknesses = [
                f"{_label(c)} ({info.get('score', 0)}/100): {(info.get('summary') or '').strip()}"
                for c, info in criteria.items()
                if (info.get("score") or 0) < 70 and (info.get("summary") or "").strip()
            ]
            actions: list[str] = []
            for c, info in criteria.items():
                if (info.get("score") or 0) >= 70:
                    continue
                for ev in info.get("evidence", [])[:2]:
                    rule = ev.get("rule") or ev.get("policy") or ev.get("guideline")
                    if ev.get("met") is False and rule:
                        actions.append(f"{_label(c)}: enforce '{rule}'.")
                    elif rule:
                        actions.append(f"{_label(c)}: review '{rule}'.")
            # Dedupe while preserving order.
            seen: set[str] = set()
            actions = [a for a in actions if not (a in seen or seen.add(a))][:6]
            report_json = {
                "summary": (
                    f"Call scored {overall_score}/100 across {len(criteria)} dimensions. "
                    f"Severity: {severity}. {len(strengths)} dimension(s) above threshold, "
                    f"{len(weaknesses)} below."
                ),
                "strengths": strengths,
                "weaknesses": weaknesses,
                "recommended_actions": actions,
            }

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

        call.current_step = "completed"
        call.status = "COMPLETED"
        db.commit()

    except Exception as exc:
        db.rollback()
        call = db.query(Call).filter(Call.id == call_id).first()
        if call and call.status != "COMPLETED":
            call.status = "FAILED"
            call.error_message = str(exc)
            call.current_step = "error"
            db.commit()
    finally:
        db.close()


def _run_pipeline(call_id: str, audio_path: str, asr_engine: str = "fasterwhisper"):
    """
    Dispatch: remote model server (if MODEL_SERVER_URL set) or local pipeline.
    Errors from either path are persisted to the Call record.
    """
    try:
        from app import model_client
        if model_client.configured():
            _run_remote_pipeline(call_id, audio_path, asr_engine=asr_engine)
        else:
            _run_real_pipeline(call_id, audio_path, asr_engine=asr_engine)
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
    file: UploadFile = File(...),
    agent_id: str = Form(default=""),
    asr_engine: str = Form(default="fasterwhisper"),
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

    try:
        asr_engine = _normalize_asr_engine(asr_engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 100 MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    sha256 = hashlib.sha256(content).hexdigest()
    call_id = str(uuid.uuid4())
    # C-4: strip any path separators / control chars from the
    # user-supplied name before joining with UPLOAD_DIR. Without this,
    # a filename of "../../etc/passwd" escapes the upload directory
    # despite the UUID prefix.
    safe_filename = _sanitize_filename(file.filename)

    dest = UPLOAD_DIR / f"{call_id}_{safe_filename}"
    dest.write_bytes(content)

    # Resolve agent employee record
    # Priority: explicit agent_id > current user's linked employee > first agent in DB
    employee = None
    if agent_id:
        employee = db.query(Employee).filter(Employee.id == agent_id).first()
    if not employee:
        employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
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
        storage_path=str(dest),
        size_bytes=len(content),
        sha256=sha256,
        status="PENDING",
        current_step="uploaded",
        call_time=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    # Run pipeline in a SEPARATE PROCESS so it gets its own GIL.
    # This eliminates all GIL contention between uvicorn (HTTP handling)
    # and the GPU pipeline.  Must use 'spawn' (not 'fork') because CUDA
    # contexts cannot be re-initialized in forked subprocesses.
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=_run_pipeline, args=(call_id, str(dest), asr_engine),
        name=f"pipeline-{call_id[:8]}", daemon=True,
    )
    p.start()

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
    # Pipeline runs in a separate process (own GIL), so DB queries here
    # don't contend with GPU work.  No need for in-memory caching.
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


# ── Pipeline Settings endpoints ──────────────────────────────────────────────

@app.get(f"{settings.API_V1_PREFIX}/settings/pipeline")
def get_pipeline_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ps = db.query(PipelineSettings).filter(PipelineSettings.id == 1).first()
    if not ps:
        ps = PipelineSettings(id=1, company_name=_default_pipeline_company())
        db.add(ps)
        db.commit()
        db.refresh(ps)
    return {
        "audioMode":     ps.audio_mode,
        "injectionScan": ps.injection_scan,
        "numSpeakers":   ps.num_speakers,
        "reportMode":    ps.report_mode,
        "useConsensus":  ps.use_consensus,
        "companyName":   ps.company_name,
    }


@app.put(f"{settings.API_V1_PREFIX}/settings/pipeline")
def update_pipeline_settings(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    ps = db.query(PipelineSettings).filter(PipelineSettings.id == 1).first()
    if not ps:
        ps = PipelineSettings(id=1, company_name=_default_pipeline_company())
        db.add(ps)

    if "audioMode" in payload:
        if payload["audioMode"] not in ("none", "denoise", "enhance"):
            raise HTTPException(status_code=400, detail="audioMode must be none|denoise|enhance")
        ps.audio_mode = payload["audioMode"]
    if "injectionScan" in payload:
        if payload["injectionScan"] not in ("static", "llm"):
            raise HTTPException(status_code=400, detail="injectionScan must be static|llm")
        ps.injection_scan = payload["injectionScan"]
    if "numSpeakers" in payload:
        val = payload["numSpeakers"]
        ps.num_speakers = int(val) if val else None
    if "reportMode" in payload:
        if payload["reportMode"] not in ("none", "simple", "narrative"):
            raise HTTPException(status_code=400, detail="reportMode must be none|simple|narrative")
        ps.report_mode = payload["reportMode"]
    if "useConsensus" in payload:
        ps.use_consensus = bool(payload["useConsensus"])
    if "companyName" in payload:
        try:
            ps.company_name = _ensure_known_company_context(payload["companyName"])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    from datetime import datetime, timezone
    ps.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ps)
    return {
        "audioMode":     ps.audio_mode,
        "injectionScan": ps.injection_scan,
        "numSpeakers":   ps.num_speakers,
        "reportMode":    ps.report_mode,
        "useConsensus":  ps.use_consensus,
        "companyName":   ps.company_name,
    }


# ── Company Context endpoints ─────────────────────────────────────────────────

# In-memory store for background ingest jobs
# { job_id: { "status": "running"|"completed"|"failed", "progress": str, "result": dict|None, "error": str|None } }
_INGEST_JOBS: dict = {}


@app.get(f"{settings.API_V1_PREFIX}/context/companies")
def list_companies(current_user: User = Depends(get_current_user)):
    import json as _json
    companies = []
    if CONTEXTS_DIR.exists():
        for f in sorted(CONTEXTS_DIR.glob("*.json")):
            if f.stem.endswith("_graph") or f.stem.endswith("_backup"):
                continue
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                companies.append({
                    "name":    data.get("company_name", f.stem),
                    "version": data.get("context_version", "1.0.0"),
                    "updated": data.get("last_updated", ""),
                    "file":    f.name,
                    "fieldCount": sum(
                        1 for k, v in data.items()
                        if isinstance(v, str) and v and k not in
                        ("company_name", "context_version", "last_updated")
                    ),
                })
            except Exception:
                pass
    return {"companies": companies}


@app.get(f"{settings.API_V1_PREFIX}/context/companies/{'{name}'}")
def get_company_context(name: str, current_user: User = Depends(get_current_user)):
    import json as _json
    path = CONTEXTS_DIR / f"{name.lower().replace(' ', '_')}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Company context not found")
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return data


def _run_ingest_job(job_id: str, tmp_path: Path, company_name: str):
    """Background thread: runs LLM ingestion and updates _INGEST_JOBS[job_id]."""
    import sys as _sys
    for p in [MODELS_DIR, MODELS_DIR / "skill_implementation"]:
        if str(p) not in _sys.path:
            _sys.path.insert(0, str(p))
    try:
        _INGEST_JOBS[job_id]["progress"] = "Pass 1/5 – script compliance…"
        from LAYER_2.company_context.text_ingestion import ingest_text_context
        result = ingest_text_context(
            text_path=str(tmp_path),
            company_name=company_name,
            contexts_dir=str(CONTEXTS_DIR),
            progress_callback=lambda msg: _INGEST_JOBS[job_id].update({"progress": msg}),
        )
        tmp_path.unlink(missing_ok=True)
        _INGEST_JOBS[job_id].update({
            "status":   "completed",
            "progress": "Done",
            "result": {
                "success":          True,
                "company":          company_name,
                "jsonPath":         result["json_path"],
                "atomicNodesCount": result.get("atomic_nodes_count", 0),
                "validation":       result.get("validation"),
                "schema":           result.get("schema"),
            },
        })
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        _INGEST_JOBS[job_id].update({
            "status":   "failed",
            "progress": "Failed",
            "error":    str(e),
        })


@app.post(f"{settings.API_V1_PREFIX}/context/ingest")
async def ingest_company_context(
    file: UploadFile = File(...),
    company_name: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in ("qa", "admin", "super_admin"):
        raise HTTPException(status_code=403, detail="QA or Admin access required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Save the text file temporarily — the background thread will delete it when done
    tmp_path = UPLOAD_DIR / f"context_{company_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.txt"
    tmp_path.write_bytes(content)

    job_id = uuid.uuid4().hex
    _INGEST_JOBS[job_id] = {
        "status":      "running",
        "progress":    "Starting…",
        "result":      None,
        "error":       None,
        "company":     company_name,
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }

    t = threading.Thread(target=_run_ingest_job, args=(job_id, tmp_path, company_name), daemon=True)
    t.start()

    return {"jobId": job_id, "status": "running"}


@app.get(f"{settings.API_V1_PREFIX}/context/ingest/{{job_id}}/status")
def ingest_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = _INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get(f"{settings.API_V1_PREFIX}/context/tickets")
def list_tickets(current_user: User = Depends(get_current_user)):
    import json as _json
    tickets = []
    if TICKETS_DIR.exists():
        for f in sorted(TICKETS_DIR.glob("*.json"), reverse=True):
            try:
                t = _json.loads(f.read_text(encoding="utf-8"))
                tickets.append(t)
            except Exception:
                pass
    return {"tickets": tickets}


@app.post(f"{settings.API_V1_PREFIX}/context/tickets")
def create_ticket(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in ("qa", "admin", "super_admin"):
        raise HTTPException(status_code=403, detail="QA or Admin access required")

    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(TICKETS_DIR.glob("TICKET-*.json"))
    next_num = len(existing) + 1
    ticket_id = f"TICKET-{next_num:03d}"

    ticket = {
        "ticket_id":    ticket_id,
        "submitted_by": current_user.email,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status":       "pending",
        "company_name": payload.get("companyName", ""),
        "field_name":   payload.get("fieldName", ""),
        "old_text":     payload.get("oldText", ""),
        "new_text":     payload.get("newText", ""),
        "reason":       payload.get("reason", ""),
    }

    out = TICKETS_DIR / f"{ticket_id}.json"
    out.write_text(_json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
    return ticket


@app.patch(f"{settings.API_V1_PREFIX}/context/tickets/{'{ticket_id}'}")
def update_ticket_status(
    ticket_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required to approve/reject tickets")

    ticket_file = TICKETS_DIR / f"{ticket_id}.json"
    if not ticket_file.exists():
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket = _json.loads(ticket_file.read_text(encoding="utf-8"))
    new_status = payload.get("status", "")
    if new_status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")
    ticket["status"] = new_status
    ticket["reviewed_by"] = current_user.email
    ticket["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if "note" in payload:
        ticket["review_note"] = payload["note"]

    ticket_file.write_text(_json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
    return ticket


# ── Serve built frontend (SPA) in production ────────────────────────────────
# If a `static/` directory exists next to the backend (Docker places it there),
# serve it and fall back to index.html for client-side routing.
# API routes are defined above and matched first; this catch-all is last.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    if (_STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = _STATIC_DIR / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_STATIC_DIR / "index.html")
