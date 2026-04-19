"""
Speaker-diarized transcription using:
  - pyannote.audio  → who spoke when
  - Whisper          → what was said

Usage:
    conda run -n tf python transcribe_diarize.py <audio.wav> [num_speakers]

Requirements:
    - pip install pyannote.audio
    - pip install transformers
    - A HuggingFace account with accepted terms for:
        https://huggingface.co/pyannote/speaker-diarization-3.1
        https://huggingface.co/pyannote/segmentation-3.0
    - HF token stored via: huggingface-cli login
"""

from __future__ import annotations

import sys
import os
import re
import io
import json
import tempfile
from pathlib import Path

# On Windows, a spawned subprocess inherits the system codepage (cp1252) for
# stdout/stderr.  The pipeline prints Unicode arrows (→) and box-drawing
# characters that cp1252 cannot encode, causing UnicodeEncodeError.
if sys.platform == "win32":
    for _stream in ("stdout", "stderr"):
        _s = getattr(sys, _stream, None)
        if _s and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# pyannote checkpoints contain many custom classes (Specifications, etc.).
# PyTorch 2.6+ changed weights_only default to True, breaking pyannote.
# Patch lightning_fabric's _load (used by pyannote) to use weights_only=False.
import torch
import lightning_fabric.utilities.cloud_io as _la_io
def _patched_la_load(path, map_location=None, **kwargs):
    kwargs["weights_only"] = False
    return torch.load(path, map_location=map_location, **kwargs)
_la_io._load = _patched_la_load

# pyannote 4.x always downloads PLDA from pyannote/speaker-diarization-community-1
# even when using AgglomerativeClustering which never uses PLDA.
# Patch get_plda to return None so no network access is attempted.
import pyannote.audio.pipelines.utils.getter as _pa_getter
import pyannote.audio.pipelines.speaker_diarization as _pa_sd
def _noop_get_plda(plda, **kwargs):
    return None
_pa_getter.get_plda = _noop_get_plda
_pa_sd.get_plda = _noop_get_plda

from collections import defaultdict, Counter

import warnings
import numpy as np
import torchaudio
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from pyannote.audio import Pipeline

# Suppress known harmless deprecation warnings from transformers / pyannote
warnings.filterwarnings("ignore", message=".*max_new_tokens.*max_length.*")
warnings.filterwarnings("ignore", message=".*generation_config.*generation-related.*")
warnings.filterwarnings("ignore", message=".*chunk_length_s.*experimental.*")
warnings.filterwarnings("ignore", message=".*forced_decoder_ids.*deprecated.*")
warnings.filterwarnings("ignore", message=".*pipelines sequentially on GPU.*")
warnings.filterwarnings("ignore", message=".*multilingual Whisper.*")
warnings.filterwarnings("ignore", message=".*max_target_positions.*")
warnings.filterwarnings("ignore", message=".*SuppressTokensLogitsProcessor.*")
warnings.filterwarnings("ignore", message=".*SuppressTokensAtBeginLogitsProcessor.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote")

# Silence transformers logger spam (these are logger.warning, not warnings.warn,
# so warnings.filterwarnings doesn't catch them).  Each message holds the GIL
# for string formatting + stderr I/O — 25+ per transcription run.
import logging
logging.getLogger("transformers.generation.utils").setLevel(logging.ERROR)
logging.getLogger("transformers.pipelines.automatic_speech_recognition").setLevel(logging.ERROR)
logging.getLogger("transformers.generation.configuration_utils").setLevel(logging.ERROR)

# GPU optimizations
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True
    torch.set_float32_matmul_precision("high")

# ── paths ───────────────────────────────────────────────────────────────────────
MODEL_DIR  = os.path.join(os.path.dirname(__file__), "../models/whisper/openai/whisper-large-v3")
DEVICE     = "cuda:0" if torch.cuda.is_available() else "cpu"

# ── model cache — loaded once, reused across pipeline calls ──────────────────
_WHISPER_MODEL   = None   # Whisper ASR pipeline
_PYANNOTE_PIPELINE = None # pyannote diarization pipeline

# ── tag parsing ────────────────────────────────────────────────────────────────
SEGMENT_RE = re.compile(
    r"<\|([a-z]{2,})\|>"       # language
    r"<\|([A-Z_]+)\|>"          # emotion
    r"<\|([A-Za-z]+)\|>"        # sound event
    r"<\|w(?:ith|o)itn\|>"      # ITN flag
    r"(.*?)(?=<\||$)",
    re.DOTALL,
)

