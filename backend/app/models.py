import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base, settings

if settings.use_sqlite:
    from sqlalchemy import JSON as JsonType
else:
    from sqlalchemy.dialects.postgresql import JSONB as JsonType


def _uuid_str():
    return str(uuid.uuid4())


# ── Auth / Admin domain ──────────────────────────────────────────────

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    is_system = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="role")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, unique=True)
    industry = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    plan = Column(String(50), nullable=False, default="trial")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="client")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    invite_token = Column(String(255), nullable=True, unique=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="users")
    client = relationship("Client", back_populates="users")


# ── QA / Call domain ─────────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    employee_code = Column(String(50), unique=True, nullable=True)
    full_name = Column(String(150), nullable=False)
    role = Column(String(20), nullable=False)  # AGENT, QA, BOTH
    assigned_qa_id = Column(String(36), ForeignKey("employees.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    calls = relationship("Call", back_populates="employee")
    user = relationship("User", foreign_keys=[user_id])


class PipelineSettings(Base):
    """Singleton table — always one row (id=1). Stores admin-controlled pipeline config."""
    __tablename__ = "pipeline_settings"

    id = Column(Integer, primary_key=True, default=1)
    audio_mode = Column(String(20), nullable=False, default="denoise")    # none | denoise | enhance
    injection_scan = Column(String(20), nullable=False, default="static") # static | llm
    num_speakers = Column(Integer, nullable=True)                          # None = auto-detect
    report_mode = Column(String(20), nullable=False, default="narrative") # none | simple | narrative | both
    use_consensus = Column(Boolean, nullable=False, default=False)
    company_name = Column(String(150), nullable=False, default="metroboost")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    external_customer_ref = Column(String(100), nullable=True)
    display_name = Column(String(150), nullable=True)
    phone_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Call(Base):
    __tablename__ = "calls"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    drive_file_id = Column(String(255), nullable=True)
    drive_folder_id = Column(String(255), nullable=True)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sample_rate_hz = Column(Integer, nullable=True)
    channels = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="COMPLETED")
    current_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    call_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="calls")
    transcript = relationship("Transcript", back_populates="call", uselist=False)
    qa_report = relationship("QaReport", back_populates="call", uselist=False)


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    call_id = Column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_text = Column(Text, nullable=False)
    speaker_turns = Column(JsonType, nullable=True)
    asr_engine = Column(String(100), nullable=True)
    asr_model = Column(String(100), nullable=True)
    avg_confidence = Column(Float, nullable=True)
    wer = Column(Float, nullable=True)
    diarization_engine = Column(String(100), nullable=True)
    der = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    call = relationship("Call", back_populates="transcript")


def _compute_grade(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 86: return "A-"
    if score >= 82: return "B+"
    if score >= 78: return "B"
    if score >= 74: return "B-"
    if score >= 70: return "C+"
    if score >= 66: return "C"
    if score >= 60: return "C-"
    return "F"


class QaReport(Base):
    __tablename__ = "qa_reports"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    call_id = Column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False)
    qa_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    overall_score = Column(Float, nullable=False)
    grade = Column(String(5), nullable=True)
    severity = Column(String(20), nullable=False)
    dimension_scores = Column(JsonType, nullable=False)
    dimension_reports = Column(JsonType, nullable=True)
    evidence = Column(JsonType, nullable=True)
    confidence_scores = Column(JsonType, nullable=True)
    report_json = Column(JsonType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    call = relationship("Call", back_populates="qa_report")
