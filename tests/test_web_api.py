"""API contract tests for the web interface."""

import json

import pytest
from fastapi.testclient import TestClient

from calibra.web import create_app


def _make_report(task, variant, repeat, outcome="success", verified=True):
    """Build a minimal trial JSON report."""
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
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [{"type": "llm_call", "prompt_tokens_est": 500}],
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 1.1,
            "verified": verified,
            "config_hash": "abc",
        },
    }


def _make_summary(variants_data, trials_data):
    """Build a summary.json from raw variant and trial data."""
    return {"variants": variants_data, "trials": trials_data}


def _stat_block(mean, std=0):
    return {
        "mean": mean,
        "median": mean,
        "std": std,
        "min": mean,
        "max": mean,
        "p90": mean,
        "ci_lower": mean,
        "ci_upper": mean,
    }


def _make_variant(label, n_trials=3, pass_rate=1.0):
    return {
        "variant_label": label,
        "n_trials": n_trials,
        "pass_rate": pass_rate,
        "outcome_counts": {"success": n_trials},
        "turns": _stat_block(3),
        "tool_calls_total": _stat_block(2),
        "tool_calls_failed": _stat_block(0),
        "llm_time_s": _stat_block(1),
        "tool_time_s": _stat_block(0.1),
        "wall_time_s": _stat_block(1.1),
        "compactions": _stat_block(0),
        "prompt_tokens_est": _stat_block(500),
        "score_per_1k_tokens": 2.0,
        "pass_rate_per_minute": 54.5,
    }


