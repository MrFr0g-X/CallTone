# LAYER 2 Architecture - Call Quality Rating Pipeline

## Overview

Layer 2 takes the output from Layer 1 (transcription + diarization + emotion detection)
and rates the customer service agent on 7 criteria. It uses company-specific context
to evaluate compliance with scripts, factual accuracy, and behavioral standards.

The QA head does NOT need any technical knowledge. They write their company's policies
as a plain text file — the system handles parsing, structuring, validation, and
change management automatically.

## The 7 Rating Criteria

| # | Criterion | Weight | Skill |
|---|-----------|--------|-------|
| 1 | Script Compliance | 25% | `rate-script-compliance` |
| 2 | Factual Accuracy | 25% | `rate-factual-accuracy` |
| 3 | Politeness & Tone | 15% | `rate-politeness-tone` |
| 4 | Empathy | 10% | `rate-empathy` |
| 5 | Conflict Detection | 15% | `rate-conflict-detection` |
| 6 | Issue Resolution | 5% | `rate-issue-resolution` |
| 7 | Overall Severity | 5% | `rate-overall-severity` |

## Architecture Diagram

```
  ┌─────────────────────────────────────────────────────────────┐
  │                    QA HEAD INPUT                            │
  │                                                             │
  │   Option A: Plain text file (.txt)   ← non-technical       │
  │   Option B: Structured JSON file     ← technical/advanced  │
  └──────────────────────┬──────────────────────────────────────┘
                         │
            ┌────────────▼──────────────┐
            │    Text Ingestion Layer   │    (Only for plain text input)
            │   ┌────────────────────┐  │
            │   │ Pass 1: Script     │  │    LLM extracts greeting, closing,
            │   │   compliance fields│  │    verification, hold, transfer,
            │   ├────────────────────┤  │    escalation, disclosures, prohibited
            │   │ Pass 2: Factual    │  │    phrases, products, promotions,
            │   │   accuracy fields  │  │    policies, troubleshooting, FAQ,
            │   ├────────────────────┤  │    contact info
            │   │ Pass 3: Behavioral │  │
            │   │   fields           │  │
            │   ├────────────────────┤  │
            │   │ Pass 4: Validation │  │    Reports OK / MISSING / INCOMPLETE
            │   │   (completeness)   │  │    per field + overall % score
            │   └────────────────────┘  │
            └────────────┬──────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │  CompanyContextSchema JSON  │   18 structured fields across
            │  (contexts/company.json)    │   3 categories
            └────────────┬───────────────┘
                         │
            ┌────────────▼─────────────┐
            │  format-company-context   │   Reformats raw fields into
            │  (Formatting Skill)       │   LLM-optimized atomic rules
            └────────────┬─────────────┘
                         │
            ┌────────────▼─────────────┐
            │    Context Graph Builder  │   Breaks context into nodes
            │  (Nodes + Edges)          │   with keyword indexes
            └────────────┬─────────────┘
                         │
     ┌───────────────────┼───────────────────────┐
     │                   │                       │
     ▼                   ▼                       ▼
┌──────────┐      ┌──────────────┐        ┌──────────────┐
│ Change   │      │ Context Graph│        │ Layer 1 JSON │
│ Tracker  │◄────►│ (Stored)     │        │ (Transcript) │
└──────────┘      └──────┬───────┘        └──────┬───────┘
                         │                       │
            ┌────────────▼───────────────────────▼──┐
            │         Graph Retriever               │
            │  (Retrieves relevant nodes per       │
            │   criterion + transcript keywords)    │
            └───────────────────┬──────────────────┘
                                │
          ┌─────────┬───────┬───┼───┬───────┬──────────┐
          ▼         ▼       ▼   ▼   ▼       ▼          ▼
     ┌────────┐┌────────┐┌──────┐┌──────┐┌──────┐┌──────┐┌─────────┐
     │Script  ││Factual ││Polite││Empthy││Conflc││Issue ││Severity │
     │Compli. ││Accuracy││Tone  ││      ││Detect││Resol.││         │
     │Skill   ││Skill   ││Skill ││Skill ││Skill ││Skill ││Skill    │
     └───┬────┘└───┬────┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘└────┬────┘
         │         │        │       │       │       │         │
         └─────────┴────────┴───────┴───────┴───────┴─────────┘
                                    │
                       ┌────────────▼────────────┐
                       │   Consensus Runner      │
                       │ (Rubric Anchored + Vote)│
                       └────────────┬────────────┘
                                    │
                       ┌────────────▼────────────┐
                       │   Final Rating Output   │
                       │ (Weighted Overall Score) │
                       └─────────────────────────┘
```

