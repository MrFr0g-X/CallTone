"""
Backend for GGUF models using llama-cpp-python.
"""

from pathlib import Path
from typing import Optional


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
        
        # Load model with deterministic settings
        self.model = Llama(
            model_path=str(self.model_path),
            n_ctx=8192,
            n_threads=4,
            seed=12345,  # Fixed seed for determinism
            verbose=False,
        )
    
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
        full_prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""
        
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
    
    def __repr__(self):
        return f"LlamaCppBackend(model={self.model_path.name})"
