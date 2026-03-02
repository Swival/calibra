"""Tests for the M2 campaign dashboard: charts, KPIs, warnings, sorting."""

import json

import pytest
from fastapi.testclient import TestClient

from calibra.web import create_app
from calibra.web.export import build_single_campaign


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
    label,
    n_trials=3,
    pass_rate=1.0,
    turns_mean=3,
    tokens_mean=500,
    llm_time=1,
    wall_time=1.1,
    turns_std=0,
    tokens_std=0,
):
    return {
        "variant_label": label,
        "n_trials": n_trials,
        "pass_rate": pass_rate,
        "outcome_counts": {"success": n_trials},
        "turns": _stat_block(turns_mean, std=turns_std, median=turns_mean),
        "tool_calls_total": _stat_block(2),
        "tool_calls_failed": _stat_block(0),
        "llm_time_s": _stat_block(llm_time),
        "tool_time_s": _stat_block(0.1),
        "wall_time_s": _stat_block(wall_time),
        "compactions": _stat_block(0),
        "prompt_tokens_est": _stat_block(tokens_mean, std=tokens_std),
        "score_per_1k_tokens": (pass_rate * 1000 / tokens_mean) if tokens_mean > 0 else 0,
        "pass_rate_per_minute": (pass_rate * 60 / wall_time) if wall_time > 0 else 0,
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


def _make_summary(variants, trials):
    return {"variants": variants, "trials": trials}


@pytest.fixture
def multi_variant_dir(tmp_path):
    """Campaign with 3 variants at different performance levels."""
    d = tmp_path / "perf-test"
    d.mkdir()
    variants = [
        _make_variant("v1_strong", n_trials=10, pass_rate=0.9, tokens_mean=800, turns_mean=4),
        _make_variant("v2_weak", n_trials=10, pass_rate=0.3, tokens_mean=1200, turns_mean=8),
        _make_variant("v3_efficient", n_trials=10, pass_rate=0.7, tokens_mean=300, turns_mean=3),
    ]
    trials = []
    for v in variants:
        for i in range(v["n_trials"]):
            verified = i < int(v["n_trials"] * v["pass_rate"])
            trials.append(_make_trial_entry("hello", v["variant_label"], verified=verified))
    (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
    return d


@pytest.fixture
def high_cv_dir(tmp_path):
    """Campaign with high coefficient of variation triggering warnings."""
    d = tmp_path / "unstable"
    d.mkdir()
    variants = [
        _make_variant(
            "v1_wild",
            n_trials=10,
            pass_rate=0.5,
            turns_mean=10,
            turns_std=8,
            tokens_mean=500,
            tokens_std=400,
        ),
    ]
    trials = [_make_trial_entry("hello", "v1_wild", verified=True) for _ in range(10)]
    (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
    return d


@pytest.fixture
def low_repeat_dir(tmp_path):
    """Campaign with fewer than 3 repeats."""
    d = tmp_path / "low-n"
    d.mkdir()
    variants = [
        _make_variant("v1_few", n_trials=2, pass_rate=1.0),
    ]
    trials = [_make_trial_entry("hello", "v1_few") for _ in range(2)]
    (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
    return d


@pytest.fixture
def single_variant_dir(tmp_path):
    """Campaign with a single variant."""
    d = tmp_path / "solo"
    d.mkdir()
    variants = [_make_variant("only_one", n_trials=5, pass_rate=0.8)]
    trials = [_make_trial_entry("hello", "only_one") for _ in range(5)]
    (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
    return d


@pytest.fixture
def zero_pass_dir(tmp_path):
    """Campaign where all trials fail."""
    d = tmp_path / "zero-pass"
    d.mkdir()
    variants = [_make_variant("v1_fail", n_trials=5, pass_rate=0.0)]
    trials = [_make_trial_entry("hello", "v1_fail", verified=False) for _ in range(5)]
    (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
    return d


def _make_client(results_dir):
    """Create a TestClient for a results directory."""
    parent = results_dir.parent
    app = create_app(parent)
    return TestClient(app)


class TestServerKPIs:
    def test_kpi_tiles_present(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert r.status_code == 200
        assert "kpi-tiles" in r.text
        assert "Med. Turns" in r.text
        assert "Failure Rate" in r.text

    def test_variants_json_inlined(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert 'id="variants-data"' in r.text

    def test_score_1k_column(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert "Score/1k" in r.text


class TestServerCharts:
    def test_plotly_loaded(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert "plotly-3.4.0.min.js" in r.text

    def test_chart_containers_present(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert 'id="chart-pass-rate"' in r.text
        assert 'id="chart-efficiency"' in r.text

    def test_chart_section_titles(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert "Pass Rate by Variant" in r.text
        assert "Efficiency: Tokens vs Pass Rate" in r.text


class TestServerSortableTable:
    def test_sort_headers_have_data_sort(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert 'data-sort="pass_rate"' in r.text
        assert 'data-sort="turns"' in r.text
        assert 'data-sort="tokens"' in r.text
        assert 'data-sort="variant_label"' in r.text
        assert 'data-sort="score_1k"' in r.text

    def test_data_attributes_on_rows(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert 'data-pass-rate="0.9"' in r.text
        assert 'data-variant-label="v1_strong"' in r.text

    def test_sort_js_present(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert "sortTable" in r.text
        assert "setUrlSort" in r.text


class TestServerDefaultRanking:
    def test_variants_ranked_by_pass_rate_desc(self, tmp_path):
        """Variants should be sorted by pass_rate desc on initial page load,
        regardless of their order in summary.json."""
        d = tmp_path / "unordered"
        d.mkdir()
        # Intentionally put worst variant first in the JSON
        variants = [
            _make_variant("v_worst", n_trials=5, pass_rate=0.2, tokens_mean=100),
            _make_variant("v_best", n_trials=5, pass_rate=0.9, tokens_mean=500),
            _make_variant("v_mid", n_trials=5, pass_rate=0.5, tokens_mean=300),
        ]
        trials = [_make_trial_entry("t", v["variant_label"]) for v in variants]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        client = _make_client(d)
        r = client.get(f"/campaign/{d.name}")
        html = r.text

        # In the rendered HTML table, v_best should appear before v_mid before v_worst
        pos_best = html.index("v_best")
        pos_mid = html.index("v_mid")
        pos_worst = html.index("v_worst")
        assert pos_best < pos_mid < pos_worst, (
            f"Expected v_best({pos_best}) < v_mid({pos_mid}) < v_worst({pos_worst})"
        )

    def test_tiebreak_by_tokens_then_turns(self, tmp_path):
        """When pass rates are equal, rank by tokens asc, then turns asc."""
        d = tmp_path / "tiebreak"
        d.mkdir()
        variants = [
            _make_variant("v_expensive", n_trials=5, pass_rate=0.8, tokens_mean=1000, turns_mean=5),
            _make_variant("v_cheap", n_trials=5, pass_rate=0.8, tokens_mean=200, turns_mean=3),
        ]
        trials = [_make_trial_entry("t", v["variant_label"]) for v in variants]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        client = _make_client(d)
        r = client.get(f"/campaign/{d.name}")
        html = r.text

        pos_cheap = html.index("v_cheap")
        pos_expensive = html.index("v_expensive")
        assert pos_cheap < pos_expensive


class TestServerRankingMalformed:
    def test_non_numeric_pass_rate_no_500(self, tmp_path):
        """Malformed pass_rate should not crash the server."""
        d = tmp_path / "malformed"
        d.mkdir()
        variants = [
            {
                "variant_label": "bad",
                "n_trials": 1,
                "pass_rate": "not_a_number",
                "outcome_counts": {},
                "turns": {"mean": "oops"},
                "tool_calls_total": _stat_block(0),
                "tool_calls_failed": _stat_block(0),
                "llm_time_s": _stat_block(0),
                "tool_time_s": _stat_block(0),
                "wall_time_s": _stat_block(0),
                "compactions": _stat_block(0),
                "prompt_tokens_est": {"mean": None},
                "score_per_1k_tokens": 0,
                "pass_rate_per_minute": 0,
            },
            _make_variant("good", n_trials=3, pass_rate=0.9),
        ]
        trials = [_make_trial_entry("t", "good")]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        client = _make_client(d)
        r = client.get(f"/campaign/{d.name}")
        assert r.status_code == 200
        assert "good" in r.text
        assert "bad" in r.text


class TestServerWarnings:
    def test_warnings_panel_container(self, multi_variant_dir):
        client = _make_client(multi_variant_dir)
        r = client.get(f"/campaign/{multi_variant_dir.name}")
        assert 'id="warnings-panel"' in r.text
        assert 'id="warnings-list"' in r.text


def _export_campaign_html(campaign_dir):
    """Build export and return the campaign detail page HTML."""
    out = build_single_campaign(campaign_dir)
    return (out / "campaign" / campaign_dir.name / "index.html").read_text(), out


class TestExportKPIs:
    def test_kpi_tiles_in_export(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert 'id="kpi-tiles"' in html
        assert 'id="kpi-turns"' in html
        assert 'id="kpi-failure"' in html
        assert "Med. Turns" in html
        assert "Failure Rate" in html


class TestExportCharts:
    def test_plotly_script_tag(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "plotly-3.4.0.min.js" in html

    def test_plotly_vendored_asset(self, multi_variant_dir):
        _, out = _export_campaign_html(multi_variant_dir)
        assert (out / "static" / "vendor" / "plotly-3.4.0.min.js").is_file()

    def test_chart_containers_in_export(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "chart-pass-rate" in html
        assert "chart-efficiency" in html

    def test_plotly_newplot_calls(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "Plotly.newPlot('chart-pass-rate'" in html
        assert "Plotly.newPlot('chart-efficiency'" in html

    def test_pareto_front_code(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "Pareto front" in html
        assert "pareto" in html


class TestExportWarnings:
    def test_warnings_js_in_export(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "warnings-panel" in html
        assert "warnings-list" in html
        assert "high variability" in html
        assert "fewer than 3 repeats" in html

    def test_high_cv_trigger(self, high_cv_dir):
        html, _ = _export_campaign_html(high_cv_dir)
        assert "warnings-panel" in html
        assert "std / mean > 1.0" in html

    def test_low_repeat_trigger(self, low_repeat_dir):
        html, _ = _export_campaign_html(low_repeat_dir)
        assert "n_trials) < 3" in html


class TestExportSortableTable:
    def test_sort_columns_in_export(self, multi_variant_dir):
        """Sort column identifiers appear in JS code that builds headers."""
        html, _ = _export_campaign_html(multi_variant_dir)
        for col in ("pass_rate", "turns", "tokens", "variant_label", "score_1k"):
            assert f'"{col}"' in html, f"Sort column {col} not in export JS"

    def test_url_state_persistence_code(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "URLSearchParams" in html
        assert "history.replaceState" in html

    def test_score_1k_column(self, multi_variant_dir):
        html, _ = _export_campaign_html(multi_variant_dir)
        assert "Score/1k" in html
        assert "score_per_1k_tokens" in html


class TestEdgeCases:
    def test_single_variant_no_pareto_line(self, single_variant_dir):
        """Pareto front line should not render with only one variant."""
        html, _ = _export_campaign_html(single_variant_dir)
        assert "Plotly.newPlot('chart-efficiency'" in html

    def test_zero_pass_rate(self, zero_pass_dir):
        """Zero pass rate should render without errors."""
        html, _ = _export_campaign_html(zero_pass_dir)
        assert "chart-pass-rate" in html
        assert "kpi-failure" in html

    def test_single_variant_server(self, single_variant_dir):
        client = _make_client(single_variant_dir)
        r = client.get(f"/campaign/{single_variant_dir.name}")
        assert r.status_code == 200
        assert "only_one" in r.text

    def test_zero_pass_rate_server(self, zero_pass_dir):
        client = _make_client(zero_pass_dir)
        r = client.get(f"/campaign/{zero_pass_dir.name}")
        assert r.status_code == 200
        assert "v1_fail" in r.text


class TestExportXSSPreservation:
    def test_script_escape_still_works(self, tmp_path):
        """Ensure </script> is still escaped in inlined JSON blocks."""
        d = tmp_path / "xss-m2"
        d.mkdir()
        evil_label = "</script><script>alert(1)</script>"
        variants = [_make_variant(evil_label, n_trials=1)]
        trials = [_make_trial_entry("hello", evil_label)]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))
        html, _ = _export_campaign_html(d)
        # The variants JSON block should escape </script> as <\/script>
        data_start = html.index('id="variants-data"')
        data_end = html.index("</script>", data_start)
        data_block = html[data_start:data_end]
        assert "</script>" not in data_block
        assert "<\\/script>" in data_block
