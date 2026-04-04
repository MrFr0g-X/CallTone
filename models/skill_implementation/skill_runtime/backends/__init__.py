"""
Backend implementations for different model formats.

Backends are imported lazily to avoid requiring all dependencies at once.
"""

__all__ = ['LlamaCppBackend', 'TransformersBackend']


def __getattr__(name):
    if name == 'LlamaCppBackend':
        from .llama_cpp_backend import LlamaCppBackend
        return LlamaCppBackend
    if name == 'TransformersBackend':
        from .transformers_backend import TransformersBackend
        return TransformersBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
