#!/usr/bin/env python3
"""
Download all required models for the grad_project pipeline.

Usage:
    python download_models.py                  # Download all models
    python download_models.py --list           # Show what will be downloaded
    python download_models.py --model llama    # Download a specific model
    python download_models.py --hf-token TOKEN # Pass HuggingFace token (required for pyannote)

Models required (~12.5 GB total):
  - Meta-Llama-3.1-8B-Instruct-Q8_0.gguf    ~8.0 GB  (skill_implementation)
  - whisper-large-v3                           ~3.0 GB  (LAYER_1 transcription)
  - resemble-enhance weights                  ~681 MB  (LAYER_1 audio enhancement)
  - Audio2Emotion-v3.0/network.onnx           ~1.2 GB  (LAYER_1 emotion detection)
  - pyannote/segmentation-3.0                 ~500 MB  (LAYER_1 diarization)
  - pyannote/wespeaker-voxceleb-resnet34-LM   ~500 MB  (LAYER_1 diarization)

NOTE: pyannote models require accepting terms at:
  https://huggingface.co/pyannote/segmentation-3.0
  https://huggingface.co/pyannote/speaker-diarization-3.1
  Then pass your HuggingFace token via --hf-token or set HF_TOKEN env var.
"""

import argparse
import os
import sys
from pathlib import Path

# Root of this repo
REPO_ROOT = Path(__file__).parent.resolve()

MODELS = {
    "llama": {
        "description": "Meta-Llama-3.1-8B-Instruct (Q8, GGUF) — used by skill_implementation",
        "size": "~8.0 GB",
        "dest": REPO_ROOT / "skill_implementation" / "models",
        "requires_token": False,
        "download": "huggingface_file",
        "repo_id": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf",
    },
    "whisper": {
        "description": "whisper-large-v3 — used by LAYER_1 transcription",
        "size": "~3.0 GB",
        "dest": REPO_ROOT / "LAYER_1" / "models" / "whisper" / "openai" / "whisper-large-v3",
        "requires_token": False,
        "download": "huggingface_snapshot",
        "repo_id": "openai/whisper-large-v3",
    },
    "resemble": {
        "description": "resemble-enhance weights — used by LAYER_1 audio enhancement",
        "size": "~681 MB",
        "dest": REPO_ROOT / "LAYER_1" / "models" / "resemble-enhance",
        "requires_token": False,
        "download": "huggingface_snapshot",
        "repo_id": "resemble-enhance/resemble-enhance",
    },
    "audio2emotion": {
        "description": "Audio2Emotion-v3.0 (ONNX) — used by LAYER_1 emotion detection",
        "size": "~1.2 GB",
        "dest": REPO_ROOT / "LAYER_1" / "audio_emotion_detection_enhanced" / "models" / "Audio2Emotion-v3.0",
        "requires_token": False,
        "download": "huggingface_snapshot",
        "repo_id": "nvidia/Audio2Emotion-v3.0",
    },
    "pyannote-segmentation": {
        "description": "pyannote/segmentation-3.0 — used by LAYER_1 diarization",
        "size": "~500 MB",
        "dest": REPO_ROOT / "LAYER_1" / "models" / "pyannote" / "segmentation-3.0",
        "requires_token": True,
        "download": "huggingface_snapshot",
        "repo_id": "pyannote/segmentation-3.0",
    },
    "pyannote-wespeaker": {
        "description": "pyannote/wespeaker-voxceleb-resnet34-LM — used by LAYER_1 diarization",
        "size": "~500 MB",
        "dest": REPO_ROOT / "LAYER_1" / "models" / "pyannote" / "wespeaker-voxceleb-resnet34-LM",
        "requires_token": True,
        "download": "huggingface_snapshot",
        "repo_id": "pyannote/wespeaker-voxceleb-resnet34-LM",
    },
}


def check_huggingface_hub():
    try:
        import huggingface_hub
        return True
    except ImportError:
        return False


def download_snapshot(repo_id, local_dir, token=None):
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        token=token,
    )


