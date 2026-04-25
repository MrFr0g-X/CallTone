"""Seed the database with roles, users, clients, and mock call data.

Demo user passwords are intentionally not embedded as source constants. Tests
opt into deterministic values via environment variables; real deployments must
provide seed passwords explicitly or receive random one-time hashes.
"""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import SessionLocal, Base, engine, settings
from app.models import (
    Client, Role, User, Employee, Customer, Call, Transcript, QaReport,
    _compute_grade,
)
from app.security import hash_password


def _seed_credentials(email_env: str, password_env: str) -> tuple[str, str] | None:
    """Return env-provided seed credentials, or None when not configured.

    This prevents production from silently creating unknown privileged users.
    Tests set these env vars explicitly in conftest.py.
    """
    email = os.getenv(email_env)
    password = os.getenv(password_env)
    if email and password:
        return email.strip().lower(), password
    return None


ROLES = [
    {"name": "owner", "display_name": "Owner"},
    {"name": "super_admin", "display_name": "Super Admin"},
    {"name": "admin", "display_name": "Admin"},
    {"name": "manager", "display_name": "Manager"},
    {"name": "viewer", "display_name": "Viewer"},
    {"name": "qa", "display_name": "QA"},
    {"name": "agent", "display_name": "Agent"},
]

CLIENTS = [
    {"name": "BankServ Global", "industry": "Finance", "status": "active", "plan": "enterprise"},
    {"name": "MetroBoost Telecom", "industry": "Telecom", "status": "active", "plan": "professional"},
]

USERS = [
    {
        "full_name": "Sarah Chen",
        "email_env": "CALLTONE_SEED_SUPER_ADMIN_EMAIL",
        "password_env": "CALLTONE_SEED_SUPER_ADMIN_PASSWORD",
        "role": "super_admin",
        "client_name": None,
    },
    {
        "full_name": "Maya QA",
        "email_env": "CALLTONE_SEED_QA_EMAIL",
        "password_env": "CALLTONE_SEED_QA_PASSWORD",
        "role": "qa",
        "client_name": "BankServ Global",
    },
    {
        "full_name": "Agent One",
        "email_env": "CALLTONE_SEED_AGENT1_EMAIL",
        "password_env": "CALLTONE_SEED_AGENT1_PASSWORD",
        "role": "agent",
        "client_name": "BankServ Global",
    },
    {
        "full_name": "Agent Two",
        "email_env": "CALLTONE_SEED_AGENT2_EMAIL",
        "password_env": "CALLTONE_SEED_AGENT2_PASSWORD",
        "role": "agent",
        "client_name": "BankServ Global",
    },
]

DRIVE_LINKS = {
    "G201-1.wav": "1A0jVNyNHpEkNdI38kUB04_q1k3RSAXoO",
    "G201-2.wav": "1vTozsSR-PD4jP_p8BR0GtTDzmUPg9FfZ",
}


