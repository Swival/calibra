"""Tests for M4 comparison page and static export verification."""

import json

import pytest
from fastapi.testclient import TestClient

from calibra.web import create_app
from calibra.web.export import SCHEMA_VERSION, build_static_site


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
        "outcome_counts": {
            "success": int(n_trials * pass_rate),
            "failure": n_trials - int(n_trials * pass_rate),
        },
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


def _make_trial_entry(task, variant, verified=True):
    return {
        "task": task,
        "variant_label": variant,
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


def _make_report(task, variant, repeat, verified=True, tokens=500):
    return {
        "version": 1,
        "result": {"outcome": "success" if verified else "failure"},
        "stats": {
            "turns": 3,
            "tool_calls_total": 2,
            "tool_calls_succeeded": 2,
            "tool_calls_failed": 0,
            "tool_calls_by_name": {},
            "total_llm_time_s": 1.0,
            "total_tool_time_s": 0.1,
            "prompt_tokens_est": tokens,
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [
            {
                "type": "llm_call",
                "prompt_tokens_est": tokens,
                "duration_s": 0.9,
                "finish_reason": "stop",
            },
        ],
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 1.1,
            "verified": verified,
            "config_hash": "abc",
        },
        "settings": {"model": "claude-sonnet", "provider": "anthropic"},
    }


def _make_summary(variants, trials):
    return {"variants": variants, "trials": trials}


def _write_campaign(base_dir, name, variant_labels, tasks, pass_rates=None, tokens=None):
    """Write a campaign with trial JSON files and summary.json.

    pass_rates: dict mapping variant_label -> pass_rate (default 1.0)
    tokens: dict mapping variant_label -> tokens (default 500)
    """
    if pass_rates is None:
        pass_rates = {}
    if tokens is None:
        tokens = {}

    campaign_dir = base_dir / name
    variants = []
    trials = []
    for vlabel in variant_labels:
        pr = pass_rates.get(vlabel, 1.0)
        tok = tokens.get(vlabel, 500)
        n_trials = len(tasks) * 2  # 2 repeats per task
        variants.append(_make_variant(vlabel, n_trials=n_trials, pass_rate=pr, tokens_mean=tok))
        for task in tasks:
            task_dir = campaign_dir / task
            task_dir.mkdir(parents=True, exist_ok=True)
            for rep in range(2):
                verified = True if pr >= 1.0 else (rep == 0)
                report = _make_report(task, vlabel, rep, verified=verified, tokens=tok)
                (task_dir / f"{vlabel}_{rep}.json").write_text(json.dumps(report, indent=2))
                trials.append(_make_trial_entry(task, vlabel, verified=verified))

    (campaign_dir / "summary.json").write_text(
        json.dumps(_make_summary(variants, trials), indent=2)
    )
    return campaign_dir


@pytest.fixture
def compare_dir(tmp_path):
    """Two campaigns with shared variant 'va' and one unique each."""
    _write_campaign(
        tmp_path,
        "camp-a",
        variant_labels=["va", "vb"],
        tasks=["task1"],
        pass_rates={"va": 0.5, "vb": 1.0},
        tokens={"va": 500, "vb": 800},
    )
    _write_campaign(
        tmp_path,
        "camp-b",
        variant_labels=["va", "vc"],
        tasks=["task1"],
        pass_rates={"va": 1.0, "vc": 0.5},
        tokens={"va": 600, "vc": 700},
    )
    return tmp_path


@pytest.fixture
def client(compare_dir):
    app = create_app(compare_dir)
    return TestClient(app)


class TestComparePage:
    def test_200_without_params(self, client):
        r = client.get("/compare")
        assert r.status_code == 200

    def test_campaign_picker_renders(self, client):
        r = client.get("/compare")
        assert 'data-test="campaign-picker"' in r.text

    def test_200_with_both_params(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert r.status_code == 200

    def test_dropdown_options_contain_campaigns(self, client):
        r = client.get("/compare")
        assert "camp-a" in r.text
        assert "camp-b" in r.text

    def test_comparison_table_present(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert 'data-test="comparison-table"' in r.text

    def test_delta_chart_present(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert 'data-test="delta-chart"' in r.text

    def test_pass_rates_in_table(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        # va has pass_rate_a=0.5 (50.0%) and pass_rate_b=1.0 (100.0%)
        assert "50.0%" in r.text
        assert "100.0%" in r.text

    def test_positive_delta_has_green(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        # va: delta_pass = 1.0 - 0.5 = 0.5 (positive) → teal
        assert "text-teal-600" in r.text

    def test_summary_tiles_present(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert 'data-test="summary-tiles"' in r.text

    def test_breadcrumb_links_to_campaigns(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert 'data-test="breadcrumb"' in r.text
        assert 'href="/"' in r.text
        assert "Compare" in r.text

    def test_only_common_variant_in_table(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        # Only 'va' is common between camp-a and camp-b
        body = r.text
        assert ">va<" in body
        # vb and vc are not common
        assert 'data-test="comparison-table"' in body

    def test_comparison_data_inlined(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert 'id="comparison-data"' in r.text

    def test_empty_state_without_params(self, client):
        r = client.get("/compare")
        assert "Select two campaigns to compare" in r.text

    def test_plotly_loaded(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        assert "plotly-3.4.0.min.js" in r.text

    def test_dropdowns_preselected(self, client):
        r = client.get("/compare?a=camp-a&b=camp-b")
        # Check that selected attribute is present on the right options
        text = r.text
        # camp-a should be selected in the first dropdown
        assert 'value="camp-a" selected' in text
        assert 'value="camp-b" selected' in text


class TestCompareErrors:
    def test_404_when_campaign_a_missing(self, client):
        r = client.get("/compare?a=nonexistent&b=camp-b")
        assert r.status_code == 404

    def test_404_when_campaign_b_missing(self, client):
        r = client.get("/compare?a=camp-a&b=nonexistent")
        assert r.status_code == 404

    def test_error_when_no_common_variants(self, compare_dir):
        # Create two campaigns with no overlapping variants
        _write_campaign(compare_dir, "only-x", variant_labels=["vx"], tasks=["t1"])
        _write_campaign(compare_dir, "only-y", variant_labels=["vy"], tasks=["t1"])
        app = create_app(compare_dir)
        c = TestClient(app)
        r = c.get("/compare?a=only-x&b=only-y")
        assert r.status_code == 200
        assert "No common variants found" in r.text
        assert 'data-test="error-message"' in r.text


class TestCompareNavigation:
    def test_campaigns_page_has_compare_link(self, client):
        r = client.get("/")
        assert 'data-nav="compare-link"' in r.text

    def test_compare_link_points_to_correct_url(self, client):
        r = client.get("/")
        assert 'href="/compare"' in r.text


class TestStaticExportVerification:
    def test_build_produces_index_html(self, compare_dir):
        build_static_site(compare_dir)
        # Should find at least one index.html
        found = list(compare_dir.rglob("web/index.html"))
        assert len(found) > 0

    def test_html_contains_data_blocks(self, compare_dir):
        build_static_site(compare_dir)
        html_files = list(compare_dir.rglob("web/index.html"))
        html = html_files[0].read_text()
        for data_id in ("data-campaign", "data-variants", "data-trials", "data-meta"):
            assert f'id="{data_id}"' in html

    def test_schema_version_in_meta(self, compare_dir):
        build_static_site(compare_dir)
        html_files = list(compare_dir.rglob("web/index.html"))
        html = html_files[0].read_text()
        start = html.index('id="data-meta"')
        json_start = html.index("{", start)
        json_end = html.index("</script>", json_start)
        meta = json.loads(html[json_start:json_end])
        assert meta["schema_version"] == SCHEMA_VERSION

    def test_assets_directory_created(self, compare_dir):
        build_static_site(compare_dir)
        assets_dirs = list(compare_dir.rglob("web/assets"))
        assert len(assets_dirs) > 0
        assert assets_dirs[0].is_dir()


class TestCompareMalformedData:
    """Regression: malformed numeric fields in trial JSON must not crash /compare or /api/compare."""

    def _write_malformed_campaigns(self, base_dir):
        """Two campaigns sharing variant 'v1', with one having malformed numeric fields."""
        camp_a = base_dir / "good"
        task_dir = camp_a / "t1"
        task_dir.mkdir(parents=True)
        report = _make_report("t1", "v1", 0)
        (task_dir / "v1_0.json").write_text(json.dumps(report, indent=2))
        (camp_a / "summary.json").write_text(
            json.dumps(
                _make_summary(
                    [_make_variant("v1", n_trials=1)],
                    [_make_trial_entry("t1", "v1")],
                )
            )
        )

        camp_b = base_dir / "bad"
        task_dir = camp_b / "t1"
        task_dir.mkdir(parents=True)
        report = _make_report("t1", "v1", 0)
        report["stats"]["turns"] = "not_a_number"
        report["stats"]["total_llm_time_s"] = "oops"
        report["stats"]["total_tool_time_s"] = None
        report["stats"]["compactions"] = "bad"
        report["timeline"] = [
            {
                "type": "llm_call",
                "prompt_tokens_est": "oops",
                "duration_s": 0.9,
                "finish_reason": "stop",
            },
        ]
        report["calibra"]["wall_time_s"] = "broken"
        (task_dir / "v1_0.json").write_text(json.dumps(report, indent=2))
        (camp_b / "summary.json").write_text(
            json.dumps(
                _make_summary(
                    [_make_variant("v1", n_trials=1)],
                    [_make_trial_entry("t1", "v1")],
                )
            )
        )

        return base_dir

    def test_compare_page_survives_malformed_data(self, tmp_path):
        root = self._write_malformed_campaigns(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/compare?a=good&b=bad")
        assert r.status_code == 200
        assert 'data-test="comparison-table"' in r.text

    def test_api_compare_survives_malformed_data(self, tmp_path):
        root = self._write_malformed_campaigns(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/api/compare?a=good&b=bad")
        assert r.status_code == 200
        data = r.json()
        assert len(data["variants"]) == 1
        assert data["variants"][0]["variant"] == "v1"

    def test_malformed_tokens_coerced_to_zero(self, tmp_path):
        root = self._write_malformed_campaigns(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/api/compare?a=good&b=bad")
        data = r.json()
        vc = data["variants"][0]
        assert vc["tokens_mean_b"] == 0.0

    def _write_nonfinite_campaigns(self, base_dir):
        """Two campaigns sharing variant 'v1', with one containing nan/inf values."""
        camp_a = base_dir / "finite"
        task_dir = camp_a / "t1"
        task_dir.mkdir(parents=True)
        report = _make_report("t1", "v1", 0)
        (task_dir / "v1_0.json").write_text(json.dumps(report, indent=2))
        (camp_a / "summary.json").write_text(
            json.dumps(
                _make_summary(
                    [_make_variant("v1", n_trials=1)],
                    [_make_trial_entry("t1", "v1")],
                )
            )
        )

        camp_b = base_dir / "nonfinite"
        task_dir = camp_b / "t1"
        task_dir.mkdir(parents=True)
        report = _make_report("t1", "v1", 0)
        report["stats"]["turns"] = "nan"
        report["stats"]["total_llm_time_s"] = "inf"
        report["timeline"] = [
            {
                "type": "llm_call",
                "prompt_tokens_est": "nan",
                "duration_s": 0.9,
                "finish_reason": "stop",
            },
        ]
        report["calibra"]["wall_time_s"] = "-inf"
        (task_dir / "v1_0.json").write_text(json.dumps(report, indent=2))
        (camp_b / "summary.json").write_text(
            json.dumps(
                _make_summary(
                    [_make_variant("v1", n_trials=1)],
                    [_make_trial_entry("t1", "v1")],
                )
            )
        )
        return base_dir

    def test_api_compare_survives_nan_inf(self, tmp_path):
        """Regression: nan/inf in trial data must not cause JSON serialization ValueError."""
        root = self._write_nonfinite_campaigns(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/api/compare?a=finite&b=nonfinite")
        assert r.status_code == 200
        data = r.json()
        assert data["variants"][0]["tokens_mean_b"] == 0.0

    def test_compare_page_survives_nan_inf(self, tmp_path):
        """Regression: nan/inf must not produce invalid inlined JSON for the client."""
        root = self._write_nonfinite_campaigns(tmp_path)
        client = TestClient(create_app(root))
        r = client.get("/compare?a=finite&b=nonfinite")
        assert r.status_code == 200
        assert 'data-test="comparison-table"' in r.text
        assert "NaN" not in r.text
        assert "Infinity" not in r.text
