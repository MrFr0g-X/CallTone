"""
Skill runner - executes skills with the appropriate backend.
"""

from pathlib import Path
from typing import Optional
from .types import SkillBundle

# Module-level backend cache — keyed by model path.
# Ensures Llama (and any other heavy model) is loaded only once per process,
# even when ConsensusRunner() is instantiated multiple times across calls.
_BACKEND_CACHE: dict = {}


def select_backend(model_dir: str):
    """
    Automatically select the appropriate backend based on model format.
    Returns a cached instance if the same model path was already loaded.

    Args:
        model_dir: Path to model directory or file

    Returns:
        Initialized backend instance (cached after first load)

    Raises:
        ValueError: If model format cannot be determined
    """
    cache_key = str(Path(model_dir).resolve())
    if cache_key in _BACKEND_CACHE:
        return _BACKEND_CACHE[cache_key]

    model_path = Path(model_dir)

    # Check for GGUF file
    if model_path.is_file() and model_path.suffix == '.gguf':
        from .backends.llama_cpp_backend import LlamaCppBackend
        backend = LlamaCppBackend(str(model_path))
        _BACKEND_CACHE[cache_key] = backend
        return backend

    # Check if directory contains GGUF files
    if model_path.is_dir():
        gguf_files = list(model_path.glob("*.gguf"))
        if gguf_files:
            from .backends.llama_cpp_backend import LlamaCppBackend
            backend = LlamaCppBackend(str(gguf_files[0]))
            _BACKEND_CACHE[cache_key] = backend
            return backend

        # Check for HuggingFace format (config.json)
        config_file = model_path / "config.json"
        if config_file.exists():
            from .backends.transformers_backend import TransformersBackend
            backend = TransformersBackend(str(model_path))
            _BACKEND_CACHE[cache_key] = backend
            return backend

    raise ValueError(
        f"Cannot determine model format for: {model_dir}\n"
        f"Expected either:\n"
        f"  - A .gguf file (for llama-cpp-python)\n"
        f"  - A directory containing .gguf files\n"
        f"  - A directory with config.json (for transformers)"
    )


def run_skill(bundle: SkillBundle, input_text: str, backend=None) -> str:
    """
    Execute a skill with the given input.
    
    Args:
        bundle: The SkillBundle containing all skill configuration
        input_text: Input text to process
        backend: Optional pre-initialized backend (for reuse)
        
    Returns:
        Generated output text
        
    Raises:
        ValueError: If model format is unsupported
        RuntimeError: If generation fails
    """
    # Select or use provided backend
    if backend is None:
        backend = select_backend(bundle['model_dir'])
    
    # Format user prompt with input
    user_prompt = bundle['user_prompt_template'].format(input_text=input_text)
    
    # Get decoding parameters
    decoding = bundle['decoding']
    
    # Generate output
    output = backend.generate(
        system_prompt=bundle['system_prompt'],
        user_prompt=user_prompt,
        temperature=decoding.get('temperature', 0.0),
        top_p=decoding.get('top_p', 1.0),
        max_tokens=decoding.get('max_tokens', 2048),
        stop=decoding.get('stop'),
    )
    
    # Ensure consistent whitespace handling
    output = output.strip()
    
    return output


def run_skill_with_validation(bundle: SkillBundle, input_text: str, validate_json: bool = True) -> str:
    """
    Run skill and optionally validate JSON output.
    
    Args:
        bundle: The SkillBundle
        input_text: Input text
        validate_json: Whether to validate output as JSON
        
    Returns:
        Generated output text
        
    Raises:
        ValueError: If output validation fails
    """
    output = run_skill(bundle, input_text)
    
    if validate_json:
        import json
        try:
            json.loads(output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Skill output is not valid JSON: {e}\nOutput:\n{output}")
    
    return output
