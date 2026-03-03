"""Tests for M5 polish: responsive tables, chart containers, keyboard shortcuts, empty/error states."""

import json

import pytest
from fastapi.testclient import TestClient

from calibra.web import create_app


def _stat_block(mean, std=0):
    return {
        "mean": mean,
        "median": mean,
        "std": std,
        "min": mean,
        "max": mean,
        "p90": mean,
        "ci_lower": mean - std,
        "ci_upper": mean + std,
    }


def _make_variant(label, n_trials=2, pass_rate=1.0, tokens_mean=500):
    return {
        "variant_label": label,
        "n_trials": n_trials,
        "pass_rate": pass_rate,
        "outcome_counts": {"success": int(n_trials * pass_rate), "failure": 0},
        "turns": _stat_block(3),
        "tool_calls_total": _stat_block(2),
        "tool_calls_failed": _stat_block(0),
        "llm_time_s": _stat_block(1),
        "tool_time_s": _stat_block(0.1),
        "wall_time_s": _stat_block(1.1),
        "compactions": _stat_block(0),
        "prompt_tokens_est": _stat_block(tokens_mean),
        "score_per_1k_tokens": 2.0,
        "pass_rate_per_minute": 54.5,
    }


def _make_trial_entry(task, variant, repeat=0, verified=True):
    return {
        "task": task,
        "variant_label": variant,
        "repeat": repeat,
        "outcome": "success" if verified else "failure",
        "verified": verified,
        "turns": 3,
        "tool_calls_total": 2,
        "tool_calls_failed": 0,
        "tool_calls_by_name": {},
        "llm_time_s": 1.0,
        "tool_time_s": 0.1,
        "wall_time_s": 1.1,
        "compactions": 0,
        "prompt_tokens_est": 500,
        "skills_used": [],
        "guardrail_interventions": 0,
        "failure_class": None,
    }


def _make_report(task, variant, repeat):
    return {
        "version": 1,
        "result": {"outcome": "success"},
        "stats": {
            "turns": 3,
            "tool_calls_total": 2,
            "tool_calls_succeeded": 2,
            "tool_calls_failed": 0,
            "tool_calls_by_name": {},
            "total_llm_time_s": 1.0,
            "total_tool_time_s": 0.1,
            "prompt_tokens_est": 500,
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [{"type": "llm_call", "prompt_tokens_est": 500, "duration_s": 0.9}],
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 1.1,
            "verified": True,
            "config_hash": "abc",
        },
        "settings": {"model": "test-model"},
    }


@pytest.fixture
def polish_dir(tmp_path):
    campaign = tmp_path / "polish"
    variants = [_make_variant("alpha"), _make_variant("beta")]
    trials = []
    for task in ("t1",):
        task_dir = campaign / task
        task_dir.mkdir(parents=True, exist_ok=True)
        for vlabel in ("alpha", "beta"):
            for rep in range(2):
                report = _make_report(task, vlabel, rep)
                (task_dir / f"{vlabel}_{rep}.json").write_text(json.dumps(report, indent=2))
                trials.append(_make_trial_entry(task, vlabel, repeat=rep))
    (campaign / "summary.json").write_text(
        json.dumps({"variants": variants, "trials": trials}, indent=2)
    )
    return campaign


@pytest.fixture
def client(polish_dir):
    app = create_app(polish_dir.parent)
    return TestClient(app)


