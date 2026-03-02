"""Shared data-preparation helpers used by both the live web app and the static exporter."""

from __future__ import annotations

from pathlib import Path

from calibra.utils import safe_num, safe_rate, weighted_pass_rate

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def stat_mean(obj: object) -> float:
    """Extract ``mean`` from a stat dict, returning 0 on failure."""
    if isinstance(obj, dict):
        return safe_num(obj.get("mean", 0))
    return 0.0


def rank_variants(variants: list[dict]) -> list[dict]:
    """Sort variants by pass_rate desc, tokens asc, turns asc."""

    def _key(v: dict) -> tuple:
        return (
            -safe_num(v.get("pass_rate", 0)),
            stat_mean(v.get("prompt_tokens_est")),
            stat_mean(v.get("turns")),
        )

    return sorted(variants, key=_key)


def campaign_stats(name: str, summary: dict) -> dict:
    """Derive display-ready campaign stats from a raw summary dict."""
    variants = summary.get("variants", [])
    trials = summary.get("trials", [])
    return {
        "name": name,
        "n_variants": len(variants),
        "n_tasks": len({t["task"] for t in trials}),
        "n_trials": len(trials),
        "pass_rate": weighted_pass_rate(variants),
    }


def build_task_cells(
    trials: list[dict], variants_list: list[dict]
) -> tuple[list[dict], list[str], list[str]]:
    """Aggregate trials into per-(task, variant) cells for the task matrix.

    Returns ``(cells_list, task_names_sorted, variant_labels)``.
    """
    variant_labels = [v["variant_label"] for v in variants_list]

    cells: dict[tuple[str, str], dict] = {}
    task_names: set[str] = set()
    for t in trials:
        task_name = t["task"]
        task_names.add(task_name)
        key = (task_name, t["variant_label"])
        if key not in cells:
            cells[key] = {
                "task": task_name,
                "variant": t["variant_label"],
                "n": 0,
                "passes": 0,
                "turns_sum": 0.0,
                "tokens_sum": 0.0,
            }
        cells[key]["n"] += 1
        if t.get("verified") is True:
            cells[key]["passes"] += 1
        cells[key]["turns_sum"] += safe_num(t.get("turns", 0))
        cells[key]["tokens_sum"] += safe_num(t.get("prompt_tokens_est", 0))

    for cell in cells.values():
        n = cell["n"]
        cell["pass_rate"] = safe_rate(cell["passes"], n)
        cell["mean_turns"] = safe_rate(cell["turns_sum"], n, ndigits=1)
        cell["mean_tokens"] = safe_rate(cell["tokens_sum"], n, ndigits=0)

    return list(cells.values()), sorted(task_names), variant_labels


def build_variant_stats(
    trials: list[dict],
) -> tuple[list[dict], dict[str, int], dict[str, dict[str, int]]]:
    """Aggregate trials for a single variant into per-task stats.

    Returns ``(task_stats, failure_counts, tool_agg)``.
    """
    per_task: dict[str, dict] = {}
    failure_counts: dict[str, int] = {}
    tool_agg: dict[str, dict[str, int]] = {}
    for t in trials:
        tk = t["task"]
        if tk not in per_task:
            per_task[tk] = {
                "task": tk,
                "n": 0,
                "passes": 0,
                "outcomes": [],
                "turns_vals": [],
                "tokens_vals": [],
                "wall_time_vals": [],
            }
        pt = per_task[tk]
        pt["n"] += 1
        if t.get("verified") is True:
            pt["passes"] += 1
        pt["outcomes"].append(t.get("outcome", "unknown"))
        pt["turns_vals"].append(safe_num(t.get("turns", 0)))
        pt["tokens_vals"].append(safe_num(t.get("prompt_tokens_est", 0)))
        pt["wall_time_vals"].append(safe_num(t.get("wall_time_s", 0)))

        fc = t.get("failure_class")
        if fc:
            failure_counts[fc] = failure_counts.get(fc, 0) + 1
        for tool_name, counts in t.get("tool_calls_by_name", {}).items():
            if tool_name not in tool_agg:
                tool_agg[tool_name] = {"succeeded": 0, "failed": 0}
            if isinstance(counts, dict):
                tool_agg[tool_name]["succeeded"] += counts.get("succeeded", 0)
                tool_agg[tool_name]["failed"] += counts.get("failed", 0)

    task_stats = []
    for tk, pt in sorted(per_task.items()):
        n = pt["n"]
        task_stats.append(
            {
                "task": tk,
                "n": n,
                "passes": pt["passes"],
                "pass_rate": safe_rate(pt["passes"], n),
                "outcomes": pt["outcomes"],
                "mean_turns": safe_rate(sum(pt["turns_vals"]), n, ndigits=1),
                "mean_tokens": safe_rate(sum(pt["tokens_vals"]), n, ndigits=0),
                "mean_wall_time": safe_rate(sum(pt["wall_time_vals"]), n, ndigits=1),
                "turns_vals": pt["turns_vals"],
            }
        )

    return task_stats, failure_counts, tool_agg
