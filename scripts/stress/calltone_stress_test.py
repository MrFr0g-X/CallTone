#!/usr/bin/env python3
"""
CallTone production stress test harness.

Runs concurrent uploads against the live backend and records:
  - upload response time and HTTP status
  - per-call status polling timeline
  - terminal result and QA detail summary when available
  - public API health snapshots
  - local client CPU/memory/network snapshots
  - optional raw GPU and Hetzner SSH resource snapshots
  - styled LaTeX/PDF report

Secrets are read from env/CLI but never written to evidence files.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT.parent
    / "ALL_DOCS"
    / "Imp & Testing Rpt 2"
    / "Final"
    / "stress-tests"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    out = dict(config)
    for key in ("password", "hetzner_password"):
        if key in out and out[key]:
            out[key] = "<redacted>"
    return out


@dataclass
class ResourceSampler:
    batch_dir: Path
    api_base: str
    interval: float
    gpu_ssh_target: str | None = None
    gpu_ssh_port: int | None = None
    gpu_ssh_key: str | None = None
    hetzner_host: str | None = None
    hetzner_password: str | None = None
    hetzner_hostkey: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="resource-sampler", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=max(5.0, self.interval + 2.0))

    def _append_jsonl(self, filename: str, payload: dict[str, Any]) -> None:
        path = self.batch_dir / filename
        with path.open("a", encoding="utf-8") as fh:
            fh.write(safe_json(payload) + "\n")

    def _run_cmd(self, args: list[str], timeout: float = 15.0) -> dict[str, Any]:
        started = time.time()
        try:
            proc = subprocess.run(
                args,
                text=True,
                capture_output=True,
                timeout=timeout,
                errors="replace",
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "elapsed_seconds": round(time.time() - started, 3),
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-4000:],
            }
        except Exception as exc:
            return {
                "ok": False,
                "returncode": None,
                "elapsed_seconds": round(time.time() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _sample_api_health(self) -> None:
        try:
            r = requests.get(f"{self.api_base}/health/detailed", timeout=10)
            body: Any
            try:
                body = r.json()
            except Exception:
                body = r.text[:1000]
            self._append_jsonl(
                "api_health.jsonl",
                {
                    "ts": utc_now(),
                    "http_status": r.status_code,
                    "ok": r.ok,
                    "body": body,
                },
            )
        except Exception as exc:
            self._append_jsonl(
                "api_health.jsonl",
                {"ts": utc_now(), "ok": False, "error": f"{type(exc).__name__}: {exc}"},
            )

    def _sample_local(self) -> None:
        net = psutil.net_io_counters()
        disk = psutil.disk_usage(str(REPO_ROOT.drive + "\\"))
        self._append_jsonl(
            "local_client_resources.jsonl",
            {
                "ts": utc_now(),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_used_mb": round(psutil.virtual_memory().used / 1024 / 1024, 1),
                "net_bytes_sent": net.bytes_sent,
                "net_bytes_recv": net.bytes_recv,
                "disk_free_gb": round(disk.free / 1024**3, 2),
            },
        )

    def _sample_gpu(self) -> None:
        if not (self.gpu_ssh_target and self.gpu_ssh_port and self.gpu_ssh_key):
            return
        remote = (
            "echo TS=$(date -Iseconds); "
            "nvidia-smi --query-gpu=timestamp,name,utilization.gpu,utilization.memory,"
            "memory.used,memory.total,power.draw,temperature.gpu "
            "--format=csv,noheader,nounits; "
            "echo MEM; free -m | awk '/Mem:/ {print $2,$3,$7}'; "
            "echo DISK; df -BG /root | tail -1; "
            "echo PROCS; ps -eo pid,pcpu,pmem,rss,etime,comm --sort=-pcpu | head -8"
        )
        args = [
            "ssh",
            "-i",
            self.gpu_ssh_key,
            "-p",
            str(self.gpu_ssh_port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            self.gpu_ssh_target,
            remote,
        ]
        self._append_jsonl("gpu_resources_raw.jsonl", {"ts": utc_now(), "sample": self._run_cmd(args)})

    def _sample_hetzner(self) -> None:
        if not (self.hetzner_host and self.hetzner_password and self.hetzner_hostkey):
            return
        plink = r"C:\Program Files\PuTTY\plink.exe"
        if not Path(plink).exists():
            return
        remote = (
            "echo TS=$(date -Iseconds); "
            "uptime; "
            "echo MEM; free -m | awk '/Mem:/ {print $2,$3,$7}'; "
            "echo DISK; df -BG / /opt | tail -n +2; "
            "echo CONN; ss -Htan state established | wc -l; "
            "echo SERVICES; systemctl is-active calltone-backend calltone-tunnel 2>/dev/null || true; "
            "echo PROCS; ps -eo pid,pcpu,pmem,rss,etime,comm --sort=-pcpu | head -8"
        )
        args = [
            plink,
            "-ssh",
            "-batch",
            "-pw",
            self.hetzner_password,
            "-hostkey",
            self.hetzner_hostkey,
            self.hetzner_host,
            remote,
        ]
        self._append_jsonl("hetzner_resources_raw.jsonl", {"ts": utc_now(), "sample": self._run_cmd(args)})

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self._sample_local()
            self._sample_api_health()
            self._sample_gpu()
            self._sample_hetzner()
            self.stop_event.wait(self.interval)


def login(api_base: str, email: str, password: str) -> tuple[str, dict[str, Any]]:
    r = requests.post(
        f"{api_base}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    token = body["access_token"]
    return token, body.get("user", {})


def get_json_or_text(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:2000]


def upload_and_poll(
    *,
    worker_id: int,
    api_base: str,
    token: str,
    audio_path: Path,
    company_name: str,
    asr_engine: str,
    poll_interval: float,
    max_wait_seconds: float,
    upload_timeout_seconds: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    result: dict[str, Any] = {
        "worker_id": worker_id,
        "started_at": utc_now(),
        "upload": {},
        "polls": [],
        "terminal_status": None,
        "call_id": None,
        "detail_summary": None,
        "error": None,
    }
    started = time.time()
    upload_started = time.time()

    try:
        with audio_path.open("rb") as fh:
            files = {"file": (audio_path.name, fh, "audio/wav")}
            data = {
                "company_name": company_name,
                "asr_engine": asr_engine,
                "agent_id": "",
            }
            resp = requests.post(
                f"{api_base}/calls/upload",
                headers=headers,
                files=files,
                data=data,
                timeout=upload_timeout_seconds,
            )
        upload_elapsed = time.time() - upload_started
        body = get_json_or_text(resp)
        result["upload"] = {
            "http_status": resp.status_code,
            "ok": resp.ok,
            "elapsed_seconds": round(upload_elapsed, 3),
            "body": body,
        }
        if not resp.ok:
            result["terminal_status"] = "UPLOAD_FAILED"
            result["finished_at"] = utc_now()
            result["total_elapsed_seconds"] = round(time.time() - started, 3)
            return result
        call_id = body.get("callId") if isinstance(body, dict) else None
        result["call_id"] = call_id
        if not call_id:
            result["terminal_status"] = "NO_CALL_ID"
            result["finished_at"] = utc_now()
            result["total_elapsed_seconds"] = round(time.time() - started, 3)
            return result
    except Exception as exc:
        result["terminal_status"] = "UPLOAD_EXCEPTION"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["finished_at"] = utc_now()
        result["total_elapsed_seconds"] = round(time.time() - started, 3)
        return result

    deadline = time.time() + max_wait_seconds
    terminal = {"COMPLETED", "FAILED"}
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_base}/calls/{result['call_id']}/status", headers=headers, timeout=30)
            body = get_json_or_text(r)
            status = body.get("status") if isinstance(body, dict) else None
            result["polls"].append(
                {
                    "ts": utc_now(),
                    "http_status": r.status_code,
                    "ok": r.ok,
                    "status": status,
                    "current_step": body.get("currentStep") if isinstance(body, dict) else None,
                    "body": body,
                }
            )
            if status in terminal:
                result["terminal_status"] = status
                break
        except Exception as exc:
            result["polls"].append(
                {"ts": utc_now(), "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            )
        time.sleep(poll_interval)

    if result["terminal_status"] is None:
        result["terminal_status"] = "POLL_TIMEOUT"

    if result["terminal_status"] == "COMPLETED":
        try:
            d = requests.get(f"{api_base}/qa/calls/{result['call_id']}", headers=headers, timeout=60)
            detail = get_json_or_text(d)
            result["detail_summary"] = summarize_call_detail(detail) if isinstance(detail, dict) else None
        except Exception as exc:
            result["detail_summary"] = {"error": f"{type(exc).__name__}: {exc}"}

    result["finished_at"] = utc_now()
    result["total_elapsed_seconds"] = round(time.time() - started, 3)
    return result


def summarize_call_detail(detail: dict[str, Any]) -> dict[str, Any]:
    report = detail.get("report") if isinstance(detail.get("report"), dict) else {}
    dims = (
        report.get("dimensionScores")
        or report.get("dimension_scores")
        or detail.get("dimensionScores")
        or detail.get("dimension_scores")
        or {}
    )
    evidence = report.get("evidence") or detail.get("evidence") or []
    transcript = detail.get("transcript") or {}
    report_json = report.get("reportJson") or report.get("report_json") or detail.get("reportJson") or detail.get("report_json") or {}
    turns = transcript.get("speakerTurns") or transcript.get("speaker_turns") or []
    return {
        "overall_score": report.get("overallScore") or report.get("overall_score") or detail.get("overallScore") or detail.get("overall_score"),
        "severity": report.get("severity") or detail.get("severity"),
        "dimension_count": len(dims) if isinstance(dims, dict) else 0,
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "speaker_turn_count": len(turns) if isinstance(turns, list) else 0,
        "has_ai_report": bool(report_json),
    }


def write_batch_results(batch_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    (batch_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    rows = []
    for item in results:
        upload = item.get("upload") or {}
        detail = item.get("detail_summary") or {}
        rows.append(
            {
                "worker_id": item.get("worker_id"),
                "call_id": item.get("call_id") or "",
                "upload_http_status": upload.get("http_status"),
                "upload_ok": upload.get("ok"),
                "upload_elapsed_seconds": upload.get("elapsed_seconds"),
                "terminal_status": item.get("terminal_status"),
                "total_elapsed_seconds": item.get("total_elapsed_seconds"),
                "overall_score": detail.get("overall_score"),
                "evidence_count": detail.get("evidence_count"),
                "speaker_turn_count": detail.get("speaker_turn_count"),
                "error": item.get("error") or "",
                "last_poll_error": _last_poll_error(item),
            }
        )
    with (batch_dir / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    upload_lat = [
        float((r.get("upload") or {}).get("elapsed_seconds"))
        for r in results
        if isinstance((r.get("upload") or {}).get("elapsed_seconds"), (int, float))
    ]
    total_lat = [
        float(r.get("total_elapsed_seconds"))
        for r in results
        if isinstance(r.get("total_elapsed_seconds"), (int, float))
    ]
    terminal_counts: dict[str, int] = {}
    for r in results:
        status = str(r.get("terminal_status"))
        terminal_counts[status] = terminal_counts.get(status, 0) + 1

    summary = {
        "concurrency": len(results),
        "terminal_counts": terminal_counts,
        "upload_latency_seconds": {
            "min": min(upload_lat) if upload_lat else None,
            "median": statistics.median(upload_lat) if upload_lat else None,
            "p95": percentile(upload_lat, 0.95),
            "max": max(upload_lat) if upload_lat else None,
        },
        "total_elapsed_seconds": {
            "min": min(total_lat) if total_lat else None,
            "median": statistics.median(total_lat) if total_lat else None,
            "p95": percentile(total_lat, 0.95),
            "max": max(total_lat) if total_lat else None,
        },
        "completed_call_ids": [r.get("call_id") for r in results if r.get("terminal_status") == "COMPLETED"],
        "failed_call_ids": [r.get("call_id") for r in results if r.get("terminal_status") == "FAILED"],
    }
    (batch_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _last_poll_error(item: dict[str, Any]) -> str:
    for poll in reversed(item.get("polls") or []):
        if poll.get("error"):
            return str(poll.get("error"))
        body = poll.get("body")
        if isinstance(body, dict) and body.get("error"):
            return str(body.get("error"))
        if isinstance(body, dict) and body.get("errorMessage"):
            return str(body.get("errorMessage"))
    return ""


def run_batch(args: argparse.Namespace, token: str, concurrency: int, run_dir: Path) -> dict[str, Any]:
    batch_dir = run_dir / f"batch_{concurrency:03d}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Batch {concurrency}: starting {concurrency} concurrent uploads ===", flush=True)

    sampler = ResourceSampler(
        batch_dir=batch_dir,
        api_base=args.api_base,
        interval=args.resource_interval,
        gpu_ssh_target=args.gpu_ssh_target,
        gpu_ssh_port=args.gpu_ssh_port,
        gpu_ssh_key=args.gpu_ssh_key,
        hetzner_host=args.hetzner_host,
        hetzner_password=args.hetzner_password,
        hetzner_hostkey=args.hetzner_hostkey,
    )
    sampler.start()
    batch_started = time.time()
    results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(
                    upload_and_poll,
                    worker_id=i + 1,
                    api_base=args.api_base,
                    token=token,
                    audio_path=Path(args.audio),
                    company_name=args.company,
                    asr_engine=args.asr,
                    poll_interval=args.poll_interval,
                    max_wait_seconds=args.max_wait,
                    upload_timeout_seconds=args.upload_timeout,
                )
                for i in range(concurrency)
            ]
            for future in as_completed(futures):
                item = future.result()
                results.append(item)
                print(
                    f"  worker={item.get('worker_id')} call={item.get('call_id')} "
                    f"status={item.get('terminal_status')} "
                    f"upload_s={(item.get('upload') or {}).get('elapsed_seconds')}",
                    flush=True,
                )
    finally:
        sampler.stop()

    summary = write_batch_results(batch_dir, sorted(results, key=lambda x: x.get("worker_id") or 0))
    summary["batch_elapsed_seconds"] = round(time.time() - batch_started, 3)
    (batch_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"=== Batch {concurrency}: {summary['terminal_counts']} ===", flush=True)
    return summary


def latex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def status_color(status: str) -> str:
    if status == "COMPLETED":
        return "green!70!black"
    if status == "FAILED":
        return "red!75!black"
    if status in {"UPLOAD_FAILED", "UPLOAD_EXCEPTION", "POLL_TIMEOUT"}:
        return "orange!85!black"
    return "gray!80!black"


def classify_failure(item: dict[str, Any]) -> str | None:
    status = str(item.get("terminal_status") or "")
    if status == "COMPLETED":
        return None
    if item.get("error"):
        error = str(item["error"])
        if error.startswith("SSLError"):
            return "Upload SSL EOF/reset"
        if "write operation timed out" in error:
            return "Upload write timeout"
        return error.split(":", 1)[0]
    poll_error = _last_poll_error(item)
    if "HTTP 409" in poll_error or "another job is in flight" in poll_error:
        return "Model server busy (HTTP 409)"
    if poll_error:
        return poll_error[:90]
    return status or "Unknown"


def failure_rows_for_report(run_dir: Path, summaries: dict[int, dict[str, Any]]) -> list[str]:
    rows = []
    for concurrency in summaries:
        batch_dir = run_dir / f"batch_{concurrency:03d}"
        results_path = batch_dir / "results.json"
        if not results_path.exists():
            continue
        results = json.loads(results_path.read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        for item in results:
            reason = classify_failure(item)
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
        if not counts:
            rows.append(f"{concurrency} & No failures & 0 " + r"\\")
            continue
        for reason, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            rows.append(f"{concurrency} & {latex_escape(reason)} & {count} " + r"\\")
    return rows


def resource_summary_for_batch(batch_dir: Path) -> dict[str, Any]:
    """Summarize raw resource JSONL into report-friendly peak metrics."""
    summary: dict[str, Any] = {}

    local_path = batch_dir / "local_client_resources.jsonl"
    if local_path.exists():
        samples = _read_jsonl(local_path)
        if samples:
            summary["local_cpu_max"] = max(_num(s.get("cpu_percent")) or 0 for s in samples)
            summary["local_mem_max_pct"] = max(_num(s.get("memory_percent")) or 0 for s in samples)
            summary["local_mem_max_mb"] = max(_num(s.get("memory_used_mb")) or 0 for s in samples)
            sent = [_num(s.get("net_bytes_sent")) for s in samples if _num(s.get("net_bytes_sent")) is not None]
            recv = [_num(s.get("net_bytes_recv")) for s in samples if _num(s.get("net_bytes_recv")) is not None]
            if len(sent) >= 2:
                summary["local_net_sent_gb"] = round((max(sent) - min(sent)) / 1024**3, 2)
            if len(recv) >= 2:
                summary["local_net_recv_gb"] = round((max(recv) - min(recv)) / 1024**3, 2)

    api_path = batch_dir / "api_health.jsonl"
    if api_path.exists():
        api_samples = _read_jsonl(api_path)
        disk_free = []
        ok_count = 0
        for item in api_samples:
            if item.get("ok"):
                ok_count += 1
            body = item.get("body") if isinstance(item.get("body"), dict) else {}
            disk = ((body.get("checks") or {}).get("disk") or {}) if isinstance(body, dict) else {}
            val = _num(disk.get("free_gb"))
            if val is not None:
                disk_free.append(val)
        summary["api_health_samples"] = len(api_samples)
        summary["api_health_ok"] = ok_count
        if disk_free:
            summary["backend_min_disk_free_gb"] = min(disk_free)

    gpu_path = batch_dir / "gpu_resources_raw.jsonl"
    if gpu_path.exists():
        gpu_samples = _read_jsonl(gpu_path)
        gpu_util: list[float] = []
        gpu_mem: list[float] = []
        gpu_power: list[float] = []
        gpu_temp: list[float] = []
        for item in gpu_samples:
            stdout = ((item.get("sample") or {}).get("stdout") or "") if isinstance(item.get("sample"), dict) else ""
            for line in stdout.splitlines():
                if "NVIDIA A100" not in line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 8:
                    continue
                util = _num(parts[2])
                mem_used = _num(parts[4])
                power = _num(parts[6])
                temp = _num(parts[7])
                if util is not None:
                    gpu_util.append(util)
                if mem_used is not None:
                    gpu_mem.append(mem_used)
                if power is not None:
                    gpu_power.append(power)
                if temp is not None:
                    gpu_temp.append(temp)
        if gpu_util:
            summary["gpu_util_max_pct"] = max(gpu_util)
        if gpu_mem:
            summary["gpu_mem_max_mib"] = max(gpu_mem)
        if gpu_power:
            summary["gpu_power_max_w"] = max(gpu_power)
        if gpu_temp:
            summary["gpu_temp_max_c"] = max(gpu_temp)

    hetzner_path = batch_dir / "hetzner_resources_raw.jsonl"
    if hetzner_path.exists():
        samples = _read_jsonl(hetzner_path)
        mem_used: list[float] = []
        conn_count: list[float] = []
        for item in samples:
            stdout = ((item.get("sample") or {}).get("stdout") or "") if isinstance(item.get("sample"), dict) else ""
            lines = stdout.splitlines()
            for i, line in enumerate(lines):
                if line == "MEM" and i + 1 < len(lines):
                    parts = lines[i + 1].split()
                    if len(parts) >= 2 and _num(parts[1]) is not None:
                        mem_used.append(_num(parts[1]) or 0)
                if line == "CONN" and i + 1 < len(lines) and _num(lines[i + 1]) is not None:
                    conn_count.append(_num(lines[i + 1]) or 0)
        if mem_used:
            summary["hetzner_mem_max_mb"] = max(mem_used)
        if conn_count:
            summary["hetzner_conn_max"] = max(conn_count)

    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None


def build_latex_report(run_dir: Path, config: dict[str, Any], summaries: dict[int, dict[str, Any]]) -> Path:
    rows = []
    for concurrency, summary in summaries.items():
        counts = summary.get("terminal_counts", {})
        upload = summary.get("upload_latency_seconds", {})
        total = summary.get("total_elapsed_seconds", {})
        rows.append(
            " & ".join(
                [
                    str(concurrency),
                    str(counts.get("COMPLETED", 0)),
                    str(counts.get("FAILED", 0)),
                    str(counts.get("UPLOAD_FAILED", 0) + counts.get("UPLOAD_EXCEPTION", 0)),
                    str(counts.get("POLL_TIMEOUT", 0)),
                    _fmt(upload.get("median")),
                    _fmt(upload.get("p95")),
                    _fmt(total.get("max")),
                    _fmt(summary.get("batch_elapsed_seconds")),
                ]
            )
            + r" \\"
        )

    resource_rows = []
    for concurrency in summaries:
        batch_dir = run_dir / f"batch_{concurrency:03d}"
        resources = resource_summary_for_batch(batch_dir)
        resource_rows.append(
            " & ".join(
                [
                    str(concurrency),
                    _fmt(resources.get("gpu_util_max_pct")),
                    _fmt(resources.get("gpu_mem_max_mib")),
                    _fmt(resources.get("gpu_power_max_w")),
                    _fmt(resources.get("local_mem_max_mb")),
                    _fmt(resources.get("local_net_sent_gb")),
                    _fmt(resources.get("backend_min_disk_free_gb")),
                    _fmt(resources.get("hetzner_mem_max_mb")),
                    _fmt(resources.get("hetzner_conn_max")),
                ]
            )
            + r" \\"
        )

    failure_rows = failure_rows_for_report(run_dir, summaries)

    detail_sections = []
    for concurrency in summaries:
        batch_dir = run_dir / f"batch_{concurrency:03d}"
        results = json.loads((batch_dir / "results.json").read_text(encoding="utf-8"))
        detail_rows = []
        for item in results[:60]:
            status = str(item.get("terminal_status"))
            upload = item.get("upload") or {}
            detail = item.get("detail_summary") or {}
            detail_rows.append(
                rf"\textcolor{{{status_color(status)}}}{{{latex_escape(status)}}} & "
                rf"{latex_escape(item.get('call_id') or '-')[:42]} & "
                rf"{latex_escape(upload.get('http_status'))} & "
                rf"{latex_escape(upload.get('elapsed_seconds'))} & "
                rf"{latex_escape(item.get('total_elapsed_seconds'))} & "
                rf"{latex_escape(detail.get('overall_score'))} & "
                rf"{latex_escape(detail.get('evidence_count'))} \\"
            )
        detail_sections.append(
            rf"""
