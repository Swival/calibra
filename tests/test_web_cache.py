"""Tests for the in-memory result cache."""

import json

from calibra.web.cache import CampaignIndex, ResultCache


def _make_summary(n_variants=1, n_trials_per_variant=3, pass_rate=1.0, tasks=("hello",)):
    """Build a minimal summary.json structure."""
    variants = []
    trials = []
    for i in range(n_variants):
        label = f"v{i}_default"
        variants.append(
            {
                "variant_label": label,
                "n_trials": n_trials_per_variant * len(tasks),
                "pass_rate": pass_rate,
                "outcome_counts": {"success": n_trials_per_variant * len(tasks)},
                "turns": {
                    "mean": 3,
                    "median": 3,
                    "std": 0,
                    "min": 3,
                    "max": 3,
                    "p90": 3,
                    "ci_lower": 3,
                    "ci_upper": 3,
                },
                "tool_calls_total": {
                    "mean": 2,
                    "median": 2,
                    "std": 0,
                    "min": 2,
                    "max": 2,
                    "p90": 2,
                    "ci_lower": 2,
                    "ci_upper": 2,
                },
                "tool_calls_failed": {
                    "mean": 0,
                    "median": 0,
                    "std": 0,
                    "min": 0,
                    "max": 0,
                    "p90": 0,
                    "ci_lower": 0,
                    "ci_upper": 0,
                },
                "llm_time_s": {
                    "mean": 1,
                    "median": 1,
                    "std": 0,
                    "min": 1,
                    "max": 1,
                    "p90": 1,
                    "ci_lower": 1,
                    "ci_upper": 1,
                },
                "tool_time_s": {
                    "mean": 0.1,
                    "median": 0.1,
                    "std": 0,
                    "min": 0.1,
                    "max": 0.1,
                    "p90": 0.1,
                    "ci_lower": 0.1,
                    "ci_upper": 0.1,
                },
                "wall_time_s": {
                    "mean": 1.1,
                    "median": 1.1,
                    "std": 0,
                    "min": 1.1,
                    "max": 1.1,
                    "p90": 1.1,
                    "ci_lower": 1.1,
                    "ci_upper": 1.1,
                },
                "compactions": {
                    "mean": 0,
                    "median": 0,
                    "std": 0,
                    "min": 0,
                    "max": 0,
                    "p90": 0,
                    "ci_lower": 0,
                    "ci_upper": 0,
                },
                "prompt_tokens_est": {
                    "mean": 500,
                    "median": 500,
                    "std": 0,
                    "min": 500,
                    "max": 500,
                    "p90": 500,
                    "ci_lower": 500,
                    "ci_upper": 500,
                },
                "score_per_1k_tokens": 2.0,
                "pass_rate_per_minute": 54.5,
            }
        )
        for task in tasks:
            for r in range(n_trials_per_variant):
                trials.append(
                    {
                        "task": task,
                        "variant_label": label,
                        "outcome": "success",
                        "verified": True,
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
                )
    return {"variants": variants, "trials": trials}


def _write_trial(campaign_dir, task, variant, repeat):
    """Write a minimal trial JSON file."""
    task_dir = campaign_dir / task
    task_dir.mkdir(parents=True, exist_ok=True)
    report = {
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
            "verified": True,
            "config_hash": "abc",
        },
    }
    (task_dir / f"{variant}_{repeat}.json").write_text(json.dumps(report))


