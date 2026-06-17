#!/usr/bin/env python3
"""
Full Pipeline Runner — Layer 1 → Layer 2

Runs the complete pipeline on an audio file:
  Layer 1: denoise → transcribe+diarize → role identification → emotion detection
  Layer 2: rate against company policy (7 criteria)

All outputs go into a single results folder.

Usage:
    conda run -n main python run_full_pipeline.py <audio.wav> --company "CompanyName" [--speakers N] [--output-dir DIR]
"""

import os
os.environ["DS_BUILD_OPS"] = "0"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # avoid fork warnings

# Vast containers often report far more logical CPUs than the process should
# actually use. Leaving BLAS/OpenMP unbounded triggers 90+ thread storms inside
# diarization/clustering and can stall the pipeline for minutes.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")

import sys

# Fix Windows subprocess Unicode encoding (cp1252 can't handle → ═ etc.)
if sys.platform == "win32":
    for _stream in ("stdout", "stderr"):
        _s = getattr(sys, _stream, None)
        if _s and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# ── Monkey-patch llama-cpp-python 0.3.x bug ──────────────────────────────────
# LlamaModel.__del__ crashes with "AttributeError: has no attribute 'sampler'"
# when the C++ model fails to load (partial init).  The patch silences that.
try:
    import llama_cpp._internals as _li
    _orig_close = _li.LlamaModel.close
    def _safe_llama_close(self):
        if not hasattr(self, "sampler"):
            return
        _orig_close(self)
    _li.LlamaModel.close = _safe_llama_close
except Exception:
    pass

# ── GPU optimizations ────────────────────────────────────────────────────────
import torch as _torch
if _torch.cuda.is_available():
    _torch.backends.cudnn.benchmark = True          # auto-tune cuDNN for fixed sizes
    _torch.set_float32_matmul_precision("high")     # TF32 on Ampere+ / Blackwell

# ── paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
LAYER1_DIR   = PROJECT_ROOT / "LAYER_1"
LAYER2_DIR   = PROJECT_ROOT / "LAYER_2"

sys.path.insert(0, str(LAYER1_DIR / "resemble-enhance"))
sys.path.insert(0, str(LAYER1_DIR / "pipeline"))
sys.path.insert(0, str(LAYER1_DIR))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "skill_implementation"))


# ── Layer 1 helpers (reused from run_pipeline.py) ────────────────────────────

# OPT-A4: SNR gate — skip resemble-enhance on already-clean telephony audio.
# Tuned via empirical spectral-flatness probe: clean telephony recordings
# typically score ≥ 18 dB. Anything below gets the full denoise pass.
# Threshold is overridable via CALLTONE_SNR_SKIP_DB for tuning/benchmarking;
# the default (18.0) preserves the original shipped behavior exactly.
try:
    _SNR_SKIP_THRESHOLD_DB = float(os.environ.get("CALLTONE_SNR_SKIP_DB", "18.0"))
except (TypeError, ValueError):
    _SNR_SKIP_THRESHOLD_DB = 18.0


def _estimate_snr_db(audio_path: str) -> float:
    """
    Quick SNR proxy via spectral flatness. Returns dB-like value where higher
    = cleaner audio (more tonal/voiced, less noise-like).

    Reads only the first 10 s of audio for speed (~50–100 ms total).
    Returns 0.0 on any failure so the gate fails safe → enhancement still runs.
    """
    try:
        import librosa
        import numpy as np
        y, _sr = librosa.load(audio_path, sr=None, mono=True, duration=10.0)
        flatness = librosa.feature.spectral_flatness(y=y)
        mean_flat = float(np.mean(flatness))
        return float(-10.0 * np.log10(max(mean_flat, 1e-6)))
    except Exception:
        return 0.0


