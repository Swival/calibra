"""Analysis engine: metrics, aggregation, statistics, ranking."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from calibra.utils import safe_num as _safe_num


@dataclass
class TrialMetrics:
    task: str
    variant_label: str
    repeat: int
    outcome: str
    verified: bool | None
    turns: int
    tool_calls_total: int
    tool_calls_failed: int
    tool_calls_by_name: dict[str, dict[str, int]]
    llm_time_s: float
    tool_time_s: float
    wall_time_s: float
    compactions: int
    prompt_tokens_est: int
    skills_used: list[str]
    guardrail_interventions: int
    failure_class: str | None


@dataclass
class StatSummary:
    mean: float
    median: float
    std: float
    min: float
    max: float
    p90: float
    ci_lower: float
    ci_upper: float


@dataclass
class AggregateMetrics:
    variant_label: str
    n_trials: int
    pass_rate: float
    outcome_counts: dict[str, int]
    turns: StatSummary
    tool_calls_total: StatSummary
    tool_calls_failed: StatSummary
    llm_time_s: StatSummary
    tool_time_s: StatSummary
    wall_time_s: StatSummary
    compactions: StatSummary
    prompt_tokens_est: StatSummary
    score_per_1k_tokens: float
    pass_rate_per_minute: float


def extract_metrics(
    report: dict, wall_time: float, verified: bool | None, failure_class: str | None
) -> TrialMetrics:
    stats = report.get("stats", {})
    cal = report.get("calibra", {})
    result = report.get("result", {})

    timeline = report.get("timeline", [])
    prompt_tokens = sum(
        _safe_num(e.get("prompt_tokens_est", 0)) for e in timeline if e.get("type") == "llm_call"
    )

    return TrialMetrics(
        task=cal.get("task", report.get("task", "")),
        variant_label=cal.get("variant", ""),
        repeat=cal.get("repeat", 0),
        outcome=result.get("outcome", "unknown"),
        verified=cal.get("verified", verified),
        turns=_safe_num(stats.get("turns", 0)),
        tool_calls_total=_safe_num(stats.get("tool_calls_total", 0)),
        tool_calls_failed=_safe_num(stats.get("tool_calls_failed", 0)),
        tool_calls_by_name=stats.get("tool_calls_by_name", {}),
        llm_time_s=_safe_num(stats.get("total_llm_time_s", 0.0)),
        tool_time_s=_safe_num(stats.get("total_tool_time_s", 0.0)),
        wall_time_s=_safe_num(cal.get("wall_time_s", wall_time)),
        compactions=_safe_num(stats.get("compactions", 0)),
        prompt_tokens_est=prompt_tokens,
        skills_used=stats.get("skills_used", []),
        guardrail_interventions=_safe_num(stats.get("guardrail_interventions", 0)),
        failure_class=cal.get("failure_class", failure_class),
    )


def _compute_stat(values: list[float]) -> StatSummary:
    if not values:
        return StatSummary(0, 0, 0, 0, 0, 0, 0, 0)
    n = len(values)
    mean = statistics.mean(values)
    med = statistics.median(values)
    std = statistics.stdev(values) if n > 1 else 0.0
    mn = min(values)
    mx = max(values)
    sorted_v = sorted(values)
    p90_idx = int(0.9 * (n - 1))
    p90 = sorted_v[p90_idx]
    se = std / (n**0.5) if n > 1 else 0
    ci_lower = mean - 1.96 * se
    ci_upper = mean + 1.96 * se
    return StatSummary(
        mean=round(mean, 3),
        median=round(med, 3),
        std=round(std, 3),
        min=round(mn, 3),
        max=round(mx, 3),
        p90=round(p90, 3),
        ci_lower=round(ci_lower, 3),
        ci_upper=round(ci_upper, 3),
    )


def aggregate_variant(metrics: list[TrialMetrics]) -> AggregateMetrics:
    n = len(metrics)
    if n == 0:
        raise ValueError("Cannot aggregate zero metrics")

    label = metrics[0].variant_label

    outcome_counts: dict[str, int] = {}
    for m in metrics:
        outcome_counts[m.outcome] = outcome_counts.get(m.outcome, 0) + 1

    passed = sum(1 for m in metrics if m.verified is True)
    pass_rate = passed / n if n > 0 else 0.0

    def vals(attr: str) -> list[float]:
        return [_safe_num(getattr(m, attr)) for m in metrics]

    turns = _compute_stat(vals("turns"))
    tool_total = _compute_stat(vals("tool_calls_total"))
    tool_fail = _compute_stat(vals("tool_calls_failed"))
    llm_time = _compute_stat(vals("llm_time_s"))
    tool_time = _compute_stat(vals("tool_time_s"))
    wall_time = _compute_stat(vals("wall_time_s"))
    compactions = _compute_stat(vals("compactions"))
    tokens = _compute_stat(vals("prompt_tokens_est"))

    score_per_1k = (pass_rate * 1000 / tokens.mean) if tokens.mean > 0 else 0.0
    pass_per_min = (pass_rate * 60 / wall_time.mean) if wall_time.mean > 0 else 0.0

    return AggregateMetrics(
        variant_label=label,
        n_trials=n,
        pass_rate=round(pass_rate, 4),
        outcome_counts=outcome_counts,
        turns=turns,
        tool_calls_total=tool_total,
        tool_calls_failed=tool_fail,
        llm_time_s=llm_time,
        tool_time_s=tool_time,
        wall_time_s=wall_time,
        compactions=compactions,
        prompt_tokens_est=tokens,
        score_per_1k_tokens=round(score_per_1k, 4),
        pass_rate_per_minute=round(pass_per_min, 4),
    )


def paired_bootstrap_ci(
    values_a: list[float],
    values_b: list[float],
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    rng = random.Random(seed)
    diffs = [a - b for a, b in zip(values_a, values_b)]
    n = len(diffs)
    boot_means = sorted(statistics.mean(rng.choices(diffs, k=n)) for _ in range(n_bootstrap))
    lo = int((1 - confidence) / 2 * n_bootstrap)
    hi = int((1 + confidence) / 2 * n_bootstrap)
    return round(boot_means[lo], 4), round(boot_means[hi], 4)


def cliffs_delta(x: list[float], y: list[float]) -> tuple[float, str]:
    n_more = sum(1 for a in x for b in y if a > b)
    n_less = sum(1 for a in x for b in y if a < b)
    delta = (n_more - n_less) / (len(x) * len(y))
    abs_d = abs(delta)
    if abs_d < 0.147:
        mag = "negligible"
    elif abs_d < 0.33:
        mag = "small"
    elif abs_d < 0.474:
        mag = "medium"
    else:
        mag = "large"
    return round(delta, 4), mag


def permutation_test(
    values_a: list[float],
    values_b: list[float],
    n_perms: int = 10000,
    seed: int = 42,
) -> float:
    diffs = [a - b for a, b in zip(values_a, values_b)]
    observed = abs(statistics.mean(diffs))
    rng = random.Random(seed)
    count = 0
    for _ in range(n_perms):
        perm = [d * rng.choice((-1, 1)) for d in diffs]
        if abs(statistics.mean(perm)) >= observed:
            count += 1
    return round(count / n_perms, 4)


def flag_instabilities(agg: AggregateMetrics) -> list[str]:
    warnings = []
    for metric_name in ["turns", "llm_time_s", "prompt_tokens_est"]:
        stat: StatSummary = getattr(agg, metric_name)
        if stat.mean > 0 and stat.std / stat.mean > 0.5:
            warnings.append(f"High CV for {metric_name}: {stat.std / stat.mean:.2f}")
    if agg.n_trials < 3:
        warnings.append("Fewer than 3 repeats, low confidence")
    return warnings


def rank_variants(aggregates: list[AggregateMetrics]) -> list[AggregateMetrics]:
    return sorted(
        aggregates,
        key=lambda a: (
            -a.pass_rate,
            a.prompt_tokens_est.mean,
            a.turns.mean,
            a.llm_time_s.mean,
        ),
    )


def pareto_front(aggregates: list[AggregateMetrics]) -> list[AggregateMetrics]:
    candidates = sorted(aggregates, key=lambda a: (-a.pass_rate, a.prompt_tokens_est.mean))
    front = []
    min_tokens = float("inf")
    for a in candidates:
        if a.prompt_tokens_est.mean < min_tokens:
            front.append(a)
            min_tokens = a.prompt_tokens_est.mean
    return front


def load_metrics(results_dir: Path) -> dict[str, list[TrialMetrics]]:
    """Scan *results_dir* for trial JSON files and return metrics grouped by variant."""
    by_variant: dict[str, list[TrialMetrics]] = {}
    for rp in results_dir.rglob("*.json"):
        if rp.name == "summary.json":
            continue
        with open(rp) as f:
            report = json.load(f)
        cal = report.get("calibra", {})
        m = extract_metrics(
            report,
            cal.get("wall_time_s", 0),
            cal.get("verified"),
            cal.get("failure_class"),
        )
        by_variant.setdefault(m.variant_label, []).append(m)
    return by_variant


def _is_campaign_dir(d: Path) -> bool:
    """A campaign dir has trial JSONs in immediate subdirs (task dirs)."""
    for sub in d.iterdir():
        if sub.is_dir():
            for f in sub.iterdir():
                if f.is_file() and f.suffix == ".json" and f.name != "summary.json":
                    return True
    return False


def _find_campaigns(results_dir: Path) -> list[Path]:
    """Return campaign dirs under results_dir, or [results_dir] if it is one."""
    if _is_campaign_dir(results_dir):
        return [results_dir]
    campaigns = sorted(d for d in results_dir.iterdir() if d.is_dir() and _is_campaign_dir(d))
    return campaigns


def _print_results(
    campaign_name: str,
    all_metrics: list[TrialMetrics],
    rankings: list[AggregateMetrics],
    front: list[AggregateMetrics],
    output_dir: Path,
):
    """Print a verbose human-readable summary to stdout."""
    tasks: set[str] = set()
    by_task: dict[str, list[TrialMetrics]] = {}
    by_variant_task: dict[str, dict[str, list[TrialMetrics]]] = {}
    n_passed = n_failed = n_unknown = 0
    for m in all_metrics:
        tasks.add(m.task)
        by_task.setdefault(m.task, []).append(m)
        by_variant_task.setdefault(m.variant_label, {}).setdefault(m.task, []).append(m)
        if m.verified is True:
            n_passed += 1
        elif m.verified is False:
            n_failed += 1
        else:
            n_unknown += 1
    tasks_sorted = sorted(tasks)
    n_variants = len({m.variant_label for m in all_metrics})

    print(f"\n{'=' * 70}")
    print(f"  Campaign: {campaign_name}")
    print(f"{'=' * 70}")
    print(f"  {len(all_metrics)} trials | {n_variants} variants | {len(tasks)} tasks")
    print(f"  {n_passed} passed | {n_failed} failed | {n_unknown} unverified")

    print("\n  Tasks:")
    max_task_len = max(len(t) for t in tasks_sorted) if tasks_sorted else 0
    for task in tasks_sorted:
        tms = by_task[task]
        passed = sum(1 for m in tms if m.verified is True)
        total = len(tms)
        rate = passed / total if total else 0
        bar_len = 20
        filled = round(rate * bar_len)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
        print(f"    {task:<{max_task_len}}  {bar}  {passed}/{total} ({rate:.0%})")

    # Rankings table
    print("\n  Rankings:")
    max_var_len = max(len(a.variant_label) for a in rankings)
    header_var = "Variant".ljust(max_var_len)
    print(
        f"    {'#':>3}  {header_var}  {'Pass':>6}  {'Turns':>6}  {'Tokens':>8}  {'LLM Time':>8}  {'Wall Time':>9}"
    )
    print(
        f"    {'---':>3}  {'-' * max_var_len}  {'------':>6}  {'------':>6}  {'--------':>8}  {'--------':>8}  {'---------':>9}"
    )
    for i, a in enumerate(rankings, 1):
        print(
            f"    {i:>3}  {a.variant_label:<{max_var_len}}  {a.pass_rate:>5.0%}"
            f"  {a.turns.mean:>6.1f}  {a.prompt_tokens_est.mean:>8.0f}"
            f"  {a.llm_time_s.mean:>7.1f}s  {a.wall_time_s.mean:>8.1f}s"
        )

    # Per-variant task breakdown
    print("\n  Pass/fail by variant and task:")
    task_col_width = max(3, *(len(t) for t in tasks_sorted)) if tasks_sorted else 3
    var_col = " " * max_var_len
    header_parts = [f"    {var_col}  "]
    for t in tasks_sorted:
        header_parts.append(f"{t:>{task_col_width}}")
    print("  ".join(header_parts))
    for a in rankings:
        parts = [f"    {a.variant_label:<{max_var_len}}  "]
        vt = by_variant_task.get(a.variant_label, {})
        for t in tasks_sorted:
            tms = vt.get(t, [])
            passed = sum(1 for m in tms if m.verified is True)
            total = len(tms)
            if total == 0:
                cell = "-"
            else:
                cell = f"{passed}/{total}"
            parts.append(f"{cell:>{task_col_width}}")
        print("  ".join(parts))

    # Pareto front
    if front:
        print("\n  Pareto front (pass rate vs tokens):")
        for a in front:
            print(
                f"    {a.variant_label}: {a.pass_rate:.0%} pass, "
                f"{a.prompt_tokens_est.mean:.0f} tokens"
            )

    # Efficiency
    print("\n  Efficiency:")
    for a in rankings:
        print(
            f"    {a.variant_label:<{max_var_len}}  "
            f"score/1k tok: {a.score_per_1k_tokens:.4f}  "
            f"pass/min: {a.pass_rate_per_minute:.4f}"
        )

    # Warnings
    any_warnings = False
    for a in rankings:
        warnings = flag_instabilities(a)
        if warnings:
            if not any_warnings:
                print("\n  Warnings:")
                any_warnings = True
            for w in warnings:
                print(f"    {a.variant_label}: {w}")

    print(f"\n  Output: {output_dir}/summary.{{json,md,csv}}")
    print()


def _analyze_single(results_dir: Path, output_dir: Path):
    """Analyze a single campaign directory. Returns True if results were found."""
    by_variant = load_metrics(results_dir)

    if not by_variant:
        return False

    all_metrics = [m for ms in by_variant.values() for m in ms]

    aggregates = [aggregate_variant(ms) for ms in by_variant.values()]
    rankings = rank_variants(aggregates)
    front = pareto_front(aggregates)

    from calibra.report import write_summary_json, write_summary_md, write_summary_csv

    write_summary_json(output_dir, aggregates, all_metrics)
    write_summary_md(output_dir, rankings, front, aggregates)
    write_summary_csv(output_dir, aggregates)

    _print_results(results_dir.name, all_metrics, rankings, front, output_dir)
    return True


def analyze_campaign(results_dir: str | Path, output_dir: str | Path | None = None):
    results_dir = Path(results_dir)
    base_output = Path(output_dir) if output_dir is not None else None

    campaigns = _find_campaigns(results_dir)
    if not campaigns:
        print(f"No trial reports found in {results_dir}")
        return

    single = len(campaigns) == 1 and campaigns[0] == results_dir

    found_any = False
    for campaign_dir in campaigns:
        if single:
            out = base_output if base_output else campaign_dir
        else:
            out = (base_output / campaign_dir.name) if base_output else campaign_dir
        out.mkdir(parents=True, exist_ok=True)
        if _analyze_single(campaign_dir, out):
            found_any = True

    if not found_any:
        print(f"No trial reports found in {results_dir}")
