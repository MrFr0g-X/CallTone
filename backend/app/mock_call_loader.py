import re
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


DB_CONFIG = {
    "host": os.getenv("CALLTONE_DB_HOST", "localhost"),
    "port": int(os.getenv("CALLTONE_DB_PORT", "5432")),
    "dbname": os.getenv("CALLTONE_DB_NAME", "calltone_db"),
    "user": os.getenv("CALLTONE_DB_USER", "postgres"),
    "password": os.getenv("CALLTONE_DB_PASSWORD", ""),
}

TRANSCRIPT_FILE = os.getenv(
    "CALLTONE_MOCK_TRANSCRIPT_FILE",
    str(Path(__file__).resolve().parent.parent / "data" / "TXT" / "G201-1.txt"),
)
GOOGLE_DRIVE_LINK = os.getenv(
    "CALLTONE_MOCK_DRIVE_LINK",
    "https://drive.google.com/file/d/1A0jVNyNHpEkNdI38kUB04_q1k3RSAXoO/view?usp=sharing",
)
ORIGINAL_FILENAME = "G201-1.wav"
CALL_TIME = datetime.now(timezone.utc)


def extract_drive_file_id(link: str) -> str:
    match = re.search(r"/file/d/([^/]+)/", link)
    if not match:
        raise ValueError("Could not extract Google Drive file ID from link.")
    return match.group(1)


def parse_transcript_file(file_path: str):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {file_path}")

    speaker_turns = []
    full_text_parts = []

    pattern = re.compile(
        r"^\[(?P<start>\d+(?:\.\d+)?),(?P<end>\d+(?:\.\d+)?)\]\t(?P<speaker>[^\t]+)\t(?P<profile>[^\t]+)\t(?P<text>.*)$"
    )

    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            match = pattern.match(line)
            if not match:
                print(f"Skipping malformed line: {line}")
                continue

            text = match.group("text").strip()

            turn = {
                "start": float(match.group("start")),
                "end": float(match.group("end")),
                "speaker": match.group("speaker").strip(),
                "profile": match.group("profile").strip(),
                "text": text,
            }
            speaker_turns.append(turn)

            if text and text not in {"[*]", ""}:
                full_text_parts.append(text)

    full_text = " ".join(full_text_parts)
    return full_text, speaker_turns


def get_or_create_customer(cur):
    cur.execute("""
        SELECT customer_id
        FROM customers
        WHERE external_customer_ref = %s
        LIMIT 1
    """, ("mock-customer-001",))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO customers (external_customer_ref, display_name, phone_hash)
        VALUES (%s, %s, %s)
        RETURNING customer_id
    """, ("mock-customer-001", "Mock Customer 001", "mock_phone_hash_001"))
    return cur.fetchone()[0]


def get_or_create_qa(cur):
    cur.execute("""
        SELECT employee_id
        FROM employees
        WHERE employee_code = %s
        LIMIT 1
    """, ("QA001",))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO employees (employee_code, full_name, role)
        VALUES (%s, %s, 'QA')
        RETURNING employee_id
    """, ("QA001", "Maya QA"))
    return cur.fetchone()[0]