EMOTION_TAG: dict[str, str] = {
    "HAPPY": "[HAPPY]", "NEUTRAL": "[NEUTRAL]", "SAD": "[SAD]",
    "ANGRY": "[ANGRY]", "FEARFUL": "[FEARFUL]", "DISGUSTED": "[DISGUSTED]",
    "SURPRISED": "[SURPRISED]", "EMO_UNKNOWN": "",
}
EVENT_TAG: dict[str, str] = {
    "Speech": "", "BGM": "[BGM]", "Applause": "[APPLAUSE]",
    "Laughter": "[LAUGHTER]", "Cry": "[CRY]", "Cough": "[COUGH]",
    "Sneeze": "[SNEEZE]", "Breath": "[BREATH]", "Noise": "[NOISE]",
}
SPEAKER_COLORS = ["A", "B", "C", "D", "E", "F"]

# ── emoji stripping ─────────────────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF"   # misc symbols, pictographs, emoticons, transport
    "\U00002600-\U000027BF"    # misc symbols & dingbats
    "\U0000FE00-\U0000FE0F"    # variation selectors
    "\U00003000-\U00003300"    # CJK symbols
    "]+",
    re.UNICODE,
)

def strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


# ── text-based behavioural signal detection ──────────────────────────────────
# Patterns tuned for customer-service quality analysis.
TEXT_SIGNALS: dict[str, list[str]] = {
    "CONFUSED":    [r"(?i)\b(confused?|not (sure|clear)|don'?t understand|what do you mean|unclear|i'?m lost)\b"],
    "FRUSTRATED":  [r"(?i)\b(frustrated?|annoyed?|upset|ridiculous|unacceptable|terrible|awful|worst)\b",
                    r"(?i)\b(already (told|said)|been waiting|still (not|haven'?t)|keep (calling|trying))\b"],
    "APOLOGETIC":  [r"(?i)\b(sorry|apologize|apologi[sz]e?|apologies|my bad|pardon)\b"],
    "HESITANT":    [r"(?i)\bum+\b|\buh+\b|\bhmm+\b|\berr?\b"],
    "SATISFIED":   [r"(?i)\b(thank(s| you)|great|perfect|excellent|wonderful|appreciate|(very )?helpful|resolved|happy with)\b"],
    "QUESTIONING": [r"\?"],
    "ESCALATION":  [r"(?i)\b(manager|supervisor|escalat|complaint|complain|sue|legal|lawyer)\b"],
}

def detect_signals(text: str) -> list[str]:
    """Return behavioural signal tags matched in the text (rule-based)."""
    return [sig for sig, pats in TEXT_SIGNALS.items()
            if any(re.search(p, text) for p in pats)]


def parse_sense_output(raw: str) -> tuple[str, str, str]:
    """Return (clean_text, dominant_emotion, dominant_event) from Whisper output."""
    # Whisper doesn't provide emotion/event tags, so we return defaults
    clean = strip_emojis(raw.strip())
    return clean, "EMO_UNKNOWN", "Speech"


def load_sense_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        print("  Whisper model already loaded — reusing cached model.")
        return _WHISPER_MODEL

    print("  Loading Whisper model...")
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        MODEL_DIR, dtype=dtype, low_cpu_mem_usage=True, use_safetensors=True
    )
    model.to(DEVICE)
    processor = AutoProcessor.from_pretrained(MODEL_DIR)

    # Clean up generation_config to avoid conflicts with our generate_kwargs
    if hasattr(model, "generation_config") and model.generation_config is not None:
        model.generation_config.max_length = None
        model.generation_config.max_new_tokens = 440
        model.generation_config.suppress_tokens = []

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        batch_size=1,           # one 30 s chunk at a time (pipeline runs in own process, no GIL contention)
        return_timestamps="word",
        dtype=dtype,
        device=DEVICE,
        generate_kwargs={"max_new_tokens": 440, "language": "en", "task": "transcribe"},
    )
    _WHISPER_MODEL = pipe
    return pipe


