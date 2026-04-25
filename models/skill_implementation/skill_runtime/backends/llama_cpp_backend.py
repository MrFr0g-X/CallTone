"""
Backend for GGUF models using llama-cpp-python.

Supports both Llama-3.1 and Qwen3 chat templates. Auto-detects from model
filename. Strips Qwen3 <think>...</think> chain-of-thought blocks before
returning output so downstream JSON parsing is unaffected.

Logs every LLM call (prompt hash, token counts, latency) for AI-output
monitoring and audit (Maturity-Checklist C5).
"""

import atexit
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("calltone.llm")


# Stripped before JSON parsing so Qwen3 thinking-mode CoT doesn't leak
# into the rating output. Compiled once at module load.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _patch_llama_model_del() -> None:
    """
    Monkey-patch LlamaModel.close so it tolerates partial initialisation.

    llama-cpp-python 0.3.x has a bug: if the C++ model fails to load (e.g.
    CUDA OOM), the Python LlamaModel wrapper is only partially constructed —
    the `sampler` attribute is never set.  When the GC later calls __del__
    → close(), it crashes:
        AttributeError: 'LlamaModel' object has no attribute 'sampler'

    The patch guards that access so the error is swallowed silently instead
    of being printed as a confusing "Exception ignored" traceback.
    """
    try:
        import llama_cpp._internals as _li

        _orig_close = _li.LlamaModel.close

        def _safe_close(self):
            if not hasattr(self, "sampler"):
                return          # object was never fully initialised — skip
            _orig_close(self)

        _li.LlamaModel.close = _safe_close
    except Exception:
        pass    # If llama_cpp layout changes, silently skip the patch


_patch_llama_model_del()


def _detect_chat_format(model_path: Path) -> str:
    """
    Pick chat template based on model filename.

    Returns "qwen3" for Qwen3-* and Qwen2.5-* models, else "llama3" (default).
    Filename match is case-insensitive.
    """
    name = model_path.name.lower()
    if "qwen3" in name or "qwen2.5" in name or "qwen-2.5" in name or "qwen-3" in name:
        return "qwen3"
    return "llama3"


class LlamaCppBackend:
    """Backend for running GGUF models with llama-cpp-python."""

    def __init__(self, model_path: str):
        """
        Initialize the llama-cpp backend.

        Args:
            model_path: Path to .gguf model file
        """
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python is not installed. Install with: "
                "pip install llama-cpp-python"
            )

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self.chat_format = _detect_chat_format(self.model_path)

        # Offload all layers to GPU when available — ~10x faster than CPU for inference
        import torch
        n_gpu_layers = -1 if torch.cuda.is_available() else 0

        # Load model with deterministic settings.
        # If loading fails (e.g. OOM), set model=None so _cleanup is a no-op
        # and the partially-initialised LlamaModel C++ object can be GC'd
        # without triggering "AttributeError: has no attribute 'sampler'".
        self.model = None
        try:
            self.model = Llama(
                model_path=str(self.model_path),
                n_ctx=8192,
                n_threads=4,
                n_gpu_layers=n_gpu_layers,
                seed=12345,  # Fixed seed for determinism
                verbose=False,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load GGUF model: {self.model_path}\n"
                f"  Cause: {exc}\n"
                f"  Tip: if CUDA out-of-memory, free GPU memory before loading "
                f"(e.g. torch.cuda.empty_cache() after Layer 1)."
            ) from exc

        # Explicitly free the model before Python teardown so llama-cpp's
        # LlamaModel.__del__ never fires in a partially-initialised state
        # (avoids "AttributeError: 'LlamaModel' has no attribute 'sampler'").
        atexit.register(self._cleanup)

    def _format_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Build the full chat prompt for the active chat format."""
        if self.chat_format == "qwen3":
            # Qwen3 ChatML template. Qwen3 supports inline /think and /no_think
            # directives at the end of the system prompt to toggle CoT mode.
            return (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
        # Default: Llama-3.1 Instruct template.
        # Note: llama.cpp prepends <|begin_of_text|> automatically; omit it here.
        return (
            f"<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_prompt}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_prompt}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

    def _default_stop(self) -> list:
        """Stop tokens for the active chat format."""
        if self.chat_format == "qwen3":
            return ["<|im_end|>", "<|endoftext|>"]
        return ["<|eot_id|>", "<|end_of_text|>"]

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        max_tokens: int = 2048,
        stop: Optional[list] = None,
        **kwargs,
    ) -> str:
        """
        Generate text using the model.

        - Auto-selects chat template (Llama-3.1 or Qwen3) from model filename.
        - Strips Qwen3 <think>...</think> chain-of-thought blocks from output.
        - Logs prompt hash + token counts + latency for monitoring/audit.

        Returns:
            Generated text string (think block stripped if present).
        """
        if self.model is None:
            raise RuntimeError("LlamaCppBackend has no loaded model (load failed at init).")

        full_prompt = self._format_prompt(system_prompt, user_prompt)
        stop_tokens = stop or self._default_stop()

        t0 = time.perf_counter()
        response = self.model(
            full_prompt,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop_tokens,
            echo=False,
            seed=12345,  # Fixed seed for determinism
        )
        elapsed = time.perf_counter() - t0

        generated_text = response["choices"][0]["text"].strip()

        # Strip Qwen3 chain-of-thought block before returning so downstream
        # JSON parsing is unaffected. Safe no-op for Llama (no <think> tags).
        cleaned = _THINK_BLOCK_RE.sub("", generated_text).strip()

        # Structured log per LLM call (Maturity-Checklist C5: AI output monitoring).
        # prompt_hash lets us detect prompt drift without logging raw PII.
        try:
            prompt_hash = hashlib.sha256(full_prompt.encode("utf-8")).hexdigest()[:16]
            usage = response.get("usage", {}) or {}
            log.info(
                "llm_call",
                extra={
                    "event": "llm_call",
                    "prompt_hash": prompt_hash,
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "latency_s": round(elapsed, 3),
                    "model": self.model_path.stem,
                    "chat_format": self.chat_format,
                    "thinking_used": "<think>" in generated_text,
                },
            )
        except Exception:
            pass  # Logging must never break inference

        return cleaned

    def _cleanup(self):
        """Eagerly free the Llama model so llama-cpp's __del__ runs while the
        interpreter is still fully operational (avoids sampler AttributeError)."""
        if getattr(self, "model", None) is not None:
            del self.model
            self.model = None

    def __repr__(self):
        return f"LlamaCppBackend(model={self.model_path.name}, chat_format={self.chat_format})"
