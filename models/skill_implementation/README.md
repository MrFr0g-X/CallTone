# Prompt-Only Skills System

A lightweight framework for creating deterministic, reusable LLM skills using local models. Skills are **prompt-only** functions that contain no logic - just prompt text and configuration.

## What is a "Prompt-Only Skill"?

A skill is a single-purpose LLM task defined by:
- **Prompts only**: System prompt + user prompt template
- **No logic**: No loops, classes, conditionals, or complex control flow
- **Deterministic**: Same input always produces same output
- **Local models**: Runs entirely on your infrastructure

Think of skills as "frozen" LLM configurations that your team can share and reuse.

## Quick Start

### Installation

```bash
cd /home/mazen/grad_project/skill_implementation
pip install -r requirements.txt
```

### Download Model (if needed)

The framework expects the model at:
```
models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf
```

If you need to download it:
```bash
# Using huggingface-cli
huggingface-cli download bartowski/Meta-Llama-3.1-8B-Instruct-GGUF \
  Meta-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --local-dir models/
```

### Run a Skill

```bash
# List available skills
python runner/run_skill.py --list

# Run with file input
python runner/run_skill.py --skill identify-call-roles --file examples/sample_transcript.txt

# Run with text input
python runner/run_skill.py --skill identify-call-roles --text "SPEAKER_A: Hello, support here."

# Validate a skill without running
python runner/run_skill.py --skill identify-call-roles --validate-only
```

## Creating a New Skill

### 1. Create Skill Folder Structure

```bash
mkdir -p skills/my-new-skill/references
cd skills/my-new-skill
```

### 2. Create SKILL.md

```markdown
---
name: my-new-skill
description: Brief description of what this skill does
version: 1.0.0
author: Your Name
---

# My New Skill

## Purpose
Explain what this skill does.

## Input Format
Describe expected input.

## Output Format
Describe expected output (prefer JSON).

## Example
Show input/output example.
```

### 3. Create skill.py (PROMPT-ONLY!)

```python
"""
Skill: my-new-skill

PROMPT-ONLY - contains NO logic, loops, classes, or conditionals.
"""

def get_my_new_skill_skill_bundle():
    """
    Return skill bundle with prompts and configuration only.
    """
    
    return {
        "name": "my-new-skill",
        
        "model_dir": "/home/mazen/grad_project/skill_implementation/models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf",
        
        "system_prompt": """You are a helpful assistant that [does X].

Your output must be [format], with no additional text.""",
        
        "user_prompt_template": """[Task description]

INPUT:
{input_text}

OUTPUT:""",
        
        "decoding": {
            "temperature": 0.0,      # MUST be 0.0 for determinism
            "top_p": 1.0,            # MUST be 1.0 for determinism
            "max_tokens": 1024,
            "seed": 12345,
            "do_sample": False,      # MUST be False for determinism
            "stop": ["\n\n\n"],
        },
        
        "output_schema": {
            "type": "object",
            # Define your expected JSON schema
        }
    }
```

### 4. Validate Your Skill

```bash
python runner/run_skill.py --skill my-new-skill --validate-only
```

## Prompt-Only Constraints

Skills MUST follow these rules:

### ✅ ALLOWED in skill.py:
- Simple variable assignments
- String concatenation
- Dictionary/list literals
- Return statements
- Comments

### ❌ FORBIDDEN in skill.py:
- `for` loops
- `while` loops
- `class` definitions
- `if`/`elif`/`else` conditionals
- `try`/`except` blocks
- Function calls (except `return`)
- Imports inside function

The validator will automatically reject skills that violate these rules.

## Determinism Contract

All skills MUST be deterministic:

**Same input + same skill + same model = identical output every run**

Enforced by:
1. `temperature=0.0` (greedy decoding)
2. `top_p=1.0` (no nucleus sampling)
3. `do_sample=False` (no sampling)
4. `seed=12345` (fixed seed)
5. Stable prompts (no timestamps, no randomness)

Test determinism:
```bash
python tests/test_determinism.py
```

## Supported Model Formats

### GGUF (llama-cpp-python)
- `.gguf` files
- Fast inference on CPU/GPU
- Recommended for production

### HuggingFace (transformers)
- Models with `config.json`
- Requires more VRAM
- Good for fine-tuned models

The framework automatically selects the right backend.

## Architecture

```
skill_implementation/
├── skills/                    # Your skill definitions (prompt-only)
│   └── identify-call-roles/
│       ├── SKILL.md          # Documentation + metadata
│       ├── skill.py          # Prompt-only bundle function
│       └── references/       # Optional reference materials
├── skill_runtime/            # Framework code (CAN have logic)
│   ├── types.py             # Type definitions
│   ├── loader.py            # Dynamic skill loading
│   ├── validator.py         # Constraint enforcement
│   ├── runner.py            # Skill execution
│   └── backends/            # Model backends
│       ├── llama_cpp_backend.py
│       └── transformers_backend.py
├── runner/
│   └── run_skill.py         # CLI interface
├── examples/                # Sample inputs
├── tests/                   # Automated tests
└── README.md               # This file
```

## API Usage

```python
from skill_runtime import load_skill, run_skill, validate_skill

# Load a skill
bundle = load_skill("identify-call-roles")

# Validate it
is_valid, errors = validate_skill("identify-call-roles", bundle)
if not is_valid:
    print("Validation errors:", errors)

# Run it
input_text = "SPEAKER_A: Hello!\nSPEAKER_B: Hi there."
output = run_skill(bundle, input_text)
print(output)
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python tests/test_determinism.py
python tests/test_skill_validation.py

# Quick validation test
python runner/run_skill.py --skill identify-call-roles --validate-only
```

## Troubleshooting

### "llama-cpp-python not installed"
```bash
pip install llama-cpp-python
```

### "Model file not found"
Check that your model is at:
```
/home/mazen/grad_project/skill_implementation/models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf
```

### "Skill validation failed: forbidden keyword"
Your `skill.py` contains logic (loops, conditionals, etc.). Skills must be prompt-only. Move any logic to the runtime or redesign as prompts.

### "Outputs not deterministic"
Check your decoding settings:
- `temperature` must be `0.0`
- `top_p` must be `1.0`
- `do_sample` must be `False`
- Prompts must not contain timestamps or random elements

### "Cannot determine model format"
Ensure your model directory contains either:
- A `.gguf` file (for llama-cpp-python), OR
- A `config.json` file (for transformers)

## Best Practices

1. **One task per skill**: Keep skills focused and single-purpose
2. **Strict output formats**: Prefer JSON with schemas for structured output
3. **Test determinism**: Always verify same input = same output
4. **Document thoroughly**: SKILL.md should have clear examples
5. **Quote extraction**: When extracting quotes, instruct model to copy exactly
6. **Word limits**: Enforce strict word/character limits in prompts
7. **No markdown**: Explicitly forbid markdown in output unless needed

## Team Workflow

1. **Create**: Developer creates skill in `skills/new-skill/`
2. **Validate**: Run validator to check constraints
3. **Test**: Verify determinism with multiple runs
4. **Document**: Update SKILL.md with examples
5. **Share**: Commit to repo, team can use immediately
6. **Reuse**: Any team member runs with `run_skill.py`

## License

Internal use only.
