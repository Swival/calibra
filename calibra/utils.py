"""Shared utility functions."""

from __future__ import annotations

import json
import math


def safe_num(val: object, default: float = 0.0) -> float:
    """Coerce any value to a finite float, returning *default* on failure."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return x


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