def _make_trial_entry(task, variant, outcome="success", verified=True):
    return {
        "task": task,
        "variant_label": variant,
        "outcome": outcome,
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


@pytest.fixture
def results_dir(tmp_path):
    """Create a results directory with two campaigns."""
    # Campaign A: 2 variants, 2 tasks
    ca = tmp_path / "campaign-alpha"
    for task in ("task-a", "task-b"):
        for variant in ("v1_default", "v2_fast"):
            task_dir = ca / task
            task_dir.mkdir(parents=True, exist_ok=True)
            report = _make_report(task, variant, 0)
            (task_dir / f"{variant}_0.json").write_text(json.dumps(report, indent=2))

    variants = [
        _make_variant("v1_default", n_trials=2, pass_rate=1.0),
        _make_variant("v2_fast", n_trials=2, pass_rate=0.5),
    ]
    trials = [
        _make_trial_entry("task-a", "v1_default"),
        _make_trial_entry("task-b", "v1_default"),
        _make_trial_entry("task-a", "v2_fast"),
        _make_trial_entry("task-b", "v2_fast", outcome="failure", verified=False),
    ]
    summary = _make_summary(variants, trials)
    (ca / "summary.json").write_text(json.dumps(summary, indent=2))

    # Campaign B: 1 variant, 1 task
    cb = tmp_path / "campaign-beta"
    task_dir = cb / "task-a"
    task_dir.mkdir(parents=True, exist_ok=True)
    report = _make_report("task-a", "v1_default", 0)
    (task_dir / "v1_default_0.json").write_text(json.dumps(report, indent=2))
    summary_b = _make_summary(
        [_make_variant("v1_default", n_trials=1)],
        [_make_trial_entry("task-a", "v1_default")],
    )
    (cb / "summary.json").write_text(json.dumps(summary_b, indent=2))

    return tmp_path


@pytest.fixture
def client(results_dir):
    app = create_app(results_dir)
    return TestClient(app)


class TestCampaignsEndpoint:
    def test_returns_list(self, client):
        r = client.get("/api/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_campaign_shape(self, client):
        r = client.get("/api/campaigns")
        data = r.json()
        campaign = next(c for c in data if c["name"] == "campaign-alpha")
        assert "n_variants" in campaign
        assert "n_tasks" in campaign
        assert "n_trials" in campaign
        assert "pass_rate" in campaign
        assert "latest" in campaign

    def test_campaign_counts(self, client):
        r = client.get("/api/campaigns")
        data = r.json()
        alpha = next(c for c in data if c["name"] == "campaign-alpha")
        assert alpha["n_variants"] == 2
        assert alpha["n_tasks"] == 2
        assert alpha["n_trials"] == 4

    def test_sorted_by_name(self, client):
        r = client.get("/api/campaigns")
        data = r.json()
        names = [c["name"] for c in data]
        assert names == sorted(names)


class TestCampaignDetailEndpoint:
    def test_returns_summary(self, client):
        r = client.get("/api/campaign/campaign-alpha")
        assert r.status_code == 200
        data = r.json()
        assert "variants" in data
        assert "trials" in data
        assert len(data["variants"]) == 2
        assert len(data["trials"]) == 4

    def test_nonexistent_returns_404(self, client):
        r = client.get("/api/campaign/nonexistent")
        assert r.status_code == 404


class TestHeatmapEndpoint:
    def test_returns_cells(self, client):
        r = client.get("/api/campaign/campaign-alpha/heatmap")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 4  # 2 tasks x 2 variants

    def test_cell_shape(self, client):
        r = client.get("/api/campaign/campaign-alpha/heatmap")
        data = r.json()
        cell = data[0]
        assert "task" in cell
        assert "variant" in cell
        assert "n" in cell
        assert "passes" in cell
        assert "pass_rate" in cell

    def test_pass_rate_calculation(self, client):
        r = client.get("/api/campaign/campaign-alpha/heatmap")
        data = r.json()
        # v1_default/task-a should be pass_rate=1.0 (verified=True)
        v1_task_a = next(c for c in data if c["task"] == "task-a" and c["variant"] == "v1_default")
        assert v1_task_a["pass_rate"] == 1.0
        assert v1_task_a["n"] == 1
        assert v1_task_a["passes"] == 1

    def test_failed_trial_in_heatmap(self, client):
        r = client.get("/api/campaign/campaign-alpha/heatmap")
        data = r.json()
        v2_task_b = next(c for c in data if c["task"] == "task-b" and c["variant"] == "v2_fast")
        assert v2_task_b["pass_rate"] == 0.0
        assert v2_task_b["passes"] == 0

    def test_nonexistent_campaign_returns_404(self, client):
        r = client.get("/api/campaign/nonexistent/heatmap")
        assert r.status_code == 404


class TestTrialEndpoint:
    def test_returns_trial(self, client):
        r = client.get("/api/campaign/campaign-alpha/trial/task-a/v1_default/0")
        assert r.status_code == 200
        data = r.json()
        assert data["calibra"]["task"] == "task-a"
        assert data["calibra"]["variant"] == "v1_default"
        assert data["calibra"]["repeat"] == 0

    def test_nonexistent_trial_returns_404(self, client):
        r = client.get("/api/campaign/campaign-alpha/trial/task-a/v1_default/99")
        assert r.status_code == 404

    def test_nonexistent_task_returns_404(self, client):
        r = client.get("/api/campaign/campaign-alpha/trial/fake-task/v1_default/0")
        assert r.status_code == 404


class TestCompareEndpoint:
    def test_compare_same_campaigns(self, client):
        r = client.get("/api/compare?a=campaign-alpha&b=campaign-beta")
        assert r.status_code == 200
        data = r.json()
        assert "name_a" in data
        assert "name_b" in data
        assert "variants" in data
        # v1_default is common to both
        assert len(data["variants"]) >= 1
        v1 = next(v for v in data["variants"] if v["variant"] == "v1_default")
        assert "pass_rate_a" in v1
        assert "pass_rate_b" in v1
        assert "delta_pass" in v1

    def test_compare_nonexistent_returns_404(self, client):
        r = client.get("/api/compare?a=campaign-alpha&b=nonexistent")
        assert r.status_code == 404


class TestReloadEndpoint:
    def test_reload_returns_ok(self, client):
        r = client.post("/api/reload")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["campaigns"] == 2

    def test_reload_picks_up_new_campaign(self, client, results_dir):
        r = client.get("/api/campaigns")
        assert len(r.json()) == 2

        # Add a new campaign
        new = results_dir / "campaign-gamma"
        new.mkdir()
        summary = _make_summary(
            [_make_variant("v1_default", n_trials=1)],
            [_make_trial_entry("task-a", "v1_default")],
        )
        (new / "summary.json").write_text(json.dumps(summary))

        client.post("/api/reload")
        r = client.get("/api/campaigns")
        assert len(r.json()) == 3


class TestPageRoutes:
    def test_home_page(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "campaign-alpha" in r.text
        assert "campaign-beta" in r.text

    def test_campaign_page(self, client):
        r = client.get("/campaign/campaign-alpha")
        assert r.status_code == 200
        assert "campaign-alpha" in r.text
        assert "v1_default" in r.text

    def test_campaign_page_nonexistent(self, client):
        r = client.get("/campaign/nonexistent")
        assert r.status_code == 404
