"""
Backend for HuggingFace models using transformers library.
"""

from pathlib import Path
from typing import Optional
import torch


class TransformersBackend:
    """Backend for running HuggingFace models with transformers."""
    
    def __init__(self, model_dir: str):
        """
        Initialize the transformers backend.
        
        Args:
            model_dir: Path to HuggingFace model directory
        """
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except ImportError:
            raise ImportError(
                "transformers is not installed. Install with: "
                "pip install transformers torch"
            )
        
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")
        
        config_file = self.model_dir / "config.json"
        if not config_file.exists():
            raise FileNotFoundError(f"config.json not found in {model_dir}")
        
        # Load model and tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
        self.model = AutoModelForCausalLM.from_pretrained(
            str(self.model_dir),
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self.model.eval()
        
        # Set pad token if not set
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
    
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
        # Format messages for chat template
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        # Generate with deterministic settings
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,  # Greedy decoding
                temperature=None,  # Not used when do_sample=False
                top_p=None,  # Not used when do_sample=False
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        
        # Decode output
        generated_text = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        )
        
        return generated_text.strip()
    
    def __repr__(self):
        return f"TransformersBackend(model={self.model_dir.name})"