## Four Key Problems Solved

### Problem 1: Non-Technical QA Input (Text Ingestion)

**Problem**: The QA head is not a developer. Asking them to write a structured JSON file
with exact field names, correct quoting, and valid syntax is unrealistic. They know
their company's policies — they should be able to describe them in plain language.

**Solution**: LLM-powered text ingestion with multi-pass extraction and validation.

```
QA writes a plain .txt file
(any format — headings, bullets, paragraphs, whatever feels natural)
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│                TEXT INGESTION MODULE                           │
│                                                               │
│  Uses Meta-Llama-3.1-8B-Instruct (same model as rating)      │
│  n_ctx = 16384 (handles long policy documents)                │
│                                                               │
│  Pass 1 — SCRIPT COMPLIANCE EXTRACTION                       │
│    Prompt focuses ONLY on: greeting, closing, verification,   │
│    hold, transfer, escalation, disclosures, prohibited words  │
│    → Returns JSON with 8 fields                               │
│                                                               │
│  Pass 2 — FACTUAL ACCURACY EXTRACTION                        │
│    Prompt focuses ONLY on: products, prices, promotions,      │
│    policies, troubleshooting, contact info, FAQ               │
│    → Returns JSON with 6 fields                               │
│                                                               │
│  Pass 3 — BEHAVIORAL EXTRACTION                              │
│    Prompt focuses ONLY on: tone, empathy, conflict handling,  │
│    resolution expectations                                    │
│    → Returns JSON with 4 fields                               │
│                                                               │
│  Pass 4 — VALIDATION                                         │
│    Checks every extracted field for completeness              │
│    Reports:                                                   │
│      [OK]         — field has sufficient content              │
│      [MISSING]    — field is empty (not in the text)          │
│      [INCOMPLETE] — field exists but missing critical details │
│    Flags critical missing fields so QA can add them           │
│                                                               │
│  AUTO-FLATTEN: If the LLM returns nested dicts instead of    │
│  flat strings, they are automatically flattened to match      │
│  the CompanyContextSchema format.                             │
│                                                               │
│  TRUNCATION RECOVERY: If model output is cut off (hits       │
│  max_tokens), the parser attempts to close open strings       │
│  and braces to recover partial JSON.                          │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
              CompanyContextSchema JSON
              (saved to contexts/ directory)
```

**Why multi-pass instead of one big prompt:**

| Approach | Context usage | Reliability | Failure mode |
|----------|---------------|-------------|--------------|
| Single pass (all 18 fields) | Very high — input + all outputs in one call | Low — model loses focus, misses fields | Entire extraction fails |
| Multi-pass (3 focused passes) | Moderate — each pass handles 4-8 fields | High — each pass is focused and small | Only one category fails, others preserved |

Each pass sees the FULL original text but is asked to extract only its specific fields.
This keeps each prompt focused and within safe token limits.

**Validation example output:**
```
  [OK]         Greeting Script
  [OK]         Closing Script
  [MISSING]    Hold Procedure
              -> No hold procedure described in the document
  [INCOMPLETE] Products And Services
              -> Product prices listed but missing data/feature details
  [OK]         Empathy Guidelines

  Summary: 14/18 OK, 2 missing, 2 incomplete
  Completeness: 78%

  CRITICAL — These required fields are missing:
    - hold_procedure
    - contact_information
```

