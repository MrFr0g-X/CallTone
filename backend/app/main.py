from datetime import datetime, timezone, timedelta
import secrets

from fastapi import FastAPI, HTTPException, status, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import text

from app.database import Base, engine, get_db, settings
from app.models import User, Client, Role
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_password, hash_password
import app.models  # noqa

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

    # Temporary placeholder values until calls/subscriptions tables are added
    calls_this_month = 0
    monthly_revenue = 0
    avg_quality_score = 0

    revenue_trend = [
        {"month": "Sep", "revenue": 0},
        {"month": "Oct", "revenue": 0},
        {"month": "Nov", "revenue": 0},
        {"month": "Dec", "revenue": 0},
        {"month": "Jan", "revenue": 0},
        {"month": "Feb", "revenue": 0},
        {"month": "Mar", "revenue": 0},
    ]

    calls_trend = [
        {"month": "Sep", "calls": 0},
        {"month": "Oct", "calls": 0},
        {"month": "Nov", "calls": 0},
        {"month": "Dec", "calls": 0},
        {"month": "Jan", "calls": 0},
        {"month": "Feb", "calls": 0},
        {"month": "Mar", "calls": 0},
    ]

    return {
        "kpis": {
            "activeClients": active_clients,
            "trialClients": trial_clients,
            "totalClients": total_clients,
            "totalAgents": total_agents,
            "callsThisMonth": calls_this_month,
            "monthlyRevenue": monthly_revenue,
        },
        "health": {
            "avgQualityScore": avg_quality_score,
            "activeClients": active_clients,
            "trialConversions": 68,
            "churnRate": 3.2,
            "uptime": 99.97,
        },
        "trends": {
            "revenue": revenue_trend,
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

##QA Calls list endpoint

@app.get(f"{settings.API_V1_PREFIX}/qa/calls")
def get_qa_calls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = text("""
        SELECT
            c.call_id,
            c.original_filename,
            c.call_time,
            c.status,
            e.full_name AS agent_name,
            qr.overall_score,
            qr.severity
        FROM calls c
        JOIN employees e ON c.employee_id = e.employee_id
        LEFT JOIN qa_reports qr ON c.call_id = qr.call_id
        ORDER BY c.created_at DESC
    """)

    rows = db.execute(query).mappings().all()

    results = []
    for row in rows:
        results.append({
            "callId": str(row["call_id"]),
            "filename": row["original_filename"],
            "callTime": row["call_time"].isoformat() if row["call_time"] else None,
            "status": row["status"],
            "agentName": row["agent_name"],
            "overallScore": float(row["overall_score"]) if row["overall_score"] is not None else None,
            "severity": row["severity"],
        })

    return {"calls": results}

## QA Call detail endpoint

@app.get(f"{settings.API_V1_PREFIX}/qa/calls/{{call_id}}")
def get_qa_call_detail(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = text("""
        SELECT
            c.call_id,
            c.original_filename,
            c.drive_file_id,
            c.call_time,
            c.duration_seconds,
            c.status,
            e.full_name AS agent_name,
            t.full_text,
            t.speaker_turns,
            qr.overall_score,
            qr.grade,
            qr.severity,
            qr.dimension_scores,
            qr.dimension_reports,
            qr.evidence,
            qr.confidence_scores,
            qr.report_json
        FROM calls c
        JOIN employees e ON c.employee_id = e.employee_id
        LEFT JOIN transcripts t ON c.call_id = t.call_id
        LEFT JOIN qa_reports qr ON c.call_id = qr.call_id
        WHERE c.call_id = :call_id
    """)

    row = db.execute(query, {"call_id": call_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    drive_file_id = row["drive_file_id"]
    drive_preview_url = (
        f"https://drive.google.com/file/d/{drive_file_id}/preview"
        if drive_file_id else None
    )
    drive_download_url = (
        f"https://drive.google.com/uc?export=download&id={drive_file_id}"
        if drive_file_id else None
    )

    return {
        "callId": str(row["call_id"]),
        "filename": row["original_filename"],
        "driveFileId": drive_file_id,
        "drivePreviewUrl": drive_preview_url,
        "driveDownloadUrl": drive_download_url,
        "callTime": row["call_time"].isoformat() if row["call_time"] else None,
        "durationSeconds": float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
        "status": row["status"],
        "agentName": row["agent_name"],
        "transcript": {
            "fullText": row["full_text"],
            "speakerTurns": row["speaker_turns"] or [],
        },
        "report": {
            "overallScore": float(row["overall_score"]) if row["overall_score"] is not None else None,
            "grade": row["grade"],
            "severity": row["severity"],
            "dimensionScores": row["dimension_scores"] or {},
            "dimensionReports": row["dimension_reports"] or {},
            "evidence": row["evidence"] or [],
            "confidenceScores": row["confidence_scores"] or {},
            "reportJson": row["report_json"] or {},
        },
    }


@app.post(f"{settings.API_V1_PREFIX}/auth/logout")
def logout():
    return {"message": "Logged out successfully"}