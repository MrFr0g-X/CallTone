# Models Directory

Place your local LLM models here.

## Expected Model

The default skill configuration expects:
```
Meta-Llama-3.1-8B-Instruct-Q8_0.gguf
```

## Download Instructions

### Using huggingface-cli:

```bash
pip install huggingface-hub

# Download GGUF version
huggingface-cli download bartowski/Meta-Llama-3.1-8B-Instruct-GGUF \
  Meta-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --local-dir .
```

### Alternative: wget

```bash
wget https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf
```

## Using Your Own Model

If you already have the model elsewhere, create a symlink:

```bash
ln -s /path/to/your/model.gguf Meta-Llama-3.1-8B-Instruct-Q8_0.gguf
```

Or update the `model_dir` in your skill.py files to point to your model location.

## Supported Formats

- **GGUF** (recommended): Fast, quantized, works with llama-cpp-python
- **HuggingFace**: Standard PyTorch models with config.json
