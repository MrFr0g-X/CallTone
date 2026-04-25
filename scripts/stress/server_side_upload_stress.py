#!/usr/bin/env python3
"""Server-side CallTone upload stress runner.

Run this on the Hetzner backend host so the audio fixture is read from local
disk and uploaded to the API over loopback. This avoids wasting local user
uplink and makes upload timings reflect backend ingestion rather than home
internet bandwidth.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def login(api_base: str, email: str, password: str) -> str:
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{api_base}/auth/login",
            json={"email": email, "password": password},
        )
        response.raise_for_status()
        return response.json()["access_token"]


def get_json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:2000]


def upload_and_poll(
    *,
    worker_id: int,
    api_base: str,
    token: str,
    audio_path: Path,
    company: str,
    asr_engine: str,
    max_wait: float,
    poll_interval: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    started = time.time()
    result: dict[str, Any] = {
        "worker_id": worker_id,
        "started_at": utc_now(),
        "call_id": None,
        "upload": {},
        "polls": [],
        "terminal_status": None,
        "detail_summary": None,
    }

    with httpx.Client(timeout=None) as client:
        upload_started = time.time()
        with audio_path.open("rb") as fh:
            response = client.post(
                f"{api_base}/calls/upload",
                headers=headers,
                files={"file": (audio_path.name, fh, "audio/wav")},
                data={
                    "company_name": company,
                    "asr_engine": asr_engine,
                    "agent_id": "",
                },
            )
        upload_body = get_json_or_text(response)
        result["upload"] = {
            "http_status": response.status_code,
            "ok": response.is_success,
            "elapsed_seconds": round(time.time() - upload_started, 3),
            "body": upload_body,
        }
        if not response.is_success:
            result["terminal_status"] = "UPLOAD_FAILED"
            result["finished_at"] = utc_now()
            result["total_elapsed_seconds"] = round(time.time() - started, 3)
            return result

        call_id = upload_body.get("callId") if isinstance(upload_body, dict) else None
        result["call_id"] = call_id
        if not call_id:
            result["terminal_status"] = "NO_CALL_ID"
            result["finished_at"] = utc_now()
            result["total_elapsed_seconds"] = round(time.time() - started, 3)
            return result

        deadline = time.time() + max_wait
        while time.time() < deadline:
            status_response = client.get(f"{api_base}/calls/{call_id}/status", headers=headers, timeout=30)
            status_body = get_json_or_text(status_response)
            status = status_body.get("status") if isinstance(status_body, dict) else None
            result["polls"].append(
                {
                    "ts": utc_now(),
                    "http_status": status_response.status_code,
                    "ok": status_response.is_success,
                    "status": status,
                    "current_step": status_body.get("currentStep") if isinstance(status_body, dict) else None,
                    "body": status_body,
                }
            )
            if status in {"COMPLETED", "FAILED"}:
                result["terminal_status"] = status
                break
            time.sleep(poll_interval)

        if result["terminal_status"] is None:
            result["terminal_status"] = "POLL_TIMEOUT"

        if result["terminal_status"] == "COMPLETED":
            detail_response = client.get(f"{api_base}/qa/calls/{call_id}", headers=headers, timeout=60)
            detail = get_json_or_text(detail_response)
            result["detail_summary"] = summarize_detail(detail) if isinstance(detail, dict) else None

    result["finished_at"] = utc_now()
    result["total_elapsed_seconds"] = round(time.time() - started, 3)
    return result


def summarize_detail(detail: dict[str, Any]) -> dict[str, Any]:
    report = detail.get("report") if isinstance(detail.get("report"), dict) else {}
    transcript = detail.get("transcript") if isinstance(detail.get("transcript"), dict) else {}
    dims = report.get("dimensionScores") or report.get("dimension_scores") or {}
    evidence = report.get("evidence") or []
    turns = transcript.get("speakerTurns") or transcript.get("speaker_turns") or []
    report_json = report.get("reportJson") or report.get("report_json") or {}
    return {
        "overall_score": report.get("overallScore") or report.get("overall_score"),
        "severity": report.get("severity"),
        "dimension_count": len(dims) if isinstance(dims, dict) else 0,
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "speaker_turn_count": len(turns) if isinstance(turns, list) else 0,
        "has_ai_report": bool(report_json),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--email", default="qa@calltone.ai")
    parser.add_argument(
        "--password",
        default=os.getenv("CALLTONE_STRESS_PASSWORD"),
        help="Login password. Prefer CALLTONE_STRESS_PASSWORD so it is not exposed in process args.",
    )
    parser.add_argument("--company", default="BankServ Global")
    parser.add_argument("--asr", default="fasterwhisper", choices=["fasterwhisper", "sensevoice"])
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--max-wait", type=float, default=1800)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument("--output-dir", default="/opt/calltone-backend/stress_runs")
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("missing password: pass --password or set CALLTONE_STRESS_PASSWORD")

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        raise SystemExit(f"audio fixture not found: {audio_path}")

    run_dir = Path(args.output_dir) / f"server_side_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    token = login(args.api_base, args.email, args.password)

    started = time.time()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(
                upload_and_poll,
                worker_id=i + 1,
                api_base=args.api_base,
                token=token,
                audio_path=audio_path,
                company=args.company,
                asr_engine=args.asr,
                max_wait=args.max_wait,
                poll_interval=args.poll_interval,
            )
            for i in range(args.concurrency)
        ]
        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            upload = item.get("upload") or {}
            print(
                f"worker={item.get('worker_id')} call={item.get('call_id')} "
                f"status={item.get('terminal_status')} upload_s={upload.get('elapsed_seconds')}",
                flush=True,
            )

    results.sort(key=lambda item: item.get("worker_id") or 0)
    counts: dict[str, int] = {}
    for item in results:
        status = str(item.get("terminal_status"))
        counts[status] = counts.get(status, 0) + 1

    summary = {
        "audio": str(audio_path),
        "audio_bytes": audio_path.stat().st_size,
        "concurrency": args.concurrency,
        "terminal_counts": counts,
        "elapsed_seconds": round(time.time() - started, 3),
        "completed_call_ids": [r.get("call_id") for r in results if r.get("terminal_status") == "COMPLETED"],
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"RUN_DIR={run_dir}", flush=True)
    return 0 if counts.get("COMPLETED", 0) == args.concurrency else 1


if __name__ == "__main__":
    raise SystemExit(main())