def denoise_audio(input_path: str, mode: str = "denoise", force: bool = False) -> str:
    """
    Process audio before transcription.

    mode:
      "none"    — skip processing, return original path
      "denoise" — noise removal only (default, faster)
      "enhance" — full enhancement: denoise + super-resolution (slower)

    OPT-A4: an SNR gate skips resemble-enhance entirely when input audio is
    already clean (SNR proxy ≥ 18 dB). Saves 15–20 s for clean telephony.
    """
    import torch
    import torch.nn.functional as F
    import soundfile as sf
    from torchaudio.functional import resample as torchaudio_resample

    if mode == "none":
        print(f"\n{'='*70}")
        print("LAYER 1 — STEP 1: AUDIO PROCESSING SKIPPED (mode=none)")
        print(f"{'='*70}")
        return input_path

    # OPT-A4: SNR gate — return original path if audio is already clean.
    # ``force`` bypasses the gate (always denoise); used for benchmarking and
    # for operators who want to guarantee the denoise pass.
    snr_db = _estimate_snr_db(input_path)
    if not force and snr_db >= _SNR_SKIP_THRESHOLD_DB:
        print(f"\n{'='*70}")
        print("LAYER 1 — STEP 1: AUDIO ENHANCEMENT SKIPPED (SNR gate)")
        print(f"{'='*70}")
        print(f"Input:    {input_path}")
        print(f"SNR est.: {snr_db:.1f} dB (threshold: {_SNR_SKIP_THRESHOLD_DB} dB) — clean audio, skipping resemble-enhance")
        return input_path

    from resemble_enhance.enhancer.inference import denoise, enhance as _enhance

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n{'='*70}")
    print("LAYER 1 — STEP 1: DENOISING")
    print(f"{'='*70}")
    print(f"Input:    {input_path}")
    print(f"Device:   {device}")
    print(f"SNR est.: {snr_db:.1f} dB (threshold: {_SNR_SKIP_THRESHOLD_DB} dB) — running enhancement\n")

    dwav_np, sr = sf.read(input_path)
    original_length = len(dwav_np)
    dwav = torch.from_numpy(dwav_np).float()

    if dwav.dim() > 1:
        dwav = dwav.mean(dim=-1) if dwav.shape[-1] > 1 else dwav.squeeze()

    run_dir = LAYER1_DIR / "models" / "resemble-enhance" / "enhancer_stage2"
    if mode == "enhance":
        print("Enhancing (denoise + super-resolution)...")
        processed_wav, new_sr = _enhance(dwav, sr, device, run_dir=run_dir)
    else:
        print("Denoising...")
        processed_wav, new_sr = denoise(dwav, sr, device, run_dir=run_dir)

    if new_sr != sr:
        processed_wav = torchaudio_resample(processed_wav, orig_freq=new_sr, new_freq=sr)
        new_sr = sr

    current_length = processed_wav.shape[-1]
    if abs(current_length - original_length) > sr * 0.1:
        if current_length > original_length:
            processed_wav = processed_wav[:original_length]
        else:
            processed_wav = F.pad(processed_wav, (0, original_length - current_length))

    base = os.path.splitext(input_path)[0]
    out_path = f"{base}_denoised.wav"
    sf.write(out_path, processed_wav.cpu().numpy(), new_sr, subtype='PCM_16')
    print(f"Saved: {out_path}")
    return out_path


def transcribe_diarize(audio_path: str, num_speakers: int | None) -> tuple[str, str]:
    import transcribe_diarize as td

    print(f"\n{'='*70}")
    print("LAYER 1 — STEP 2: TRANSCRIPTION & DIARIZATION")
    print(f"{'='*70}")
    print(f"Input:    {audio_path}")
    print(f"Speakers: {num_speakers if num_speakers else 'auto-detect'}\n")

    original_argv = sys.argv.copy()
    sys.argv = ["transcribe_diarize.py", audio_path]
    if num_speakers:
        sys.argv.append(str(num_speakers))
    try:
        td.main()
    finally:
        sys.argv = original_argv

    base = os.path.splitext(audio_path)[0]
    return f"{base}_diarized.txt", f"{base}_diarized.json"


def run_role_identification(json_path: str, txt_path: str):
    print(f"\n{'='*70}")
    print("LAYER 1 — STEP 3: ROLE IDENTIFICATION")
    print(f"{'='*70}\n")

    from role_identification import identify_speaker_roles, apply_roles_to_outputs
    role_map = identify_speaker_roles(json_path)
    if role_map:
        apply_roles_to_outputs(json_path, txt_path, role_map)
        print(f"Roles applied: {role_map}")
    else:
        print("Warning: no roles detected, keeping generic labels.")