### Problem 2: Context Change Effect

**Problem**: The QA head rewrites a rule (same meaning, different wording).
The model interprets the new wording differently → agent scores change unfairly.

**Solution**: Change Management System with semantic equivalence checking.

```
QA Head changes text  →  ChangeTicket created
                              │
                    ┌─────────▼──────────┐
                    │ process-context-    │
                    │ change Skill        │
                    │ (checks semantic    │
                    │  equivalence)       │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Same meaning?       │
                    ├── YES: Add          │
                    │   "same_concept"    │
                    │   edge, update      │
                    │   wording only      │
                    │   → NO score change │
                    ├── NO: Create new    │
                    │   node, mark old    │
                    │   as "superseded"   │
                    │   → Scores may      │
                    │     change          │
                    └────────────────────┘
```

**Two types of change tickets:**

| Type | Example | Graph action | Score impact |
|------|---------|--------------|--------------|
| Policy update | AutoPay discount changed from "2nd cycle" to "1st cycle" | `supersedes` edge, new active node | Scores recalculated against new rule |
| Error correction | QA wrote "10GB" but correct is "5GB" | `supersedes` edge, new active node | Agents previously flagged for stating "5GB" are now correct |

### Problem 3: Context Too Large

**Problem**: Company context file is too big for the model to process at once.
The model ignores parts of it → inaccurate scores.

**Solution**: Graph-based context with targeted retrieval.

```
Full Company Context (may be very large)
           │
    ┌──────▼──────┐
    │ Graph Builder│  Breaks into individual nodes:
    │              │  - Each rule = 1 node
    │              │  - Each product = 1 node
    │              │  - Each policy = 1 node
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ Context Graph│  Nodes connected by edges:
    │  ┌───┐ ┌───┐│  - related_to (shared keywords)
    │  │ A ├─┤ B ││  - same_concept (rewording)
    │  └─┬─┘ └───┘│  - supersedes (updated version)
    │    │   ┌───┐│  - part_of (sub-rules)
    │    └───┤ C ││
    │        └───┘│
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  Retriever   │  For each criterion:
    │              │  1. Get nodes matching category
    │              │  2. Score by transcript keywords
    │              │  3. Return top N most relevant
    │              │  → Model sees ONLY relevant chunks
    └─────────────┘
```

### Problem 4: Non-Deterministic Outputs

**Problem**: Running the model multiple times gives different scores each time.

**Solution**: Multi-layered determinism approach.

```
Layer 1: Rubric-Anchored Scoring
  → Model MUST pick from {0, 25, 50, 75, 100}
  → Each level has explicit definition
  → Constrains output space from infinite to 5 options
  → Dramatically reduces variance

Layer 2: Evidence-Before-Score Pattern
  → Model must cite evidence FIRST
  → Then assign score based on evidence
  → Anchors reasoning, reduces random drift

Layer 3: Deterministic Decoding
  → temperature = 0.0 (greedy decoding)
  → top_p = 1.0 (no nucleus sampling)
  → do_sample = False
  → seed = 12345 (fixed)
  → Same input → same token selection

Layer 4: Consensus Vote (optional, for critical evaluations)
  → Run skill 3 times
  → Take median score
  → If all agree → high confidence
  → If disagree by >1 level → flag for review
  → Much cheaper than averaging N runs
```

**Why this is better than averaging N runs:**

| Approach | Cost | Output | Determinism |
|----------|------|--------|-------------|
| Average N runs | N × compute | Fractional (e.g., 73.2%) | Pseudo-deterministic |
| Rubric anchoring | 1 × compute | Discrete (0/25/50/75/100) | Highly deterministic |
| Rubric + consensus | 3 × compute | Discrete + confidence | Very highly deterministic |

