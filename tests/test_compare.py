"""Tests for compare.py: compute_comparison and compare_campaigns."""

import json

from calibra.compare import (
    ComparisonResult,
    VariantComparison,
    compare_campaigns,
    compute_comparison,
)


def _make_trial_report(task, variant, repeat, verified=True, tokens=800):
    return {
        "version": 1,
        "result": {"outcome": "success"},
        "stats": {
            "turns": 5,
            "tool_calls_total": 3,
            "tool_calls_succeeded": 3,
            "tool_calls_failed": 0,
            "tool_calls_by_name": {},
            "total_llm_time_s": 1.5,
            "total_tool_time_s": 0.1,
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [
            {"type": "llm_call", "prompt_tokens_est": tokens},
        ],
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 2.0,
            "verified": verified,
            "config_hash": "abc123",
        },
    }


def _setup_campaign(tmp_path, name, variant, tasks, verified=True, tokens=800):
    campaign_dir = tmp_path / name
    for task in tasks:
        task_dir = campaign_dir / task
        task_dir.mkdir(parents=True)
        for r in range(2):
            report = _make_trial_report(task, variant, r, verified=verified, tokens=tokens)
            (task_dir / f"{variant}_{r}.json").write_text(json.dumps(report, indent=2) + "\n")
    return campaign_dir


def test_compute_comparison_basic(tmp_path):
    dir_a = _setup_campaign(tmp_path, "run-a", "v1_default_none_none_base", ["hello"], tokens=1000)
    dir_b = _setup_campaign(tmp_path, "run-b", "v1_default_none_none_base", ["hello"], tokens=500)

    result = compute_comparison(dir_a, dir_b)

    assert result is not None
    assert isinstance(result, ComparisonResult)
    assert result.name_a == "run-a"
    assert result.name_b == "run-b"
    assert len(result.variants) == 1

    vc = result.variants[0]
    assert isinstance(vc, VariantComparison)
    assert vc.variant == "v1_default_none_none_base"
    assert vc.pass_rate_a == 1.0
    assert vc.pass_rate_b == 1.0
    assert vc.delta_pass == 0.0
    assert vc.tokens_mean_a == 1000.0
    assert vc.tokens_mean_b == 500.0
    assert vc.effect_size is not None
    assert vc.effect_magnitude is not None


def test_compute_comparison_no_common_variants(tmp_path):
    dir_a = _setup_campaign(tmp_path, "run-a", "v1_default_none_none_base", ["hello"])
    dir_b = _setup_campaign(tmp_path, "run-b", "v2_default_none_none_base", ["hello"])

    result = compute_comparison(dir_a, dir_b)
    assert result is None


def test_compute_comparison_mixed_verification(tmp_path):
    dir_a = _setup_campaign(
        tmp_path, "run-a", "v1_default_none_none_base", ["hello"], verified=True
    )
    dir_b = _setup_campaign(
        tmp_path, "run-b", "v1_default_none_none_base", ["hello"], verified=False
    )

    result = compute_comparison(dir_a, dir_b)
    assert result is not None
    vc = result.variants[0]
    assert vc.pass_rate_a == 1.0
    assert vc.pass_rate_b == 0.0
    assert vc.delta_pass == -1.0


def test_compare_campaigns_writes_markdown(tmp_path):
    dir_a = _setup_campaign(tmp_path, "run-a", "v1_default_none_none_base", ["hello"], tokens=1000)
    dir_b = _setup_campaign(tmp_path, "run-b", "v1_default_none_none_base", ["hello"], tokens=500)

    compare_campaigns(dir_a, dir_b, output_dir=tmp_path)

    md_path = tmp_path / "comparison.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "Campaign Comparison" in content
    assert "run-a" in content
    assert "run-b" in content
    assert "v1_default_none_none_base" in content
    assert "100.0%" in content


def test_compare_campaigns_no_common(tmp_path, capsys):
    dir_a = _setup_campaign(tmp_path, "run-a", "v1_default_none_none_base", ["hello"])
    dir_b = _setup_campaign(tmp_path, "run-b", "v2_default_none_none_base", ["hello"])

    compare_campaigns(dir_a, dir_b, output_dir=tmp_path)

    captured = capsys.readouterr()
    assert "No common variants" in captured.out
    assert not (tmp_path / "comparison.md").exists()
