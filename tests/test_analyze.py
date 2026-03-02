"""Tests for analyze.py: metrics, aggregation, statistics, ranking."""

import pytest

from calibra.analyze import (
    AggregateMetrics,
    StatSummary,
    TrialMetrics,
    aggregate_variant,
    cliffs_delta,
    extract_metrics,
    flag_instabilities,
    paired_bootstrap_ci,
    pareto_front,
    permutation_test,
    rank_variants,
)


def _report(outcome="success", turns=5, tool_ok=3, tool_fail=0, llm_time=1.5, tool_time=0.5):
    return {
        "version": 1,
        "result": {"outcome": outcome},
        "stats": {
            "turns": turns,
            "tool_calls_total": tool_ok + tool_fail,
            "tool_calls_succeeded": tool_ok,
            "tool_calls_failed": tool_fail,
            "tool_calls_by_name": {"read": {"succeeded": tool_ok, "failed": tool_fail}},
            "total_llm_time_s": llm_time,
            "total_tool_time_s": tool_time,
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [
            {"type": "llm_call", "prompt_tokens_est": 500},
            {"type": "llm_call", "prompt_tokens_est": 300},
        ],
        "calibra": {
            "task": "hello",
            "variant": "m0_default_none_none_base",
            "wall_time_s": 2.0,
            "verified": True,
        },
    }


def test_extract_metrics():
    report = _report()
    m = extract_metrics(report, 2.0, True, None)
    assert m.task == "hello"
    assert m.outcome == "success"
    assert m.turns == 5
    assert m.prompt_tokens_est == 800
    assert m.verified is True


def test_extract_metrics_no_timeline():
    report = _report()
    report["timeline"] = []
    m = extract_metrics(report, 1.0, None, None)
    assert m.prompt_tokens_est == 0


def _trial_metrics(verified=True, turns=5, tokens=800, wall_time=2.0):
    return TrialMetrics(
        task="hello",
        variant_label="v1",
        repeat=0,
        outcome="success",
        verified=verified,
        turns=turns,
        tool_calls_total=3,
        tool_calls_failed=0,
        tool_calls_by_name={},
        llm_time_s=1.5,
        tool_time_s=0.5,
        wall_time_s=wall_time,
        compactions=0,
        prompt_tokens_est=tokens,
        skills_used=[],
        guardrail_interventions=0,
        failure_class=None,
    )


def test_aggregate_basic():
    metrics = [_trial_metrics() for _ in range(3)]
    agg = aggregate_variant(metrics)
    assert agg.variant_label == "v1"
    assert agg.n_trials == 3
    assert agg.pass_rate == 1.0
    assert agg.turns.mean == 5.0
    assert agg.turns.std == 0.0


def test_aggregate_mixed_verification():
    metrics = [
        _trial_metrics(verified=True),
        _trial_metrics(verified=False),
        _trial_metrics(verified=True),
    ]
    agg = aggregate_variant(metrics)
    assert abs(agg.pass_rate - 2 / 3) < 0.01


def test_aggregate_zero_trials():
    with pytest.raises(ValueError):
        aggregate_variant([])


def test_cliffs_delta_identical():
    x = [1.0, 2.0, 3.0]
    y = [1.0, 2.0, 3.0]
    d, mag = cliffs_delta(x, y)
    assert d == 0.0
    assert mag == "negligible"


def test_cliffs_delta_large():
    x = [10.0, 20.0, 30.0]
    y = [1.0, 2.0, 3.0]
    d, mag = cliffs_delta(x, y)
    assert d == 1.0
    assert mag == "large"


def test_paired_bootstrap_ci():
    a = [10.0, 12.0, 11.0, 13.0, 10.0]
    b = [8.0, 9.0, 10.0, 11.0, 7.0]
    lo, hi = paired_bootstrap_ci(a, b, n_bootstrap=5000, seed=42)
    assert lo > 0  # A > B consistently
    assert hi > lo


def test_permutation_test_same():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0]
    p = permutation_test(a, b, n_perms=1000, seed=42)
    assert p == 1.0  # no difference


def test_permutation_test_different():
    a = [100.0, 200.0, 300.0, 400.0, 500.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0]
    p = permutation_test(a, b, n_perms=1000, seed=42)
    assert p < 0.1  # with n=5 the sign-flip test has limited power


def test_rank_variants():
    aggs = [
        _make_agg("v1", pass_rate=0.5, tokens=1000),
        _make_agg("v2", pass_rate=0.8, tokens=2000),
        _make_agg("v3", pass_rate=0.8, tokens=1500),
    ]
    ranked = rank_variants(aggs)
    assert ranked[0].variant_label == "v3"  # higher pass, fewer tokens
    assert ranked[1].variant_label == "v2"  # higher pass, more tokens
    assert ranked[2].variant_label == "v1"  # lower pass


