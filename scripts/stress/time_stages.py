#!/usr/bin/env python3
"""Run the full pipeline once and print per-stage wall-clock timings.

Wraps models/run_full_pipeline.py as a subprocess, timestamps each stdout line,
and reports the duration between the known stage markers. Used to decide where
intra-call parallelism (if any) is worth it.
"""
import subprocess, sys, time, re

REPO = "/opt/calltone"
MARKERS = [
    ("denoise",       "LAYER 1 — STEP 1"),
    ("diarization",   "Step 1/3  Running speaker diarization"),
    ("transcription", "Step 2/3  Transcribing"),
    ("role_id",       "LAYER 1 — STEP 3"),
    ("emotion",       "LAYER 1 — STEP 4"),
    ("layer2_score",  "LAYER 2"),
    ("layer3_report", "LAYER 3"),
    ("end",           "PIPELINE COMPLETE"),
]

cmd = [sys.executable, f"{REPO}/models/run_full_pipeline.py", f"{REPO}/sample.wav",
       "--company", "metroboost", "--output-dir", "/tmp/timing2",
       "--report", "narrative", "--asr", "fasterwhisper", "--speakers", "2"]

hits = []  # (label, t)
start = time.time()
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
for line in p.stdout:
    now = time.time()
    for label, marker in MARKERS:
        if marker in line:
            hits.append((label, now))
            break
p.wait()
total = time.time() - start

print("\n===== PER-STAGE WALL CLOCK =====")
for i, (label, t) in enumerate(hits):
    nxt = hits[i + 1][1] if i + 1 < len(hits) else (start + total)
    print(f"{label:14} start +{t-start:6.1f}s   dur {nxt-t:6.1f}s")
print(f"{'TOTAL':14} {total:6.1f}s")