def transcribe_chunk(model, waveform: torch.Tensor, sample_rate: int) -> tuple[str, str, str]:
    """Transcribe a single waveform tensor. Returns (text, emotion, event)."""
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)   # stereo → mono

    # Convert to numpy for Whisper pipeline
    audio_array = waveform.squeeze().cpu().numpy()
    
    # Resample to 16kHz if needed (Whisper expects 16kHz)
    if sample_rate != 16000:
        resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=16000)
        audio_array = resampler(waveform).squeeze().cpu().numpy()
    
    try:
        result = model(audio_array)
        raw = result["text"] if result else ""
    except Exception as e:
        print(f"    Transcription error: {e}")
        raw = ""

    return parse_sense_output(raw)


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def speaker_label(pyannote_id: str, index_map: dict) -> str:
    if pyannote_id not in index_map:
        idx = len(index_map)
        index_map[pyannote_id] = SPEAKER_COLORS[idx] if idx < len(SPEAKER_COLORS) else str(idx)
    return f"SPEAKER_{index_map[pyannote_id]}"


def estimate_pitch(waveform: torch.Tensor, sr: int) -> float:
    """
    Return the median voiced fundamental frequency (Hz) of a mono waveform.
    Uses torchaudio autocorrelation-based pitch detector.
    Returns 0.0 for unvoiced / too-short segments.
    """
    audio = waveform.squeeze().cpu()
    if audio.numel() < int(sr * 0.15):   # need at least 150 ms
        return 0.0
    try:
        pitch_hz = torchaudio.functional.detect_pitch_frequency(
            audio.unsqueeze(0), sr,
            frame_time=0.01,
            win_length=30,
            freq_low=60,
            freq_high=400,
        )
        voiced = pitch_hz[pitch_hz > 60]
        return float(voiced.median().item()) if voiced.numel() > 0 else 0.0
    except Exception:
        return 0.0


def relabel_speakers_by_pitch(
    turns: list[tuple],
    pitches: list[float],
    num_speakers: int = 2,
) -> list[tuple]:
    """
    Rename pyannote speaker labels using global median pitch ordering.

    Pitch is used only to decide the label ordering:
      lowest-median-pitch cluster → SPEAKER_00, next → SPEAKER_01 …

    Pyannote's per-turn cluster assignments are preserved unchanged.
    Only the label names are remapped.  This is more robust than per-turn
    pitch classification because pyannote uses deep speaker embeddings for
    within-recording clustering; individual turns should not be reclassified
    by a single acoustic feature.
    """
    # Collect voiced pitches grouped by pyannote's original speaker label
    spk_pitches: dict[str, list[float]] = {}
    for (_, _, spk), p in zip(turns, pitches):
        if p > 0:
            spk_pitches.setdefault(spk, []).append(p)

    if len(spk_pitches) < num_speakers:
        return turns   # not enough data; leave unchanged

    # Sort speakers by global median pitch → SPEAKER_00 = lowest pitch
    spk_sorted = sorted(spk_pitches, key=lambda s: float(np.median(spk_pitches[s])))

    # Build rename map: original pyannote label → new stable label
    label_map = {spk: f"SPEAKER_{i:02d}" for i, spk in enumerate(spk_sorted)}

    return [(t0, t1, label_map.get(spk, spk)) for t0, t1, spk in turns]