The rubric anchoring alone eliminates most variance because the model can't produce
73% vs 71% - it must choose between 75 or 50. With temperature=0, the same evidence
will consistently lead to the same anchor level.

## Complete Data Flow

```
  ┌──────────────────┐
  │ QA Head writes   │
  │ company policy   │
  │ as plain text    │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐    ┌──────────────────┐
  │ Text Ingestion   │    │ Validation Report │
  │ (4 LLM passes)  │───►│ "14/18 OK,       │
  │                  │    │  2 missing..."    │
  └────────┬─────────┘    └──────────────────┘
           │
           ▼
  ┌──────────────────┐
  │ Structured JSON  │◄─── QA can also write JSON directly
  │ (18 fields)      │     if they prefer
  └────────┬─────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
  ┌────────┐  ┌──────────┐
  │ Format │  │ Graph    │
  │ Skill  │  │ Builder  │
  └───┬────┘  └────┬─────┘
      │            │
      ▼            ▼
  ┌──────────────────┐    ┌──────────────────┐
  │ Context Graph    │◄──►│ Change Tracker   │
  │ (nodes + edges)  │    │ (tickets)        │
  └────────┬─────────┘    └──────────────────┘
           │
           ├──── Layer 1 JSON (transcript + emotions)
           │
           ▼
  ┌──────────────────┐
  │ Graph Retriever  │    Pulls relevant context per criterion
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ 7 Rating Skills  │    Each gets: relevant context + transcript
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Consensus Runner │    Rubric-anchored, optionally 3x vote
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Final Ratings    │    Weighted score + per-criterion details
  └──────────────────┘
```

## File Structure

```
LAYER_2/
├── __init__.py
├── pipeline.py                         # Main orchestration + CLI (rate, ingest, process-change)
├── LAYER_2_ARCHITECTURE.md             # This file
├── company_context/
│   ├── __init__.py
│   ├── schema.py                       # CompanyContextSchema — 18 structured fields
│   ├── context_store.py                # Read/write company context JSON files
│   ├── text_ingestion.py              # NEW — Plain text → structured JSON conversion
│   └── contexts/
│       ├── example_company.json        # Example context (JSON format)
│       └── metroboost_policy.txt       # Example context (plain text format)
├── context_graph/
│   ├── __init__.py
│   ├── graph.py                        # Graph data structure (nodes + edges)
│   ├── builder.py                      # Builds graph from company context
│   └── retriever.py                    # Retrieves relevant nodes for a query
├── change_management/
│   ├── __init__.py
│   ├── change_tracker.py              # Tracks changes, semantic equivalence
│   └── tickets/                       # Stored change tickets
│       ├── TICKET-001_*.json          # Policy update tickets
│       └── TICKET-002_*.json          # Error correction tickets
└── consensus/
    ├── __init__.py
    └── consensus_runner.py            # Determinism solution

skill_implementation/skills/
├── format-company-context/             # Formats QA head input for LLM
├── process-context-change/             # Checks semantic equivalence
├── rate-script-compliance/             # Criterion 1 (25%)
├── rate-factual-accuracy/              # Criterion 2 (25%)
├── rate-politeness-tone/               # Criterion 3 (15%)
├── rate-empathy/                       # Criterion 4 (10%)
├── rate-conflict-detection/            # Criterion 5 (15%)
├── rate-issue-resolution/              # Criterion 6 (5%)
└── rate-overall-severity/              # Criterion 7 (5%)
```

## The 18 Context Fields

These are the fields the QA head's input must cover (extracted automatically from plain text,
or provided directly in JSON):

### Script Compliance Fields (8)

| Field | Description | Required |
|-------|-------------|----------|
| `greeting_script` | Exact greeting agent must use when answering | Yes |
| `closing_script` | Exact closing agent must use when ending call | Yes |
| `required_verification_steps` | Steps to verify customer identity | Yes |
| `hold_procedure` | What to say before/after placing on hold | Yes |
| `transfer_procedure` | What to say/do when transferring | Yes |
| `escalation_procedure` | When and how to escalate to supervisor | Yes |
| `mandatory_disclosures` | Legal/regulatory statements to read | No |
| `prohibited_phrases` | Words/phrases agents must never use | No |