def download_file(repo_id, filename, local_dir, token=None):
    from huggingface_hub import hf_hub_download
    local_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(local_dir),
        token=token,
    )


def is_already_downloaded(model_key, model_info):
    dest = model_info["dest"]
    if not dest.exists():
        return False
    if model_info["download"] == "huggingface_file":
        return (dest / model_info["filename"]).exists()
    # For snapshots, check if dest is non-empty (has files beyond READMEs)
    files = list(dest.rglob("*"))
    model_extensions = {".pt", ".pth", ".bin", ".onnx", ".safetensors", ".gguf"}
    return any(f.suffix in model_extensions for f in files)


def print_model_list():
    print("\nModels required for grad_project:\n")
    total = 0
    for key, info in MODELS.items():
        token_note = "  [requires HF token]" if info["requires_token"] else ""
        print(f"  {key:<28} {info['size']:<12} {info['description']}{token_note}")
    print("\n  Total: ~12.5 GB")
    print()


def download_model(key, info, token=None):
    dest = info["dest"]
    print(f"\n[{key}] {info['description']}")
    print(f"  Source : {info['repo_id']}")
    print(f"  Target : {dest}")
    print(f"  Size   : {info['size']}")

    if is_already_downloaded(key, info):
        print(f"  Status : Already downloaded, skipping.")
        return True

    if info["requires_token"] and not token:
        print(f"  Status : SKIPPED — requires HuggingFace token.")
        print(f"           Accept terms at https://huggingface.co/{info['repo_id']}")
        print(f"           Then re-run: python download_models.py --model {key} --hf-token YOUR_TOKEN")
        return False

    dest.mkdir(parents=True, exist_ok=True)
    try:
        print(f"  Status : Downloading...")
        if info["download"] == "huggingface_file":
            download_file(info["repo_id"], info["filename"], dest, token=token)
        else:
            download_snapshot(info["repo_id"], dest, token=token)
        print(f"  Status : Done.")
        return True
    except Exception as e:
        print(f"  Status : FAILED — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download all models required for grad_project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--list", action="store_true", help="List all models and exit")
    parser.add_argument("--model", metavar="NAME", help="Download only this model (e.g. llama, whisper)")
    parser.add_argument("--hf-token", metavar="TOKEN", help="HuggingFace token (required for pyannote models)")
    args = parser.parse_args()

    if args.list:
        print_model_list()
        return

    # Resolve token from arg or environment
    token = args.hf_token or os.environ.get("HF_TOKEN")

    if not check_huggingface_hub():
        print("Error: huggingface_hub is not installed.")
        print("Install it with:  pip install huggingface-hub")
        sys.exit(1)

    print_model_list()

    # Warn about pyannote token requirement upfront
    pyannote_models = [k for k, v in MODELS.items() if v["requires_token"]]
    if not token:
        print("WARNING: No HuggingFace token provided.")
        print("         pyannote models will be skipped.")
        print("         To include them, pass: --hf-token YOUR_TOKEN")
        print("         or set the HF_TOKEN environment variable.\n")
        print("         First accept the terms at:")
        for k in pyannote_models:
            print(f"           https://huggingface.co/{MODELS[k]['repo_id']}")
        print()

    models_to_download = MODELS if not args.model else {args.model: MODELS[args.model]}

    if args.model and args.model not in MODELS:
        print(f"Error: Unknown model '{args.model}'. Use --list to see available models.")
        sys.exit(1)

    results = {}
    for key, info in models_to_download.items():
        results[key] = download_model(key, info, token=token)

    print("\n" + "=" * 60)
    print("Summary:")
    for key, ok in results.items():
        status = "OK" if ok else "SKIPPED/FAILED"
        print(f"  {key:<28} {status}")
    print("=" * 60)

    failed = [k for k, ok in results.items() if not ok]
    if failed:
        print(f"\n{len(failed)} model(s) were not downloaded. Re-run with --hf-token if needed.")
        sys.exit(1)
    else:
        print("\nAll models downloaded successfully.")


if __name__ == "__main__":
    main()
