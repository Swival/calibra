"""Tests for the static site exporter."""

import json

import pytest

from calibra.web.export import (
    SCHEMA_VERSION,
    _build_campaign_bundle,
    _build_task_aggregates,
    build_single_campaign,
    build_static_site,
)


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


def _make_variant(label, n_trials=2, pass_rate=1.0):
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


def _make_trial_entry(task, variant, verified=True):
    return {
        "task": task,
        "variant_label": variant,
        "outcome": "success",
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
def campaign_dir(tmp_path):
    """Create a campaign directory with summary.json."""
    d = tmp_path / "test-campaign"
    d.mkdir()
    variants = [
        _make_variant("v1_default", n_trials=2, pass_rate=1.0),
        _make_variant("v2_fast", n_trials=2, pass_rate=0.5),
    ]
    trials = [
        _make_trial_entry("hello", "v1_default"),
        _make_trial_entry("world", "v1_default"),
        _make_trial_entry("hello", "v2_fast"),
        _make_trial_entry("world", "v2_fast", verified=False),
    ]
    summary = _make_summary(variants, trials)
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    return d


@pytest.fixture
def results_dir(campaign_dir):
    return campaign_dir.parent


class TestBuildCampaignBundle:
    def test_basic_bundle(self, campaign_dir):
        bundle = _build_campaign_bundle(campaign_dir)
        assert "campaign" in bundle
        assert "variants" in bundle
        assert "tasks" in bundle
        assert "trials" in bundle
        assert "meta" in bundle

    def test_campaign_data(self, campaign_dir):
        bundle = _build_campaign_bundle(campaign_dir)
        c = bundle["campaign"]
        assert c["name"] == "test-campaign"
        assert c["n_variants"] == 2
        assert c["n_tasks"] == 2
        assert c["n_trials"] == 4

    def test_meta_has_schema_version(self, campaign_dir):
        bundle = _build_campaign_bundle(campaign_dir)
        meta = bundle["meta"]
        assert meta["schema_version"] == SCHEMA_VERSION
        assert "generated_at" in meta
        assert meta["generator"] == "calibra"

    def test_variants_preserved(self, campaign_dir):
        bundle = _build_campaign_bundle(campaign_dir)
        assert len(bundle["variants"]) == 2

    def test_trials_preserved(self, campaign_dir):
        bundle = _build_campaign_bundle(campaign_dir)
        assert len(bundle["trials"]) == 4

    def test_no_summary_raises(self, tmp_path):
        d = tmp_path / "no-summary"
        d.mkdir()
        with pytest.raises(FileNotFoundError, match="summary.json"):
            _build_campaign_bundle(d)

    def test_corrupt_summary_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "summary.json").write_text("not json{{{")
        with pytest.raises(ValueError, match="Corrupt summary.json"):
            _build_campaign_bundle(d)

    def test_invalid_structure_raises(self, tmp_path):
        d = tmp_path / "wrong-shape"
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"data": "wrong"}))
        with pytest.raises(ValueError, match="Invalid summary.json structure"):
            _build_campaign_bundle(d)


class TestTaskAggregates:
    def test_groups_by_task_and_variant(self):
        trials = [
            _make_trial_entry("hello", "v1"),
            _make_trial_entry("hello", "v1"),
            _make_trial_entry("hello", "v2"),
            _make_trial_entry("world", "v1"),
        ]
        result = _build_task_aggregates(trials)
        assert len(result) == 3  # (hello,v1), (hello,v2), (world,v1)

    def test_pass_rate_calculation(self):
        trials = [
            _make_trial_entry("hello", "v1", verified=True),
            _make_trial_entry("hello", "v1", verified=False),
        ]
        result = _build_task_aggregates(trials)
        cell = result[0]
        assert cell["n"] == 2
        assert cell["passes"] == 1
        assert cell["pass_rate"] == 0.5

    def test_sorted_output(self):
        trials = [
            _make_trial_entry("world", "v2"),
            _make_trial_entry("hello", "v1"),
        ]
        result = _build_task_aggregates(trials)
        keys = [(r["task"], r["variant"]) for r in result]
        assert keys == sorted(keys)


class TestBuildStaticSite:
    def test_produces_index_html(self, results_dir):
        build_static_site(results_dir)
        out = results_dir / "test-campaign" / "web" / "index.html"
        assert out.is_file()
        content = out.read_text()
        assert "test-campaign" in content

    def test_copies_assets(self, results_dir):
        build_static_site(results_dir)
        assets = results_dir / "test-campaign" / "web" / "assets"
        assert assets.is_dir()
        assert (assets / "htmx-2.0.8.min.js").is_file()

    def test_inlined_json_blocks(self, results_dir):
        build_static_site(results_dir)
        html = (results_dir / "test-campaign" / "web" / "index.html").read_text()
        for data_id in ("data-campaign", "data-variants", "data-tasks", "data-trials", "data-meta"):
            assert f'id="{data_id}"' in html

    def test_schema_version_in_output(self, results_dir):
        build_static_site(results_dir)
        html = (results_dir / "test-campaign" / "web" / "index.html").read_text()
        # Extract the meta JSON block
        start = html.index('id="data-meta"')
        json_start = html.index("{", start)
        json_end = html.index("</script>", json_start)
        meta = json.loads(html[json_start:json_end])
        assert meta["schema_version"] == SCHEMA_VERSION

    def test_custom_output_dir(self, results_dir, tmp_path):
        out = tmp_path / "custom-output"
        build_static_site(results_dir, output_dir=out)
        assert (out / "test-campaign" / "web" / "index.html").is_file()

    def test_no_campaigns_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No analyzed campaigns"):
            build_static_site(empty)

    def test_nonexistent_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Results directory not found"):
            build_static_site(tmp_path / "nonexistent")