MOCK_REPORTS = [
    {
        "overall_score": 80.0,
        "severity": "Moderate",
        "dimension_scores": {
            "script_compliance": 75,
            "factual_accuracy": 82,
            "politeness_tone": 88,
            "empathy": 74,
            "conflict_detection": 79,
            "issue_resolution": 76,
            "overall_severity": 81,
        },
        "dimension_reports": {
            "script_compliance": "The agent followed the greeting script but missed the required verification steps.",
            "factual_accuracy": "Product information was mostly accurate with minor gaps on promotion details.",
            "politeness_tone": "Maintained a professional and courteous tone throughout the call.",
            "empathy": "Some empathy cues present but could acknowledge customer frustration more directly.",
            "conflict_detection": "Minor tension was addressed but escalation cues were partially missed.",
            "issue_resolution": "The issue was partially resolved; follow-up was promised but not confirmed.",
            "overall_severity": "Moderate issues detected — coaching recommended on verification and empathy.",
        },
        "confidence_scores": {
            "script_compliance": 0.82,
            "factual_accuracy": 0.87,
            "politeness_tone": 0.91,
            "empathy": 0.71,
            "conflict_detection": 0.77,
            "issue_resolution": 0.73,
            "overall_severity": 0.84,
        },
        "report_json": {
            "summary": "This call shows moderate quality with strong politeness but gaps in empathy and script compliance. The agent maintained professionalism but missed verification steps and could improve acknowledgment of customer concerns.",
            "strengths": [
                "Professional and courteous tone maintained throughout",
                "Accurate product information provided",
                "Stable conversation flow with clear communication",
            ],
            "weaknesses": [
                "Missed required verification steps in the greeting",
                "Limited empathy signals when customer expressed frustration",
                "No formal closing statement or follow-up confirmation",
            ],
            "recommended_actions": [
                "Review the mandatory verification checklist before each call",
                "Practice empathy phrases: acknowledge feelings before solving",
                "Use the standard closing script with follow-up confirmation",
            ],
        },
    },
    {
        "overall_score": 62.0,
        "severity": "Major",
        "dimension_scores": {
            "script_compliance": 50,
            "factual_accuracy": 68,
            "politeness_tone": 72,
            "empathy": 55,
            "conflict_detection": 60,
            "issue_resolution": 58,
            "overall_severity": 65,
        },
        "dimension_reports": {
            "script_compliance": "Greeting was informal and did not follow the company script. Closing was abrupt.",
            "factual_accuracy": "Agent provided mostly correct info but gave wrong promotion end date.",
            "politeness_tone": "Generally polite but tone became dismissive when customer repeated their question.",
            "empathy": "Minimal acknowledgment of customer frustration. Focused only on resolution steps.",
            "conflict_detection": "Customer showed clear signs of escalation that were not addressed.",
            "issue_resolution": "Issue was not fully resolved. Customer was told to call back.",
            "overall_severity": "Major issues — this call should be reviewed by a supervisor.",
        },
        "confidence_scores": {
            "script_compliance": 0.88,
            "factual_accuracy": 0.79,
            "politeness_tone": 0.83,
            "empathy": 0.75,
            "conflict_detection": 0.81,
            "issue_resolution": 0.72,
            "overall_severity": 0.86,
        },
        "report_json": {
            "summary": "Below-average call quality. The agent failed to follow scripted procedures, provided inaccurate promotion details, and did not adequately address the customer's escalation signals. Immediate coaching required.",
            "strengths": [
                "Basic politeness maintained for most of the call",
                "Attempted to provide troubleshooting steps",
            ],
            "weaknesses": [
                "Did not follow greeting or closing scripts",
                "Provided incorrect promotion expiry date",
                "Dismissed customer escalation signals",
                "Failed to resolve the issue — told customer to call back",
            ],
            "recommended_actions": [
                "Mandatory script compliance refresher training",
                "Review current promotions fact sheet before shifts",
                "Escalation handling workshop — recognize and de-escalate",
                "Shadow a senior agent for 3 calls to observe resolution techniques",
            ],
        },
    },
    {
        "overall_score": 93.0,
        "severity": "Minor",
        "dimension_scores": {
            "script_compliance": 95,
            "factual_accuracy": 92,
            "politeness_tone": 96,
            "empathy": 90,
            "conflict_detection": 88,
            "issue_resolution": 94,
            "overall_severity": 93,
        },
        "dimension_reports": {
            "script_compliance": "Excellent adherence to greeting, verification, and closing scripts.",
            "factual_accuracy": "All product and policy information was accurate and up to date.",
            "politeness_tone": "Warm, professional tone with appropriate pacing and active listening cues.",
            "empathy": "Strong empathy demonstrated — acknowledged feelings before offering solutions.",
            "conflict_detection": "No significant conflict, but agent proactively checked for satisfaction.",
            "issue_resolution": "Issue fully resolved in the call. Follow-up email confirmed.",
            "overall_severity": "Minor — exemplary call, suitable for training material.",
        },
        "confidence_scores": {
            "script_compliance": 0.95,
            "factual_accuracy": 0.93,
            "politeness_tone": 0.97,
            "empathy": 0.89,
            "conflict_detection": 0.85,
            "issue_resolution": 0.94,
            "overall_severity": 0.92,
        },
        "report_json": {
            "summary": "Excellent call quality across all dimensions. The agent demonstrated strong script compliance, accurate information delivery, genuine empathy, and effective resolution. This call can be used as a positive training example.",
            "strengths": [
                "Perfect script compliance with natural delivery",
                "Accurate and confident product knowledge",
                "Genuine empathy with active listening signals",
                "Complete issue resolution with follow-up confirmation",
            ],
            "weaknesses": [
                "Slightly long hold time during system lookup (minor)",
            ],
            "recommended_actions": [
                "Use this call as a training example for new agents",
                "Consider this agent for mentor/buddy program",
            ],
        },
    },
]


def parse_transcript(file_path: Path):
    """Parse a transcript .txt file into speaker_turns and full_text."""
    speaker_turns = []
    full_text_parts = []

    pattern = re.compile(
        r"^\[(?P<start>\d+(?:\.\d+)?),(?P<end>\d+(?:\.\d+)?)\]\t"
        r"(?P<speaker>[^\t]+)\t(?P<profile>[^\t]+)\t(?P<text>.*)$"
    )

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if not m:
                continue
            text = m.group("text").strip()
            turn = {
                "start": float(m.group("start")),
                "end": float(m.group("end")),
                "speaker": m.group("speaker").strip(),
                "profile": m.group("profile").strip(),
                "text": text,
            }
            speaker_turns.append(turn)
            if text and text not in {"[*]", ""}:
                full_text_parts.append(text)

    return " ".join(full_text_parts), speaker_turns