class TestResponsiveTables:
    def test_campaign_table_overflow_x_auto(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}")
        assert "overflow-x-auto" in r.text

    def test_variant_per_task_table_overflow_x_auto(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}/variant/alpha")
        assert 'data-test="per-task-table"' in r.text
        # The wrapper div around per-task-table should have overflow-x-auto
        idx = r.text.index('data-test="per-task-table"')
        preceding = r.text[max(0, idx - 200) : idx]
        assert "overflow-x-auto" in preceding

    def test_variant_trials_table_overflow_x_auto(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}/variant/alpha")
        assert 'data-test="trial-list"' in r.text
        idx = r.text.index('data-test="trial-list"')
        preceding = r.text[max(0, idx - 500) : idx]
        assert "overflow-x-auto" in preceding

    def test_compare_table_overflow_x_auto(self, client, polish_dir):
        # Need two campaigns for comparison
        camp_b = polish_dir.parent / "polish-b"
        camp_b.mkdir()
        t1 = camp_b / "t1"
        t1.mkdir()
        report = _make_report("t1", "alpha", 0)
        (t1 / "alpha_0.json").write_text(json.dumps(report, indent=2))
        variants = [_make_variant("alpha")]
        trials = [_make_trial_entry("t1", "alpha")]
        (camp_b / "summary.json").write_text(
            json.dumps({"variants": variants, "trials": trials}, indent=2)
        )
        # Refresh cache
        app = create_app(polish_dir.parent)
        c = TestClient(app)
        r = c.get(f"/compare?a={polish_dir.name}&b=polish-b")
        assert r.status_code == 200
        assert 'data-test="comparison-table"' in r.text
        idx = r.text.index('data-test="comparison-table"')
        preceding = r.text[max(0, idx - 200) : idx]
        assert "overflow-x-auto" in preceding


class TestChartContainers:
    def test_campaign_chart_uses_chart_container_class(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}")
        assert 'class="chart-container"' in r.text

    def test_heatmap_uses_chart_container_lg(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}/tasks")
        assert "chart-container-lg" in r.text


class TestKeyboardShortcuts:
    def test_base_has_escape_handler(self, client, polish_dir):
        r = client.get("/")
        assert "Escape" in r.text

    def test_base_has_slash_handler(self, client, polish_dir):
        r = client.get("/")
        assert "data-shortcut-search" in r.text

    def test_campaign_has_variant_filter_with_search_shortcut(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}")
        assert 'data-test="variant-filter"' in r.text
        assert "data-shortcut-search" in r.text


class TestEmptyErrorStates:
    def test_variant_empty_trials_with_task_filter(self, client, polish_dir):
        r = client.get(f"/campaign/{polish_dir.name}/variant/alpha?task=nonexistent")
        assert r.status_code == 200
        assert 'data-test="empty-trials"' in r.text

    def test_tasks_empty_heatmap(self, tmp_path):
        campaign = tmp_path / "empty-camp"
        campaign.mkdir()
        variants = [_make_variant("v1")]
        (campaign / "summary.json").write_text(
            json.dumps({"variants": variants, "trials": []}, indent=2)
        )
        app = create_app(tmp_path)
        c = TestClient(app)
        r = c.get(f"/campaign/{campaign.name}/tasks")
        assert r.status_code == 200
        assert 'data-test="empty-heatmap"' in r.text

    def test_trial_corrupt_json_shows_error(self, client, polish_dir):
        corrupt_path = polish_dir / "t1" / "alpha_99.json"
        corrupt_path.write_text("{broken json!!!")
        r = client.get(f"/campaign/{polish_dir.name}/trial/t1/alpha/99")
        assert r.status_code == 200
        assert 'data-test="error-message"' in r.text
        assert "Failed to load" in r.text

    def test_trial_invalid_utf8_shows_error(self, client, polish_dir):
        corrupt_path = polish_dir / "t1" / "alpha_98.json"
        corrupt_path.write_bytes(b"\x80\x81\x82\xff")
        r = client.get(f"/campaign/{polish_dir.name}/trial/t1/alpha/98")
        assert r.status_code == 200
        assert 'data-test="error-message"' in r.text
        assert "Failed to load" in r.text

    def test_empty_heatmap_no_plotly_error(self, tmp_path):
        campaign = tmp_path / "no-data"
        campaign.mkdir()
        variants = [_make_variant("v1")]
        (campaign / "summary.json").write_text(
            json.dumps({"variants": variants, "trials": []}, indent=2)
        )
        app = create_app(tmp_path)
        c = TestClient(app)
        r = c.get(f"/campaign/{campaign.name}/tasks")
        assert r.status_code == 200
        assert "if (!heatmapEl) return;" in r.text
