"""
Backend for GGUF models using llama-cpp-python.
"""

import atexit
from pathlib import Path
from typing import Optional


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
    
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        max_tokens: int = 2048,
        stop: Optional[list] = None,
        **kwargs
    ) -> str:
        """
        Generate text using the model.
        
        Returns:
            Generated text string
        """
        # Format prompt for Llama-3.1-Instruct
        # Note: llama.cpp prepends <|begin_of_text|> automatically; omit it here.
        full_prompt = (
            f"<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_prompt}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_prompt}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
        
        if self.model is None:
            raise RuntimeError("LlamaCppBackend has no loaded model (load failed at init).")

        # Ensure deterministic generation
        response = self.model(
            full_prompt,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop or ["<|eot_id|>", "<|end_of_text|>"],
            echo=False,
            seed=12345,  # Fixed seed
        )
        
        # Extract generated text
        generated_text = response['choices'][0]['text']
        
        # Clean up and return
        return generated_text.strip()
    
    def _cleanup(self):
        """Eagerly free the Llama model so llama-cpp's __del__ runs while the
        interpreter is still fully operational (avoids sampler AttributeError)."""
        if getattr(self, 'model', None) is not None:
            del self.model
            self.model = None

    def __repr__(self):
        return f"LlamaCppBackend(model={self.model_path.name})"