### Factual Accuracy Fields (6)

| Field | Description | Required |
|-------|-------------|----------|
| `products_and_services` | Products with correct names, prices, features | Yes |
| `current_promotions` | Active promotions with exact terms | No |
| `policies` | Billing, refund, cancellation, etc. | Yes |
| `common_troubleshooting` | Standard troubleshooting steps | No |
| `contact_information` | Department numbers, emails, hours | Yes |
| `frequently_asked_questions` | Common questions with correct answers | No |

### Behavioral Fields (4)

| Field | Description | Required |
|-------|-------------|----------|
| `tone_guidelines` | How agent should speak and behave | No |
| `empathy_guidelines` | How to handle emotional customers | No |
| `conflict_resolution_guidelines` | How to handle angry/hostile customers | No |
| `resolution_expectations` | What counts as resolving an issue | No |

## Usage

### 1. Ingest Company Context from Plain Text (Recommended)

The QA head writes a `.txt` file describing their company's policies in any format:

```
Our agents should open every call with:
"Thank you for calling Acme Corp, my name is [Name]. How can I help?"

We sell two plans:
- Basic: $29/month, 100GB storage
- Pro: $59/month, 1TB storage, priority support

When customers are upset, always acknowledge their frustration before
trying to fix the problem...
```

Then ingest it:

```bash
python LAYER_2/pipeline.py ingest company_policy.txt --company "Acme Corp"
```

The system will:
1. Parse the text into 18 structured fields using 3 focused LLM passes
2. Validate completeness and report any missing fields
3. Save the result as a JSON file ready for the rating pipeline

### 2. Setup Company Context via JSON (Advanced)

```python
from LAYER_2.company_context.schema import CompanyContextSchema
from LAYER_2.company_context.context_store import ContextStore

context = CompanyContextSchema(
    company_name="My Company",
    context_version="1.0.0",
    last_updated="2026-03-18",
    greeting_script="Thank you for calling My Company...",
    # ... fill all fields
)

store = ContextStore()
store.save(context)
```

### 3. Rate a Call

```bash
python LAYER_2/pipeline.py rate \
    --input Test_audio/full_test/test_diarized_with_emotions.json \
    --company "Example Company" \
    --output results/call_rating.json
```

### 4. Rate with Consensus (Extra Reliability)

```bash
python LAYER_2/pipeline.py rate \
    --input Test_audio/full_test/test_diarized_with_emotions.json \
    --company "Example Company" \
    --output results/call_rating.json \
    --consensus
```

### 5. Process a Context Change

```bash
python LAYER_2/pipeline.py process-change \
    --company "Example Company" \
    --old-text "Agent must verify customer identity" \
    --new-text "The agent is required to confirm who the customer is" \
    --field "required_verification_steps" \
    --topic "verification" \
    --category "script_compliance"
```

## Output Format

```json
{
  "call_metadata": { ... },
  "company_name": "Example Company",
  "scoring_method": "single_run",
  "overall_weighted_score": 75,
  "criteria_ratings": {
    "script_compliance": {
      "score": 75,
      "weight": 0.25,
      "evidence": [...],
      "violations": [...],
      "summary": "...",
      "score_justification": "...",
      "consensus_confidence": null
    },
    "factual_accuracy": { ... },
    "politeness_tone": { ... },
    "empathy": { ... },
    "conflict_detection": { ... },
    "issue_resolution": { ... },
    "overall_severity": { ... }
  },
  "graph_stats": {
    "total_nodes": 42,
    "active_nodes": 42,
    "total_edges": 15,
    "categories": ["script_compliance", "factual_accuracy", ...],
    "topics": ["greeting", "products", ...]
  }
}
```