def run_emotion_detection(audio_path: str, json_path: str) -> tuple[str, str]:
    print(f"\n{'='*70}")
    print("LAYER 1 — STEP 4: EMOTION DETECTION")
    print(f"{'='*70}\n")

    from emotion_integration import enhance_diarization_with_emotions
    enhanced_json = enhance_diarization_with_emotions(audio_path, json_path)
    enhanced_txt = enhanced_json.replace('.json', '.txt')
    return enhanced_txt, enhanced_json


# ── Layer 2 ──────────────────────────────────────────────────────────────────

# OPT-A2: skip the LAYER 1 VRAM purge entirely on large GPUs (≥40 GB).
# A100 80 GB and similar can hold LAYER 1 models (~3.4 GB) + Qwen3-8B Q4_K_M
# (~5 GB) simultaneously, so reloading wastes 5–8 s per call.
_LARGE_VRAM_GB_THRESHOLD = 40.0
_KEEP_LAYER1_RESIDENT_MIN_FREE_GB = 55.0


def _gpu_total_vram_gb() -> float:
    """Total VRAM in GB for the first CUDA device (0.0 if no GPU)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        return torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    except Exception:
        return 0.0


def _gpu_free_vram_gb() -> float:
    """
    Real free VRAM in GB for the first CUDA device.

    Uses the CUDA driver's global view via ``torch.cuda.mem_get_info`` so we
    account for non-PyTorch allocations too (onnxruntime, llama.cpp, cuDNN
    workspaces). This is more accurate than ``memory_reserved`` which only sees
    PyTorch's allocator.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free_bytes, _total_bytes = torch.cuda.mem_get_info(0)
        return free_bytes / 1024 ** 3
    except Exception:
        return 0.0


def _free_layer1_vram() -> None:
    """
    Release VRAM held by Layer 1 models (Whisper, pyannote, ONNX emotion detector)
    before loading the Layer 2 LLM.

    On GPUs with ≥40 GB VRAM (e.g. A100 80 GB), this is a no-op — there's
    enough headroom to keep LAYER 1 resident while LAYER 2 loads, saving the
    5–8 s reload cost per call (OPT-A2). Smaller GPUs (RTX 30/40-series with
    8–24 GB) still get the full purge to avoid OOM.

    PyTorch's allocator keeps reserved blocks invisible to llama.cpp's CUDA
    allocator.  Nulling the module-level caches + calling empty_cache() returns
    those blocks to the driver so the LLM can load.

    This function is safe to call even if Layer 1 was never run in this process.
    """
    import gc
    import torch

    total_gb = _gpu_total_vram_gb()
    free_gb = _gpu_free_vram_gb()
    if (
        total_gb >= _LARGE_VRAM_GB_THRESHOLD
        and free_gb >= _KEEP_LAYER1_RESIDENT_MIN_FREE_GB
    ):
        print(
            f"  [VRAM] {total_gb:.0f} GB GPU detected, {free_gb:.0f} GB free "
            f"— keeping LAYER 1 resident (OPT-A2)"
        )
        return
    if total_gb >= _LARGE_VRAM_GB_THRESHOLD:
        print(
            f"  [VRAM] {total_gb:.0f} GB GPU detected but only {free_gb:.0f} GB free "
            f"(< {_KEEP_LAYER1_RESIDENT_MIN_FREE_GB:.0f} GB) — freeing LAYER 1 before LAYER 2"
        )

    # Clear Whisper + pyannote caches (transcribe_diarize.py module globals)
    try:
        import transcribe_diarize as _td
        _td._WHISPER_MODEL     = None
        _td._PYANNOTE_PIPELINE = None
        if hasattr(_td, "_SENSEVOICE_MODEL"):
            _td._SENSEVOICE_MODEL = None
    except Exception:
        pass

    # Clear resemble-enhance denoiser — uses @functools.cache, holds model on GPU
    try:
        from resemble_enhance.enhancer.inference import load_enhancer
        load_enhancer.cache_clear()
    except Exception:
        pass

    # Clear Audio2Emotion detector cache (emotion_integration.py module global).
    # The ONNX session holds its own CUDA memory, so we must delete the session
    # explicitly — torch.cuda.empty_cache() does NOT release ONNX allocations.
    try:
        from emotion_integration import _DETECTOR_CACHE as _edc
        for det in _edc.values():
            if hasattr(det, "onnx_session") and det.onnx_session is not None:
                del det.onnx_session
                det.onnx_session = None
        _edc.clear()
    except Exception:
        pass

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        reserved_mb = torch.cuda.memory_reserved(0) // 1024 ** 2
        free_mb     = (torch.cuda.get_device_properties(0).total_memory
                       - torch.cuda.memory_reserved(0)) // 1024 ** 2
        print(f"  [VRAM] PyTorch reserved: {reserved_mb} MB | CUDA free: {free_mb} MB")


