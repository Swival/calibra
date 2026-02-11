"""Tests for M3 drilldown pages: task matrix, variant detail, trial inspector."""

import json

import pytest
from fastapi.testclient import TestClient

from calibra.web import create_app


def _stat_block(mean, std=0, median=None):
    if median is None:
        median = mean
    return {
        "mean": mean,
        "median": median,
        "std": std,
        "min": mean,
        "max": mean,
        "p90": mean,
        "ci_lower": mean - std,
        "ci_upper": mean + std,
    }


def _make_variant(
    label, n_trials=3, pass_rate=1.0, turns_mean=3, tokens_mean=500, llm_time=1, wall_time=1.1
):
    return {
        "variant_label": label,
        "n_trials": n_trials,
        "pass_rate": pass_rate,
        "outcome_counts": {
            "success": int(n_trials * pass_rate),
            "failure": n_trials - int(n_trials * pass_rate),
        },
        "turns": _stat_block(turns_mean),
        "tool_calls_total": _stat_block(2),
        "tool_calls_failed": _stat_block(0),
        "llm_time_s": _stat_block(llm_time),
        "tool_time_s": _stat_block(0.1),
        "wall_time_s": _stat_block(wall_time),
        "compactions": _stat_block(0),
        "prompt_tokens_est": _stat_block(tokens_mean),
        "score_per_1k_tokens": (pass_rate * 1000 / tokens_mean) if tokens_mean > 0 else 0,
        "pass_rate_per_minute": (pass_rate * 60 / wall_time) if wall_time > 0 else 0,
    }


def _make_trial_entry(
    task, variant, repeat=0, verified=True, failure_class=None, tool_calls_by_name=None
):
    return {
        "task": task,
        "variant_label": variant,
        "repeat": repeat,
        "outcome": "success" if verified else "failure",
        "verified": verified,
        "turns": 3,
        "tool_calls_total": 2,
        "tool_calls_failed": 0,
        "tool_calls_by_name": tool_calls_by_name or {},
        "llm_time_s": 1.0,
        "tool_time_s": 0.1,
        "wall_time_s": 1.1,
        "compactions": 0,
        "prompt_tokens_est": 500,
        "skills_used": [],
        "guardrail_interventions": 0,
        "failure_class": failure_class,
    }


def _make_report(
    task, variant, repeat, outcome="success", verified=True, timeline=None, settings=None
):
    return {
        "version": 1,
        "result": {"outcome": outcome},
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
        "timeline": timeline
        or [
            {
                "type": "llm_call",
                "prompt_tokens_est": 500,
                "duration_s": 0.9,
                "finish_reason": "stop",
            }
        ],
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 1.1,
            "verified": verified,
            "config_hash": "abc",
        },
        "settings": settings or {"model": "claude-sonnet", "provider": "anthropic"},
    }


def _make_summary(variants, trials):
    return {"variants": variants, "trials": trials}


@pytest.fixture
def drilldown_dir(tmp_path):
    """Campaign with 2 variants, 2 tasks, trial JSON files including diverse timeline events."""
    campaign = tmp_path / "drill"

    variants = [
        _make_variant("va", n_trials=4, pass_rate=0.75, turns_mean=4, tokens_mean=600),
        _make_variant("vb", n_trials=4, pass_rate=0.5, turns_mean=6, tokens_mean=900),
    ]

    trials = []
    for task in ("task-x", "task-y"):
        for vi, vlabel in enumerate(("va", "vb")):
            task_dir = campaign / task
            task_dir.mkdir(parents=True, exist_ok=True)
            for rep in range(2):
                verified = (vi + rep) % 2 == 0
                outcome = "success" if verified else "failure"
                fc = None if verified else "task"

                timeline = [
                    {
                        "type": "llm_call",
                        "prompt_tokens_est": 500,
                        "duration_s": 0.9,
                        "finish_reason": "stop",
                        "is_retry": False,
                    },
                    {
                        "type": "tool_call",
                        "name": "bash",
                        "succeeded": True,
                        "duration_s": 0.2,
                        "arguments": {"cmd": "echo hello"},
                    },
                    {
                        "type": "compaction",
                        "strategy": "sliding_window",
                        "tokens_before": 4000,
                        "tokens_after": 2000,
                    },
                    {"type": "guardrail", "tool": "bash", "level": "warn"},
                    {
                        "type": "llm_call",
                        "prompt_tokens_est": 300,
                        "duration_s": 0.5,
                        "finish_reason": "stop",
                        "is_retry": True,
                    },
                    {
                        "type": "tool_call",
                        "name": "write_file",
                        "succeeded": not verified,
                        "duration_s": 0.1,
                    },
                ]

                report = _make_report(
                    task,
                    vlabel,
                    rep,
                    outcome=outcome,
                    verified=verified,
                    timeline=timeline,
                    settings={"model": "claude-sonnet", "provider": "anthropic", "max_turns": 10},
                )
                (task_dir / f"{vlabel}_{rep}.json").write_text(json.dumps(report, indent=2))

                tcbn = {"bash": {"succeeded": 1, "failed": 0}}
                trials.append(
                    _make_trial_entry(
                        task,
                        vlabel,
                        repeat=rep,
                        verified=verified,
                        failure_class=fc,
                        tool_calls_by_name=tcbn,
                    )
                )

    (campaign / "summary.json").write_text(json.dumps(_make_summary(variants, trials), indent=2))
    return campaign


