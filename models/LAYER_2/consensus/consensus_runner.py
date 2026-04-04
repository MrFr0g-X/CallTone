"""
Consensus Runner - ensures deterministic, stable ratings across multiple runs.

PROBLEM: Even with temperature=0 and fixed seeds, LLM outputs can vary slightly
between runs (due to floating-point non-determinism, batching differences, etc.).
Running N times and averaging is expensive.

SOLUTION: A multi-layered approach to determinism:

1. RUBRIC-ANCHORED SCORING: Instead of asking the model for an arbitrary percentage,
   force it to score against specific rubric levels (0, 25, 50, 75, 100) with
   explicit definitions. This constrains the output space dramatically.

2. EVIDENCE-BEFORE-SCORE: The model must cite specific evidence from the transcript
   BEFORE assigning a score. This anchors the reasoning and reduces variance.

3. STRUCTURED OUTPUT: JSON schema forces consistent output format.

4. CONSENSUS VOTE (when needed): For critical evaluations, run the skill 3 times
   with different evidence orderings. Take the median score. If all 3 agree,
   confidence is high. If they disagree by more than one level, flag for review.

The consensus mechanism is OPTIONAL and only used when extra reliability is needed.
For most cases, the rubric-anchored approach with temp=0 is sufficient.
"""

import json
import re
import statistics
from typing import List, Optional, Tuple
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skill_implementation"))

from skill_runtime.runner import run_skill, select_backend
from skill_runtime.types import SkillBundle


# The 5 anchor levels used across all rating criteria
SCORE_ANCHORS = {
    0: "Not met at all - complete failure to meet this criterion",
    25: "Poorly met - significant gaps, major issues present",
    50: "Partially met - some effort shown but notable deficiencies",
    75: "Mostly met - minor issues only, generally good performance",
    100: "Fully met - excellent performance, no issues detected",
}


def get_rubric_text() -> str:
    """Get the standard rubric text to include in prompts."""
    lines = ["SCORING RUBRIC (you MUST pick one of these exact scores):"]
    for score, description in SCORE_ANCHORS.items():
        lines.append(f"  {score} = {description}")
    return "\n".join(lines)