def run_layer2(layer1_json: str, company_name: str, output_path: str,
               injection_scan_mode: str = "llm",
               use_consensus: bool = False) -> dict:
    print(f"\n{'='*70}")
    print("LAYER 2 — CALL QUALITY RATING")
    print(f"{'='*70}")
    print(f"Transcript:       {layer1_json}")
    print(f"Company:          {company_name}")
    print(f"Output:           {output_path}")
    print(f"Injection scan:   {injection_scan_mode}\n")
    print(f"Consensus:        {use_consensus}\n")

    # Free VRAM used by Layer 1 models so the Layer 2 LLM has room to load.
    # This is a no-op when Layer 1 was not run in the same process.
    _free_layer1_vram()

    from LAYER_2.pipeline import run_layer2_pipeline, InjectionBlockedError
    try:
        result = run_layer2_pipeline(
            layer1_json_path=layer1_json,
            company_name=company_name,
            use_consensus=use_consensus,
            output_path=output_path,
            injection_scan_mode=injection_scan_mode,
        )
    except InjectionBlockedError as e:
        print(f"\n{'!'*70}")
        print("SECURITY ALERT — CALL BLOCKED")
        print(f"{'!'*70}")
        print(f"Prompt injection detected in transcript.")
        print(f"Severity: {e.scan_result.severity}")
        print(f"Reason:   {e.scan_result.overall_reasoning}")
        if e.scan_result.suspicious_segments:
            print("\nSuspicious segments:")
            for seg in e.scan_result.suspicious_segments[:5]:
                print(f"  [{seg.get('speaker','?')}] \"{seg.get('quote','')[:100]}\"")
                print(f"    → {seg.get('explanation','')}")
        print(f"\nThis call will NOT be rated. Flag for supervisor review.")
        print(f"{'!'*70}\n")
        raise
    return result


# ── pretty print the Layer 2 result ─────────────────────────────────────────

def print_rating_summary(result: dict):
    print(f"\n{'='*70}")
    print("RATING SUMMARY")
    print(f"{'='*70}")
    print(f"Company:         {result.get('company_name')}")
    print(f"Overall Score:   {result.get('overall_weighted_score')} / 100")
    print(f"Scoring Method:  {result.get('scoring_method')}")
    print()

    weights = {
        "script_compliance":    0.25,
        "factual_accuracy":     0.25,
        "politeness_tone":      0.15,
        "empathy":              0.10,
        "conflict_detection":   0.15,
        "issue_resolution":     0.05,
        "overall_severity":     0.05,
    }

    criteria = result.get("criteria_ratings", {})
    print(f"  {'Criterion':<28} {'Score':>6}  {'Weight':>7}  Summary")
    print(f"  {'-'*28}  {'-'*6}  {'-'*7}  {'-'*35}")
    for criterion, info in criteria.items():
        score   = info.get("score", "?")
        weight  = f"{weights.get(criterion, 0)*100:.0f}%"
        summary = info.get("summary", "")[:60]
        label   = criterion.replace("_", " ").title()
        print(f"  {label:<28} {str(score):>6}  {weight:>7}  {summary}")

    print()
    graph = result.get("graph_stats", {})
    print(f"Graph: {graph.get('total_nodes')} nodes, {graph.get('total_edges')} edges")


# ── main ─────────────────────────────────────────────────────────────────────

def run_layer3(rating_json: str, output_dir: str, mode: str, use_skill: bool) -> dict:
    print(f"\n{'='*70}")
    print("LAYER 3 — REPORT GENERATION")
    print(f"{'='*70}")
    from LAYER_3.pipeline import run_layer3_pipeline
    return run_layer3_pipeline(
        layer2_json_path=rating_json,
        output_dir=output_dir,
        mode=mode,
        use_skill=use_skill,
    )