def resolve_overlaps(
    turns: list[tuple],
    min_dur: float = 0.5,
    merge_gap: float = 0.4,
) -> list[tuple]:
    """
    Post-process pyannote turns to clean up overlapping speech.

    Strategy
    --------
    1. Sort turns by start time.
    2. For each turn that overlaps with the most-recent resolved turn:
         - Small overlap (< 50 % of the shorter segment):
             trim the earlier turn's end to the current turn's start.
         - Large overlap (≥ 50 % of the shorter segment, i.e. subsumption):
             keep the longer segment, discard the shorter.
    3. Merge consecutive same-speaker turns whose gap is ≤ merge_gap seconds.
    4. Drop any segments shorter than min_dur seconds.
    """
    if not turns:
        return []

    turns = sorted(turns, key=lambda x: x[0])
    resolved: list[list] = []

    for t0, t1, spk in turns:
        if not resolved:
            if t1 - t0 >= min_dur:
                resolved.append([t0, t1, spk])
            continue

        prev = resolved[-1]
        p0, p1, _ = prev

        if t0 < p1:                                        # overlap detected
            overlap  = p1 - t0
            dur_prev = p1 - p0
            dur_curr = t1 - t0
            shorter  = min(dur_prev, dur_curr)

            if overlap / shorter >= 0.5:                   # large / subsumption
                if dur_prev >= dur_curr:
                    continue                                # current subsumed → skip
                else:
                    resolved.pop()                         # previous subsumed → replace
            else:                                          # small overlap → trim earlier
                new_end = t0
                if new_end - p0 >= min_dur:
                    prev[1] = new_end
                else:
                    resolved.pop()

        if t1 - t0 >= min_dur:
            resolved.append([t0, t1, spk])

    # merge adjacent same-speaker turns with a small gap
    merged: list[list] = []
    for seg in resolved:
        if merged and merged[-1][2] == seg[2] and seg[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = seg[1]
        else:
            merged.append(list(seg))

    return [(t0, t1, spk) for t0, t1, spk in merged]


def build_report(audio_path: str, segments: list[dict]) -> str:
    """Build the full formatted text report (bracket tags, no emojis)."""
    lines = []
    W = 70

    lines.append("═" * W)
    lines.append("  TRANSCRIPTION WITH SPEAKER DIARIZATION")
    lines.append(f"  File     : {os.path.basename(audio_path)}")
    speaker_ids = sorted({s["speaker"] for s in segments})
    lines.append(f"  Speakers : {len(speaker_ids)}  ({', '.join(speaker_ids)})")
    lines.append("═" * W)
    lines.append("")

    # ── conversation ──────────────────────────────────────────────────────────
    prev_speaker = None
    for seg in segments:
        spk  = seg["speaker"]
        emo  = seg["emotion"]
        evt  = seg["event"]
        text = seg["text"]
        t0   = fmt_time(seg["start"])
        t1   = fmt_time(seg["end"])

        if prev_speaker and prev_speaker != spk:
            lines.append("")

        emo_tag  = EMOTION_TAG.get(emo, "")
        evt_tag  = EVENT_TAG.get(evt, "")
        sig_tags = "  ".join(f"[{s}]" for s in seg.get("signals", []))
        parts    = [p for p in [emo_tag, evt_tag, sig_tags] if p]
        header   = f"[{t0}→{t1}]  {spk:<12}  {'  '.join(parts)}".rstrip()
        lines.append(header)

        words, line_buf = text.split(), ""
        for w in words:
            if len(line_buf) + len(w) + 1 > 64:
                lines.append(f"    {line_buf.rstrip()}")
                line_buf = w + " "
            else:
                line_buf += w + " "
        if line_buf.strip():
            lines.append(f"    {line_buf.rstrip()}")

        prev_speaker = spk

    # ── summary ───────────────────────────────────────────────────────────────
    lines.append("")
    lines.append("─" * W)
    lines.append("  ANALYSIS SUMMARY")
    lines.append("─" * W)

    total_dur  = sum(s["end"] - s["start"] for s in segments)
    all_events = [s["event"] for s in segments if s["event"] != "Speech"]

    lines.append(f"  Total speech time : {fmt_duration(total_dur)}")
    lines.append(f"  Segments          : {len(segments)}")
    lines.append("")

    for spk in speaker_ids:
        spk_segs = [s for s in segments if s["speaker"] == spk]
        spk_dur  = sum(s["end"] - s["start"] for s in spk_segs)
        pct      = 100 * spk_dur / total_dur if total_dur else 0
        emotions = [s["emotion"] for s in spk_segs if s["emotion"] != "EMO_UNKNOWN"]
        emo_dist = Counter(emotions).most_common()
        all_sigs: list[str] = []
        for s in spk_segs:
            all_sigs.extend(s.get("signals", []))
        sig_dist = Counter(all_sigs).most_common()

        lines.append(f"  {spk}")
        lines.append(f"    Talk time        : {fmt_duration(spk_dur)} ({pct:.0f}%)")
        # Emotion detection disabled - not showing emotion info
        if sig_dist:
            sig_str = "  ".join(f"[{s}]x{n}" for s, n in sig_dist)
            lines.append(f"    Signals          : {sig_str}")
        lines.append("")

    lines.append("  Sound events detected :")
    if all_events:
        for ev, n in Counter(all_events).most_common():
            lines.append(f"    {EVENT_TAG.get(ev, ev)} x{n}")
    else:
        lines.append("    None (speech only)")

    lines.append("═" * W)
    return "\n".join(lines)


RATING_CRITERIA = [
    {"id": 1, "name": "Script Compliance",  "weight": 0.25,
     "description": "Did the agent follow required protocols and scripts?"},
    {"id": 2, "name": "Factual Accuracy",   "weight": 0.25,
     "description": "Were statements and information provided correct?"},
    {"id": 3, "name": "Politeness & Tone",  "weight": 0.15,
     "description": "Was communication professional and courteous?"},
    {"id": 4, "name": "Empathy",            "weight": 0.10,
     "description": "Were customer feelings acknowledged appropriately?"},
    {"id": 5, "name": "Conflict Detection", "weight": 0.15,
     "description": "Were escalations or conflicts present?"},
    {"id": 6, "name": "Issue Resolution",   "weight": 0.05,
     "description": "Was the customer's problem resolved?"},
    {"id": 7, "name": "Overall Severity",   "weight": 0.05,
     "description": "Classify the call as: Minor / Moderate / Major / Critical"},
]


def build_json(
    audio_path: str,
    segments: list[dict],
    spk_pitch_summary: dict[str, list[float]],
    roles: dict[str, str] | None = None,
) -> dict:
    """Build structured JSON for the downstream QA rating layer."""
    speaker_ids = sorted({s["speaker"] for s in segments})
    total_dur   = sum(s["end"] - s["start"] for s in segments)

    speaker_summary = {}
    for spk in speaker_ids:
        spk_segs = [s for s in segments if s["speaker"] == spk]
        spk_dur  = sum(s["end"] - s["start"] for s in spk_segs)
        all_sigs: list[str] = []
        for s in spk_segs:
            all_sigs.extend(s.get("signals", []))
        ps = spk_pitch_summary.get(spk, [])
        speaker_summary[spk] = {
            **({"role": roles[spk]} if roles and spk in roles else {}),
            "talk_time_seconds":   round(spk_dur, 2),
            "talk_time_pct":       round(100 * spk_dur / total_dur, 1) if total_dur else 0,
            "median_pitch_hz":     round(float(np.median(ps)), 1) if ps else None,
            # Emotion detection disabled
            "behavioral_signals":  dict(Counter(all_sigs).most_common()),
        }

    transcript_items = [
        {
            "id":      i,
            "start":   round(s["start"], 2),
            "end":     round(s["end"], 2),
            "speaker": s["speaker"],
            **({"role": roles[s["speaker"]]} if roles and s["speaker"] in roles else {}),
            "emotion": s["emotion"],
            "event":   s["event"],
            "signals": s.get("signals", []),
            "text":    s["text"],
        }
        for i, s in enumerate(segments, 1)
    ]

    return {
        "call_metadata": {
            "file":             os.path.basename(audio_path),
            "duration_seconds": round(total_dur, 2),
            "num_speakers":     len(speaker_ids),
            "total_segments":   len(segments),
        },
        "speaker_summary": speaker_summary,
        "transcript":      transcript_items,
        "rating_criteria": RATING_CRITERIA,
    }


def main():
    audio_path   = sys.argv[1] if len(sys.argv) > 1 else "test/2077589677_final_stereo.wav"
    num_speakers = int(sys.argv[2]) if len(sys.argv) > 2 else None
    # Optional: comma-separated role names, e.g. "AGENT,CUSTOMER"
    roles: dict[str, str] | None = None
    if len(sys.argv) > 3:
        role_names = [r.strip() for r in sys.argv[3].split(",")]
        roles = {f"SPEAKER_{SPEAKER_COLORS[i]}": r
                 for i, r in enumerate(role_names) if i < len(SPEAKER_COLORS)}

    if not os.path.isfile(audio_path):
        print(f"Error: file not found: {audio_path}")
        sys.exit(1)

    # Check for local model — env var overrides the default local path
    _default_local = Path(__file__).parent.parent / "models" / "pyannote" / "speaker-diarization-3.1"
    local_model_path = os.environ.get("PYANNOTE_MODEL_PATH") or str(_default_local)

    if os.path.exists(local_model_path):
        # Newer huggingface_hub validates the argument as a repo id when it
        # looks like a path. pyannote.Pipeline.from_pretrained only skips that
        # validation when the argument points directly at a file. If we got a
        # directory, append config.yaml so we land on the file branch.
        if os.path.isdir(local_model_path):
            _cfg = os.path.join(local_model_path, "config.yaml")
            if os.path.isfile(_cfg):
                local_model_path = _cfg
        print(f"Using local pyannote model: {local_model_path}")
    else:
        # Try fallback to HuggingFace if local model not found
        try:
            from huggingface_hub import get_token
            hf_token = get_token()
            if not hf_token:
                print("ERROR: No local model found and no HuggingFace token available.")
                print(f"  Expected local model at: {local_model_path}")
                sys.exit(1)
            local_model_path = None  # Use online mode
        except ImportError:
            print("ERROR: No local model found and huggingface_hub not installed.")
            print(f"  Expected local model at: {local_model_path}")
            sys.exit(1)

    print(f"\nAudio : {audio_path}")
    print(f"Device: {DEVICE}\n")

    # ── 1. Diarization ─────────────────────────────────────────────────────────
    print("Step 1/3  Running speaker diarization (pyannote)...")

    global _PYANNOTE_PIPELINE
    if _PYANNOTE_PIPELINE is not None:
        print("  pyannote pipeline already loaded — reusing cached model.")
        pipeline = _PYANNOTE_PIPELINE
    else:
        if local_model_path and os.path.exists(local_model_path):
            # Patch hardcoded absolute paths in config.yaml (original dev used /home/mazen/...)
            # Recompute from __file__ so this works on any machine without manual edits.
            _config_file = Path(local_model_path) / "config.yaml"
            if _config_file.exists():
                _pyannote_root = Path(__file__).parent.parent / "models" / "pyannote"
                _new_seg = (_pyannote_root / "segmentation-3.0").as_posix()
                _new_emb = (_pyannote_root / "wespeaker-voxceleb-resnet34-LM").as_posix()
                _patched = []
                for _ln in _config_file.read_text(encoding="utf-8").splitlines():
                    _s = _ln.lstrip()
                    _ind = _ln[: len(_ln) - len(_s)]
                    if _s.startswith("segmentation:") and "segmentation-3.0" in _s:
                        _patched.append(f"{_ind}segmentation: {_new_seg}")
                    elif _s.startswith("embedding:") and "wespeaker" in _s:
                        _patched.append(f"{_ind}embedding: {_new_emb}")
                    else:
                        _patched.append(_ln)
                _config_file.write_text("\n".join(_patched) + "\n", encoding="utf-8")
            pipeline = Pipeline.from_pretrained(local_model_path)
        else:
            # Online mode with HuggingFace token
            try:
                from huggingface_hub import get_token
                hf_token = get_token()
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=hf_token,
                )
            except Exception as e:
                print(f"\nERROR: Could not load pyannote model: {e}")
                print("  You must either:")
                print("    1. Set PYANNOTE_MODEL_PATH to use local models")
                print("    2. Login to HuggingFace and accept model terms")
                sys.exit(1)

        if pipeline is None:
            print("\nERROR: Could not load pyannote/speaker-diarization-3.1")
            print("  You must accept the model terms at:")
            print("    https://huggingface.co/pyannote/speaker-diarization-3.1")
            print("    https://huggingface.co/pyannote/segmentation-3.0")
            print("  (log in with your HF account, then click 'Agree and access repository')")
            sys.exit(1)
        pipeline.to(torch.device(DEVICE))
        _PYANNOTE_PIPELINE = pipeline

    # Load audio into memory and pass as a waveform dict to pyannote.
    # This bypasses pyannote's AudioDecoder (which requires torchcodec /
    # FFmpeg DLLs that are missing on Windows) and avoids sample-count
    # mismatches that occur when pyannote reads compressed files directly.
    # NOTE: torchaudio.load() itself uses torchcodec since v2.9, so we
    # use soundfile (libsndfile) which has no FFmpeg dependency.
    import soundfile as sf
    _wav_np, sr = sf.read(audio_path, dtype="float32")
    waveform = torch.from_numpy(_wav_np).T if _wav_np.ndim > 1 else torch.from_numpy(_wav_np).unsqueeze(0)

    diarize_kwargs = {"num_speakers": num_speakers} if num_speakers else {}
    diarization = pipeline(
        {"waveform": waveform, "sample_rate": sr}, **diarize_kwargs
    )

    # Handle different pyannote output formats
    # Local models return DiarizeOutput with speaker_diarization attribute
    # HuggingFace models return Annotation directly
    if hasattr(diarization, 'speaker_diarization'):
        # DiarizeOutput from local model - extract the Annotation
        annotation = diarization.speaker_diarization
    else:
        # Direct Annotation from HuggingFace
        annotation = diarization
    
    raw_turns = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        if turn.end - turn.start > 0.3:   # skip < 0.3 s fragments
            raw_turns.append((turn.start, turn.end, speaker))

    turns = resolve_overlaps(raw_turns)
    print(f"  → {len(raw_turns)} raw turns → {len(turns)} after overlap resolution")

    # ── Pitch-based speaker anchoring ──────────────────────────────────────────
    # Load audio once here; reused in step 2 below.
    _wav_np2, sr = sf.read(audio_path, dtype="float32")
    waveform = torch.from_numpy(_wav_np2).T if _wav_np2.ndim > 1 else torch.from_numpy(_wav_np2).unsqueeze(0)

    print("  Anchoring speaker labels by pitch (F0)...")
    pitches = []
    for t0, t1, _ in turns:
        chunk = waveform[:, int(t0 * sr):int(t1 * sr)]
        if chunk.shape[0] > 1:
            chunk = chunk.mean(dim=0, keepdim=True)
        pitches.append(estimate_pitch(chunk, sr))

    n_spk = num_speakers or len({spk for _, _, spk in turns})
    turns = relabel_speakers_by_pitch(turns, pitches, n_spk)

    voiced_pitches = [(spk, p) for (_, _, spk), p in zip(turns, pitches) if p > 0]
    spk_pitch_summary = {}
    for spk, p in voiced_pitches:
        spk_pitch_summary.setdefault(spk, []).append(p)
    for spk, ps in sorted(spk_pitch_summary.items()):
        print(f"    {spk}  median F0 = {np.median(ps):.0f} Hz  ({len(ps)} voiced turns)")

    # ── 2. Full-file transcription + alignment to diarization turns ────────────
    # Transcribe the ENTIRE audio in one pass with word-level timestamps.
    # Whisper internally splits into 30 s windows, so any file length works.
    # This is 5-10× faster than per-turn inference because:
    #   • ONE encoder pass over the full spectrogram (not 65 separate ones)
    #   • No variable-length padding waste across turns
    print("Step 2/3  Transcribing full audio (Whisper, single pass)...")
    sense_model = load_sense_model()

    mono = waveform.mean(dim=0) if waveform.shape[0] > 1 else waveform.squeeze()
    full_result = sense_model(
        {"array": mono.cpu().numpy(), "sampling_rate": sr},
        return_timestamps="word",
        chunk_length_s=30,
        ignore_warning=True,
        generate_kwargs={"max_new_tokens": 440, "language": "en", "task": "transcribe"},
    )

    # Build sorted list of (word_center_time, word_text)
    word_entries: list[tuple[float, str]] = []
    for chunk in full_result.get("chunks", []):
        ts = chunk.get("timestamp", (None, None))
        if ts[0] is not None and ts[1] is not None:
            word_entries.append(((ts[0] + ts[1]) / 2.0, chunk["text"]))
    print(f"  Whisper returned {len(word_entries)} words — aligning to {len(turns)} turns...")

    # Assign words to diarization turns by word center time
    index_map = {}
    segments  = []
    wi = 0   # pointer into word_entries (sorted by time)
    for t0, t1, raw_spk in turns:
        turn_words: list[str] = []
        # Advance pointer past words before this turn
        while wi < len(word_entries) and word_entries[wi][0] < t0:
            wi += 1
        # Collect words inside this turn
        j = wi
        while j < len(word_entries) and word_entries[j][0] <= t1:
            turn_words.append(word_entries[j][1])
            j += 1

        text = "".join(turn_words).strip()
        if not text:
            continue

        text, emo, evt = parse_sense_output(text)
        if not text:
            continue
        segments.append({
            "start":   t0,
            "end":     t1,
            "speaker": speaker_label(raw_spk, index_map),
            "emotion": emo,
            "event":   evt,
            "signals": detect_signals(text),
            "text":    text,
        })

    print(f"  → {len(segments)} segments transcribed")

    # ── 3. Format & save ───────────────────────────────────────────────────────
    print("Step 3/3  Formatting output...")
    report = build_report(audio_path, segments)
    print("\n" + report)

    base = os.path.splitext(audio_path)[0]

    out_path = base + "_diarized.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nText  → {out_path}")

    json_data = build_json(audio_path, segments, spk_pitch_summary, roles)
    json_path = base + "_diarized.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON  → {json_path}")


if __name__ == "__main__":
    main()