def main():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # ── Roles ──
        for role_data in ROLES:
            if not db.query(Role).filter(Role.name == role_data["name"]).first():
                db.add(Role(**role_data))
        db.commit()

        # ── Clients ──
        for client_data in CLIENTS:
            if not db.query(Client).filter(Client.name == client_data["name"]).first():
                db.add(Client(**client_data))
        db.commit()

        # ── Users ──
        seeded_agent_emails = {}
        for user_data in USERS:
            credentials = _seed_credentials(user_data["email_env"], user_data["password_env"])
            if not credentials:
                continue

            email, password = credentials
            seeded_agent_emails[user_data["password_env"]] = email

            if db.query(User).filter(User.email == email).first():
                continue

            role = db.query(Role).filter(Role.name == user_data["role"]).first()
            client = None
            if user_data["client_name"]:
                client = db.query(Client).filter(Client.name == user_data["client_name"]).first()

            db.add(
                User(
                    full_name=user_data["full_name"],
                    email=email,
                    password_hash=hash_password(password),
                    role_id=role.id,
                    client_id=client.id if client else None,
                    is_active=True,
                )
            )
        db.commit()

        # ── QA domain: employees, customers, calls, transcripts, reports ──
        if db.query(Employee).count() > 0:
            print("QA data already seeded — skipping.")
        else:
            _seed_qa_data(db, seeded_agent_emails)

        print("Seed completed successfully.")

    finally:
        db.close()


def _seed_qa_data(db, seeded_agent_emails=None):
    seeded_agent_emails = seeded_agent_emails or {}
    # Create QA employee
    qa_emp = Employee(
        id=str(uuid.uuid4()),
        employee_code="QA001",
        full_name="Maya QA",
        role="QA",
    )
    db.add(qa_emp)
    db.flush()

    # Create agents — link to their User records via user_id
    agents = []
    agent_user_emails = [
        seeded_agent_emails.get("CALLTONE_SEED_AGENT1_PASSWORD"),
        seeded_agent_emails.get("CALLTONE_SEED_AGENT2_PASSWORD"),
        None,
    ]
    agent_names = ["Agent One", "Agent Two", "Rania Mahmoud"]
    for i, (name, email) in enumerate(zip(agent_names, agent_user_emails), start=1):
        user_id = None
        if email:
            u = db.query(User).filter(User.email == email).first()
            user_id = u.id if u else None
        agent = Employee(
            id=str(uuid.uuid4()),
            employee_code=f"AG{i:03d}",
            full_name=name,
            role="AGENT",
            assigned_qa_id=qa_emp.id,
            user_id=user_id,
        )
        db.add(agent)
        agents.append(agent)
    db.flush()

    # Create customer
    customer = Customer(
        id=str(uuid.uuid4()),
        external_customer_ref="customer-001",
        display_name="Sample Customer",
        phone_hash="hash_placeholder",
    )
    db.add(customer)
    db.flush()

    # Load transcript files
    data_dir = Path(__file__).resolve().parent.parent / "data" / "TXT"
    txt_files = sorted(data_dir.glob("*.txt")) if data_dir.exists() else []

    if not txt_files:
        print("  No transcript files found in backend/data/TXT/ — creating minimal mock data.")
        txt_files = []

    base_time = datetime(2026, 3, 15, 9, 0, 0, tzinfo=timezone.utc)

    for i, txt_file in enumerate(txt_files):
        agent = agents[i % len(agents)]
        report_template = MOCK_REPORTS[i % len(MOCK_REPORTS)]
        wav_name = txt_file.stem + ".wav"
        drive_id = DRIVE_LINKS.get(wav_name)

        full_text, speaker_turns = parse_transcript(txt_file)
        duration = speaker_turns[-1]["end"] if speaker_turns else 30.0

        call_id = str(uuid.uuid4())
        call_time = base_time + timedelta(hours=i * 3, minutes=i * 17)

        call = Call(
            id=call_id,
            customer_id=customer.id,
            employee_id=agent.id,
            drive_file_id=drive_id,
            original_filename=wav_name,
            duration_seconds=round(duration, 3),
            status="COMPLETED",
            current_step="qa_report_generated",
            call_time=call_time,
        )
        db.add(call)

        transcript = Transcript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            full_text=full_text,
            speaker_turns=speaker_turns,
            asr_engine="SenseVoice",
            asr_model="SenseVoiceSmall",
            avg_confidence=0.91,
            wer=0.054,
            diarization_engine="pyannote-3.0",
            der=0.041,
        )
        db.add(transcript)

        # Build evidence from actual transcript
        evidence = []
        for turn in speaker_turns[:5]:
            if turn["text"] and turn["text"] not in {"[*]", ""}:
                evidence.append({
                    "dimension": "general",
                    "quote": turn["text"],
                    "speaker": f"Speaker {turn['speaker']}",
                    "reason": "Evidence extracted from call transcript.",
                })

        overall = report_template["overall_score"] + (i % 5) * 2 - 4
        overall = max(0, min(100, overall))

        report = QaReport(
            id=str(uuid.uuid4()),
            call_id=call_id,
            qa_id=qa_emp.id,
            overall_score=overall,
            grade=_compute_grade(overall),
            severity=report_template["severity"],
            dimension_scores=report_template["dimension_scores"],
            dimension_reports=report_template["dimension_reports"],
            evidence=evidence if evidence else report_template.get("evidence", []),
            confidence_scores=report_template["confidence_scores"],
            report_json=report_template["report_json"],
        )
        db.add(report)

    db.commit()
    print(f"  Seeded {len(txt_files)} calls with transcripts and QA reports.")


if __name__ == "__main__":
    main()
