#!/usr/bin/env python3
"""ASR-only WER for CALL1 (faster-whisper direct), beam 1 and beam 3.

Plain + normalized + no-fillers WER/CER against the external human reference.
No pyannote / no Qwen needed; CT2 model is public (no HF token).
"""
import re
from jiwer import wer, cer
from faster_whisper import WhisperModel

REF = "/opt/calltone/CALL1_ref.txt"
AUDIO = "/opt/calltone/CALL1.wav"
FILLERS = {"um","uh","erm","hmm","mm","uhh","umm","ah","er","mhm"}

def norm(t, drop=False):
    t = re.sub(r"[^a-z0-9\s]", " ", t.lower())
    if drop:
        t = " ".join(w for w in t.split() if w not in FILLERS)
    return re.sub(r"\s+", " ", t).strip()

ref = open(REF, encoding="utf-8").read()
print("reference words:", len(ref.split()))
m = WhisperModel("Systran/faster-whisper-large-v3", device="cuda", compute_type="float16")
for beam in (1, 3):
    segs, _ = m.transcribe(AUDIO, beam_size=beam, vad_filter=True, language="en")
    hyp = " ".join(s.text for s in segs)
    print(f"\nASR beam {beam} (VAD): hyp words {len(hyp.split())}")
    print(f"  plain      WER {wer(ref,hyp):.2%}  CER {cer(ref,hyp):.2%}")
    print(f"  normalized WER {wer(norm(ref),norm(hyp)):.2%}  CER {cer(norm(ref),norm(hyp)):.2%}")
    print(f"  no-fillers WER {wer(norm(ref,True),norm(hyp,True)):.2%}")
