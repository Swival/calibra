"""Shared data-preparation helpers used by both the live web app and the static exporter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from calibra.utils import safe_num, safe_rate, sum_prompt_tokens, weighted_pass_rate

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


@dataclass
class KpiDelta:
    a: float
    b: float
    delta: float
    pct: float | None

    @staticmethod
    def build(a_raw: object, b_raw: object) -> KpiDelta:
        a = safe_num(a_raw)
        b = safe_num(b_raw)
        delta = b - a
        pct = (delta / a) if a != 0 else None
        return KpiDelta(a, b, delta, pct)


@dataclass
class ToolDiffEntry:
    tool: str
    succeeded_a: int
    failed_a: int
    succeeded_b: int
    failed_b: int
    only_in: str | None


@dataclass
class TrialDiff:
    label_a: str
    label_b: str
    wall_time: KpiDelta
    turns: KpiDelta
    tokens: KpiDelta
    llm_time: KpiDelta
    tool_time: KpiDelta
    llm_calls: KpiDelta
    tool_calls_total: KpiDelta
    tool_calls_failed: KpiDelta
    compactions: KpiDelta
    outcome_a: str
    outcome_b: str
    verified_a: bool | None
    verified_b: bool | None
    tool_usage: list[ToolDiffEntry]
    settings_diff: dict[str, tuple]
    model_a: str
    model_b: str
    provider_a: str
    provider_b: str


def _safe_dict(val: object) -> dict:
    return val if isinstance(val, dict) else {}


def _tool_counts(stats: dict, name: str) -> tuple[int, int]:
    by_name = _safe_dict(stats.get("tool_calls_by_name"))
    entry = by_name.get(name, {})
    if not isinstance(entry, dict):
        return (0, 0)
    return (int(safe_num(entry.get("succeeded", 0))), int(safe_num(entry.get("failed", 0))))


def build_trial_diff(report_a: dict, report_b: dict, label_a: str, label_b: str) -> TrialDiff:
    cal_a = _safe_dict(report_a.get("calibra"))
    cal_b = _safe_dict(report_b.get("calibra"))
    stats_a = _safe_dict(report_a.get("stats"))
    stats_b = _safe_dict(report_b.get("stats"))
    result_a = _safe_dict(report_a.get("result"))
    result_b = _safe_dict(report_b.get("result"))
    settings_a = _safe_dict(report_a.get("settings"))
    settings_b = _safe_dict(report_b.get("settings"))

    tokens_a = sum_prompt_tokens(report_a)
    tokens_b = sum_prompt_tokens(report_b)

    all_tools = set()
    for s in (stats_a, stats_b):
        by_name = _safe_dict(s.get("tool_calls_by_name"))
        all_tools.update(by_name.keys())

    tool_usage: list[ToolDiffEntry] = []
    tools_a_set = set(_safe_dict(stats_a.get("tool_calls_by_name")).keys())
    tools_b_set = set(_safe_dict(stats_b.get("tool_calls_by_name")).keys())
    for name in sorted(all_tools):
        sa, fa = _tool_counts(stats_a, name)
        sb, fb = _tool_counts(stats_b, name)
        only_in = None
        if name in tools_a_set and name not in tools_b_set:
            only_in = "a"
        elif name in tools_b_set and name not in tools_a_set:
            only_in = "b"
        tool_usage.append(ToolDiffEntry(name, sa, fa, sb, fb, only_in))
    tool_usage.sort(key=lambda e: -(e.succeeded_a + e.failed_a + e.succeeded_b + e.failed_b))

    all_setting_keys = set(settings_a.keys()) | set(settings_b.keys())
    settings_diff: dict[str, tuple] = {}
    for key in sorted(all_setting_keys):
        val_a = settings_a.get(key)
        val_b = settings_b.get(key)
        if val_a != val_b:
            settings_diff[key] = (val_a, val_b)

    return TrialDiff(
        label_a=label_a,
        label_b=label_b,
        wall_time=KpiDelta.build(cal_a.get("wall_time_s", 0), cal_b.get("wall_time_s", 0)),
        turns=KpiDelta.build(stats_a.get("turns", 0), stats_b.get("turns", 0)),
        tokens=KpiDelta.build(tokens_a, tokens_b),
        llm_time=KpiDelta.build(
            stats_a.get("total_llm_time_s", 0), stats_b.get("total_llm_time_s", 0)
        ),
        tool_time=KpiDelta.build(
            stats_a.get("total_tool_time_s", 0), stats_b.get("total_tool_time_s", 0)
        ),
        llm_calls=KpiDelta.build(stats_a.get("llm_calls", 0), stats_b.get("llm_calls", 0)),
        tool_calls_total=KpiDelta.build(
            stats_a.get("tool_calls_total", 0), stats_b.get("tool_calls_total", 0)
        ),
        tool_calls_failed=KpiDelta.build(
            stats_a.get("tool_calls_failed", 0), stats_b.get("tool_calls_failed", 0)
        ),
        compactions=KpiDelta.build(stats_a.get("compactions", 0), stats_b.get("compactions", 0)),
        outcome_a=result_a.get("outcome", "unknown"),
        outcome_b=result_b.get("outcome", "unknown"),
        verified_a=cal_a.get("verified"),
        verified_b=cal_b.get("verified"),
        tool_usage=tool_usage,
        settings_diff=settings_diff,
        model_a=report_a.get("model", "unknown"),
        model_b=report_b.get("model", "unknown"),
        provider_a=report_a.get("provider", "unknown"),
        provider_b=report_b.get("provider", "unknown"),
    )
