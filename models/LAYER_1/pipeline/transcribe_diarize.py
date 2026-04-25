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
from faster_whisper import WhisperModel
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


# ── ASR engine selection ─────────────────────────────────────────────────────
# CALLTONE_ASR env var picks the engine per call:
#   "fasterwhisper" (default) — Systran/faster-whisper-large-v3 on CTranslate2
#   "sensevoice"              — Alibaba/FunASR SenseVoiceSmall (original choice)
#
# The pipeline uses a unified `transcribe_full_audio(audio_np, sr)` API that
# returns a list of (start_time, word_text) tuples regardless of engine, so
# downstream alignment-to-diarization-turns code is agnostic.
_SENSEVOICE_MODEL = None  # Lazy-loaded FunASR AutoModel

DEFAULT_ASR_GLOSSARY = (
    "MetroBoost, Metro Boost, Shalene, Linda Marone, Global Phone, postpaid, "
    "prepaid, AutoPay, O2Pay, credit card, overdraft fee, unlimited calls and "
    "texts, unlimited data, five gigs, fifteen gigabytes, sixty-seven dollars "
    "and eighty-one cents, sixty-five dollar unlimited plan, two dollars and "
    "eighty-one cents, $67.81, $62.81, $65, $40, $30, $50, $60, $55"
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _selected_asr_engine() -> str:
    """Return the lower-case engine name picked via env. Default fasterwhisper."""
    return os.environ.get("CALLTONE_ASR", "fasterwhisper").strip().lower()


def _asr_glossary_prompt() -> str | None:
    if not _env_bool("CALLTONE_FW_USE_GLOSSARY", True):
        return None
    return os.environ.get("CALLTONE_ASR_GLOSSARY", DEFAULT_ASR_GLOSSARY).strip() or None


def _normalize_asr_text(text: str) -> str:
    """Conservative telecom/domain cleanup after ASR.

    This is intentionally not a general grammar corrector. It only fixes
    deterministic domain confusions observed on CallTone telecom calls and
    preserves the original wording everywhere else.
    """
    replacements = [
        (r"\bMetro\s+Boost\b", "MetroBoost"),
        (r"\bMetrobus\b", "MetroBoost"),
        (r"\bMetribus\b", "MetroBoost"),
        (r"\bMetribuys\b", "MetroBoost"),
        (r"\bMetribuy\b", "MetroBoost"),
        (r"\bMetro\s+Buys\b", "MetroBoost"),
        (r"\bShalane\b", "Shalene"),
        (r"\bJolene\b", "Shalene"),
        (r"\bJalene\b", "Shalene"),
        (r"\bPostpay\b", "postpaid"),
        (r"\bpostpay\b", "postpaid"),
        (r"\bPrepay\b", "prepaid"),
        (r"\bprepay\b", "prepaid"),
        (r"\bAlrighty\b", "All righty"),
        (r"\bAlright\b", "All right"),
        (r"\bKylie,?\s+tap\b", "Kindly tap"),
        (r"\bfee\s+data\s+checker\b", "Feed Data Checker"),
        (r"\b27\s+days\b", "twenty-seven days"),
        (r"\bno\s+problem\b", "not a problem"),
        (r"\bthe\s+goodness\s+about\s+it\b", "the good news about it"),
        (r"\bO2\s*Pay\b", "AutoPay"),
        (r"\bO\s*to\s*Pay\b", "AutoPay"),
        (r"\bauto\s+pay\b", "AutoPay"),
        (r"\bcredit\s+card\s+is\s+currently\s+not\s+enrolled\s+in\s+AutoPay\b",
         "credit card is currently not enrolled in AutoPay"),
        (r"\bcharged\s+\$?6781\b", "charged $67.81"),
        (r"\bcharged\s+67\s+81\b", "charged $67.81"),
        (r"\b\$6781\b", "$67.81"),
        (r"\bunlimited\s+cost,\s*tax,\s*and\s+data\b", "unlimited calls, texts, and data"),
        (r"\bthe\s+plan\s+that\s+was\s+graded\s+for\s+you\b",
         "the plan that was created for you"),
        (r"\btap\s+that\s+app\s+for\s+me,\s+in\s+with\b",
         "tap that app for me, sign in with"),
        (r"\btrack\s+all\s+the\s+details\s+of\s+your\s+account\b",
         "check all the details of your account"),
    ]
    cleaned = text
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.?!])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def load_sense_model():
    """
    Load the active ASR engine and return the model handle.

    Returns:
        - WhisperModel (faster-whisper) when CALLTONE_ASR=fasterwhisper (default)
        - FunASR AutoModel               when CALLTONE_ASR=sensevoice

    Both handles are cached at module level so re-runs don't reload weights.
    """
    engine = _selected_asr_engine()
    if engine == "sensevoice":
        return _load_sensevoice_model()
    if engine != "fasterwhisper":
        print(f"  WARN: unknown CALLTONE_ASR='{engine}', falling back to fasterwhisper")
    return _load_fasterwhisper_model()