class TestCampaignIndex:
    def test_n_variants(self):
        summary = _make_summary(n_variants=3)
        idx = CampaignIndex(name="test", summary=summary, trial_files=[], latest_mtime=0.0)
        assert idx.n_variants == 3

    def test_n_tasks_from_trials(self):
        summary = _make_summary(n_variants=1, tasks=("hello", "world"))
        idx = CampaignIndex(name="test", summary=summary, trial_files=[], latest_mtime=0.0)
        assert idx.n_tasks == 2

    def test_n_trials(self):
        summary = _make_summary(n_variants=2, n_trials_per_variant=5, tasks=("hello",))
        idx = CampaignIndex(name="test", summary=summary, trial_files=[], latest_mtime=0.0)
        assert idx.n_trials == 10

    def test_n_trials_falls_back_to_files(self):
        from pathlib import Path

        idx = CampaignIndex(
            name="test",
            summary=None,
            trial_files=[Path("a.json"), Path("b.json")],
            latest_mtime=0.0,
        )
        assert idx.n_trials == 2

    def test_pass_rate_weighted(self):
        summary = {
            "variants": [
                {"variant_label": "v1", "n_trials": 10, "pass_rate": 1.0},
                {"variant_label": "v2", "n_trials": 10, "pass_rate": 0.5},
            ],
            "trials": [],
        }
        idx = CampaignIndex(name="test", summary=summary, trial_files=[], latest_mtime=0.0)
        assert idx.pass_rate == 0.75

    def test_pass_rate_none_without_summary(self):
        idx = CampaignIndex(name="test", summary=None, trial_files=[], latest_mtime=0.0)
        assert idx.pass_rate is None

    def test_pass_rate_none_empty_variants(self):
        idx = CampaignIndex(
            name="test",
            summary={"variants": [], "trials": []},
            trial_files=[],
            latest_mtime=0.0,
        )
        assert idx.pass_rate is None

    def test_zero_values_without_summary(self):
        idx = CampaignIndex(name="test", summary=None, trial_files=[], latest_mtime=0.0)
        assert idx.n_variants == 0
        assert idx.n_tasks == 0


class TestResultCache:
    def test_scan_empty_dir(self, tmp_path):
        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert cache.campaigns == {}

    def test_scan_nonexistent_dir(self, tmp_path):
        cache = ResultCache(results_dir=tmp_path / "nonexistent")
        cache.scan()
        assert cache.campaigns == {}

    def test_scan_finds_campaigns(self, tmp_path):
        c1 = tmp_path / "campaign-a"
        c1.mkdir()
        _write_trial(c1, "hello", "v1", 0)
        (c1 / "summary.json").write_text(json.dumps(_make_summary()))

        c2 = tmp_path / "campaign-b"
        c2.mkdir()
        _write_trial(c2, "world", "v1", 0)

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert "campaign-a" in cache.campaigns
        assert "campaign-b" in cache.campaigns

    def test_scan_skips_hidden_dirs(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert ".hidden" not in cache.campaigns

    def test_scan_skips_files(self, tmp_path):
        (tmp_path / "not-a-dir.txt").write_text("hello")
        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert cache.campaigns == {}

    def test_get_existing(self, tmp_path):
        c = tmp_path / "my-campaign"
        c.mkdir()
        (c / "summary.json").write_text(json.dumps(_make_summary()))

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        idx = cache.get("my-campaign")
        assert idx is not None
        assert idx.name == "my-campaign"
        assert idx.n_variants == 1

    def test_get_nonexistent(self, tmp_path):
        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert cache.get("nonexistent") is None

    def test_reload_picks_up_new_campaign(self, tmp_path):
        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert len(cache.campaigns) == 0

        c = tmp_path / "new-campaign"
        c.mkdir()
        _write_trial(c, "hello", "v1", 0)

        cache.reload()
        assert "new-campaign" in cache.campaigns

    def test_reload_picks_up_new_summary(self, tmp_path):
        c = tmp_path / "evolving"
        c.mkdir()
        _write_trial(c, "hello", "v1", 0)

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        assert cache.get("evolving").summary is None

        (c / "summary.json").write_text(json.dumps(_make_summary()))
        cache.reload()
        assert cache.get("evolving").summary is not None
        assert cache.get("evolving").n_variants == 1

    def test_corrupt_summary_handled(self, tmp_path):
        c = tmp_path / "bad-data"
        c.mkdir()
        (c / "summary.json").write_text("not json{{{")

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        idx = cache.get("bad-data")
        assert idx is not None
        assert idx.summary is None

    def test_trial_file_indexing(self, tmp_path):
        c = tmp_path / "multi-trial"
        c.mkdir()
        _write_trial(c, "task_a", "v1", 0)
        _write_trial(c, "task_a", "v1", 1)
        _write_trial(c, "task_b", "v1", 0)

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        idx = cache.get("multi-trial")
        assert len(idx.trial_files) == 3

    def test_latest_mtime_tracked(self, tmp_path):
        c = tmp_path / "timed"
        c.mkdir()
        _write_trial(c, "hello", "v1", 0)

        cache = ResultCache(results_dir=tmp_path)
        cache.scan()
        idx = cache.get("timed")
        assert idx.latest_mtime > 0
