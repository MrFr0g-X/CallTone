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
from sqlalchemy import func, text, or_

from app.database import Base, engine, get_db, settings, SessionLocal
from app.models import (
    User, Client, Role,
    Employee, Customer, Call, Transcript, QaReport,
    PipelineJob, PipelineSettings, ClientPolicy, EmailEvent, EmailPreference,
    _compute_grade,
)
from app.email import service as email_service
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_password, hash_password
from app.security_headers import SecurityHeadersMiddleware
from app.rate_limit import login_limiter, invite_accept_limiter, client_key
from app.logging_config import configure_logging, get_logger
import app.models  # noqa

configure_logging()
log = get_logger("calltone.api")

OWNER_ROLE = "owner"
ADMIN_READ_ROLES = (OWNER_ROLE, "super_admin", "admin", "manager", "viewer")
ADMIN_MUTATION_ROLES = (OWNER_ROLE, "super_admin", "admin")
QA_OPERATOR_ROLES = ("qa", OWNER_ROLE, "admin", "super_admin")
QA_CALL_ROLES = ("qa", OWNER_ROLE, "admin", "super_admin", "agent")
OWNER_ASSIGNABLE_ROLES = ("super_admin", "admin", "manager", "viewer", "qa", "agent")
ADMIN_ASSIGNABLE_ROLES = ("admin", "manager", "viewer", "qa", "agent")
PLATFORM_ROLES = (OWNER_ROLE, "super_admin")
TENANT_ADMIN_ROLES = ("admin", "manager", "viewer")
TENANT_MUTATION_ROLES = ("admin",)
TENANT_QA_ROLES = ("qa", "admin")
TENANT_USER_ROLES = ("admin", "manager", "viewer", "qa", "agent")
CLIENT_POLICY_BOOLEAN_FIELDS = (
    "agent_portal_enabled",
    "agent_can_view_call_list",
    "agent_can_open_call_detail",
    "agent_can_play_audio",
    "agent_can_view_transcript",
    "agent_can_view_scores",
    "agent_can_view_evidence",
    "agent_can_view_ai_report",
    "agent_can_view_trends",
    "qa_can_upload_calls",
    "qa_can_manage_context_tickets",
    "tenant_admin_can_invite_admins",
)
CLIENT_POLICY_QA_SCOPES = ("company", "assigned_team", "own_uploads")


def _role_name(user: User) -> str:
    return user.role.name if user.role else ""


def _is_platform_user(user: User) -> bool:
    """CallTone operators. These accounts are not scoped to one client."""
    role = _role_name(user)
    if role == OWNER_ROLE:
        return True
    if role == "super_admin" and user.client_id is None:
        return True
    # Legacy safety: an admin without a client is treated as a platform admin
    # until the explicit platform_admin role migration is done.
    if role == "admin" and user.client_id is None:
        return True
    return False


def _is_tenant_user(user: User) -> bool:
    return not _is_platform_user(user)


def _tenant_client_id(user: User) -> int:
    if user.client_id is None:
        raise HTTPException(status_code=403, detail="Tenant user is not assigned to a client")
    return int(user.client_id)


def _can_read_admin_area(user: User) -> bool:
    role = _role_name(user)
    return _is_platform_user(user) or role in ADMIN_READ_ROLES


def _can_mutate_users(user: User) -> bool:
    role = _role_name(user)
    if _is_platform_user(user):
        return role in ADMIN_MUTATION_ROLES
    return role in TENANT_MUTATION_ROLES and user.client_id is not None


def _can_use_qa_tools(user: User) -> bool:
    role = _role_name(user)
    return _is_platform_user(user) or (role in ("qa", "admin") and user.client_id is not None)


def _can_read_qa_calls(user: User) -> bool:
    role = _role_name(user)
    return _can_use_qa_tools(user) or role == "agent"


def _assignable_roles_for(user: User) -> tuple[str, ...]:
    if _role_name(user) == OWNER_ROLE:
        return OWNER_ASSIGNABLE_ROLES
    if _is_platform_user(user):
        return ADMIN_ASSIGNABLE_ROLES
    if _role_name(user) == "admin" and user.client_id is not None:
        return ("qa", "agent", "viewer", "manager")
    return ()


def _guard_protected_admin_target(current_user: User, target_user: User, action: str) -> None:
    actor_role = _role_name(current_user)
    target_role = _role_name(target_user)
    if target_role == OWNER_ROLE and actor_role != OWNER_ROLE:
        raise HTTPException(status_code=403, detail=f"Only the Owner can {action} the Owner account")
    if target_role == "super_admin" and actor_role != OWNER_ROLE:
        raise HTTPException(status_code=403, detail=f"Only the Owner can {action} Super Admin accounts")
    if _is_tenant_user(current_user):
        actor_client_id = _tenant_client_id(current_user)
        if target_user.client_id != actor_client_id:
            raise HTTPException(status_code=403, detail=f"Cannot {action} users outside your company")
        if target_role in PLATFORM_ROLES or target_user.client_id is None:
            raise HTTPException(status_code=403, detail=f"Cannot {action} platform users")


def _can_manage_client_policy(user: User) -> bool:
    role = _role_name(user)
    if _is_platform_user(user):
        return role in ADMIN_MUTATION_ROLES
    return role == "admin" and user.client_id is not None


def _employee_role_for_user_role(role_name: str) -> str | None:
    """Map platform auth roles to QA-domain employee roles.

    Uploads are tied to `employees`, not directly to `users`. Every invited
    tenant agent/QA user therefore needs a linked Employee row so calls can be
    attributed to the real call handler and QA workflows can resolve reviewers.
    """
    if role_name == "agent":
        return "AGENT"
    if role_name == "qa":
        return "QA"
    return None


def _ensure_employee_profile_for_user(db: Session, user: User) -> Employee | None:
    employee_role = _employee_role_for_user_role(_role_name(user))
    if not employee_role or user.client_id is None:
        return None

    existing = db.query(Employee).filter(Employee.user_id == user.id).first()
    if existing:
        if existing.client_id is None:
            existing.client_id = user.client_id
        if existing.role != employee_role:
            existing.role = employee_role
        if not existing.full_name:
            existing.full_name = user.full_name
        return existing

    employee = Employee(
        client_id=user.client_id,
        employee_code=f"USR-{user.id}",
        full_name=user.full_name,
        role=employee_role,
        user_id=user.id,
    )
    db.add(employee)
    return employee


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


def _context_slug(company_name: str) -> str:
    return str(company_name or "").strip().lower().replace(" ", "_")


def _context_path(company_name: str) -> Path:
    return CONTEXTS_DIR / f"{_context_slug(company_name)}.json"


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


