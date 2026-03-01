"""Report writers: JSON, Markdown, CSV."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from calibra.analyze import AggregateMetrics, TrialMetrics, flag_instabilities


def write_summary_json(
    output_dir: Path,
    aggregates: list[AggregateMetrics],
    all_metrics: list[TrialMetrics],
):
    data = {
        "variants": [asdict(a) for a in aggregates],
        "trials": [asdict(m) for m in all_metrics],
    }
    path = output_dir / "summary.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def write_summary_md(
    output_dir: Path,
    rankings: list[AggregateMetrics],
    pareto: list[AggregateMetrics],
    aggregates: list[AggregateMetrics],
):
    lines = ["# Campaign Results\n"]

    has_reviews = any(a.review_rounds is not None for a in rankings)
    lines.append("## Rankings\n")
    if has_reviews:
        lines.append(
            "| Rank | Variant | Pass Rate | Turns (mean) | Tokens (mean) "
            "| LLM Time (mean) | Reviews (mean) |"
        )
        lines.append(
            "|------|---------|-----------|-------------|---------------|"
            "-----------------|----------------|"
        )
    else:
        lines.append(
            "| Rank | Variant | Pass Rate | Turns (mean) | Tokens (mean) | LLM Time (mean) |"
        )
        lines.append(
            "|------|---------|-----------|-------------|---------------|-----------------|"
        )
    for i, a in enumerate(rankings, 1):
        base = (
            f"| {i} | {a.variant_label} | {a.pass_rate:.1%} | {a.turns.mean:.1f} "
            f"| {a.prompt_tokens_est.mean:.0f} | {a.llm_time_s.mean:.1f}s |"
        )
        if has_reviews:
            rr = a.review_rounds.mean if a.review_rounds else 0.0
            base += f" {rr:.1f} |"
        lines.append(base)

    lines.append("\n## Pareto Front (pass rate vs tokens)\n")
    for a in pareto:
        lines.append(
            f"- **{a.variant_label}**: {a.pass_rate:.1%} pass, {a.prompt_tokens_est.mean:.0f} tokens"
        )

    lines.append("\n## Warnings\n")
    any_warnings = False
    for a in aggregates:
        warnings = flag_instabilities(a)
        if warnings:
            any_warnings = True
            for w in warnings:
                lines.append(f"- {a.variant_label}: {w}")
    if not any_warnings:
        lines.append("No instability warnings.")

    path = output_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n")


def write_summary_csv(output_dir: Path, aggregates: list[AggregateMetrics]):
    path = output_dir / "summary.csv"
    has_reviews = any(a.review_rounds is not None for a in aggregates)
    fieldnames = [
        "variant",
        "n_trials",
        "pass_rate",
        "turns_mean",
        "turns_std",
        "tokens_mean",
        "tokens_std",
        "llm_time_mean",
        "tool_time_mean",
        "wall_time_mean",
        "score_per_1k_tokens",
        "pass_rate_per_minute",
    ]
    if has_reviews:
        fieldnames.append("review_rounds_mean")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in aggregates:
            row = {
                "variant": a.variant_label,
                "n_trials": a.n_trials,
                "pass_rate": a.pass_rate,
                "turns_mean": a.turns.mean,
                "turns_std": a.turns.std,
                "tokens_mean": a.prompt_tokens_est.mean,
                "tokens_std": a.prompt_tokens_est.std,
                "llm_time_mean": a.llm_time_s.mean,
                "tool_time_mean": a.tool_time_s.mean,
                "wall_time_mean": a.wall_time_s.mean,
                "score_per_1k_tokens": a.score_per_1k_tokens,
                "pass_rate_per_minute": a.pass_rate_per_minute,
            }
            if has_reviews:
                row["review_rounds_mean"] = a.review_rounds.mean if a.review_rounds else 0.0
            writer.writerow(row)