class ConsensusRunner:
    """
    Runs rating skills with determinism guarantees.

    Usage:
        runner = ConsensusRunner()

        # Single run (fast, usually sufficient with rubric anchoring)
        result = runner.run_single(skill_bundle, input_text)

        # Consensus run (3 runs, median vote, for critical evaluations)
        result, confidence = runner.run_consensus(skill_bundle, input_text)
    """

    def __init__(self, backend=None):
        """
        Args:
            backend: Optional pre-initialized backend for reuse across runs
        """
        self.backend = backend

    def run_single(self, bundle: SkillBundle, input_text: str) -> dict:
        """
        Run a skill once and parse the JSON result.

        Returns:
            Parsed JSON dict with score and evidence
        """
        if self.backend is None:
            self.backend = select_backend(bundle['model_dir'])

        output = run_skill(bundle, input_text, backend=self.backend)
        return self._parse_json_safe(output)

    @staticmethod
    def _parse_json_safe(text: str) -> dict:
        """
        Parse JSON from LLM output with recovery for truncated or malformed responses.

        Handles:
        - Extra text before/after the JSON object
        - Truncated output (hit max_tokens mid-JSON)
        - Unclosed strings, missing closing braces
        """
        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Find outermost JSON object
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # 3. Truncation repair — close open strings and braces
        if start >= 0:
            fragment = text[start:]
            # Count unescaped quotes to detect open string
            quote_count = sum(
                1 for i, c in enumerate(fragment)
                if c == '"' and (i == 0 or fragment[i - 1] != "\\")
            )
            if quote_count % 2 == 1:
                fragment += '"'
            # Close any trailing comma before we close braces (invalid JSON)
            fragment = re.sub(r",\s*$", "", fragment)
            # Close open square brackets
            open_sq = fragment.count("[") - fragment.count("]")
            fragment += "]" * max(0, open_sq)
            # Close open curly braces
            open_br = fragment.count("{") - fragment.count("}")
            fragment += "}" * max(0, open_br)
            try:
                return json.loads(fragment)
            except json.JSONDecodeError:
                pass

        # 4. Last resort — extract score if present and return minimal valid result
        score_match = re.search(r'"score"\s*:\s*(\d+)', text)
        score = int(score_match.group(1)) if score_match else 0
        summary_match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
        summary = summary_match.group(1) if summary_match else "Output truncated — could not parse full response."
        return {
            "score": score,
            "evidence": [],
            "violations": ["Output was truncated; full evaluation incomplete."],
            "summary": summary,
            "score_justification": "Partial output recovered from truncated LLM response.",
        }

    def run_consensus(
        self,
        bundle: SkillBundle,
        input_text: str,
        num_runs: int = 3,
    ) -> Tuple[dict, float]:
        """
        Run a skill multiple times and take consensus.

        Instead of averaging (which gives fractional scores), we:
        1. Run the skill num_runs times
        2. Collect all scores
        3. Take the median score (which will be one of the anchor values)
        4. Calculate agreement rate as confidence

        Args:
            bundle: The skill bundle
            input_text: Input text to process
            num_runs: Number of runs (default 3, always use odd number)

        Returns:
            Tuple of (consensus_result, confidence)
            - consensus_result: The result dict with the median score
            - confidence: 0.0-1.0, how much the runs agreed
        """
        if self.backend is None:
            self.backend = select_backend(bundle['model_dir'])

        results = []
        scores = []

        for i in range(num_runs):
            output = run_skill(bundle, input_text, backend=self.backend)
            result = json.loads(output)
            results.append(result)
            scores.append(result.get("score", 0))

        # Calculate median score
        median_score = int(statistics.median(scores))

        # Snap to nearest anchor
        median_score = self._snap_to_anchor(median_score)

        # Calculate confidence based on agreement
        if len(set(scores)) == 1:
            confidence = 1.0  # Perfect agreement
        else:
            # How close are all scores to the median?
            max_deviation = max(abs(s - median_score) for s in scores)
            if max_deviation <= 25:
                confidence = 0.8  # Within one rubric level
            else:
                confidence = 0.5  # Significant disagreement

        # Use the result closest to the median
        best_result = min(results, key=lambda r: abs(r.get("score", 0) - median_score))
        best_result["score"] = median_score
        best_result["consensus_confidence"] = confidence
        best_result["all_scores"] = scores
        best_result["consensus_runs"] = num_runs

        return best_result, confidence

    def _snap_to_anchor(self, score: int) -> int:
        """Snap a score to the nearest anchor value."""
        anchors = list(SCORE_ANCHORS.keys())
        return min(anchors, key=lambda a: abs(a - score))

    def run_all_criteria(
        self,
        skill_bundles: dict,
        input_text: str,
        use_consensus: bool = False,
    ) -> dict:
        """
        Run all 7 rating criteria and return combined results.

        Args:
            skill_bundles: Dict mapping criterion name to SkillBundle
            input_text: The formatted input for all skills
            use_consensus: Whether to use consensus voting

        Returns:
            Dict with all criterion ratings and overall score
        """
        results = {}
        weights = {
            "script_compliance": 0.25,
            "factual_accuracy": 0.25,
            "politeness_tone": 0.15,
            "empathy": 0.10,
            "conflict_detection": 0.15,
            "issue_resolution": 0.05,
            "overall_severity": 0.05,
        }

        for criterion_name, bundle in skill_bundles.items():
            if use_consensus:
                result, confidence = self.run_consensus(bundle, input_text)
                result["consensus_confidence"] = confidence
            else:
                result = self.run_single(bundle, input_text)
                result["consensus_confidence"] = None

            results[criterion_name] = result

        # Calculate weighted overall score (exclude overall_severity as it's a classification)
        weighted_sum = 0
        weight_sum = 0
        for criterion_name, result in results.items():
            if criterion_name == "overall_severity":
                continue
            w = weights.get(criterion_name, 0)
            weighted_sum += result.get("score", 0) * w
            weight_sum += w

        overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0
        overall_score = self._snap_to_anchor(int(overall_score))

        return {
            "criteria_ratings": results,
            "overall_weighted_score": overall_score,
            "scoring_method": "consensus" if use_consensus else "single",
        }
