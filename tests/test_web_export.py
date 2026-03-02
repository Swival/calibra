"""Tests for the static site exporter."""

import json

import pytest

from calibra.web.export import (
    _load_summary,
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


def _make_trial_entry(task, variant, verified=True, repeat=0):
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


def _make_summary(variants, trials):
    return {"variants": variants, "trials": trials}


def _make_trial_json(task, variant, repeat=0, verified=True):
    """Create a full trial JSON file content (as stored on disk)."""
    return {
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": 1.1,
            "verified": verified,
        },
        "settings": {"model": "test-model"},
        "stats": {"turns": 3, "total_llm_time_s": 1.0, "total_tool_time_s": 0.1},
        "result": {"outcome": "success" if verified else "failure"},
        "timeline": [
            {"type": "llm_call", "duration_s": 0.5, "prompt_tokens_est": 250},
            {"type": "tool_call", "name": "bash", "succeeded": True, "duration_s": 0.1},
            {"type": "llm_call", "duration_s": 0.5, "prompt_tokens_est": 250},
        ],
    }


@pytest.fixture
def campaign_dir(tmp_path):
    """Create a campaign directory with summary.json and trial files."""
    d = tmp_path / "test-campaign"
    d.mkdir()
    variants = [
        _make_variant("v1_default", n_trials=2, pass_rate=1.0),
        _make_variant("v2_fast", n_trials=2, pass_rate=0.5),
    ]
    trials = [
        _make_trial_entry("hello", "v1_default", repeat=0),
        _make_trial_entry("world", "v1_default", repeat=0),
        _make_trial_entry("hello", "v2_fast", repeat=0),
        _make_trial_entry("world", "v2_fast", verified=False, repeat=0),
    ]
    summary = _make_summary(variants, trials)
    (d / "summary.json").write_text(json.dumps(summary, indent=2))

    # Create actual trial JSON files for trial inspector pages
    for task in ("hello", "world"):
        task_dir = d / task
        task_dir.mkdir()
        for vlabel in ("v1_default", "v2_fast"):
            verified = not (task == "world" and vlabel == "v2_fast")
            trial_data = _make_trial_json(task, vlabel, repeat=0, verified=verified)
            (task_dir / f"{vlabel}_0.json").write_text(json.dumps(trial_data, indent=2))

    return d


@pytest.fixture
def results_dir(campaign_dir):
    return campaign_dir.parent


class TestLoadSummary:
    def test_valid_summary(self, campaign_dir):
        summary = _load_summary(campaign_dir)
        assert "variants" in summary
        assert "trials" in summary

    def test_no_summary_raises(self, tmp_path):
        d = tmp_path / "no-summary"
        d.mkdir()
        with pytest.raises(FileNotFoundError, match="summary.json"):
            _load_summary(d)

    def test_corrupt_summary_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "summary.json").write_text("not json{{{")
        with pytest.raises(ValueError, match="Corrupt summary.json"):
            _load_summary(d)

    def test_invalid_structure_raises(self, tmp_path):
        d = tmp_path / "wrong-shape"
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"data": "wrong"}))
        with pytest.raises(ValueError, match="Invalid summary.json structure"):
            _load_summary(d)


