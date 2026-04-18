# LAYER 1 Evaluation

`wer_eval.py` measures word-error-rate and character-error-rate of
SenseVoice hypothesis transcripts against reference transcripts using
`jiwer`.

## Usage

```bash
# 1. Run the pipeline to produce hypothesis transcripts (one .txt per call)
python LAYER_1/pipeline.py --input path/to/audio.mp3

# 2. Place reference transcripts alongside (same filenames) under a refs/ dir
# 3. Run eval
python -m models.eval.wer_eval \
    --transcripts path/to/pipeline_transcripts \
    --refs        models/eval/ground_truth \
    --out         models/eval/results/eval_results.json
```

Output is a JSON report with per-file WER/CER plus session-wide means.

## MVP targets

- Transcription WER: <20% (MVP), <8% (production)
- WER here is computed on lowercased, whitespace-stripped text; punctuation
  differences are counted. Use `jiwer` directly if you need normalisation.
