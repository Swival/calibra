"""Cross-campaign comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from calibra.analyze import (
    aggregate_variant,
    cliffs_delta,
    load_metrics,
)


@dataclass
class VariantComparison:
    variant: str
    pass_rate_a: float
    pass_rate_b: float
    delta_pass: float
    effect_size: float | None
    effect_magnitude: str | None
    tokens_mean_a: float
    tokens_mean_b: float


@dataclass
class ComparisonResult:
    name_a: str
    name_b: str
    variants: list[VariantComparison]


def compute_comparison(
    dir_a: str | Path,
    dir_b: str | Path,
) -> ComparisonResult | None:
    dir_a = Path(dir_a)
    dir_b = Path(dir_b)

    metrics_a = load_metrics(dir_a)
    metrics_b = load_metrics(dir_b)

    common = sorted(set(metrics_a.keys()) & set(metrics_b.keys()))
    if not common:
        return None

    variant_comparisons = []
    for v in common:
        agg_a = aggregate_variant(metrics_a[v])
        agg_b = aggregate_variant(metrics_b[v])

        delta_pass = agg_b.pass_rate - agg_a.pass_rate
        tokens_a = [m.prompt_tokens_est for m in metrics_a[v]]
        tokens_b = [m.prompt_tokens_est for m in metrics_b[v]]

        effect_size = None
        effect_magnitude = None
        if len(tokens_a) == len(tokens_b) and len(tokens_a) > 1:
            d, mag = cliffs_delta(
                [float(x) for x in tokens_a],
                [float(x) for x in tokens_b],
            )
            effect_size = d
            effect_magnitude = mag

        variant_comparisons.append(
            VariantComparison(
                variant=v,
                pass_rate_a=agg_a.pass_rate,
                pass_rate_b=agg_b.pass_rate,
                delta_pass=round(delta_pass, 4),
                effect_size=effect_size,
                effect_magnitude=effect_magnitude,
                tokens_mean_a=agg_a.prompt_tokens_est.mean,
                tokens_mean_b=agg_b.prompt_tokens_est.mean,
            )
        )

    return ComparisonResult(
        name_a=dir_a.name,
        name_b=dir_b.name,
        variants=variant_comparisons,
    )


def compare_campaigns(
    dir_a: str | Path,
    dir_b: str | Path,
    output_dir: str | Path | None = None,
):
    dir_a = Path(dir_a)
    dir_b = Path(dir_b)
    if output_dir is None:
        output_dir = dir_a.parent
    output_dir = Path(output_dir)

    result = compute_comparison(dir_a, dir_b)
    if result is None:
        print("No common variants found between campaigns.")
        return

    lines = ["# Campaign Comparison\n"]
    lines.append(f"A: {result.name_a}")
    lines.append(f"B: {result.name_b}\n")

    lines.append("| Variant | Pass A | Pass B | Delta | Effect | Tokens A | Tokens B |")
    lines.append("|---------|--------|--------|-------|--------|----------|----------|")

    for vc in result.variants:
        if vc.effect_size is not None:
            effect = f"{vc.effect_size:.2f} ({vc.effect_magnitude})"
        else:
            effect = "n/a"

        sign = "+" if vc.delta_pass > 0 else ""
        lines.append(
            f"| {vc.variant} | {vc.pass_rate_a:.1%} | {vc.pass_rate_b:.1%} "
            f"| {sign}{vc.delta_pass:.1%} | {effect} "
            f"| {vc.tokens_mean_a:.0f} | {vc.tokens_mean_b:.0f} |"
        )

    path = output_dir / "comparison.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"Comparison written to {path}")