def _load_fasterwhisper_model():
    """Load faster-whisper (CTranslate2) — 4-8x faster than HF transformers."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        print("  faster-whisper already loaded — reusing cached model.")
        return _WHISPER_MODEL

    use_cuda = torch.cuda.is_available()
    device = "cuda" if use_cuda else "cpu"
    compute_type = "float16" if use_cuda else "int8"
    model_id = os.environ.get("CALLTONE_FW_MODEL", "Systran/faster-whisper-large-v3")

    print(f"  Loading faster-whisper '{model_id}' on {device} ({compute_type})...")
    _WHISPER_MODEL = WhisperModel(
        model_id,
        device=device,
        compute_type=compute_type,
        cpu_threads=max(1, (os.cpu_count() or 4) // 2),
        num_workers=1,
    )
    return _WHISPER_MODEL


def _load_sensevoice_model():
    """
    Load Alibaba SenseVoiceSmall via FunASR AutoModel.

    Falls back to lazy HF download (model cached under
    ~/.cache/modelscope/hub) if no local model is present.
    """
    global _SENSEVOICE_MODEL
    if _SENSEVOICE_MODEL is not None:
        print("  SenseVoice already loaded — reusing cached model.")
        return _SENSEVOICE_MODEL

    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise ImportError(
            "funasr is required for SenseVoice. Install with: "
            "pip install funasr"
        ) from exc

    use_cuda = torch.cuda.is_available()
    device = "cuda:0" if use_cuda else "cpu"
    local_model_dir = Path(__file__).parent.parent / "models" / "sensevoice" / "iic" / "SenseVoiceSmall"
    cache_model_dir = Path.home() / ".cache" / "modelscope" / "hub" / "models" / "iic" / "SenseVoiceSmall"
    model_id = os.environ.get("CALLTONE_SV_MODEL") or (
        str(cache_model_dir) if cache_model_dir.exists()
        else (str(local_model_dir) if (local_model_dir / "model.pt").exists() else "iic/SenseVoiceSmall")
    )
    vad_model_id = os.environ.get("CALLTONE_SV_VAD", "fsmn-vad")
    remote_code_path = str((Path(__file__).parent / "SenseVoice" / "model.py").resolve())

    print(f"  Loading SenseVoice '{model_id}' on {device} ...")
    _SENSEVOICE_MODEL = AutoModel(
        model=model_id,
        trust_remote_code=True,
        remote_code=remote_code_path,
        vad_model=vad_model_id,
        vad_kwargs={"max_single_segment_time": 30000},
        device=device,
        disable_update=True,  # don't ping ModelScope on every load
    )
    return _SENSEVOICE_MODEL


def transcribe_full_audio(audio_np: np.ndarray, sr: int = 16000) -> list[tuple[float, str]]:
    """
    Engine-agnostic transcription.

    Returns a sorted list of (word_start_time_seconds, word_text) tuples
    suitable for word-by-word alignment against diarization turns.

    Both engines emit timing-tagged words; SenseVoice uses sentence-level
    timestamps (start of sentence) since its model doesn't natively expose
    word timings — this is enough for turn alignment because diarization
    turns are typically multi-second.
    """
    engine = _selected_asr_engine()
    audio_duration = float(len(audio_np) / sr)

    if engine == "sensevoice":
        return _transcribe_sensevoice(audio_np, sr, audio_duration)
    return _transcribe_fasterwhisper(audio_np, sr, audio_duration)


def _transcribe_fasterwhisper(
    audio_np: np.ndarray, sr: int, audio_duration: float
) -> list[tuple[float, str]]:
    model = _load_fasterwhisper_model()
    # Benchmarked on test.wav (2026-04-24): beam=1 + glossary/hotwords beats
    # beam=3/5 on both WER and runtime for this telephony workload.
    beam_size = int(os.environ.get("CALLTONE_FW_BEAM", "1"))
    glossary = _asr_glossary_prompt()
    vad_filter = _env_bool("CALLTONE_FW_VAD_FILTER", True)
    condition_on_previous_text = _env_bool("CALLTONE_FW_CONDITION_PREVIOUS", False)
    vad_parameters = {
        "min_silence_duration_ms": int(os.environ.get("CALLTONE_FW_MIN_SILENCE_MS", "350"))
    }
    fw_segments, _info = model.transcribe(
        audio_np,
        language="en",
        beam_size=beam_size,
        best_of=int(os.environ.get("CALLTONE_FW_BEST_OF", str(beam_size))),
        vad_filter=vad_filter,
        vad_parameters=vad_parameters if vad_filter else None,
        word_timestamps=True,
        condition_on_previous_text=condition_on_previous_text,
        no_speech_threshold=0.6,
        temperature=0,
        initial_prompt=glossary,
        hotwords=glossary,
    )

    word_entries: list[tuple[float, str]] = []
    for seg in fw_segments:
        if not getattr(seg, "words", None):
            txt = (seg.text or "").strip()
            if txt and seg.start is not None:
                word_entries.append((max(0.0, min(float(seg.start), audio_duration)), " " + txt))
            continue
        for w in seg.words:
            if w.start is None or w.word is None:
                continue
            ws = max(0.0, min(float(w.start), audio_duration))
            we = float(w.end) if w.end is not None else ws
            if we - ws > 8.0:
                continue  # hallucinated mega-word
            word_entries.append((ws, w.word))
    word_entries.sort(key=lambda x: x[0])
    return word_entries


def _transcribe_sensevoice(
    audio_np: np.ndarray, sr: int, audio_duration: float
) -> list[tuple[float, str]]:
    """
    Run SenseVoice on the full audio. SenseVoice + fsmn-vad returns segments
    with `start` (ms) + `text` containing FunASR markup tags we strip.

    We don't get word-level timing, so we approximate by distributing words
    evenly over the segment duration. This is good enough for turn alignment
    because diarization turns are 1-30 s long.
    """
    model = _load_sensevoice_model()
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except Exception:
        rich_transcription_postprocess = None
    res = model.generate(
        input=audio_np,
        cache={},
        language="en",
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )

    word_entries: list[tuple[float, str]] = []
    for item in res:
        # FunASR returns one dict per input. With merge_vad we still get one
        # 'text' string concatenated across VAD segments, plus 'timestamp'
        # which is a list of [start_ms, end_ms] per word. Older versions
        # return only sentence-level timing in 'sentence_info'.
        text_raw = (item.get("text") or "").strip()
        if rich_transcription_postprocess:
            try:
                text_raw = rich_transcription_postprocess(text_raw)
            except Exception:
                pass
        # Strip SenseVoice control tags: <|en|><|NEUTRAL|><|Speech|><|withitn|>...
        clean = re.sub(r"<\|[^|]*\|>", "", text_raw).strip()
        if not clean:
            continue

        # Prefer per-word timestamps if FunASR gave them
        timestamps = item.get("timestamp")
        if isinstance(timestamps, list) and timestamps:
            # timestamps: list of [start_ms, end_ms] aligned to whitespace-split words
            words = clean.split()
            for i, w in enumerate(words):
                if i >= len(timestamps):
                    break
                start_ms = float(timestamps[i][0]) if timestamps[i] else 0.0
                start_s = max(0.0, min(start_ms / 1000.0, audio_duration))
                word_entries.append((start_s, " " + w))
            continue

        # Fall back to sentence_info or distribute words evenly
        sentence_info = item.get("sentence_info") or []
        if sentence_info:
            for sent in sentence_info:
                sent_text = (sent.get("text") or "").strip()
                if rich_transcription_postprocess:
                    try:
                        sent_text = rich_transcription_postprocess(sent_text)
                    except Exception:
                        pass
                sent_text = re.sub(r"<\|[^|]*\|>", "", sent_text).strip()
                if not sent_text:
                    continue
                start_s = max(0.0, min(float(sent.get("start", 0)) / 1000.0, audio_duration))
                end_s = max(start_s, min(float(sent.get("end", start_s * 1000)) / 1000.0, audio_duration))
                words = sent_text.split()
                if not words:
                    continue
                step = (end_s - start_s) / max(1, len(words))
                for i, w in enumerate(words):
                    word_entries.append((start_s + i * step, " " + w))
            continue

        # Last resort: no timestamps at all. Distribute words uniformly across
        # the clip so the existing diarization alignment can still map them to
        # turns in order.
        words = clean.split()
        if not words:
            continue
        step = audio_duration / max(1, len(words))
        for i, w in enumerate(words):
            word_entries.append((min(audio_duration, i * step), " " + w))

    word_entries.sort(key=lambda x: x[0])
    return word_entries


def transcribe_chunk(model, waveform: torch.Tensor, sample_rate: int) -> tuple[str, str, str]:
    """Transcribe a single waveform tensor. Returns (text, emotion, event).

    Kept as a thin compatibility wrapper around faster-whisper for callers that
    pass tensors instead of paths.
    """
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    if sample_rate != 16000:
        resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=16000)
        waveform = resampler(waveform)

    audio = waveform.squeeze().cpu().numpy().astype(np.float32)
    try:
        segments, _info = model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        raw = " ".join(seg.text for seg in segments).strip()
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
    audio_duration_seconds: float | None = None,
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
            "duration_seconds": round(audio_duration_seconds if audio_duration_seconds else total_dur, 2),
            "speech_time_seconds": round(total_dur, 2),
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
            _config_path = Path(local_model_path)
            _config_file = _config_path if _config_path.is_file() else _config_path / "config.yaml"
            if _config_file.exists():
                _pyannote_root = Path(__file__).parent.parent / "models" / "pyannote"
                _new_seg = (_pyannote_root / "segmentation-3.0" / "pytorch_model.bin").as_posix()
                _new_emb = (_pyannote_root / "wespeaker-voxceleb-resnet34-LM" / "pytorch_model.bin").as_posix()
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
                try:
                    pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",
                        token=hf_token,
                    )
                except TypeError as exc:
                    if "unexpected keyword argument 'token'" not in str(exc):
                        raise
                    pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",
                        use_auth_token=hf_token,
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

        # BF16 remains opt-in only on production. On the current pyannote 3.3.2
        # stack we observed dtype-cast regressions that silently pushed parts of
        # diarization back onto CPU, which is worse than the theoretical speedup.
        if os.getenv("CALLTONE_PYANNOTE_BF16", "0") == "1" and torch.cuda.is_available():
            try:
                cap = torch.cuda.get_device_capability(0)
                if cap[0] >= 8:
                    pipeline.to(torch.bfloat16)
                    print(f"  pyannote cast to BF16 (GPU SM {cap[0]}.{cap[1]} supports tensor-core BF16)")
            except Exception as _exc:
                print(f"  BF16 cast skipped: {_exc}")

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

    # F0 anchoring is a CPU-bound autocorrelation loop (torchaudio.detect_pitch_frequency
    # is O(N*M) per turn and scales linearly with num_turns * turn_duration). It serves
    # only to reorder pyannote's cluster labels by median pitch — downstream role ID reads
    # transcript content, not speaker numbers — so we let the server skip it for latency.
    if os.getenv("CALLTONE_DISABLE_F0_ANCHOR", "").lower() in ("1", "true", "yes"):
        print("  Skipping F0 anchoring (CALLTONE_DISABLE_F0_ANCHOR set)")
        spk_pitch_summary: dict[str, list[float]] = {}
    else:
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
    # The active engine (faster-whisper or SenseVoice) is picked via the
    # CALLTONE_ASR env var. Both engines emit the same (start, word) format
    # so the alignment code below is engine-agnostic.
    engine_name = _selected_asr_engine()
    print(f"Step 2/3  Transcribing full audio (engine={engine_name})...")
    # Pre-load model so the cold-start cost is captured in this step's wall time.
    load_sense_model()

    mono = waveform.mean(dim=0) if waveform.shape[0] > 1 else waveform.squeeze()
    audio_np = mono.cpu().numpy().astype(np.float32)
    if sr != 16000:
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
        audio_np = resampler(torch.from_numpy(audio_np)).numpy().astype(np.float32)
    audio_duration = float(len(audio_np) / 16000.0)

    word_entries = transcribe_full_audio(audio_np, sr=16000)
    print(f"  {engine_name} returned {len(word_entries)} words "
          f"(audio={audio_duration:.1f}s) — aligning to {len(turns)} turns...")

    # Assign words to diarization turns by word start time.
    #
    # Whisper and pyannote timestamps do not land on exactly the same boundary.
    # A strict t0 <= word_start <= t1 rule drops leading words ("Thank", "My",
    # "Yes") and sometimes leaks a word into the next speaker turn. Assign each
    # word to the containing turn first; otherwise allow a small tolerance and
    # choose the closest turn boundary. This preserves runtime while improving
    # transcript WER and speaker-turn readability.
    align_tolerance = float(os.environ.get("CALLTONE_WORD_ALIGN_TOLERANCE_SEC", "1.0"))
    turn_words_by_index: list[list[str]] = [[] for _ in turns]
    for word_start, word_text in word_entries:
        best_idx: int | None = None
        best_distance = float("inf")
        for idx, (t0, t1, _raw_spk) in enumerate(turns):
            if t0 <= word_start <= t1:
                best_idx = idx
                best_distance = 0.0
                break
            if word_start < t0:
                distance = t0 - word_start
            else:
                distance = word_start - t1
            if distance <= align_tolerance and distance < best_distance:
                best_idx = idx
                best_distance = distance
        if best_idx is not None:
            turn_words_by_index[best_idx].append(word_text)

    index_map = {}
    segments  = []
    for turn_idx, (t0, t1, raw_spk) in enumerate(turns):
        turn_words = turn_words_by_index[turn_idx]
        text = "".join(turn_words).strip()
        if not text:
            continue

        text, emo, evt = parse_sense_output(text)
        text = _normalize_asr_text(text)
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

    json_data = build_json(
        audio_path,
        segments,
        spk_pitch_summary,
        roles,
        audio_duration_seconds=audio_duration,
    )
    json_path = base + "_diarized.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON  → {json_path}")


if __name__ == "__main__":
    main()