def test_pareto_front():
    aggs = [
        _make_agg("v1", pass_rate=0.5, tokens=500),
        _make_agg("v2", pass_rate=0.8, tokens=2000),
        _make_agg("v3", pass_rate=0.9, tokens=3000),
        _make_agg("v4", pass_rate=0.7, tokens=2500),  # dominated
    ]
    front = pareto_front(aggs)
    labels = [a.variant_label for a in front]
    assert "v3" in labels  # best pass rate
    assert "v1" in labels  # fewest tokens
    assert "v4" not in labels  # dominated


def test_flag_instabilities_low_repeats():
    agg = _make_agg("v1", n_trials=2)
    warnings = flag_instabilities(agg)
    assert any("low confidence" in w for w in warnings)


def test_flag_instabilities_high_cv():
    agg = _make_agg("v1", n_trials=5)
    agg.turns = StatSummary(
        mean=5.0, median=5.0, std=6.0, min=1.0, max=10.0, p90=9.0, ci_lower=3.0, ci_upper=7.0
    )
    warnings = flag_instabilities(agg)
    assert any("High CV" in w for w in warnings)


def test_extract_metrics_malformed_numeric_fields():
    """Regression: non-numeric stats values must not crash extract_metrics."""
    report = _report()
    report["stats"]["turns"] = "not_a_number"
    report["stats"]["total_llm_time_s"] = None
    report["stats"]["total_tool_time_s"] = "bad"
    report["stats"]["compactions"] = "oops"
    report["calibra"]["wall_time_s"] = "broken"
    report["timeline"] = [
        {"type": "llm_call", "prompt_tokens_est": "garbage"},
        {"type": "llm_call", "prompt_tokens_est": 200},
    ]
    m = extract_metrics(report, 0, True, None)
    assert m.turns == 0.0
    assert m.llm_time_s == 0.0
    assert m.tool_time_s == 0.0
    assert m.wall_time_s == 0.0
    assert m.prompt_tokens_est == 200.0  # "garbage" → 0, 200 → 200


def test_aggregate_variant_malformed_numeric_fields():
    """Regression: non-numeric TrialMetrics values must not crash aggregate_variant."""
    m = _trial_metrics()
    # Simulate a field that somehow ended up as a string
    m.turns = "oops"
    m.llm_time_s = None
    agg = aggregate_variant([m])
    assert agg.turns.mean == 0.0
    assert agg.llm_time_s.mean == 0.0


def test_extract_metrics_non_finite_values():
    """Regression: nan/inf in trial data must coerce to 0, not propagate."""
    report = _report()
    report["stats"]["turns"] = "nan"
    report["stats"]["total_llm_time_s"] = "inf"
    report["stats"]["total_tool_time_s"] = "-inf"
    report["calibra"]["wall_time_s"] = float("nan")
    report["timeline"] = [
        {"type": "llm_call", "prompt_tokens_est": float("inf")},
        {"type": "llm_call", "prompt_tokens_est": 200},
    ]
    m = extract_metrics(report, 0, True, None)
    assert m.turns == 0.0
    assert m.llm_time_s == 0.0
    assert m.tool_time_s == 0.0
    assert m.wall_time_s == 0.0
    assert m.prompt_tokens_est == 200.0


def test_aggregate_variant_non_finite_values():
    """Regression: nan/inf in TrialMetrics must coerce to 0 during aggregation."""
    m = _trial_metrics()
    m.turns = float("nan")
    m.prompt_tokens_est = float("inf")
    agg = aggregate_variant([m])
    assert agg.turns.mean == 0.0
    assert agg.prompt_tokens_est.mean == 0.0


def _make_agg(label, pass_rate=1.0, tokens=800, n_trials=5):
    stat = StatSummary(
        mean=5.0, median=5.0, std=0.5, min=4.0, max=6.0, p90=5.5, ci_lower=4.5, ci_upper=5.5
    )
    tok_stat = StatSummary(
        mean=tokens,
        median=tokens,
        std=10.0,
        min=tokens - 50,
        max=tokens + 50,
        p90=tokens,
        ci_lower=tokens - 20,
        ci_upper=tokens + 20,
    )
    return AggregateMetrics(
        variant_label=label,
        n_trials=n_trials,
        pass_rate=pass_rate,
        outcome_counts={"success": n_trials},
        turns=stat,
        tool_calls_total=stat,
        tool_calls_failed=stat,
        llm_time_s=stat,
        tool_time_s=stat,
        wall_time_s=stat,
        compactions=stat,
        prompt_tokens_est=tok_stat,
        score_per_1k_tokens=pass_rate * 1000 / tokens if tokens else 0,
        pass_rate_per_minute=0.5,
    )