@pytest.fixture
def client(drilldown_dir):
    app = create_app(drilldown_dir.parent)
    return TestClient(app)


class TestTaskMatrix:
    def test_200_response(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert r.status_code == 200

    def test_heatmap_container(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert 'data-test="heatmap-container"' in r.text

    def test_plotly_loaded(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert "plotly-3.4.0.min.js" in r.text

    def test_breadcrumb(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert 'data-test="breadcrumb"' in r.text
        assert drilldown_dir.name in r.text
        assert "Task Matrix" in r.text

    def test_404_for_missing_campaign(self, client):
        r = client.get("/campaign/nonexistent/tasks")
        assert r.status_code == 404

    def test_cells_data_embedded(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert 'id="cells-data"' in r.text

    def test_all_tasks_present(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert "task-x" in r.text
        assert "task-y" in r.text


class TestVariantDetail:
    def test_200_response(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert r.status_code == 200

    def test_kpis_present(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="kpi-tiles"' in r.text
        assert 'data-test="kpi-pass-rate"' in r.text
        assert 'data-test="kpi-trials"' in r.text
        assert 'data-test="kpi-turns"' in r.text
        assert 'data-test="kpi-tokens"' in r.text

    def test_per_task_table(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="per-task-table"' in r.text
        assert "task-x" in r.text
        assert "task-y" in r.text

    def test_chart_containers(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="chart-turns"' in r.text

    def test_trial_list(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="trial-list"' in r.text
        assert 'data-test="trial-row"' in r.text

    def test_outcome_badges(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="outcome-badge"' in r.text

    def test_404_for_missing_variant(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/nonexistent")
        assert r.status_code == 404

    def test_404_for_missing_campaign(self, client):
        r = client.get("/campaign/nonexistent/variant/va")
        assert r.status_code == 404

    def test_task_filter_query_param(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va?task=task-x")
        assert r.status_code == 200
        assert "filtered: task-x" in r.text

    def test_variant_label_in_header(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert 'data-test="variant-label"' in r.text
        assert ">va<" in r.text

    def test_dimensions_shown(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert "Dimensions:" in r.text

    def test_plotly_loaded(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert "plotly-3.4.0.min.js" in r.text


class TestTrialInspector:
    def test_200_response(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert r.status_code == 200

    def test_timeline_rendered(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="timeline"' in r.text
        assert 'data-test="timeline-event"' in r.text

    def test_outcome_badge(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="outcome-badge"' in r.text

    def test_settings_panel(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="settings-panel"' in r.text
        assert "claude-sonnet" in r.text
        assert "anthropic" in r.text

    def test_raw_json_panel(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="raw-json"' in r.text
        assert "raw-json-content" in r.text

    def test_kpi_tiles(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="kpi-tiles"' in r.text
        assert "Wall Time" in r.text
        assert "Turns" in r.text
        assert "Tokens" in r.text
        assert "LLM Time" in r.text
        assert "Tool Time" in r.text

    def test_event_types_rendered(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-event-type="llm_call"' in r.text
        assert 'data-event-type="tool_call"' in r.text
        assert 'data-event-type="compaction"' in r.text
        assert 'data-event-type="guardrail"' in r.text

    def test_404_for_missing_trial(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/99")
        assert r.status_code == 404

    def test_404_for_missing_task(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/fake-task/va/0")
        assert r.status_code == 404

    def test_path_traversal_rejected(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/..%2f..%2fetc/0")
        assert r.status_code in (400, 404)

    def test_raw_json_uses_textcontent(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ".textContent" in r.text

    def test_breadcrumb(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert 'data-test="breadcrumb"' in r.text
        assert f"/campaign/{drilldown_dir.name}/variant/va" in r.text
        assert f'/campaign/{drilldown_dir.name}"' in r.text


class TestNavigation:
    def test_campaign_has_variant_links(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}")
        assert f"/campaign/{drilldown_dir.name}/variant/va" in r.text
        assert 'data-nav="variant-link"' in r.text

    def test_campaign_has_task_matrix_link(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}")
        assert f"/campaign/{drilldown_dir.name}/tasks" in r.text
        assert 'data-nav="task-matrix"' in r.text

    def test_variant_has_trial_links(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert f"/campaign/{drilldown_dir.name}/trial/" in r.text

    def test_trial_has_variant_breadcrumb(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert f"/campaign/{drilldown_dir.name}/variant/va" in r.text

    def test_three_click_path(self, client, drilldown_dir):
        """Verify the 3-click path: campaign → variant → trial."""
        r1 = client.get(f"/campaign/{drilldown_dir.name}")
        assert r1.status_code == 200
        assert f"/campaign/{drilldown_dir.name}/variant/va" in r1.text

        r2 = client.get(f"/campaign/{drilldown_dir.name}/variant/va")
        assert r2.status_code == 200
        assert f"/campaign/{drilldown_dir.name}/trial/" in r2.text

        r3 = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert r3.status_code == 200
        assert 'data-test="timeline"' in r3.text


class TestTimelineEventKeys:
    """Regression: timeline must use real Swival field names (name, succeeded, is_retry)."""

    def test_tool_name_rendered(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ">bash<" in r.text

    def test_tool_succeeded_renders_ok(self, client, drilldown_dir):
        """First tool_call has succeeded=True → should show 'ok' badge."""
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ">ok<" in r.text

    def test_tool_failed_renders_fail(self, client, drilldown_dir):
        """va rep=0 is verified=True, so write_file has succeeded=not True=False → 'fail'."""
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ">fail<" in r.text

    def test_is_retry_badge_shown(self, client, drilldown_dir):
        """Second llm_call has is_retry=True → retry badge should appear."""
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ">retry<" in r.text


class TestTokenKPI:
    """Regression: token KPI must sum timeline llm_call events, not read stats."""

    def test_token_total_from_timeline(self, client, drilldown_dir):
        """Timeline has two llm_calls: 500 + 300 = 800 tokens."""
        r = client.get(f"/campaign/{drilldown_dir.name}/trial/task-x/va/0")
        assert ">800<" in r.text


class TestMalformedSummaryData:
    """Regression: non-numeric fields in summary.json must not cause 500."""

    def test_task_matrix_malformed_turns(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        variants = [_make_variant("v1")]
        trials = [_make_trial_entry("t1", "v1")]
        trials[0]["turns"] = "not_a_number"
        trials[0]["prompt_tokens_est"] = None
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
        client = TestClient(create_app(tmp_path))
        r = client.get("/campaign/bad/tasks")
        assert r.status_code == 200

    def test_variant_detail_malformed_fields(self, tmp_path):
        d = tmp_path / "bad2"
        d.mkdir()
        variants = [_make_variant("v1")]
        trials = [_make_trial_entry("t1", "v1")]
        trials[0]["turns"] = "oops"
        trials[0]["wall_time_s"] = "broken"
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
        client = TestClient(create_app(tmp_path))
        r = client.get("/campaign/bad2/variant/v1")
        assert r.status_code == 200


class TestHeatmapClick:
    """Regression: heatmap click must use pt.x/pt.y as category values, not indices."""

    def test_click_uses_category_values(self, client, drilldown_dir):
        r = client.get(f"/campaign/{drilldown_dir.name}/tasks")
        assert "var variant = pt.x;" in r.text
        assert "var task = pt.y;" in r.text
        assert "variants[pt.x]" not in r.text
        assert "tasks[pt.y]" not in r.text


class TestTrialMalformedNumeric:
    """Regression: trial inspector must not 500 on non-numeric fields in trial JSON."""

    def _write_malformed_trial(self, tmp_path):
        campaign = tmp_path / "mal"
        task_dir = campaign / "t1"
        task_dir.mkdir(parents=True)
        report = _make_report("t1", "v1", 0)
        report["calibra"]["wall_time_s"] = "oops"
        report["stats"]["total_llm_time_s"] = "bad"
        report["stats"]["total_tool_time_s"] = None
        report["timeline"] = [
            {
                "type": "llm_call",
                "prompt_tokens_est": "not_int",
                "duration_s": "slow",
                "finish_reason": "stop",
                "is_retry": False,
            },
            {"type": "tool_call", "name": "bash", "succeeded": True, "duration_s": "nope"},
        ]
        (task_dir / "v1_0.json").write_text(json.dumps(report, indent=2))
        summary = _make_summary(
            [_make_variant("v1", n_trials=1)],
            [_make_trial_entry("t1", "v1")],
        )
        (campaign / "summary.json").write_text(json.dumps(summary))
        return tmp_path

    def test_malformed_wall_time(self, tmp_path):
        root = self._write_malformed_trial(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/campaign/mal/trial/t1/v1/0")
        assert r.status_code == 200

    def test_malformed_timeline_tokens(self, tmp_path):
        root = self._write_malformed_trial(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/campaign/mal/trial/t1/v1/0")
        assert r.status_code == 200
        assert "Tokens" in r.text

    def test_malformed_duration_s(self, tmp_path):
        root = self._write_malformed_trial(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/campaign/mal/trial/t1/v1/0")
        assert r.status_code == 200
        assert "LLM Call" in r.text
