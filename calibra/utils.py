"""Shared utility functions."""

from __future__ import annotations

import json
import math
from pathlib import Path


def safe_num(val: object, default: float = 0.0) -> float:
    """Coerce any value to a finite float, returning *default* on failure."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return x


def sum_prompt_tokens(report: dict) -> float:
    """Sum ``prompt_tokens_est`` from LLM call events in a report timeline."""
    return sum(
        safe_num(e.get("prompt_tokens_est", 0))
        for e in report.get("timeline", [])
        if e.get("type") == "llm_call"
    )


def write_json(path: Path, data: object) -> None:
    """Write *data* as JSON with indent=2 and trailing newline (project convention)."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def safe_rate(numerator: float, denominator: float, ndigits: int = 4) -> float:
    """Compute *numerator / denominator*, returning 0.0 when *denominator* is zero."""
    return round(numerator / denominator, ndigits) if denominator > 0 else 0.0


def json_for_html(data: object) -> str:
    """Serialize *data* as JSON safe for embedding inside ``<script>`` tags."""
    return json.dumps(data).replace("</", "<\\/")


def weighted_pass_rate(variants: list[dict]) -> float | None:
    """Compute trial-weighted average pass rate from variant dicts."""
    try:
        total_trials = sum(safe_num(v.get("n_trials", 0)) for v in variants)
        if total_trials > 0:
            weighted = sum(
                safe_num(v.get("pass_rate", 0)) * safe_num(v.get("n_trials", 0)) for v in variants
            )
            return round(weighted / total_trials, 4)
    except (TypeError, ValueError):
        pass
    return None