def main():
    parser = argparse.ArgumentParser(description="Full pipeline: Layer 1 → Layer 2 → Layer 3")
    parser.add_argument("audio_file", help="Path to the input .wav audio file")
    parser.add_argument("--company", required=True, help="Company name for Layer 2 rating")
    parser.add_argument("--speakers", type=int, default=None, help="Number of speakers (default: auto)")
    parser.add_argument("--output-dir", default=None, help="Output folder (default: auto-named next to audio)")
    parser.add_argument(
        "--skip-layer1", action="store_true",
        help="Skip Layer 1 and reuse existing denoised/transcribed files next to the audio."
             " Useful for re-running Layer 2 without re-processing the audio.",
    )
    parser.add_argument(
        "--report", choices=["simple", "narrative", "both", "none"], default="both",
        help="Layer 3 report mode (default: both). Use 'none' to skip report generation.",
    )
    parser.add_argument(
        "--report-no-skill", action="store_true",
        help="(narrative mode) Skip the LLM for report generation; format Layer 2 data directly.",
    )
    parser.add_argument(
        "--injection-scan", choices=["llm", "static", "off"], default="llm",
        help="Prompt injection scan mode: 'llm' (default) = static + LLM detector, "
             "'static' = regex only (faster), 'off' = disabled (not recommended).",
    )
    parser.add_argument(
        "--asr", choices=["fasterwhisper", "sensevoice"], default=None,
        help="ASR engine to use. Default = fasterwhisper (also via CALLTONE_ASR env). "
             "Set 'sensevoice' to use Alibaba/FunASR SenseVoiceSmall.",
    )
    parser.add_argument(
        "--use-consensus", action="store_true",
        help="Run 3-pass consensus scoring for Layer 2 instead of one deterministic pass.",
    )
    parser.add_argument(
        "--denoise", choices=["auto", "force", "off"], default="auto",
        help="Audio denoise policy: 'auto' (default) = SNR gate decides (skip clean "
             "audio); 'force' = always denoise; 'off' = never denoise.",
    )
    args = parser.parse_args()

    # Propagate --asr to transcribe_diarize via env var (subprocess-safe).
    if args.asr:
        os.environ["CALLTONE_ASR"] = args.asr

    audio_file = args.audio_file
    if not os.path.exists(audio_file):
        print(f"Error: file not found: {audio_file}")
        sys.exit(1)

    # ── Create output folder ──────────────────────────────────────────────────
    audio_stem = Path(audio_file).stem
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(audio_file).parent / f"{audio_stem}_full_pipeline_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print("FULL PIPELINE — LAYER 1 + LAYER 2 + LAYER 3")
    print(f"{'='*70}")
    print(f"Audio:      {audio_file}")
    print(f"Company:    {args.company}")
    print(f"Speakers:   {args.speakers if args.speakers else 'auto'}")
    print(f"Output dir: {output_dir}")
    print(f"Skip L1:    {args.skip_layer1}")
    print(f"Started:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Layer 1 ───────────────────────────────────────────────────────────────

    if args.skip_layer1:
        # Reuse existing Layer 1 outputs — locate them next to the audio file
        base = os.path.splitext(audio_file)[0]
        # Denoise may have been skipped by the SNR gate, in which case the
        # original audio path is the effective "denoised" input.
        denoised_path = (
            f"{base}_denoised.wav"
            if os.path.exists(f"{base}_denoised.wav")
            else audio_file
        )
        # Support both cache layouts:
        #   - denoise ran       → *_denoised_diarized(_with_emotions).json
        #   - denoise skipped   → *_diarized(_with_emotions).json
        json_candidates = [
            f"{base}_denoised_diarized_with_emotions.json",
            f"{base}_diarized_with_emotions.json",
            f"{base}_denoised_diarized.json",
            f"{base}_diarized.json",
        ]
        json_path = next((p for p in json_candidates if os.path.exists(p)), json_candidates[0])
        txt_path  = json_path.replace(".json", ".txt")
        for p in [denoised_path, json_path, txt_path]:
            if not os.path.exists(p):
                print(f"Error: --skip-layer1 requires existing file: {p}")
                sys.exit(1)
        print(f"\n[SKIP LAYER 1]  Reusing: {json_path}")
    else:
        # Step 1: Denoise
        _denoise_mode = "none" if args.denoise == "off" else "denoise"
        denoised_path = denoise_audio(
            audio_file, mode=_denoise_mode, force=(args.denoise == "force")
        )

        # Step 2: Transcribe + diarize
        txt_path, json_path = transcribe_diarize(denoised_path, args.speakers)

        # Step 3: Role identification
        try:
            run_role_identification(json_path, txt_path)
        except Exception as e:
            print(f"Warning: role identification failed: {e}")

        # Free Whisper + pyannote VRAM so Audio2Emotion can load on GPU
        import gc as _gc
        try:
            import transcribe_diarize as _td
            _td._WHISPER_MODEL     = None
            _td._PYANNOTE_PIPELINE = None
        except Exception:
            pass
        try:
            from resemble_enhance.enhancer.inference import load_enhancer
            load_enhancer.cache_clear()
        except Exception:
            pass
        _gc.collect()
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()

        # Step 4: Emotion detection
        try:
            txt_path, json_path = run_emotion_detection(denoised_path, json_path)
        except Exception as e:
            print(f"Warning: emotion detection failed: {e}")

    # ── Layer 2 ───────────────────────────────────────────────────────────────
    # (VRAM is freed inside run_layer2 before loading the LLM)

    rating_output = str(output_dir / "layer2_ratings.json")
    try:
        result = run_layer2(json_path, args.company, rating_output,
                            injection_scan_mode=args.injection_scan,
                            use_consensus=args.use_consensus)
        print_rating_summary(result)
    except Exception as e:
        import traceback
        print(f"\nLayer 2 failed: {e}")
        traceback.print_exc()
        result = None

    # ── Layer 3 — Report Generation ───────────────────────────────────────────

    layer3_outputs = {}
    if args.report != "none" and result:
        try:
            layer3_outputs = run_layer3(
                rating_json=rating_output,
                output_dir=str(output_dir),
                mode=args.report,
                use_skill=not args.report_no_skill,
            )
        except Exception as e:
            import traceback
            print(f"\nLayer 3 failed: {e}")
            traceback.print_exc()

    # ── Collect all outputs into the folder ──────────────────────────────────

    print(f"\n{'='*70}")
    print("COLLECTING OUTPUTS")
    print(f"{'='*70}")

    files_to_copy = [
        denoised_path,          # denoised wav
        txt_path,               # transcript txt (with emotions + roles)
        json_path,              # transcript json (with emotions + roles)
        rating_output,          # layer2 ratings json
    ]

    for src in files_to_copy:
        if src and os.path.exists(src):
            dst = output_dir / Path(src).name
            try:
                shutil.copy2(src, dst)
                size = os.path.getsize(dst)
                print(f"  Copied: {Path(src).name}  ({size//1024} KB)")
            except shutil.SameFileError:
                size = os.path.getsize(src)
                print(f"  Already in folder: {Path(src).name}  ({size//1024} KB)")

    # Write a pipeline summary
    summary = {
        "pipeline_run": datetime.now().isoformat(),
        "input_audio": str(audio_file),
        "company": args.company,
        "speakers": args.speakers,
        "layer1": {
            "denoised_audio": str(denoised_path),
            "transcript_txt": str(txt_path),
            "transcript_json": str(json_path),
            "features": ["denoise", "transcription", "diarization", "role_identification", "emotion_detection"],
        },
        "layer2": {
            "ratings_json": rating_output,
            "overall_score": result.get("overall_weighted_score") if result else None,
            "criteria": {
                k: v.get("score") for k, v in result.get("criteria_ratings", {}).items()
            } if result else {},
        },
        "layer3": {
            "report_mode": args.report,
            "outputs": layer3_outputs,
        },
    }
    summary_path = output_dir / "pipeline_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved:  pipeline_summary.json")

    print(f"\n{'='*70}")
    print("PIPELINE COMPLETE")
    print(f"{'='*70}")
    print(f"All outputs in: {output_dir}")
    if result:
        print(f"Overall Score:  {result.get('overall_weighted_score')} / 100")
    if layer3_outputs:
        print("Reports generated:")
        for label, fpath in layer3_outputs.items():
            print(f"  {label}: {Path(fpath).name}")
    print(f"Finished:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()