class TestBuildSingleCampaign:
    def test_builds_single(self, campaign_dir):
        out = build_single_campaign(campaign_dir)
        assert (out / "index.html").is_file()
        assert (out / "assets").is_dir()

    def test_custom_output(self, campaign_dir, tmp_path):
        out = tmp_path / "my-export"
        result = build_single_campaign(campaign_dir, output_dir=out)
        assert result == out
        assert (out / "index.html").is_file()


class TestDeterminism:
    def test_full_html_deterministic(self, campaign_dir):
        """Verify the entire index.html is byte-identical across builds."""
        out1 = campaign_dir / "web1"
        out2 = campaign_dir / "web2"

        build_single_campaign(campaign_dir, output_dir=out1)
        build_single_campaign(campaign_dir, output_dir=out2)

        html1 = (out1 / "index.html").read_text()
        html2 = (out2 / "index.html").read_text()
        assert html1 == html2

    def test_meta_uses_summary_mtime(self, campaign_dir):
        """generated_at should derive from summary.json mtime, not wall clock."""
        out = campaign_dir / "web-check"
        build_single_campaign(campaign_dir, output_dir=out)
        html = (out / "index.html").read_text()
        meta = _extract_json_block(html, "data-meta")
        assert meta["schema_version"] == SCHEMA_VERSION
        assert "generated_at" in meta
        # Should be a fixed timestamp, not current time
        from datetime import datetime, timezone

        summary_mtime = datetime.fromtimestamp(
            (campaign_dir / "summary.json").stat().st_mtime, tz=timezone.utc
        ).isoformat()
        assert meta["generated_at"] == summary_mtime


class TestScriptInjectionPrevention:
    def test_script_tag_in_variant_label(self, tmp_path):
        """Variant label containing </script> must not break out of JSON block."""
        d = tmp_path / "xss-campaign"
        d.mkdir()
        evil_label = '</script><script>alert("xss")</script>'
        variants = [_make_variant(evil_label, n_trials=1)]
        trials = [_make_trial_entry("hello", evil_label)]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        out = d / "web"
        build_single_campaign(d, output_dir=out)
        html = (out / "index.html").read_text()

        # The literal </script> must NOT appear inside any data block
        # Instead it should be escaped as <\/script>
        data_start = html.index('id="data-variants"')
        data_end = html.index("</script>", data_start)
        data_block = html[data_start:data_end]
        assert "</script>" not in data_block
        assert "<\\/script>" in data_block

    def test_html_in_variant_label_escaped_in_js(self, tmp_path):
        """HTML in variant labels must be escaped when rendered in JS."""
        d = tmp_path / "html-campaign"
        d.mkdir()
        html_label = "<img src=x onerror=alert(1)>"
        variants = [_make_variant(html_label, n_trials=1)]
        trials = [_make_trial_entry("hello", html_label)]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        out = d / "web"
        build_single_campaign(d, output_dir=out)
        html = (out / "index.html").read_text()

        # The JS code should use esc() to escape the label, not raw insertion
        assert "esc(v.variant_label)" in html

    def test_all_cell_values_escaped(self, tmp_path):
        """All dynamic cell values must go through esc(), not just labels."""
        d = tmp_path / "numeric-xss"
        d.mkdir()
        evil = _make_variant("v1", n_trials=1)
        evil["turns"] = {
            "mean": "<img src=x>",
            "median": 0,
            "std": 0,
            "min": 0,
            "max": 0,
            "p90": 0,
            "ci_lower": 0,
            "ci_upper": 0,
        }
        trials = [_make_trial_entry("hello", "v1")]
        (d / "summary.json").write_text(json.dumps(_make_summary([evil], trials)))

        out = d / "web"
        build_single_campaign(d, output_dir=out)
        html = (out / "index.html").read_text()

        # Every td value insertion must use esc()
        # The JS uses stat() which calls Number(); a non-numeric string becomes NaN → 0
        # Then esc() HTML-escapes the formatted result. Either way, raw HTML must not appear.
        assert "esc(stat(" in html

    def test_campaign_name_html_escaped(self, tmp_path):
        """Campaign name with HTML chars must be escaped in the page title/header."""
        d = tmp_path / "bad<img src=x>"
        d.mkdir()
        variants = [_make_variant("v1", n_trials=1)]
        trials = [_make_trial_entry("hello", "v1")]
        (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials)))

        out = tmp_path / "out"
        build_single_campaign(d, output_dir=out)
        html = (out / "index.html").read_text()

        # In the <title> tag, the name must be HTML-escaped
        import re

        title_match = re.search(r"<title>(.*?)</title>", html)
        assert title_match is not None
        assert "<img" not in title_match.group(1)
        assert "&lt;img" in title_match.group(1)

        # In the <h1> tag, the name must be HTML-escaped
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html)
        assert h1_match is not None
        assert "<img" not in h1_match.group(1)
        assert "&lt;img" in h1_match.group(1)


class TestSingleCampaignPath:
    def test_build_static_site_with_campaign_dir(self, campaign_dir):
        """build_static_site should work when given a campaign dir directly."""
        out = build_static_site(campaign_dir)
        assert (out / "index.html").is_file()

    def test_build_static_site_campaign_dir_custom_output(self, campaign_dir, tmp_path):
        out = tmp_path / "exported"
        build_static_site(campaign_dir, output_dir=out)
        assert (out / "index.html").is_file()


def _extract_json_block(html: str, data_id: str) -> dict:
    """Extract a JSON data block from the HTML."""
    marker = f'id="{data_id}"'
    start = html.index(marker)
    json_start = html.index("\n", start) + 1
    json_end = html.index("\n</script>", json_start)
    return json.loads(html[json_start:json_end])