def _read_company_context_payload(company_name: str) -> dict | None:
    import json as _json

    path = _context_path(company_name)
    if not path.exists():
        return None
    try:
        payload = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise FileNotFoundError(f"Could not read context for {company_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FileNotFoundError(f"Context for {company_name} is not a JSON object.")
    return payload


def _sync_company_context_to_model_server(company_name: str) -> bool:
    """Mirror a local context JSON to the GPU model server if remote mode is on."""
    if not os.getenv("MODEL_SERVER_URL"):
        return False
    payload = _read_company_context_payload(company_name)
    if payload is None:
        return False
    try:
        from app import model_client
        model_client.put_context(company_name, payload)
        return True
    except Exception as exc:
        log.warning(
            "model_server.context_sync_failed",
            extra={"event": "context_sync_failed", "company": company_name, "err": str(exc)},
        )
        return False


def _ensure_known_company_context(company_name: str) -> str:
    company_name = str(company_name or "").strip()
    if not company_name:
        raise FileNotFoundError("No company context configured for QA scoring.")
    if _context_path(company_name).exists():
        _sync_company_context_to_model_server(company_name)
        return company_name

    available = _available_company_contexts()
    if os.getenv("MODEL_SERVER_URL"):
        try:
            from app import model_client
            if model_client.context_exists(company_name):
                return company_name
            remote = ", ".join(c.get("name", "") for c in model_client.list_contexts()) or "none"
        except Exception as exc:
            raise FileNotFoundError(
                f"Cannot verify model-server context for {company_name}: {exc}"
            ) from exc
        raise FileNotFoundError(
            "No context found for company: "
            f"{company_name}. Backend contexts: {', '.join(available) or 'none'}. "
            f"Model-server contexts: {remote}."
        )

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

        def _cols(table_name: str) -> list[str]:
            return [c["name"] for c in inspector.get_columns(table_name)]

        def _add_client_id_if_missing(table_name: str) -> None:
            if "client_id" not in _cols(table_name):
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN client_id INTEGER REFERENCES clients(id)"))
                conn.commit()

        emp_cols = [c["name"] for c in inspector.get_columns("employees")]
        if "user_id" not in emp_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            conn.commit()
        _add_client_id_if_missing("employees")

        call_cols = [c["name"] for c in inspector.get_columns("calls")]
        if "storage_path" not in call_cols:
            conn.execute(text("ALTER TABLE calls ADD COLUMN storage_path VARCHAR(512)"))
            conn.commit()
        _add_client_id_if_missing("customers")
        _add_client_id_if_missing("calls")
        _add_client_id_if_missing("pipeline_jobs")
        _add_client_id_if_missing("pipeline_settings")
        _add_client_id_if_missing("email_events")

    db = SessionLocal()
    try:
        default_client = (
            db.query(Client)
            .filter(Client.status.in_(["active", "trial"]))
            .order_by(Client.id.asc())
            .first()
        )

        # Backfill tenant ownership. Existing deployments started as a
        # single-tenant demo, so safe inference is: employee.user.client_id when
        # linked, otherwise the first active/trial client.
        employees = db.query(Employee).all()
        for employee in employees:
            if employee.client_id is not None:
                continue
            if employee.user and employee.user.client_id is not None:
                employee.client_id = employee.user.client_id
            elif default_client is not None:
                employee.client_id = default_client.id

        customers = db.query(Customer).all()
        for customer in customers:
            if customer.client_id is None and default_client is not None:
                customer.client_id = default_client.id

        calls = db.query(Call).all()
        for call in calls:
            if call.client_id is None:
                if call.employee and call.employee.client_id is not None:
                    call.client_id = call.employee.client_id
                elif default_client is not None:
                    call.client_id = default_client.id

        jobs = db.query(PipelineJob).all()
        for job in jobs:
            if job.client_id is None:
                call = db.query(Call).filter(Call.id == job.call_id).first()
                if call and call.client_id is not None:
                    job.client_id = call.client_id
                elif default_client is not None:
                    job.client_id = default_client.id

        for event in db.query(EmailEvent).all():
            if event.client_id is None and event.recipient and event.recipient.client_id is not None:
                event.client_id = event.recipient.client_id

        # Ensure global fallback row and per-client settings/policies exist.
        ps = db.query(PipelineSettings).filter(PipelineSettings.id == 1).first()
        if not ps:
            ps = PipelineSettings(id=1, client_id=None, company_name=_default_pipeline_company())
            db.add(ps)
        if ps.report_mode == "none":
            ps.report_mode = "narrative"

        next_pipeline_settings_id = (db.query(func.max(PipelineSettings.id)).scalar() or 0) + 1
        for client in db.query(Client).all():
            if not db.query(PipelineSettings).filter(PipelineSettings.client_id == client.id).first():
                db.add(
                    PipelineSettings(
                        id=next_pipeline_settings_id,
                        client_id=client.id,
                        company_name=client.name if _context_path(client.name).exists() else _default_pipeline_company(),
                    )
                )
                next_pipeline_settings_id += 1
            if not db.query(ClientPolicy).filter(ClientPolicy.client_id == client.id).first():
                db.add(ClientPolicy(client_id=client.id))

        # Inviting a tenant agent/QA creates an auth user. The QA/call domain
        # still needs a linked Employee row because uploads and reports are
        # attributed to employees. Backfill legacy invites so upload does not
        # fail with "No agent found in database" after accepting an invite.
        for user in (
            db.query(User)
            .join(User.role)
            .filter(User.client_id.isnot(None), Role.name.in_(["agent", "qa"]))
            .all()
        ):
            _ensure_employee_profile_for_user(db, user)

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
optional_bearer_scheme = HTTPBearer(auto_error=False)


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


def _iter_criterion_evidence(criterion: str, info: dict) -> list[dict]:
    """Return evidence-like rows from all skill-specific output shapes."""
    rows: list[dict] = []
    raw_evidence = info.get("evidence")
    if isinstance(raw_evidence, list):
        rows.extend(ev for ev in raw_evidence if isinstance(ev, dict))

    def _append(values, quote_keys: tuple[str, ...], reason_keys: tuple[str, ...], default_reason: str):
        if not isinstance(values, list):
            return
        for item in values:
            if not isinstance(item, dict):
                continue
            quote = next((str(item.get(k, "")).strip() for k in quote_keys if item.get(k)), "")
            reason = next((str(item.get(k, "")).strip() for k in reason_keys if item.get(k)), "")
            if quote or reason:
                rows.append({"quote": quote, "reason": reason or default_reason})

    _append(info.get("claims"), ("quote", "statement", "claim"), ("assessment", "reason", "status"), "Factual claim reviewed")
    _append(info.get("emotional_moments"), ("quote", "customer_quote", "agent_quote"), ("assessment", "reason", "emotion"), "Empathy signal")
    _append(info.get("conflicts_detected"), ("quote", "customer_quote", "agent_quote", "description"), ("assessment", "reason", "severity"), "Conflict signal")
    _append(info.get("resolution_steps"), ("quote", "agent_quote", "step", "description"), ("assessment", "reason", "status"), "Resolution step")
    _append(info.get("issues_found"), ("quote", "description", "issue"), ("assessment", "reason", "severity"), "Severity issue")
    _append(info.get("positive_examples"), ("quote", "agent_quote", "example"), ("assessment", "reason"), "Positive example")
    _append(info.get("negative_examples"), ("quote", "agent_quote", "example"), ("assessment", "reason"), "Negative example")

    if not rows:
        summary = str(info.get("summary") or "").strip()
        if summary:
            rows.append({"quote": "", "reason": f"{criterion.replace('_', ' ').title()}: {summary}"})
    return rows


def _effective_report_mode(ps: PipelineSettings | None) -> str:
    mode = str(ps.report_mode if ps else "narrative").strip().lower()
    return mode if mode in {"simple", "narrative", "both"} else "narrative"


def _audio_duration_metadata(audio_path: str | Path) -> tuple[float | None, int | None, int | None]:
    """Return real file duration/sample-rate/channels when cheaply available."""
    path = Path(audio_path)
    try:
        import soundfile as sf
        info = sf.info(str(path))
        duration = float(info.frames) / float(info.samplerate) if info.samplerate else None
        return duration, int(info.samplerate) if info.samplerate else None, int(info.channels) if info.channels else None
    except Exception:
        pass
    try:
        import wave
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            frames = wf.getnframes()
            channels = wf.getnchannels()
            return (frames / rate if rate else None), rate or None, channels or None
    except Exception:
        return None, None, None


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


def _user_from_access_token(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    try:
        user_pk = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid media token")

    user = db.query(User).filter(User.id == user_pk, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    return _user_from_access_token(credentials.credentials, db)


def _create_call_media_token(call_id: str, user_id: int) -> str:
    """Short-lived signed token for native browser media requests.

    Native <audio> cannot attach the normal Authorization header. A scoped
    token lets the browser stream/range-request one call's audio without
    exposing the full session JWT in the URL.
    """
    expires = datetime.now(timezone.utc) + timedelta(minutes=60)
    payload = {
        "sub": str(user_id),
        "call_id": call_id,
        "scope": "call_audio",
        "exp": expires,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _user_from_call_media_token(token: str, call_id: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid media token")

    if payload.get("scope") != "call_audio" or payload.get("call_id") != call_id:
        raise HTTPException(status_code=401, detail="Invalid media token scope")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid media token")

    try:
        user_pk = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid media token")

    user = db.query(User).filter(User.id == user_pk, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def _require_role(user: User, allowed: set[str] | tuple[str, ...] | list[str], detail: str = "Not authorized") -> str:
    role = _role_name(user)
    if role not in allowed:
        raise HTTPException(status_code=403, detail=detail)
    return role


def _require_admin_read(current_user: User) -> None:
    if not _can_read_admin_area(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")


def _require_qa_operator(current_user: User) -> None:
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")


def _get_client_policy(db: Session, client_id: int | None) -> ClientPolicy | None:
    if client_id is None:
        return None
    policy = db.query(ClientPolicy).filter(ClientPolicy.client_id == client_id).first()
    if not policy:
        policy = ClientPolicy(client_id=client_id)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def _policy_client_id_for_request(current_user: User, client_id: int | None) -> int:
    if _is_platform_user(current_user):
        if client_id is None:
            raise HTTPException(status_code=400, detail="client_id is required for platform users")
        return int(client_id)
    return _tenant_client_id(current_user)


def _serialize_client_policy(policy: ClientPolicy) -> dict:
    return {
        "clientId": policy.client_id,
        "agentPortalEnabled": bool(policy.agent_portal_enabled),
        "agentCanViewCallList": bool(policy.agent_can_view_call_list),
        "agentCanOpenCallDetail": bool(policy.agent_can_open_call_detail),
        "agentCanPlayAudio": bool(policy.agent_can_play_audio),
        "agentCanViewTranscript": bool(policy.agent_can_view_transcript),
        "agentCanViewScores": bool(policy.agent_can_view_scores),
        "agentCanViewEvidence": bool(policy.agent_can_view_evidence),
        "agentCanViewAiReport": bool(policy.agent_can_view_ai_report),
        "agentCanViewTrends": bool(policy.agent_can_view_trends),
        "qaCanUploadCalls": bool(policy.qa_can_upload_calls),
        "qaCanManageContextTickets": bool(policy.qa_can_manage_context_tickets),
        "qaScope": policy.qa_scope,
        "tenantAdminCanInviteAdmins": bool(policy.tenant_admin_can_invite_admins),
        "updatedAt": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def _apply_client_policy_payload(policy: ClientPolicy, payload: dict) -> None:
    field_map = {
        "agentPortalEnabled": "agent_portal_enabled",
        "agentCanViewCallList": "agent_can_view_call_list",
        "agentCanOpenCallDetail": "agent_can_open_call_detail",
        "agentCanPlayAudio": "agent_can_play_audio",
        "agentCanViewTranscript": "agent_can_view_transcript",
        "agentCanViewScores": "agent_can_view_scores",
        "agentCanViewEvidence": "agent_can_view_evidence",
        "agentCanViewAiReport": "agent_can_view_ai_report",
        "agentCanViewTrends": "agent_can_view_trends",
        "qaCanUploadCalls": "qa_can_upload_calls",
        "qaCanManageContextTickets": "qa_can_manage_context_tickets",
        "tenantAdminCanInviteAdmins": "tenant_admin_can_invite_admins",
    }
    for api_name, model_name in field_map.items():
        if api_name in payload:
            setattr(policy, model_name, bool(payload[api_name]))

    if "qaScope" in payload:
        qa_scope = str(payload["qaScope"]).strip()
        if qa_scope not in CLIENT_POLICY_QA_SCOPES:
            raise HTTPException(
                status_code=400,
                detail=f"qaScope must be one of: {', '.join(CLIENT_POLICY_QA_SCOPES)}",
            )
        policy.qa_scope = qa_scope

    policy.updated_at = datetime.now(timezone.utc)


def _client_ids_visible_to_user(current_user: User) -> list[int] | None:
    """Return None for platform-wide users; otherwise the single tenant id."""
    if _is_platform_user(current_user):
        return None
    return [_tenant_client_id(current_user)]


def _scope_users_query(query, current_user: User):
    if _is_platform_user(current_user):
        return query
    return query.filter(User.client_id == _tenant_client_id(current_user))


def _scope_employee_query(query, current_user: User):
    if _is_platform_user(current_user):
        return query
    return query.filter(Employee.client_id == _tenant_client_id(current_user))


def _scope_call_query(query, current_user: User):
    if _is_platform_user(current_user):
        return query
    client_id = _tenant_client_id(current_user)
    return query.filter(
        or_(
            Call.client_id == client_id,
            # Backward-compatible fallback for legacy rows created before the
            # migration where Call.client_id is null but Employee.client_id is set.
            (Call.client_id.is_(None) & (Employee.client_id == client_id)),
        )
    )


def _scope_pipeline_job_query(query, current_user: User):
    if _is_platform_user(current_user):
        return query
    return query.filter(PipelineJob.client_id == _tenant_client_id(current_user))


def _pipeline_settings_for_client(db: Session, client_id: int | None, create: bool = True) -> PipelineSettings | None:
    query = db.query(PipelineSettings)
    if client_id is None:
        settings_row = query.filter(PipelineSettings.client_id.is_(None)).order_by(PipelineSettings.id.asc()).first()
    else:
        settings_row = query.filter(PipelineSettings.client_id == client_id).first()
    if settings_row or not create:
        return settings_row

    client = db.query(Client).filter(Client.id == client_id).first() if client_id is not None else None
    settings_row = PipelineSettings(
        client_id=client_id,
        company_name=_default_pipeline_company() if client is None else client.name,
    )
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def _pipeline_settings_for_user(db: Session, current_user: User, create: bool = True) -> PipelineSettings | None:
    return _pipeline_settings_for_client(
        db,
        None if _is_platform_user(current_user) else _tenant_client_id(current_user),
        create=create,
    )


def _policy_capabilities(policy: ClientPolicy | None, role: str) -> dict[str, bool]:
    """Return server-enforced UI capabilities for the authenticated user."""
    if role in PLATFORM_ROLES or policy is None:
        return {
            "canUseAdmin": True,
            "canManageUsers": True,
            "canManageClients": True,
            "canUseQa": True,
            "canUploadCalls": True,
            "canManageContext": True,
            "canViewAgentDashboard": True,
            "canViewAgentCalls": True,
            "canPlayAudio": True,
            "canViewTranscript": True,
            "canViewScores": True,
            "canViewEvidence": True,
            "canViewAiReport": True,
            "canViewTrends": True,
        }
    if role in ("admin", "manager", "viewer"):
        return {
            "canUseAdmin": True,
            "canManageUsers": role == "admin",
            "canManageClients": False,
            "canUseQa": role == "admin",
            "canUploadCalls": role == "admin" and policy.qa_can_upload_calls,
            "canManageContext": role == "admin" and policy.qa_can_manage_context_tickets,
            "canViewAgentDashboard": False,
            "canViewAgentCalls": False,
            "canPlayAudio": True,
            "canViewTranscript": True,
            "canViewScores": True,
            "canViewEvidence": True,
            "canViewAiReport": True,
            "canViewTrends": True,
        }
    if role == "qa":
        return {
            "canUseAdmin": False,
            "canManageUsers": False,
            "canManageClients": False,
            "canUseQa": True,
            "canUploadCalls": policy.qa_can_upload_calls,
            "canManageContext": policy.qa_can_manage_context_tickets,
            "canViewAgentDashboard": False,
            "canViewAgentCalls": False,
            "canPlayAudio": True,
            "canViewTranscript": True,
            "canViewScores": True,
            "canViewEvidence": True,
            "canViewAiReport": True,
            "canViewTrends": True,
        }
    if role == "agent":
        return {
            "canUseAdmin": False,
            "canManageUsers": False,
            "canManageClients": False,
            "canUseQa": False,
            "canUploadCalls": False,
            "canManageContext": False,
            "canViewAgentDashboard": policy.agent_portal_enabled,
            "canViewAgentCalls": policy.agent_portal_enabled and policy.agent_can_view_call_list,
            "canPlayAudio": policy.agent_portal_enabled and policy.agent_can_play_audio,
            "canViewTranscript": policy.agent_portal_enabled and policy.agent_can_view_transcript,
            "canViewScores": policy.agent_portal_enabled and policy.agent_can_view_scores,
            "canViewEvidence": policy.agent_portal_enabled and policy.agent_can_view_evidence,
            "canViewAiReport": policy.agent_portal_enabled and policy.agent_can_view_ai_report,
            "canViewTrends": policy.agent_portal_enabled and policy.agent_can_view_trends,
        }
    return {}


def _context_names_visible_to_user(db: Session, current_user: User) -> set[str] | None:
    """Return None for platform scope, otherwise the company/context names allowed."""
    if _is_platform_user(current_user):
        return None
    client_id = _tenant_client_id(current_user)
    names: set[str] = set()
    client = db.query(Client).filter(Client.id == client_id).first()
    if client and client.name:
        names.add(client.name)
    ps = _pipeline_settings_for_client(db, client_id, create=True)
    if ps and ps.company_name:
        names.add(ps.company_name)
    return {name.strip().lower() for name in names if name and name.strip()}


def _ensure_company_allowed_for_user(db: Session, current_user: User, company_name: str) -> str:
    company_name = str(company_name or "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required")
    allowed = _context_names_visible_to_user(db, current_user)
    if allowed is not None and company_name.lower() not in allowed:
        raise HTTPException(status_code=403, detail="Cannot access another company's context")
    return company_name


def _agent_employee_id(user: User, db: Session) -> str | None:
    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    return employee.id if employee else None


def _ensure_call_visible_to_user(call: Call, user: User, db: Session) -> None:
    role = _role_name(user)
    if _is_platform_user(user):
        return
    client_id = _tenant_client_id(user)
    call_client_id = call.client_id or (call.employee.client_id if call.employee else None)
    if call_client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this call")
    if role in ("admin", "qa"):
        return
    if role == "agent":
        policy = _get_client_policy(db, client_id)
        if policy and not policy.agent_portal_enabled:
            raise HTTPException(status_code=403, detail="Agent portal is disabled by company policy")
        employee_id = _agent_employee_id(user, db)
        if employee_id and call.employee_id == employee_id:
            return
    raise HTTPException(status_code=403, detail="Not authorized to access this call")


@app.get("/")
def root():
    from pathlib import Path as _P
    from fastapi.responses import FileResponse as _FR
    _idx = _P(__file__).resolve().parent.parent / "static" / "index.html"
    if _idx.is_file():
        return _FR(_idx)
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
    role_name = user.role.name if user.role else ""
    policy = _get_client_policy(db, user.client_id) if user.client_id else None

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": role_name,
            "clientId": user.client_id,
            "clientName": user.client.name if user.client else None,
            "roleScope": "platform" if _is_platform_user(user) else "tenant",
            "capabilities": _policy_capabilities(policy, role_name),
        },
    }


@app.get(f"{settings.API_V1_PREFIX}/auth/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role_name = current_user.role.name if current_user.role else ""
    policy = _get_client_policy(db, current_user.client_id) if current_user.client_id else None
    return {
        "id": current_user.id,
        "name": current_user.full_name,
        "email": current_user.email,
        "role": role_name,
        "clientId": current_user.client_id,
        "clientName": current_user.client.name if current_user.client else None,
        "roleScope": "platform" if _is_platform_user(current_user) else "tenant",
        "capabilities": _policy_capabilities(policy, role_name),
        "isActive": current_user.is_active,
        "lastLoginAt": current_user.last_login_at,
    }

@app.get(f"{settings.API_V1_PREFIX}/admin/dashboard")
def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_read(current_user)
    visible_client_ids = _client_ids_visible_to_user(current_user)
    client_query = db.query(Client)
    if visible_client_ids is not None:
        client_query = client_query.filter(Client.id.in_(visible_client_ids))

    active_clients = client_query.filter(Client.status == "active").count()
    trial_clients = client_query.filter(Client.status == "trial").count()
    total_clients = client_query.count()

    user_query = db.query(User).join(User.role)
    call_query = db.query(Call).join(Employee, Call.employee_id == Employee.id)
    report_query = db.query(QaReport).join(Call, QaReport.call_id == Call.id).join(Employee, Call.employee_id == Employee.id)
    if visible_client_ids is not None:
        user_query = user_query.filter(User.client_id.in_(visible_client_ids))
        call_query = _scope_call_query(call_query, current_user)
        report_query = _scope_call_query(report_query, current_user)

    agent_query = db.query(Employee).filter(Employee.role == "AGENT")
    if visible_client_ids is not None:
        agent_query = agent_query.filter(Employee.client_id.in_(visible_client_ids))
    total_agents = agent_query.count()

    # Compute real stats from call data
    total_calls = call_query.count()
    completed_calls = call_query.filter(Call.status == "COMPLETED").count()

    avg_score_row = report_query.with_entities(func.avg(QaReport.overall_score)).first()
    avg_quality_score = round(avg_score_row[0], 1) if avg_score_row and avg_score_row[0] else 0

    # Build monthly call trend from actual data
    calls_by_month_query = (
        db.query(
            func.extract("month", Call.call_time).label("m"),
            func.count(Call.id).label("cnt"),
        )
        .join(Employee, Call.employee_id == Employee.id)
        .filter(Call.call_time.isnot(None))
    )
    if visible_client_ids is not None:
        calls_by_month_query = _scope_call_query(calls_by_month_query, current_user)
    calls_by_month = calls_by_month_query.group_by("m").all()
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
    _require_admin_read(current_user)

    clients_query = db.query(Client)
    visible_client_ids = _client_ids_visible_to_user(current_user)
    if visible_client_ids is not None:
        clients_query = clients_query.filter(Client.id.in_(visible_client_ids))
    clients = clients_query.order_by(Client.name.asc()).all()

    result = []
    for client in clients:
        agent_count = db.query(Employee).filter(Employee.client_id == client.id, Employee.role == "AGENT").count()

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
                "callsThisMonth": db.query(Call).filter(Call.client_id == client.id).count(),
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


@app.post(f"{settings.API_V1_PREFIX}/admin/clients")
def create_admin_client(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_platform_user(current_user) or _role_name(current_user) not in ADMIN_MUTATION_ROLES:
        raise HTTPException(status_code=403, detail="Platform admin access required to create clients")

    name = str(payload.get("name") or "").strip()
    industry = str(payload.get("industry") or "").strip() or None
    status = str(payload.get("status") or "trial").strip().lower()
    plan = str(payload.get("plan") or "trial").strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")
    if status not in ("active", "trial", "suspended", "churned"):
        raise HTTPException(status_code=400, detail="status must be active|trial|suspended|churned")
    if db.query(Client).filter(func.lower(Client.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="A client with this name already exists")

    client = Client(name=name, industry=industry, status=status, plan=plan)
    db.add(client)
    db.flush()

    next_pipeline_settings_id = (db.query(func.max(PipelineSettings.id)).scalar() or 0) + 1
    next_client_policy_id = (db.query(func.max(ClientPolicy.id)).scalar() or 0) + 1
    db.add(PipelineSettings(id=next_pipeline_settings_id, client_id=client.id, company_name=name))
    db.add(ClientPolicy(id=next_client_policy_id, client_id=client.id))
    db.commit()
    db.refresh(client)

    return {
        "client": {
            "id": client.id,
            "name": client.name,
            "industry": client.industry or "Unknown",
            "status": client.status,
            "plan": client.plan,
            "agents": 0,
            "qaCount": 0,
            "callsThisMonth": 0,
            "mrr": 0,
            "avgScore": 0,
        }
    }


@app.get(f"{settings.API_V1_PREFIX}/agents")
def list_upload_agents(
    client_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")

    query = db.query(Employee).filter(Employee.role == "AGENT")
    if _is_platform_user(current_user):
        if client_id is not None:
            query = query.filter(Employee.client_id == int(client_id))
    else:
        query = query.filter(Employee.client_id == _tenant_client_id(current_user))

    agents = query.order_by(Employee.full_name.asc()).all()
    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.full_name,
                "clientId": agent.client_id,
                "clientName": agent.client.name if agent.client else None,
                "userId": agent.user_id,
                "email": agent.user.email if agent.user else None,
            }
            for agent in agents
        ]
    }


@app.get(f"{settings.API_V1_PREFIX}/admin/client-policy")
def get_admin_client_policy(
    client_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_read(current_user)
    resolved_client_id = _policy_client_id_for_request(current_user, client_id)
    client = db.query(Client).filter(Client.id == resolved_client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    policy = _get_client_policy(db, resolved_client_id)
    return {
        "client": {
            "id": client.id,
            "name": client.name,
            "status": client.status,
            "plan": client.plan,
        },
        "policy": _serialize_client_policy(policy),
    }


@app.put(f"{settings.API_V1_PREFIX}/admin/client-policy")
def update_admin_client_policy(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_manage_client_policy(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update client policy")
    client_id = payload.get("clientId") or payload.get("client_id")
    resolved_client_id = _policy_client_id_for_request(current_user, int(client_id) if client_id else None)
    client = db.query(Client).filter(Client.id == resolved_client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    policy = _get_client_policy(db, resolved_client_id)
    _apply_client_policy_payload(policy, payload)
    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return {
        "client": {
            "id": client.id,
            "name": client.name,
            "status": client.status,
            "plan": client.plan,
        },
        "policy": _serialize_client_policy(policy),
    }


@app.get(f"{settings.API_V1_PREFIX}/admin/users")
def get_admin_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_read(current_user)

    users = (
        _scope_users_query(db.query(User), current_user)
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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to invite users")

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    role_name = (payload.get("role") or "").strip()
    requested_client_id = payload.get("clientId")

    if not name or not email or not role_name:
        raise HTTPException(status_code=400, detail="Name, email, and role are required")

    allowed_roles = _assignable_roles_for(current_user)
    if role_name not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed roles: {', '.join(allowed_roles)}")

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    client_id = None
    if _is_platform_user(current_user):
        if role_name in TENANT_USER_ROLES:
            try:
                client_id = int(requested_client_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Client is required for tenant users")
            if not db.query(Client).filter(Client.id == client_id).first():
                raise HTTPException(status_code=404, detail="Client not found")
        elif role_name in PLATFORM_ROLES:
            client_id = None
        else:
            raise HTTPException(status_code=400, detail="Unsupported role")
    else:
        client_id = _tenant_client_id(current_user)
        if role_name == "admin":
            policy = _get_client_policy(db, client_id)
            if not policy or not policy.tenant_admin_can_invite_admins:
                raise HTTPException(status_code=403, detail="Company policy does not allow tenant admins to invite admins")

    invite_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    invited_user = User(
        full_name=name,
        email=email,
        password_hash="INVITED_ACCOUNT_NO_PASSWORD_YET",
        role_id=role.id,
        client_id=client_id,
        is_active=False,
        invite_token=invite_token,
        invite_expires_at=now + timedelta(days=7),
        invited_at=now,
    )

    db.add(invited_user)
    db.flush()
    _ensure_employee_profile_for_user(db, invited_user)
    db.commit()
    db.refresh(invited_user)

    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={invite_token}"
    email_event = email_service.send_invite_email(
        db,
        user=invited_user,
        invite_url=invite_url,
        invited_by=current_user,
    )

    return {
        "message": (
            "Invitation created and email sent"
            if email_event.status == "sent"
            else "Invitation created successfully"
        ),
        "inviteUrl": invite_url,
        "emailStatus": email_event.status,
        "emailMessageId": email_event.provider_message_id,
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
    email_service.send_account_activated_email(db, user=user)

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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    new_role_name = (payload.get("role") or "").strip()
    allowed_roles = _assignable_roles_for(current_user)

    if new_role_name not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed roles: {', '.join(allowed_roles)}")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    _guard_protected_admin_target(current_user, user, "change")

    role = db.query(Role).filter(Role.name == new_role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    old_role_name = user.role.name if user.role else None
    user.role_id = role.id
    user.role = role
    if _employee_role_for_user_role(role.name):
        _ensure_employee_profile_for_user(db, user)
    else:
        for employee in db.query(Employee).filter(Employee.user_id == user.id).all():
            employee.user_id = None
    db.commit()
    db.refresh(user)
    email_service.send_role_changed_email(
        db,
        user=user,
        old_role=old_role_name,
        new_role=role.name,
        actor=current_user,
    )

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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    new_status = (payload.get("status") or "").strip()

    if new_status not in ["active", "disabled"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    _guard_protected_admin_target(current_user, user, "disable")

    if user.invite_token and not user.is_active:
        raise HTTPException(status_code=400, detail="Invited users cannot be enabled/disabled. They must accept the invitation or be deleted.")

    old_status = "active" if user.is_active else "disabled"
    user.is_active = new_status == "active"
    db.commit()
    db.refresh(user)
    email_service.send_status_changed_email(
        db,
        user=user,
        new_status=new_status,
        actor=current_user,
    )

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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_protected_admin_target(current_user, user, "view invite for")

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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    _guard_protected_admin_target(current_user, user, "delete")

    was_invited = bool(user.invite_token and not user.is_active)
    user_name = user.full_name
    target_email = user.email
    target_id = user.id

    linked_employees = db.query(Employee).filter(Employee.user_id == user.id).all()
    for employee in linked_employees:
        employee.user_id = None

    # Keep the outbound-mail audit trail, but detach it from the deleted user.
    # Otherwise PostgreSQL rejects the delete because email_events records invite
    # and activation attempts against recipient_user_id.
    detached_email_events = (
        db.query(EmailEvent)
        .filter(EmailEvent.recipient_user_id == user.id)
        .update({EmailEvent.recipient_user_id: None}, synchronize_session=False)
    )
    db.query(EmailPreference).filter(EmailPreference.user_id == user.id).delete(synchronize_session=False)

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
            "detached_employee_ids": [employee.id for employee in linked_employees],
            "detached_email_events": detached_email_events,
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
    if not _can_read_qa_calls(current_user):
        raise HTTPException(status_code=403, detail="QA, Admin, or owning Agent access required")
    role = _role_name(current_user)
    if role == "agent":
        policy = _get_client_policy(db, current_user.client_id)
        if not policy or not policy.agent_portal_enabled or not policy.agent_can_view_call_list:
            return {"calls": []}
    query = (
        db.query(Call, Employee, QaReport)
        .join(Employee, Call.employee_id == Employee.id)
        .outerjoin(QaReport, Call.id == QaReport.call_id)
    )
    query = _scope_call_query(query, current_user)
    if role == "agent":
        employee_id = _agent_employee_id(current_user, db)
        if not employee_id:
            return {"calls": []}
        query = query.filter(Call.employee_id == employee_id)

    rows = query.order_by(Call.created_at.desc()).all()

    results = []
    for call, emp, report in rows:
        policy = _get_client_policy(db, current_user.client_id) if role == "agent" else None
        results.append({
            "callId": call.id,
            "filename": call.original_filename,
            "callTime": call.call_time.isoformat() if call.call_time else None,
            "status": call.status,
            "agentName": emp.full_name,
            "overallScore": report.overall_score if report and (role != "agent" or (policy and policy.agent_can_view_scores)) else None,
            "severity": report.severity if report and (role != "agent" or (policy and policy.agent_can_view_scores)) else None,
        })

    return {"calls": results}


## QA Call detail endpoint

@app.get(f"{settings.API_V1_PREFIX}/qa/calls/{{call_id}}/audio")
def get_qa_call_audio(
    call_id: str,
    media_token: str | None = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
):
    from fastapi.responses import FileResponse
    import mimetypes

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if credentials:
        current_user = _user_from_access_token(credentials.credentials, db)
    elif media_token:
        current_user = _user_from_call_media_token(media_token, call_id, db)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    _ensure_call_visible_to_user(call, current_user, db)
    if _role_name(current_user) == "agent":
        policy = _get_client_policy(db, current_user.client_id)
        if not policy or not policy.agent_can_play_audio:
            raise HTTPException(status_code=403, detail="Audio playback is disabled by company policy")
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
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=300",
            "Cross-Origin-Resource-Policy": "cross-origin",
        },
        content_disposition_type="inline",
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
    _ensure_call_visible_to_user(call, current_user, db)
    role = _role_name(current_user)
    policy = _get_client_policy(db, current_user.client_id) if role == "agent" else None
    if role == "agent" and policy and not policy.agent_can_open_call_detail:
        raise HTTPException(status_code=403, detail="Call detail is disabled by company policy")

    drive_file_id = call.drive_file_id
    drive_preview_url = (
        f"https://drive.google.com/file/d/{drive_file_id}/preview"
        if drive_file_id else None
    )
    drive_download_url = (
        f"https://drive.google.com/uc?export=download&id={drive_file_id}"
        if drive_file_id else None
    )
    audio_url = None
    can_play_audio = role != "agent" or (policy and policy.agent_can_play_audio)
    if can_play_audio and call.storage_path and Path(call.storage_path).is_file():
        media_token = _create_call_media_token(call.id, current_user.id)
        audio_url = f"{settings.API_V1_PREFIX}/qa/calls/{call.id}/audio?media_token={media_token}"

    can_view_transcript = role != "agent" or (policy and policy.agent_can_view_transcript)
    can_view_scores = role != "agent" or (policy and policy.agent_can_view_scores)
    can_view_evidence = role != "agent" or (policy and policy.agent_can_view_evidence)
    can_view_ai_report = role != "agent" or (policy and policy.agent_can_view_ai_report)

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
            "fullText": transcript.full_text if transcript and can_view_transcript else "",
            "speakerTurns": transcript.speaker_turns or [] if transcript and can_view_transcript else [],
        },
        "report": {
            "overallScore": report.overall_score if report and can_view_scores else None,
            "grade": report.grade if report and can_view_scores else None,
            "severity": report.severity if report and can_view_scores else None,
            "dimensionScores": report.dimension_scores or {} if report and can_view_scores else {},
            "dimensionReports": report.dimension_reports or {} if report and can_view_scores else {},
            "evidence": report.evidence or [] if report and can_view_evidence else [],
            "confidenceScores": report.confidence_scores or {} if report and can_view_scores else {},
            "reportJson": report.report_json or {} if report and can_view_ai_report else {},
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
    _require_role(current_user, ("agent",), "Agent access required")
    policy = _get_client_policy(db, current_user.client_id)
    if not policy or not policy.agent_portal_enabled:
        raise HTTPException(status_code=403, detail="Agent portal is disabled by company policy")
    employee = _get_agent_employee(current_user, db)
    if not employee:
        return {
            "scores": {
                "overall": 0,
                "politeness": 0,
                "empathy": 0,
                "conflictRate": 0,
                "resolutionRate": 0,
            },
            "trend": [],
        }

    query = db.query(QaReport).join(Call, QaReport.call_id == Call.id)
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
    if policy.agent_can_view_trends:
        for i, r in enumerate(reversed(reports[:12])):
            trend.append({"name": f"Call {i + 1}", "overall": r.overall_score or 0})

    return {
        "scores": {
            "overall": round(avg, 1) if policy.agent_can_view_scores else 0,
            "politeness": politeness if policy.agent_can_view_scores else 0,
            "empathy": empathy if policy.agent_can_view_scores else 0,
            "conflictRate": conflict_rate if policy.agent_can_view_scores else 0,
            "resolutionRate": resolution_rate if policy.agent_can_view_scores else 0,
        },
        "trend": trend,
    }


@app.get(f"{settings.API_V1_PREFIX}/agent/calls")
def get_agent_calls(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_role(current_user, ("agent",), "Agent access required")
    policy = _get_client_policy(db, current_user.client_id)
    if not policy or not policy.agent_portal_enabled or not policy.agent_can_view_call_list:
        return {"calls": [], "total": 0}
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
            "overallScore": report.overall_score if report and policy.agent_can_view_scores else None,
            "severity": report.severity if report and policy.agent_can_view_scores else None,
        })

    return {"calls": results, "total": len(results)}


## ── Call Upload endpoint (FR-10) ──────────────────────────────────────

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp3",
    "audio/flac", "audio/ogg", "audio/webm", "audio/mp4",
    "application/octet-stream",
}
# Keep backend and Tier-3 model-server limits aligned. The stress-test call is
# ~89 MB, so buffering many concurrent uploads at the old 100 MB cap caused
# TLS/write resets before jobs reached the GPU. Uploads are streamed below.
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024
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


async def _stream_upload_to_disk(file: UploadFile, dest: Path) -> tuple[int, str]:
    """Stream an uploaded audio file to disk while computing SHA-256.

    This avoids buffering large WAV files in backend RAM. It also removes
    partial files on oversize/error so failed stress waves do not leave junk
    behind in the uploads directory.
    """
    sha256_hash = hashlib.sha256()
    total_bytes = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)",
                    )
                sha256_hash.update(chunk)
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if total_bytes == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty file")

    return total_bytes, sha256_hash.hexdigest()


def _run_real_pipeline(
    call_id: str,
    audio_path: str,
    company: str | None = None,
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
        ps = _pipeline_settings_for_client(db, call.client_id, create=True)
        audio_mode      = ps.audio_mode      if ps else "denoise"
        injection_scan  = ps.injection_scan  if ps else "static"
        num_speakers    = ps.num_speakers    if ps else None
        report_mode     = _effective_report_mode(ps)
        use_consensus   = ps.use_consensus   if ps else False
        _requested_company = company or (ps.company_name if ps else _default_pipeline_company())
        _company        = _ensure_known_company_context(_requested_company)

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
        if duration:
            existing_duration = float(call.duration_seconds or 0)
            call.duration_seconds = round(max(existing_duration, float(duration)), 3)
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
            json_path,
            _company,
            rating_output,
            injection_scan_mode=injection_scan,
            use_consensus=use_consensus,
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
            for ev in _iter_criterion_evidence(crit, info):
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
                           f"Rated by CallTone AI pipeline against {_company} quality standards.",
                "strengths": strengths or ["Overall adequate performance"],
                "weaknesses": weaknesses or ["No major issues detected"],
                "recommended_actions": [
                    info.get("recommendation", "")
                    for info in criteria.values() if info.get("recommendation")
                ] or ["Continue monitoring"],
            }

        # Resolve QA employee for report
        qa_emp = db.query(Employee).filter(
            Employee.role == "QA",
            Employee.client_id == call.client_id,
        ).first()
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
    company: str | None = None,
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

        ps = _pipeline_settings_for_client(db, call.client_id, create=True)
        num_speakers = ps.num_speakers if ps else None
        report_mode = _effective_report_mode(ps)
        use_consensus = ps.use_consensus if ps else False
        _requested_company = company or (ps.company_name if ps else _default_pipeline_company())
        _company = _ensure_known_company_context(_requested_company)

        call.status = "PROCESSING"
        call.current_step = "queued"
        db.commit()

        job_id = model_client.submit(
            audio_path, company=_company, speakers=num_speakers,
            filename=call.original_filename,
            asr_engine=asr_engine,
            report_mode=report_mode,
            use_consensus=use_consensus,
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
        if duration:
            existing_duration = float(call.duration_seconds or 0)
            call.duration_seconds = round(max(existing_duration, float(duration)), 3)
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
            for ev in _iter_criterion_evidence(crit, info):
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
                for ev in _iter_criterion_evidence(c, info)[:2]:
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

        qa_emp = db.query(Employee).filter(
            Employee.role == "QA",
            Employee.client_id == call.client_id,
        ).first()
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


def _run_pipeline(
    call_id: str,
    audio_path: str,
    asr_engine: str = "fasterwhisper",
    company_name: str | None = None,
):
    """
    Dispatch: remote model server (if MODEL_SERVER_URL set) or local pipeline.
    Errors from either path are persisted to the Call record.
    """
    try:
        from app import model_client
        if model_client.configured():
            _run_remote_pipeline(call_id, audio_path, company=company_name, asr_engine=asr_engine)
        else:
            _run_real_pipeline(call_id, audio_path, company=company_name, asr_engine=asr_engine)
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


PIPELINE_QUEUE_ETA_SECONDS = int(os.getenv("PIPELINE_QUEUE_ETA_SECONDS", "120"))
PIPELINE_QUEUE_POLL_SECONDS = float(os.getenv("PIPELINE_QUEUE_POLL_SECONDS", "2"))
_PIPELINE_QUEUE_LOCK = threading.Lock()
_PIPELINE_QUEUE_WAKE_EVENT = threading.Event()
_PIPELINE_ACTIVE_CALL_ID: str | None = None
_PIPELINE_WORKER_THREAD: threading.Thread | None = None
_PIPELINE_RECOVERY_DONE = False


def _ensure_pipeline_queue_worker_started() -> None:
    """Start the durable pipeline queue worker if it is not running."""
    global _PIPELINE_RECOVERY_DONE, _PIPELINE_WORKER_THREAD
    with _PIPELINE_QUEUE_LOCK:
        if not _PIPELINE_RECOVERY_DONE:
            _recover_interrupted_pipeline_jobs()
            _PIPELINE_RECOVERY_DONE = True
        if _PIPELINE_WORKER_THREAD is not None and _PIPELINE_WORKER_THREAD.is_alive():
            return
        _PIPELINE_WORKER_THREAD = threading.Thread(
            target=_pipeline_queue_worker_loop,
            name="calltone-pipeline-queue",
            daemon=True,
        )
        _PIPELINE_WORKER_THREAD.start()


def _enqueue_pipeline(
    call_id: str,
    audio_path: str,
    asr_engine: str = "fasterwhisper",
    company_name: str | None = None,
    client_id: int | None = None,
) -> int:
    """Persist one pipeline job and return its 1-based queue position."""
    _ensure_pipeline_queue_worker_started()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        job = db.query(PipelineJob).filter(PipelineJob.call_id == call_id).first()
        if job is None:
            job = PipelineJob(
                call_id=call_id,
                client_id=client_id,
                audio_path=audio_path,
                asr_engine=asr_engine,
                company_name=company_name,
                status="queued",
                created_at=now,
                updated_at=now,
            )
            db.add(job)
        elif job.status not in ("running", "completed"):
            job.audio_path = audio_path
            job.asr_engine = asr_engine
            job.company_name = company_name
            job.client_id = client_id
            job.status = "queued"
            job.locked_at = None
            job.finished_at = None
            job.updated_at = now
        db.commit()
    finally:
        db.close()

    _PIPELINE_QUEUE_WAKE_EVENT.set()
    snapshot = _pipeline_queue_snapshot(call_id)
    return int(snapshot["queuePosition"] or 0)


def _queued_pipeline_jobs(db: Session) -> list[PipelineJob]:
    return (
        db.query(PipelineJob)
        .filter(PipelineJob.status == "queued")
        .order_by(PipelineJob.priority.asc(), PipelineJob.created_at.asc(), PipelineJob.id.asc())
        .all()
    )


def _pipeline_queue_snapshot(call_id: str | None = None) -> dict[str, int | str | None]:
    db = SessionLocal()
    try:
        queued_jobs = _queued_pipeline_jobs(db)
        queued = [job.call_id for job in queued_jobs]
        running = db.query(PipelineJob).filter(PipelineJob.status == "running").first()
        running_call_id = running.call_id if running else None
    finally:
        db.close()
    with _PIPELINE_QUEUE_LOCK:
        active_id = _PIPELINE_ACTIVE_CALL_ID
    active_id = active_id or running_call_id
    position = None
    if call_id:
        if call_id == active_id:
            position = 0
        elif call_id in queued:
            position = queued.index(call_id) + 1
    eta = None
    if position is not None:
        eta = PIPELINE_QUEUE_ETA_SECONDS if position == 0 else position * PIPELINE_QUEUE_ETA_SECONDS
    return {
        "activeCallId": active_id,
        "queuePosition": position,
        "queuedCount": len(queued),
        "etaSeconds": eta,
    }


def _pipeline_queue_overview() -> dict[str, int | str | list[str] | None]:
    db = SessionLocal()
    try:
        queued_jobs = _queued_pipeline_jobs(db)
        queued = [job.call_id for job in queued_jobs]
        running_jobs = (
            db.query(PipelineJob)
            .filter(PipelineJob.status == "running")
            .order_by(PipelineJob.started_at.asc(), PipelineJob.id.asc())
            .all()
        )
        running = [job.call_id for job in running_jobs]
        failed_jobs = (
            db.query(PipelineJob)
            .filter(PipelineJob.status == "failed")
            .order_by(PipelineJob.updated_at.desc(), PipelineJob.id.asc())
            .limit(20)
            .all()
        )
        failed_count = db.query(PipelineJob).filter(PipelineJob.status == "failed").count()
    finally:
        db.close()
    with _PIPELINE_QUEUE_LOCK:
        active_id = _PIPELINE_ACTIVE_CALL_ID
    active_id = active_id or (running[0] if running else None)
    return {
        "activeCallId": active_id,
        "queuedCount": len(queued),
        "queuedCallIds": queued,
        "runningCallIds": running,
        "failedCount": failed_count,
        "failedCallIds": [job.call_id for job in failed_jobs],
        "etaSecondsPerJob": PIPELINE_QUEUE_ETA_SECONDS,
        "estimatedDrainSeconds": len(queued) * PIPELINE_QUEUE_ETA_SECONDS,
    }


def _pipeline_job_to_public(job: PipelineJob) -> dict:
    return {
        "id": job.id,
        "callId": job.call_id,
        "audioPath": job.audio_path,
        "asrEngine": job.asr_engine,
        "companyName": job.company_name,
        "status": job.status,
        "priority": job.priority,
        "attempts": job.attempts,
        "maxAttempts": job.max_attempts,
        "errorMessage": job.error_message,
        "lockedAt": job.locked_at.isoformat() if job.locked_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }


def _notify_pipeline_terminal_state(
    db: Session,
    *,
    call: Call | None,
    job: PipelineJob,
    completed: bool,
    error_message: str | None,
) -> None:
    """Send terminal pipeline notifications without affecting job state."""
    if not call:
        return
    try:
        if completed:
            report = db.query(QaReport).filter(QaReport.call_id == call.id).first()
            if report and call.employee and call.employee.user and call.employee.user.is_active:
                email_service.send_call_completed_email(
                    db,
                    user=call.employee.user,
                    call=call,
                    report=report,
                )
            return

        admins = (
            db.query(User)
            .join(User.role)
            .filter(User.is_active == True)
            .all()
        )
        for user in admins:
            if not user.role or user.role.name not in ADMIN_MUTATION_ROLES:
                continue
            if call.client_id is not None and user.client_id not in (None, call.client_id):
                continue
            if user.client_id is None and not _is_platform_user(user):
                continue
            if user.role and user.role.name in ADMIN_MUTATION_ROLES:
                email_service.send_call_failed_email(
                    db,
                    user=user,
                    call=call,
                    error=error_message or job.error_message or "Pipeline failed",
                )
    except Exception as exc:
        log.warning(
            "email.pipeline_notification_failed",
            extra={"event": "pipeline_notification_failed", "call_id": call.id, "err": str(exc)},
        )


def _recover_interrupted_pipeline_jobs() -> None:
    """Put jobs that were running during a backend restart back into the queue."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        interrupted = db.query(PipelineJob).filter(PipelineJob.status == "running").all()
        for job in interrupted:
            job.status = "queued"
            job.locked_at = None
            job.updated_at = now
            call = db.query(Call).filter(Call.id == job.call_id).first()
            if call and call.status != "COMPLETED":
                call.status = "PENDING"
                call.current_step = "queued"
        db.commit()
    finally:
        db.close()


def _claim_next_pipeline_job() -> dict[str, str] | None:
    db = SessionLocal()
    try:
        if db.bind and db.bind.dialect.name.startswith("postgres"):
            got_lock = db.execute(text("SELECT pg_try_advisory_xact_lock(42620260425)")).scalar()
            if got_lock is not True:
                return None

        running_exists = db.query(PipelineJob.id).filter(PipelineJob.status == "running").first()
        if running_exists is not None:
            return None

        query = (
            db.query(PipelineJob)
            .filter(PipelineJob.status == "queued")
            .order_by(PipelineJob.priority.asc(), PipelineJob.created_at.asc(), PipelineJob.id.asc())
        )
        if db.bind and db.bind.dialect.name.startswith("postgres"):
            query = query.with_for_update(skip_locked=True)
        job = query.first()
        if job is None:
            return None

        now = datetime.now(timezone.utc)
        job.status = "running"
        job.attempts = int(job.attempts or 0) + 1
        job.locked_at = now
        job.started_at = job.started_at or now
        job.updated_at = now
        job.error_message = None

        call = db.query(Call).filter(Call.id == job.call_id).first()
        if call:
            call.status = "PENDING"
            call.current_step = "starting"
            call.error_message = None

        payload = {
            "call_id": job.call_id,
            "audio_path": job.audio_path,
            "asr_engine": job.asr_engine,
            "company_name": job.company_name or "",
        }
        db.commit()
        return payload
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _finish_pipeline_job(call_id: str, worker_error: str | None = None) -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        job = db.query(PipelineJob).filter(PipelineJob.call_id == call_id).first()
        call = db.query(Call).filter(Call.id == call_id).first()
        if job is None:
            return

        if worker_error:
            error_message = worker_error
            call_completed = False
        else:
            call_completed = bool(call and call.status == "COMPLETED")
            error_message = call.error_message if call else "Call record not found after pipeline run"

        if call_completed:
            job.status = "completed"
            job.error_message = None
            job.finished_at = now
        elif job.attempts < job.max_attempts:
            job.status = "queued"
            job.error_message = error_message or "Pipeline failed; queued for retry"
            job.locked_at = None
            if call:
                call.status = "PENDING"
                call.current_step = "queued"
            _PIPELINE_QUEUE_WAKE_EVENT.set()
        else:
            job.status = "failed"
            job.error_message = error_message or "Pipeline failed"
            job.finished_at = now
            if call and call.status != "COMPLETED":
                call.status = "FAILED"
                call.current_step = "error"
                call.error_message = job.error_message

        job.updated_at = now
        db.commit()
        if call_completed or job.status == "failed":
            _notify_pipeline_terminal_state(
                db,
                call=call,
                job=job,
                completed=call_completed,
                error_message=error_message,
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _pipeline_queue_worker_loop() -> None:
    global _PIPELINE_ACTIVE_CALL_ID
    while True:
        job = _claim_next_pipeline_job()
        if job is None:
            _PIPELINE_QUEUE_WAKE_EVENT.wait(PIPELINE_QUEUE_POLL_SECONDS)
            _PIPELINE_QUEUE_WAKE_EVENT.clear()
            continue

        call_id = job["call_id"]
        with _PIPELINE_QUEUE_LOCK:
            _PIPELINE_ACTIVE_CALL_ID = call_id
        worker_error = None
        try:
            _run_pipeline(call_id, job["audio_path"], job["asr_engine"], job["company_name"] or None)
        except Exception as exc:
            worker_error = f"Pipeline worker crashed: {exc}"
        finally:
            _finish_pipeline_job(call_id, worker_error=worker_error)
            with _PIPELINE_QUEUE_LOCK:
                if _PIPELINE_ACTIVE_CALL_ID == call_id:
                    _PIPELINE_ACTIVE_CALL_ID = None


@app.on_event("startup")
def _start_pipeline_queue_worker_on_startup() -> None:
    if os.getenv("PIPELINE_QUEUE_AUTOSTART", "1") != "0":
        _ensure_pipeline_queue_worker_started()


@app.post(f"{settings.API_V1_PREFIX}/calls/upload")
async def upload_call(
    file: UploadFile = File(...),
    agent_id: str = Form(default=""),
    asr_engine: str = Form(default="fasterwhisper"),
    company_name: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to upload calls")
    if _is_tenant_user(current_user):
        policy = _get_client_policy(db, current_user.client_id)
        if not policy or not policy.qa_can_upload_calls:
            raise HTTPException(status_code=403, detail="Call upload is disabled by company policy")

    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Upload an audio file.",
        )

    try:
        asr_engine = _normalize_asr_engine(asr_engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if _is_tenant_user(current_user) and asr_engine != "fasterwhisper":
        raise HTTPException(status_code=403, detail="ASR engine selection is restricted to platform admins")

    # Resolve agent employee record before selecting context. Upload attribution
    # must be explicit: QA/admin users choose the real agent who handled the
    # call. Falling back to the first database agent causes wrong reports.
    employee_query = db.query(Employee).filter(Employee.role == "AGENT")
    if _is_tenant_user(current_user):
        employee_query = employee_query.filter(Employee.client_id == _tenant_client_id(current_user))
    if not agent_id:
        raise HTTPException(status_code=400, detail="Select the agent who handled this call")
    employee = employee_query.filter(Employee.id == agent_id).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Selected agent is not available for your company")

    upload_client_id = employee.client_id
    if _is_tenant_user(current_user):
        upload_client_id = _tenant_client_id(current_user)
        if employee.client_id != upload_client_id:
            raise HTTPException(status_code=403, detail="Cannot upload calls for another company's agent")

    try:
        ps = _pipeline_settings_for_client(db, upload_client_id, create=True)
        client = db.query(Client).filter(Client.id == upload_client_id).first() if upload_client_id is not None else None
        default_context_name = (ps.company_name if ps and ps.company_name else "") or (client.name if client else "")
        allowed_context_aliases = {
            value.strip().lower()
            for value in (client.name if client else "", default_context_name)
            if value and value.strip()
        }
        if client and company_name and company_name.strip().lower() not in allowed_context_aliases:
            raise HTTPException(status_code=400, detail="Selected context must match the selected agent's company")
        requested_company = default_context_name or company_name or _default_pipeline_company()
        requested_company = _ensure_company_allowed_for_user(db, current_user, requested_company)
        selected_company = _ensure_known_company_context(requested_company)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    call_id = str(uuid.uuid4())
    # C-4: strip any path separators / control chars from the
    # user-supplied name before joining with UPLOAD_DIR. Without this,
    # a filename of "../../etc/passwd" escapes the upload directory
    # despite the UUID prefix.
    safe_filename = _sanitize_filename(file.filename)

    dest = UPLOAD_DIR / f"{call_id}_{safe_filename}"
    total_bytes, sha256 = await _stream_upload_to_disk(file, dest)
    duration_seconds, sample_rate_hz, channels = _audio_duration_metadata(dest)

    # Resolve or create customer
    customer_query = db.query(Customer)
    if upload_client_id is not None:
        customer_query = customer_query.filter(Customer.client_id == upload_client_id)
    customer = customer_query.first()
    if not customer:
        customer = Customer(
            id=str(uuid.uuid4()),
            client_id=upload_client_id,
            display_name="Uploaded Call Customer",
            phone_hash="upload",
        )
        db.add(customer)
        db.flush()

    call = Call(
        id=call_id,
        client_id=upload_client_id,
        customer_id=customer.id,
        employee_id=employee.id,
        original_filename=safe_filename,
        storage_path=str(dest),
        size_bytes=total_bytes,
        sha256=sha256,
        duration_seconds=round(duration_seconds, 3) if duration_seconds else None,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        status="PENDING",
        current_step="queued",
        call_time=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    queue_position = _enqueue_pipeline(call_id, str(dest), asr_engine, selected_company, upload_client_id)

    return {
        "callId": call_id,
        "filename": safe_filename,
        "status": "QUEUED",
        "queuePosition": queue_position,
        "etaSeconds": queue_position * PIPELINE_QUEUE_ETA_SECONDS,
        "message": "Call uploaded successfully. Processing queued.",
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
    _ensure_call_visible_to_user(call, current_user, db)

    has_transcript = db.query(Transcript).filter(Transcript.call_id == call_id).first() is not None
    has_report = db.query(QaReport).filter(QaReport.call_id == call_id).first() is not None
    queue_state = _pipeline_queue_snapshot(call_id)

    return {
        "callId": call.id,
        "status": call.status,
        "currentStep": call.current_step,
        "hasTranscript": has_transcript,
        "hasReport": has_report,
        "error": call.error_message,
        "queuePosition": queue_state["queuePosition"],
        "queuedCount": queue_state["queuedCount"],
        "etaSeconds": queue_state["etaSeconds"],
    }


@app.get(f"{settings.API_V1_PREFIX}/pipeline/queue")
def get_pipeline_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to inspect pipeline queue")
    if _is_tenant_user(current_user):
        query = _scope_pipeline_job_query(db.query(PipelineJob), current_user)
        queued = query.filter(PipelineJob.status == "queued").order_by(PipelineJob.created_at.asc()).all()
        running = query.filter(PipelineJob.status == "running").order_by(PipelineJob.started_at.asc()).all()
        failed = query.filter(PipelineJob.status == "failed").order_by(PipelineJob.updated_at.desc()).limit(20).all()
        return {
            "activeCallId": running[0].call_id if running else None,
            "queuedCount": len(queued),
            "queuedCallIds": [job.call_id for job in queued],
            "runningCallIds": [job.call_id for job in running],
            "failedCount": query.filter(PipelineJob.status == "failed").count(),
            "failedCallIds": [job.call_id for job in failed],
            "etaSecondsPerJob": PIPELINE_QUEUE_ETA_SECONDS,
            "estimatedDrainSeconds": len(queued) * PIPELINE_QUEUE_ETA_SECONDS,
        }
    return _pipeline_queue_overview()


@app.get(f"{settings.API_V1_PREFIX}/pipeline/jobs")
def list_pipeline_jobs(
    status_filter: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to inspect pipeline jobs")
    limit = max(1, min(int(limit or 50), 200))
    query = _scope_pipeline_job_query(db.query(PipelineJob), current_user)
    if status_filter:
        allowed = {"queued", "running", "completed", "failed"}
        if status_filter not in allowed:
            raise HTTPException(status_code=400, detail=f"status_filter must be one of {', '.join(sorted(allowed))}")
        query = query.filter(PipelineJob.status == status_filter)
    jobs = (
        query.order_by(PipelineJob.created_at.desc(), PipelineJob.id.asc())
        .limit(limit)
        .all()
    )
    return {"jobs": [_pipeline_job_to_public(job) for job in jobs]}


@app.post(f"{settings.API_V1_PREFIX}/pipeline/jobs/{{call_id}}/retry")
def retry_pipeline_job(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    job = db.query(PipelineJob).filter(PipelineJob.call_id == call_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    if _is_tenant_user(current_user) and job.client_id != _tenant_client_id(current_user):
        raise HTTPException(status_code=403, detail="Cannot retry another company's job")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Cannot retry a running job")
    if job.status == "completed":
        raise HTTPException(status_code=409, detail="Completed jobs cannot be retried")

    now = datetime.now(timezone.utc)
    job.status = "queued"
    job.attempts = 0
    job.error_message = None
    job.locked_at = None
    job.started_at = None
    job.finished_at = None
    job.updated_at = now
    call = db.query(Call).filter(Call.id == call_id).first()
    if call and call.status != "COMPLETED":
        call.status = "PENDING"
        call.current_step = "queued"
        call.error_message = None
    db.commit()
    db.refresh(job)
    _PIPELINE_QUEUE_WAKE_EVENT.set()
    return {"ok": True, "job": _pipeline_job_to_public(job)}


@app.post(f"{settings.API_V1_PREFIX}/pipeline/jobs/{{call_id}}/dead-letter")
def dead_letter_pipeline_job(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    job = db.query(PipelineJob).filter(PipelineJob.call_id == call_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    if _is_tenant_user(current_user) and job.client_id != _tenant_client_id(current_user):
        raise HTTPException(status_code=403, detail="Cannot dead-letter another company's job")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Cannot dead-letter a running job")
    if job.status == "completed":
        raise HTTPException(status_code=409, detail="Completed jobs cannot be dead-lettered")

    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.max_attempts = max(job.max_attempts, job.attempts)
    job.error_message = job.error_message or "Manually dead-lettered by admin"
    job.locked_at = None
    job.finished_at = now
    job.updated_at = now
    call = db.query(Call).filter(Call.id == call_id).first()
    if call and call.status != "COMPLETED":
        call.status = "FAILED"
        call.current_step = "error"
        call.error_message = job.error_message
    db.commit()
    db.refresh(job)
    _notify_pipeline_terminal_state(
        db,
        call=call,
        job=job,
        completed=False,
        error_message=job.error_message,
    )
    return {"ok": True, "job": _pipeline_job_to_public(job)}


@app.post(f"{settings.API_V1_PREFIX}/auth/logout")
def logout():
    return {"message": "Logged out successfully"}


# ── Mail Settings endpoints ─────────────────────────────────────────────────

@app.get(f"{settings.API_V1_PREFIX}/settings/mail")
def get_mail_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_platform_user(current_user):
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return email_service.mail_status(db)


@app.post(f"{settings.API_V1_PREFIX}/settings/mail/test")
def send_mail_test(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_platform_user(current_user) or _role_name(current_user) not in ADMIN_MUTATION_ROLES:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    event = email_service.send_test_email(db, user=current_user)
    return {
        "ok": event.status == "sent",
        "event": {
            "id": event.id,
            "eventType": event.event_type,
            "recipientEmail": event.recipient_email,
            "subject": event.subject,
            "status": event.status,
            "provider": event.provider,
            "providerMessageId": event.provider_message_id,
            "error": event.error,
            "createdAt": event.created_at,
            "sentAt": event.sent_at,
        },
    }


# ── Pipeline Settings endpoints ──────────────────────────────────────────────

@app.get(f"{settings.API_V1_PREFIX}/settings/pipeline")
def get_pipeline_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    ps = _pipeline_settings_for_user(db, current_user, create=True)
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
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    ps = _pipeline_settings_for_user(db, current_user, create=True)

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
        if payload["reportMode"] not in ("none", "simple", "narrative", "both"):
            raise HTTPException(status_code=400, detail="reportMode must be none|simple|narrative|both")
        ps.report_mode = payload["reportMode"]
    if "useConsensus" in payload:
        ps.use_consensus = bool(payload["useConsensus"])
    if "companyName" in payload:
        try:
            requested_company = _ensure_company_allowed_for_user(db, current_user, payload["companyName"])
            ps.company_name = _ensure_known_company_context(requested_company)
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
def list_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    allowed_names = _context_names_visible_to_user(db, current_user)
    import json as _json
    companies = []
    seen_slugs: set[str] = set()
    if CONTEXTS_DIR.exists():
        for f in sorted(CONTEXTS_DIR.glob("*.json")):
            if f.stem.endswith("_graph") or f.stem.endswith("_backup"):
                continue
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                company_name = str(data.get("company_name", f.stem))
                if allowed_names is not None and company_name.lower() not in allowed_names:
                    continue
                seen_slugs.add(f.stem)
                companies.append({
                    "name":    company_name,
                    "slug":    f.stem,
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
    if os.getenv("MODEL_SERVER_URL"):
        try:
            from app import model_client
            for item in model_client.list_contexts():
                slug = str(item.get("slug") or item.get("file", "")).replace(".json", "")
                if slug and slug in seen_slugs:
                    continue
                item_name = str(item.get("name") or slug)
                if allowed_names is not None and item_name.lower() not in allowed_names:
                    continue
                companies.append(item)
        except Exception as exc:
            log.warning(
                "model_server.context_list_failed",
                extra={"event": "context_list_failed", "err": str(exc)},
            )
    return {"companies": companies}


@app.get(f"{settings.API_V1_PREFIX}/context/companies/{'{name}'}")
def get_company_context(
    name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    name = _ensure_company_allowed_for_user(db, current_user, name)
    import json as _json
    path = CONTEXTS_DIR / f"{name.lower().replace(' ', '_')}.json"
    if not path.exists():
        if os.getenv("MODEL_SERVER_URL"):
            try:
                from app import model_client
                remote = model_client.get_context(name)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            if remote is not None:
                return remote
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
        synced = _sync_company_context_to_model_server(company_name)
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
                "syncedToModelServer": synced,
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
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    if _is_tenant_user(current_user):
        policy = _get_client_policy(db, current_user.client_id)
        if not policy or not policy.qa_can_manage_context_tickets:
            raise HTTPException(status_code=403, detail="Context management is disabled by company policy")
    company_name = _ensure_company_allowed_for_user(db, current_user, company_name)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Save the text file temporarily — the background thread will delete it when done.
    # Sanitize the company-derived path component: platform/super-admin callers skip
    # the tenant whitelist in _ensure_company_allowed_for_user, so company_name must
    # not be trusted to build a filesystem path (path-traversal guard).
    safe_company = _sanitize_filename(company_name.lower().replace(" ", "_"))
    tmp_path = UPLOAD_DIR / f"context_{safe_company}_{uuid.uuid4().hex[:8]}.txt"
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
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    job = _INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if _is_tenant_user(current_user):
        allowed = _context_names_visible_to_user(db, current_user)
        if allowed is not None and str(job.get("company", "")).lower() not in allowed:
            raise HTTPException(status_code=403, detail="Cannot inspect another company's ingest job")
    return job


@app.get(f"{settings.API_V1_PREFIX}/context/tickets")
def list_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    allowed_names = _context_names_visible_to_user(db, current_user)
    import json as _json
    tickets = []
    if TICKETS_DIR.exists():
        for f in sorted(TICKETS_DIR.glob("*.json"), reverse=True):
            try:
                t = _json.loads(f.read_text(encoding="utf-8"))
                if allowed_names is not None and str(t.get("company_name", "")).lower() not in allowed_names:
                    continue
                tickets.append(t)
            except Exception:
                pass
    return {"tickets": tickets}


@app.post(f"{settings.API_V1_PREFIX}/context/tickets")
def create_ticket(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json as _json
    if not _can_use_qa_tools(current_user):
        raise HTTPException(status_code=403, detail="QA or Admin access required")
    if _is_tenant_user(current_user):
        policy = _get_client_policy(db, current_user.client_id)
        if not policy or not policy.qa_can_manage_context_tickets:
            raise HTTPException(status_code=403, detail="Context tickets are disabled by company policy")
    company_name = _ensure_company_allowed_for_user(db, current_user, payload.get("companyName", ""))

    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(TICKETS_DIR.glob("TICKET-*.json"))
    next_num = len(existing) + 1
    ticket_id = f"TICKET-{next_num:03d}"

    ticket = {
        "ticket_id":    ticket_id,
        "submitted_by": current_user.email,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status":       "pending",
        "company_name": company_name,
        "field_name":   payload.get("fieldName", ""),
        "old_text":     payload.get("oldText", ""),
        "new_text":     payload.get("newText", ""),
        "reason":       payload.get("reason", ""),
    }

    out = TICKETS_DIR / f"{ticket_id}.json"
    out.write_text(_json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        reviewers = (
            db.query(User)
            .join(User.role)
            .filter(User.is_active == True)
            .all()
        )
        for reviewer in reviewers:
            if not reviewer.role or reviewer.role.name not in ADMIN_MUTATION_ROLES:
                continue
            if reviewer.client_id is not None:
                reviewer_allowed = _context_names_visible_to_user(db, reviewer)
                if reviewer_allowed is not None and ticket["company_name"].lower() not in reviewer_allowed:
                    continue
            email_service.send_context_ticket_email(
                db,
                recipient=reviewer,
                title="New CallTone context ticket",
                company=ticket["company_name"],
                field=ticket["field_name"],
                status="pending",
                actor=current_user,
                ticket_id=ticket_id,
            )
    except Exception as exc:
        log.warning(
            "email.context_ticket_notification_failed",
            extra={"event": "context_ticket_notification_failed", "ticket_id": ticket_id, "err": str(exc)},
        )
    return ticket


@app.patch(f"{settings.API_V1_PREFIX}/context/tickets/{'{ticket_id}'}")
def update_ticket_status(
    ticket_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json as _json
    if not _can_mutate_users(current_user):
        raise HTTPException(status_code=403, detail="Admin access required to approve/reject tickets")

    ticket_file = TICKETS_DIR / f"{ticket_id}.json"
    if not ticket_file.exists():
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket = _json.loads(ticket_file.read_text(encoding="utf-8"))
    _ensure_company_allowed_for_user(db, current_user, ticket.get("company_name", ""))
    new_status = payload.get("status", "")
    if new_status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")
    ticket["status"] = new_status
    ticket["reviewed_by"] = current_user.email
    ticket["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if "note" in payload:
        ticket["review_note"] = payload["note"]

    ticket_file.write_text(_json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        submitter = db.query(User).filter(User.email == ticket.get("submitted_by", "")).first()
        if submitter and submitter.is_active:
            email_service.send_context_ticket_email(
                db,
                recipient=submitter,
                title="CallTone context ticket reviewed",
                company=ticket.get("company_name", ""),
                field=ticket.get("field_name", ""),
                status=new_status,
                actor=current_user,
                ticket_id=ticket_id,
            )
    except Exception as exc:
        log.warning(
            "email.context_ticket_review_notification_failed",
            extra={"event": "context_ticket_review_notification_failed", "ticket_id": ticket_id, "err": str(exc)},
        )
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