class TestBuildStaticSite:
    def test_produces_all_pages(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)

        assert (out / "index.html").is_file()
        assert (out / "campaign" / "test-campaign" / "index.html").is_file()
        assert (out / "campaign" / "test-campaign" / "tasks" / "index.html").is_file()
        assert (
            out / "campaign" / "test-campaign" / "variant" / "v1_default" / "index.html"
        ).is_file()
        assert (out / "campaign" / "test-campaign" / "variant" / "v2_fast" / "index.html").is_file()

    def test_copies_static_assets(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        assert (out / "static" / "vendor" / "htmx-2.0.8.min.js").is_file()
        assert (out / "static" / "style.css").is_file()

    def test_campaigns_page_lists_campaign(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "index.html").read_text()
        assert "test-campaign" in html

    def test_campaign_detail_has_variants(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "index.html").read_text()
        assert "v1_default" in html
        assert "v2_fast" in html

    def test_task_matrix_has_cells(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "tasks" / "index.html").read_text()
        assert "hello" in html
        assert "world" in html

    def test_variant_page_has_task_stats(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (
            out / "campaign" / "test-campaign" / "variant" / "v1_default" / "index.html"
        ).read_text()
        assert "hello" in html
        assert "world" in html

    def test_trial_pages_generated(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        trial_page = (
            out
            / "campaign"
            / "test-campaign"
            / "trial"
            / "hello"
            / "v1_default"
            / "0"
            / "index.html"
        )
        assert trial_page.is_file()
        html = trial_page.read_text()
        assert "Timeline" in html
        assert "LLM Call" in html

    def test_no_campaigns_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No analyzed campaigns"):
            build_static_site(empty)

    def test_nonexistent_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Results directory not found"):
            build_static_site(tmp_path / "nonexistent")


class TestBuildSingleCampaign:
    def test_builds_all_pages(self, campaign_dir):
        out = build_single_campaign(campaign_dir)
        assert (out / "index.html").is_file()
        assert (out / "campaign" / "test-campaign" / "index.html").is_file()
        assert (out / "campaign" / "test-campaign" / "tasks" / "index.html").is_file()
        assert (out / "static" / "vendor").is_dir()

    def test_custom_output(self, campaign_dir, tmp_path):
        out = tmp_path / "my-export"
        result = build_single_campaign(campaign_dir, output_dir=out)
        assert result == out
        assert (out / "index.html").is_file()

    def test_campaign_dir_via_build_static_site(self, campaign_dir):
        """build_static_site should work when given a campaign dir directly."""
        out = build_static_site(campaign_dir)
        assert (out / "index.html").is_file()
        assert (out / "campaign" / "test-campaign" / "index.html").is_file()


class TestNavigation:
    """Verify that navigation links use correct relative root paths."""

    def test_campaigns_page_links_to_campaign(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "index.html").read_text()
        assert 'href="./campaign/test-campaign"' in html

    def test_campaign_page_links_to_root(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "index.html").read_text()
        assert 'href="../../"' in html

    def test_campaign_page_links_to_tasks(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "index.html").read_text()
        assert "../../campaign/test-campaign/tasks" in html

    def test_campaign_page_links_to_variants(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "index.html").read_text()
        assert "../../campaign/test-campaign/variant/v1_default" in html

    def test_static_assets_relative(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (out / "campaign" / "test-campaign" / "index.html").read_text()
        assert "../../static/vendor/" in html

    def test_variant_page_breadcrumbs(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        html = (
            out / "campaign" / "test-campaign" / "variant" / "v1_default" / "index.html"
        ).read_text()
        assert "../../../../" in html  # root link
        assert "../../../../campaign/test-campaign" in html  # campaign link

    def test_trial_page_links(self, results_dir):
        out = results_dir / "web"
        build_static_site(results_dir, output_dir=out)
        trial_page = (
            out
            / "campaign"
            / "test-campaign"
            / "trial"
            / "hello"
            / "v1_default"
            / "0"
            / "index.html"
        )
        html = trial_page.read_text()
        assert "../../../../../../" in html  # root link


class TestMultipleCampaigns:
    def test_index_lists_all_campaigns(self, tmp_path):
        for name in ("campaign-a", "campaign-b"):
            d = tmp_path / name
            d.mkdir()
            variants = [_make_variant("v1", n_trials=1)]
            trials = [_make_trial_entry("task1", "v1")]
            (d / "summary.json").write_text(json.dumps(_make_summary(variants, trials), indent=2))

        out = tmp_path / "web"
        build_static_site(tmp_path, output_dir=out)
        html = (out / "index.html").read_text()
        assert "campaign-a" in html
        assert "campaign-b" in html
        assert (out / "campaign" / "campaign-a" / "index.html").is_file()
        assert (out / "campaign" / "campaign-b" / "index.html").is_file()
