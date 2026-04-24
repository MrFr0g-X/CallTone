#!/usr/bin/env python3
"""Benchmark Faster-Whisper settings for the CallTone test.wav reference.

This script is intentionally standalone so it can run on the GPU server without
touching the production API path. It compares ASR text against a timestamped
reference transcript and writes JSON results for parameter selection.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from faster_whisper import WhisperModel


REFERENCE_RE = re.compile(
    r"(\d\d):(\d\d):(\d\d),(\d{3})\s+-->\s+"
    r"(\d\d):(\d\d):(\d\d),(\d{3})\s+\[Speaker\s+(\d+)\]\s*\n"
    r"(.*?)(?=\n\s*\n\d\d:\d\d:\d\d,|\Z)",
    re.S,
)


GLOSSARY = (
    "MetroBoost, Metro Boost, Shalene, Linda Marone, Global Phone, postpaid, "
    "prepaid, Prepay, AutoPay, O2Pay, credit card, overdraft fee, unlimited "
    "calls and texts, unlimited data, five gigs, fifteen gigabytes, sixty-seven "
    "dollars and eighty-one cents, sixty-five dollar unlimited plan, two "
    "dollars and eighty-one cents, $67.81, $62.81, $65, $40, $30, $50, $60, $55"
)


@dataclass
class BenchmarkResult:
    name: str
    seconds: float
    plain_wer_pct: float
    business_wer_pct: float
    business_no_fillers_wer_pct: float
    words: int
    segments: int
    text_preview: str
    config: dict


def _norm_base(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = text.replace("-", " ")
    text = re.sub(r"\$", " ", text)
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    return " ".join(text.split())


BUSINESS_REPLACEMENTS = [
    ("metroboost", "metro boost"),
    ("metrobus", "metro boost"),
    ("metribus", "metro boost"),
    ("metribuys", "metro boost"),
    ("metribuy", "metro boost"),
    ("metro buys", "metro boost"),
    ("o2pay", "auto pay"),
    ("o to pay", "auto pay"),
    ("postpay", "postpaid"),
    ("prepay", "prepaid"),
    ("shalane", "shalene"),
    ("jolene", "shalene"),
    ("jalene", "shalene"),
    ("sixty seven dollars and eighty one cents", "67 81"),
    ("sixty seven eighty one", "67 81"),
    ("six to seven eighty one", "67 81"),
    ("67.81", "67 81"),
    ("6781", "67 81"),
    ("sixty two dollars and eighty one cents", "62 81"),
    ("62.81", "62 81"),
    ("two dollars and eighty one cents", "2 81"),
    ("2.81", "2 81"),
    ("forty dollars", "40"),
    ("forty dollar", "40"),
    ("sixty five dollars", "65"),
    ("sixty five dollar", "65"),
    ("five dollars", "5"),
    ("five dollar", "5"),
    ("sixty dollars", "60"),
    ("sixty dollar", "60"),
    ("fifty five dollars", "55"),
    ("fifty five dollar", "55"),
    ("thirty dollar", "30"),
    ("thirty dollars", "30"),
    ("fifty dollar", "50"),
    ("fifty dollars", "50"),
    ("five gigs", "5 gigs"),
    ("five gigabytes", "5 gigabytes"),
    ("fifteen gigabytes", "15 gigabytes"),
    ("fifteen gigs", "15 gigs"),
    ("twenty first", "21st"),
    ("oh nine oh three", "0903"),
    ("zero nine zero three", "0903"),
    ("six oh seven five nine eight six nine nine two", "607 598 6992"),
]

FILLERS = {"uh", "um", "erm", "hmm"}


def normalize_plain(text: str) -> str:
    text = _norm_base(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_business(text: str, remove_fillers: bool = False) -> str:
    text = _norm_base(text)
    for src, dst in BUSINESS_REPLACEMENTS:
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = text.split()
    if remove_fillers:
        tokens = [token for token in tokens if token not in FILLERS]
    return " ".join(tokens)


def edit_counts(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    sm = SequenceMatcher(a=ref, b=hyp, autojunk=False)
    substitutions = insertions = deletions = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            substitutions += min(i2 - i1, j2 - j1)
            deletions += max(0, (i2 - i1) - (j2 - j1))
            insertions += max(0, (j2 - j1) - (i2 - i1))
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "insert":
            insertions += j2 - j1
    return substitutions, insertions, deletions


def wer(reference: str, hypothesis: str) -> float:
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()
    s, i, d = edit_counts(ref_tokens, hyp_tokens)
    return (s + i + d) / max(1, len(ref_tokens))


def parse_reference(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts = []
    for match in REFERENCE_RE.finditer(raw):
        parts.append(" ".join(match.group(10).split()))
    return " ".join(parts)


def transcribe(model: WhisperModel, audio: Path, config: dict) -> tuple[str, int]:
    kwargs = dict(config)
    name = kwargs.pop("name")
    if kwargs.pop("use_glossary", False):
        kwargs["initial_prompt"] = GLOSSARY
        kwargs["hotwords"] = GLOSSARY
    segments_iter, _info = model.transcribe(str(audio), **kwargs)
    segments = list(segments_iter)
    return " ".join(segment.text.strip() for segment in segments if segment.text).strip(), len(segments)


def run(audio: Path, reference: Path, output: Path) -> None:
    reference_text = parse_reference(reference)
    model = WhisperModel(
        "Systran/faster-whisper-large-v3",
        device="cuda",
        compute_type="float16",
        local_files_only=False,
    )

    configs = [
        {
            "name": "current_beam1_vad_on_cond_off",
            "language": "en",
            "beam_size": 1,
            "best_of": 1,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },
        {
            "name": "beam3_vad_on_cond_off",
            "language": "en",
            "beam_size": 3,
            "best_of": 3,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },
        {
            "name": "beam5_vad_on_cond_off",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },
        {
            "name": "beam5_vad_off_cond_off",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },
        {
            "name": "beam5_vad_on_cond_on",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": True,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },
        {
            "name": "beam5_vad_off_cond_on",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": True,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": False,
        },

        {
            "name": "beam1_vad_on_cond_off_glossary",
            "language": "en",
            "beam_size": 1,
            "best_of": 1,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam3_vad_on_cond_off_glossary",
            "language": "en",
            "beam_size": 3,
            "best_of": 3,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam1_vad_off_cond_off_glossary",
            "language": "en",
            "beam_size": 1,
            "best_of": 1,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam3_vad_off_cond_off_glossary",
            "language": "en",
            "beam_size": 3,
            "best_of": 3,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam5_vad_on_700ms_glossary",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 700},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam5_vad_on_cond_off_glossary",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 350},
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
        {
            "name": "beam5_vad_off_cond_off_glossary",
            "language": "en",
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0,
            "use_glossary": True,
        },
    ]

    results: list[BenchmarkResult] = []
    text_dir = output.with_suffix("")
    text_dir.mkdir(parents=True, exist_ok=True)

    for config in configs:
        start = time.perf_counter()
        text, segment_count = transcribe(model, audio, config)
        elapsed = time.perf_counter() - start
        (text_dir / f"{config['name']}.txt").write_text(text, encoding="utf-8")
        result = BenchmarkResult(
            name=config["name"],
            seconds=round(elapsed, 2),
            plain_wer_pct=round(wer(normalize_plain(reference_text), normalize_plain(text)) * 100, 2),
            business_wer_pct=round(wer(normalize_business(reference_text), normalize_business(text)) * 100, 2),
            business_no_fillers_wer_pct=round(
                wer(
                    normalize_business(reference_text, remove_fillers=True),
                    normalize_business(text, remove_fillers=True),
                )
                * 100,
                2,
            ),
            words=len(normalize_plain(text).split()),
            segments=segment_count,
            text_preview=text[:500],
            config=config,
        )
        results.append(result)
        output.write_text(
            json.dumps([asdict(item) for item in results], indent=2),
            encoding="utf-8",
        )
        print(json.dumps(asdict(result), indent=2), flush=True)

    ranked = sorted(results, key=lambda item: (item.business_wer_pct, item.seconds))
    print("\nRANKED")
    for item in ranked:
        print(
            f"{item.name}: business WER={item.business_wer_pct}% "
            f"plain WER={item.plain_wer_pct}% time={item.seconds}s",
            flush=True,
        )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.audio, args.reference, args.output)


if __name__ == "__main__":
    main()
