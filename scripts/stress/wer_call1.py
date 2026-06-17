#!/usr/bin/env python3
"""Comprehensive WER for CALL1 against its external human reference.

Computes plain / normalized / no-fillers WER+CER for:
  - the full pipeline transcript (from the diarized output JSON), and
  - the ASR stage alone (faster-whisper run directly) at beam 1 and beam 3.
All transforms are transparent and reproducible.
"""
import json, re, sys

REPO = "/opt/calltone"
REF = f"{REPO}/CALL1_ref.txt"
DIA = f"{REPO}/out_call1/CALL1_diarized_with_emotions.json"
AUDIO = f"{REPO}/CALL1.wav"
FILLERS = {"um", "uh", "erm", "hmm", "mm", "uhh", "umm", "ah", "er", "mhm", "uh-huh"}

from jiwer import wer, cer


def norm(t, drop_fillers=False):
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    if drop_fillers:
        t = " ".join(w for w in t.split() if w not in FILLERS)
    return re.sub(r"\s+", " ", t).strip()


def row(label, ref, hyp):
    plain_w, plain_c = wer(ref, hyp), cer(ref, hyp)
    n_ref, n_hyp = norm(ref), norm(hyp)
    norm_w, norm_c = wer(n_ref, n_hyp), cer(n_ref, n_hyp)
    f_ref, f_hyp = norm(ref, True), norm(hyp, True)
    nf_w = wer(f_ref, f_hyp)
    print(f"{label:34} plain {plain_w:6.2%} (CER {plain_c:5.2%}) | "
          f"norm {norm_w:6.2%} (CER {norm_c:5.2%}) | no-fillers {nf_w:6.2%}")


ref = open(REF, encoding="utf-8").read()
print(f"reference words: {len(ref.split())}\n")

# 1) full pipeline (diarized output)
d = json.load(open(DIA, encoding="utf-8"))
segs = d if isinstance(d, list) else d.get("segments", [])
hyp_full = " ".join(s.get("text", "") for s in segs)
row("Full pipeline (diarized)", ref, hyp_full)

# 2) ASR-only, faster-whisper directly
from faster_whisper import WhisperModel
model = WhisperModel("Systran/faster-whisper-large-v3", device="cuda", compute_type="float16")
for beam in (1, 3):
    segments, _ = model.transcribe(AUDIO, beam_size=beam, vad_filter=True, language="en")
    hyp = " ".join(s.text for s in segments)
    row(f"ASR only (beam {beam}, VAD)", ref, hyp)