\subsection*{{Batch {concurrency}}}
\begin{{longtable}}{{@{{}}p{{2.7cm}}p{{5.4cm}}rrrrr@{{}}}}
\toprule
Status & Call ID & HTTP & Upload s & Total s & Score & Evidence \\
\midrule
{chr(10).join(detail_rows)}
\bottomrule
\end{{longtable}}

Raw evidence folder: \texttt{{{latex_escape(str(batch_dir))}}}
"""
        )

    tex = rf"""
\documentclass[11pt]{{article}}
\usepackage[a4paper,margin=1.55cm]{{geometry}}
\usepackage{{booktabs,longtable,array,xcolor,hyperref,tcolorbox,enumitem}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\definecolor{{ctNavy}}{{HTML}}{{071426}}
\definecolor{{ctTeal}}{{HTML}}{{19D3C5}}
\definecolor{{ctGreen}}{{HTML}}{{2FBF71}}
\definecolor{{ctRed}}{{HTML}}{{E04F5F}}
\definecolor{{ctOrange}}{{HTML}}{{F59E0B}}
\hypersetup{{colorlinks=true,linkcolor=ctNavy,urlcolor=ctTeal}}
\pagestyle{{plain}}
\begin{{document}}
\begin{{center}}
{{\Huge\bfseries\color{{ctNavy}} CallTone Production Stress Test Report}}\\[3pt]
{{\large 5 / 10 / 20 / 50 concurrent uploads}}\\[6pt]
{{\small Generated {latex_escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S Africa/Cairo'))}}}
\end{{center}}

\begin{{tcolorbox}}[colback=ctNavy!4,colframe=ctTeal,title=Test Scope]
The same audio file was uploaded concurrently in four waves: 5, 10, 20, and 50.
The test targets the live three-tier CallTone deployment. It measures frontend/API upload acceptance,
backend status handling, model-server backpressure, and resource telemetry. Secrets and bearer tokens
are intentionally excluded from evidence files.
\end{{tcolorbox}}

\section*{{Configuration}}
\begin{{tabular}}{{@{{}}ll@{{}}}}
\toprule
API base & \texttt{{{latex_escape(config.get('api_base'))}}} \\
Audio file & \texttt{{{latex_escape(config.get('audio'))}}} \\
Audio bytes & {latex_escape(config.get('audio_bytes'))} \\
Company & {latex_escape(config.get('company'))} \\
ASR engine & {latex_escape(config.get('asr'))} \\
Batches & {latex_escape(config.get('batches'))} \\
Output folder & \texttt{{{latex_escape(str(run_dir))}}} \\
\bottomrule
\end{{tabular}}

\section*{{Executive Summary}}
\begin{{longtable}}{{@{{}}rrrrrrrrr@{{}}}}
\toprule
Concurrency & Completed & Failed & Upload errors & Timeouts & Median upload s & P95 upload s & Max total s & Batch s \\
\midrule
{chr(10).join(rows)}
\bottomrule
\end{{longtable}}

\begin{{tcolorbox}}[colback=ctOrange!8,colframe=ctOrange,title=Expected bottleneck]
The model server is intentionally single-slot: it accepts one GPU pipeline at a time and returns HTTP 409 when busy.
Therefore this stress test primarily evaluates upload pressure, backend memory behavior, failure clarity, and
backpressure behavior. A production queue would be required for true multi-call GPU throughput.
\end{{tcolorbox}}

\section*{{Resource Peak Summary}}
\begin{{longtable}}{{@{{}}rrrrrrrrr@{{}}}}
\toprule
Concurrency & GPU util \% & GPU MiB & GPU W & Client MB & Upload GB & Backend GB free & VPS MB & VPS conn \\
\midrule
{chr(10).join(resource_rows)}
\bottomrule
\end{{longtable}}

The raw JSONL files listed below remain the source of truth for every sample. This table only extracts the peak values needed for screenshot/report evidence.

\section*{{Failure Classification}}
\begin{{longtable}}{{@{{}}rlr@{{}}}}
\toprule
Concurrency & Failure class & Count \\
\midrule
{chr(10).join(failure_rows)}
\bottomrule
\end{{longtable}}

\section*{{Per-Call Results}}
{chr(10).join(detail_sections)}

\section*{{Resource Evidence Files}}
Each batch folder contains:
\begin{{itemize}}[nosep]
\item \texttt{{results.json}} and \texttt{{results.csv}}: per-call status and timing.
\item \texttt{{summary.json}}: aggregate counts and latency statistics.
\item \texttt{{api\_health.jsonl}}: public backend/model-server health snapshots.
\item \texttt{{local\_client\_resources.jsonl}}: client CPU, memory, disk, and network counters.
\item \texttt{{gpu\_resources\_raw.jsonl}}: raw A100 \texttt{{nvidia-smi}}, memory, disk, and top process snapshots when SSH was available.
\item \texttt{{hetzner\_resources\_raw.jsonl}}: raw VPS memory, disk, connection, service, and top process snapshots when SSH was available.
\end{{itemize}}

\section*{{Interpretation Rules}}
\begin{{itemize}}
\item A completed call must show terminal status \texttt{{COMPLETED}} and have non-empty QA detail if fetched.
\item A failed call is still useful evidence if the backend records a clear error instead of silently showing zero scores.
\item HTTP 409 from the model server means the GPU slot was busy. That is expected with the current one-job design.
\item Backend crashes, upload exceptions, or health failures are recorded as stress-test failures and must be treated as capacity limits.
\end{{itemize}}

\end{{document}}
"""
    tex_path = run_dir / "CallTone_Stress_Test_Report.tex"
    tex_path.write_text(tex, encoding="utf-8")
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=str(run_dir),
        text=True,
        capture_output=True,
        timeout=120,
    )
    return tex_path


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}"
    except Exception:
        return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CallTone concurrent upload stress test.")
    parser.add_argument("--api-base", default=os.getenv("CALLTONE_API_BASE", "https://api.calltone.tech/api"))
    parser.add_argument("--audio", default=os.getenv("CALLTONE_STRESS_AUDIO", r"C:\Users\Hothifa Hamdan\Downloads\test.wav"))
    parser.add_argument("--email", default=os.getenv("CALLTONE_STRESS_EMAIL", "qa@calltone.ai"))
    parser.add_argument("--password", default=os.getenv("CALLTONE_STRESS_PASSWORD"))
    parser.add_argument("--company", default=os.getenv("CALLTONE_STRESS_COMPANY", "BankServ Global"))
    parser.add_argument("--asr", choices=["fasterwhisper", "sensevoice"], default=os.getenv("CALLTONE_STRESS_ASR", "fasterwhisper"))
    parser.add_argument("--batches", default=os.getenv("CALLTONE_STRESS_BATCHES", "5,10,20,50"))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--max-wait", type=float, default=2400.0)
    parser.add_argument("--upload-timeout", type=float, default=1800.0)
    parser.add_argument("--resource-interval", type=float, default=10.0)
    parser.add_argument("--cooldown", type=float, default=20.0)
    parser.add_argument("--gpu-ssh-target", default=os.getenv("CALLTONE_GPU_SSH_TARGET", "root@185.65.93.114"))
    parser.add_argument("--gpu-ssh-port", type=int, default=int(os.getenv("CALLTONE_GPU_SSH_PORT", "47993")))
    parser.add_argument("--gpu-ssh-key", default=os.getenv("CALLTONE_GPU_SSH_KEY", str(REPO_ROOT / "deployment" / "ssh-keys" / "calltone_vast_ed25519")))
    parser.add_argument("--hetzner-host", default=os.getenv("CALLTONE_HETZNER_HOST", "root@91.99.208.254"))
    parser.add_argument("--hetzner-password", default=os.getenv("CALLTONE_HETZNER_PASSWORD"))
    parser.add_argument("--hetzner-hostkey", default=os.getenv("CALLTONE_HETZNER_HOSTKEY", "ssh-ed25519 255 SHA256:KZIzszCxuzskxUHaiRX9kpvCiPisAcqJzyl64YPORQA"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.password:
        print("ERROR: set CALLTONE_STRESS_PASSWORD or pass --password", file=sys.stderr)
        return 2
    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"ERROR: audio file not found: {audio_path}", file=sys.stderr)
        return 2

    batch_values = [int(x.strip()) for x in args.batches.split(",") if x.strip()]
    run_id = datetime.now().strftime("stress_%Y%m%d_%H%M%S")
    run_dir = Path(args.output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    token, user = login(args.api_base, args.email, args.password)
    config = {
        "run_id": run_id,
        "started_at": utc_now(),
        "api_base": args.api_base,
        "audio": str(audio_path),
        "audio_bytes": audio_path.stat().st_size,
        "email": args.email,
        "password": args.password,
        "company": args.company,
        "asr": args.asr,
        "batches": batch_values,
        "poll_interval": args.poll_interval,
        "max_wait": args.max_wait,
        "upload_timeout": args.upload_timeout,
        "resource_interval": args.resource_interval,
        "cooldown": args.cooldown,
        "login_user": user,
        "gpu_ssh_target": args.gpu_ssh_target,
        "gpu_ssh_port": args.gpu_ssh_port,
        "hetzner_host": args.hetzner_host,
        "hetzner_password": args.hetzner_password,
    }
    (run_dir / "config.json").write_text(json.dumps(redact_config(config), indent=2), encoding="utf-8")

    summaries: dict[int, dict[str, Any]] = {}
    started = time.time()
    for index, concurrency in enumerate(batch_values):
        summaries[concurrency] = run_batch(args, token, concurrency, run_dir)
        if index < len(batch_values) - 1 and args.cooldown > 0:
            print(f"Cooling down {args.cooldown}s before next batch...", flush=True)
            time.sleep(args.cooldown)

    full_summary = {
        "run_id": run_id,
        "started_at": config["started_at"],
        "finished_at": utc_now(),
        "elapsed_seconds": round(time.time() - started, 3),
        "batches": summaries,
    }
    (run_dir / "summary.json").write_text(json.dumps(full_summary, indent=2), encoding="utf-8")
    tex_path = build_latex_report(run_dir, redact_config(config), summaries)
    print(f"\nStress test complete: {run_dir}")
    print(f"LaTeX report: {tex_path}")
    pdf_path = tex_path.with_suffix(".pdf")
    if pdf_path.exists():
        print(f"PDF report: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