def get_or_create_agent(cur, qa_id):
    cur.execute("""
        SELECT employee_id
        FROM employees
        WHERE employee_code = %s
        LIMIT 1
    """, ("AG001",))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO employees (employee_code, full_name, role, assigned_qa_id)
        VALUES (%s, %s, 'AGENT', %s)
        RETURNING employee_id
    """, ("AG001", "Agent One", qa_id))
    return cur.fetchone()[0]


def build_mock_report(speaker_turns):
    dimension_scores = {
        "greeting": 82,
        "professionalism": 88,
        "empathy": 74,
        "active_listening": 79,
        "clarity": 84,
        "resolution": 76,
        "closing": 81
    }

    dimension_reports = {
        "greeting": "The opening was acceptable but not strongly structured.",
        "professionalism": "The speaker maintained a mostly professional tone.",
        "empathy": "Empathy appeared occasionally, but not strongly throughout the interaction.",
        "active_listening": "Some listening cues were present, but deeper acknowledgment was limited.",
        "clarity": "The content was understandable and mostly clear.",
        "resolution": "The interaction progressed but did not show a strong resolution close.",
        "closing": "The ending lacked a formal closing pattern."
    }

    evidence = []
    for turn in speaker_turns[:4]:
        if turn["text"] and turn["text"] != "[*]":
            evidence.append({
                "dimension": "general",
                "quote": turn["text"],
                "speaker": turn["speaker"],
                "reason": "Sample mock evidence from transcript."
            })

    confidence_scores = {
        "greeting": 0.82,
        "professionalism": 0.87,
        "empathy": 0.71,
        "active_listening": 0.77,
        "clarity": 0.89,
        "resolution": 0.73,
        "closing": 0.68
    }

    report_json = {
        "summary": "This mock report shows moderate call quality with good professionalism and clarity, but only average empathy and resolution handling.",
        "strengths": [
            "Clear phrases",
            "Mostly professional tone",
            "Stable conversation flow"
        ],
        "weaknesses": [
            "Weak structured greeting",
            "Limited empathy signals",
            "Closing not formal enough"
        ],
        "recommended_actions": [
            "Use a stronger opening greeting",
            "Acknowledge feelings more explicitly",
            "Use a structured closing statement"
        ]
    }

    return {
        "overall_score": Decimal("80.00"),
        "severity": "Moderate",
        "dimension_scores": dimension_scores,
        "dimension_reports": dimension_reports,
        "evidence": evidence,
        "confidence_scores": confidence_scores,
        "report_json": report_json,
    }


def insert_mock_call():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "CALLTONE_DB_PASSWORD is required for mock_call_loader.py; "
            "do not hardcode database credentials in source."
        )

    drive_file_id = extract_drive_file_id(GOOGLE_DRIVE_LINK)
    full_text, speaker_turns = parse_transcript_file(TRANSCRIPT_FILE)
    mock_report = build_mock_report(speaker_turns)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            qa_id = get_or_create_qa(cur)
            agent_id = get_or_create_agent(cur, qa_id)
            customer_id = get_or_create_customer(cur)

            cur.execute("""
                INSERT INTO calls (
                    customer_id,
                    employee_id,
                    drive_file_id,
                    drive_folder_id,
                    original_filename,
                    duration_seconds,
                    size_bytes,
                    sample_rate_hz,
                    channels,
                    sha256,
                    status,
                    current_step,
                    error_message,
                    call_time
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'COMPLETED', %s, %s, %s
                )
                RETURNING call_id
            """, (
                customer_id,
                agent_id,
                drive_file_id,
                None,
                ORIGINAL_FILENAME,
                Decimal("13.101"),
                1024000,
                16000,
                1,
                "mock_sha256_call_001",
                "qa_report_generated",
                None,
                CALL_TIME,
            ))
            call_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO transcripts (
                    call_id,
                    full_text,
                    speaker_turns,
                    asr_engine,
                    asr_model,
                    avg_confidence,
                    wer,
                    diarization_engine,
                    der
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                call_id,
                full_text,
                Json(speaker_turns),
                "mock_asr_engine",
                "mock_asr_model_v1",
                Decimal("0.9123"),
                Decimal("0.05432"),
                "mock_diarization_engine",
                Decimal("0.04120"),
            ))

            cur.execute("""
                INSERT INTO qa_reports (
                    call_id,
                    qa_id,
                    overall_score,
                    severity,
                    dimension_scores,
                    dimension_reports,
                    evidence,
                    confidence_scores,
                    report_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_id
            """, (
                call_id,
                qa_id,
                mock_report["overall_score"],
                mock_report["severity"],
                Json(mock_report["dimension_scores"]),
                Json(mock_report["dimension_reports"]),
                Json(mock_report["evidence"]),
                Json(mock_report["confidence_scores"]),
                Json(mock_report["report_json"]),
            ))
            report_id = cur.fetchone()[0]

        conn.commit()
        print("Mock call inserted successfully.")
        print("Call ID:", call_id)
        print("Report ID:", report_id)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


if __name__ == "__main__":
    insert_mock_call()
