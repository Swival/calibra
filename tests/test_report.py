"""Tests for report.py and analyze_campaign end-to-end."""

import csv
import json

from calibra.analyze import (
    AggregateMetrics,
    StatSummary,
    TrialMetrics,
    analyze_campaign,
)
from calibra.report import write_summary_csv, write_summary_json, write_summary_md


def _stat(mean=5.0):
    return StatSummary(
        mean=mean, median=mean, std=0.5, min=4.0, max=6.0, p90=5.5, ci_lower=4.5, ci_upper=5.5
    )


def _agg(label="v1", pass_rate=0.8, tokens=1000, n_trials=5):
    return AggregateMetrics(
        variant_label=label,
        n_trials=n_trials,
        pass_rate=pass_rate,
        outcome_counts={
            "success": int(n_trials * pass_rate),
            "exhausted": n_trials - int(n_trials * pass_rate),
        },
        turns=_stat(),
        tool_calls_total=_stat(3.0),
        tool_calls_failed=_stat(0.0),
        llm_time_s=_stat(1.5),
        tool_time_s=_stat(0.5),
        wall_time_s=_stat(2.0),
        compactions=_stat(0.0),
        prompt_tokens_est=_stat(float(tokens)),
        score_per_1k_tokens=round(pass_rate * 1000 / tokens, 4) if tokens else 0,
        pass_rate_per_minute=0.5,
    )


def _metric(label="v1", verified=True):
    return TrialMetrics(
        task="hello",
        variant_label=label,
        repeat=0,
        outcome="success",
        verified=verified,
        turns=5,
        tool_calls_total=3,
        tool_calls_failed=0,
        tool_calls_by_name={},
        llm_time_s=1.5,
        tool_time_s=0.5,
        wall_time_s=2.0,
        compactions=0,
        prompt_tokens_est=800,
        skills_used=[],
        guardrail_interventions=0,
        failure_class=None,
    )


def test_write_summary_json(tmp_path):
    aggs = [_agg("v1"), _agg("v2", pass_rate=0.6)]
    metrics = [_metric("v1"), _metric("v2")]
    write_summary_json(tmp_path, aggs, metrics)

    path = tmp_path / "summary.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data["variants"]) == 2
    assert len(data["trials"]) == 2


def test_write_summary_csv(tmp_path):
    aggs = [_agg("v1"), _agg("v2")]
    write_summary_csv(tmp_path, aggs)

    path = tmp_path / "summary.csv"
    assert path.exists()
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["variant"] == "v1"
    assert "pass_rate" in rows[0]


def test_write_summary_md(tmp_path):
    aggs = [_agg("v1"), _agg("v2")]
    rankings = aggs
    front = [aggs[0]]
    write_summary_md(tmp_path, rankings, front, aggs)

    path = tmp_path / "summary.md"
    assert path.exists()
    content = path.read_text()
    assert "Rankings" in content
    assert "v1" in content
    assert "Pareto" in content


def test_analyze_campaign_e2e(tmp_path):
    results = tmp_path / "results"
    task_dir = results / "hello"
    task_dir.mkdir(parents=True)

    for i in range(3):
        report = {
            "version": 1,
            "result": {"outcome": "success"},
            "stats": {
                "turns": 5,
                "tool_calls_total": 3,
                "tool_calls_succeeded": 3,
                "tool_calls_failed": 0,
                "tool_calls_by_name": {},
                "total_llm_time_s": 1.5,
                "total_tool_time_s": 0.5,
                "compactions": 0,
                "skills_used": [],
                "guardrail_interventions": 0,
            },
            "timeline": [
                {"type": "llm_call", "prompt_tokens_est": 400},
            ],
            "calibra": {
                "task": "hello",
                "variant": "m0_default_none_none_base",
                "repeat": i,
                "wall_time_s": 2.0,
                "verified": True,
            },
        }
        with open(task_dir / f"m0_default_none_none_base_{i}.json", "w") as f:
            json.dump(report, f)

    analyze_campaign(results, output_dir=results)

    assert (results / "summary.json").exists()
    assert (results / "summary.md").exists()
    assert (results / "summary.csv").exists()

    data = json.loads((results / "summary.json").read_text())
    assert len(data["variants"]) == 1
    assert data["variants"][0]["pass_rate"] == 1.0
