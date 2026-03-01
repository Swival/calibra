"""Tests for reviewer support: config, runner helpers, CLI trial execution, analysis."""

import json
import stat
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from calibra.config import (
    BudgetConfig,
    Campaign,
    ConfigError,
    ModelVariant,
    AgentInstructionsVariant,
    EnvironmentVariant,
    McpVariant,
    RetryConfig,
    ReviewerConfig,
    SamplingConfig,
    SkillsVariant,
    load_campaign,
)
from calibra.matrix import Variant
from calibra.runner import (
    TrialSpec,
    TrialResult,
    _classify_cli_failure,
    _make_isolated_env,
    _reviewer_verdict,
    _session_opts_to_cli_args,
    _write_cli_mcp_config,
    run_trial_cli,
    setup_workspace,
    write_trial_report,
)
from calibra.tasks import Task
from calibra.analyze import (
    TrialMetrics,
    aggregate_variant,
    extract_metrics,
)


def _write_campaign_toml(tmp_path, extra=""):
    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text("Say hello.")
    (task_dir / "env").mkdir(exist_ok=True)

    agents_md = tmp_path / "agents.md"
    agents_md.write_text("You are a helpful assistant.")

    config = tmp_path / "campaign.toml"
    config.write_text(
        f"""\
[campaign]
name = "test"
tasks_dir = "tasks"

[[matrix.model]]
provider = "test"
model = "m"
label = "m"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"

{extra}
"""
    )
    return config


def _make_reviewer_script(tmp_path, name="review.sh", exit_code=0):
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _variant():
    return Variant(
        model=ModelVariant(provider="test", model="test-model", label="m0"),
        agent_instructions=AgentInstructionsVariant(label="default", agents_md=""),
        skills=SkillsVariant(label="none", skills_dirs=[]),
        mcp=McpVariant(label="none", config=""),
        environment=EnvironmentVariant(label="base", overlay=""),
    )


def _task(tmp_path, name="hello"):
    task_dir = tmp_path / name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text("Say hello.")
    env_dir = task_dir / "env"
    env_dir.mkdir(exist_ok=True)
    return Task(name=name, prompt="Say hello.", env_dir=env_dir, verify_script=None, meta={})


def _campaign(reviewer=None):
    return Campaign(
        name="test",
        description="",
        repeat=1,
        max_turns=10,
        timeout_s=60,
        seed=42,
        tasks_dir="/tmp",
        budget=BudgetConfig(),
        retry=RetryConfig(),
        sampling=SamplingConfig(),
        models=[ModelVariant(provider="test", model="m", label="m0")],
        agent_instructions=[AgentInstructionsVariant(label="default", agents_md="")],
        skills=[SkillsVariant(label="none", skills_dirs=[])],
        mcp=[McpVariant(label="none", config="")],
        environments=[EnvironmentVariant(label="base", overlay="")],
        reviewer=reviewer,
        config_hash="abc123",
    )


class TestReviewerConfig:
    def test_valid_reviewer(self, tmp_path):
        script = _make_reviewer_script(tmp_path)
        config = _write_campaign_toml(
            tmp_path,
            f'[reviewer]\ncommand = "{script}"\nmax_rounds = 3',
        )
        campaign = load_campaign(config)
        assert campaign.reviewer is not None
        assert campaign.reviewer.max_rounds == 3

    def test_reviewer_default_max_rounds(self, tmp_path):
        script = _make_reviewer_script(tmp_path)
        config = _write_campaign_toml(
            tmp_path,
            f'[reviewer]\ncommand = "{script}"',
        )
        campaign = load_campaign(config)
        assert campaign.reviewer.max_rounds == 5

    def test_no_reviewer_section(self, tmp_path):
        config = _write_campaign_toml(tmp_path)
        campaign = load_campaign(config)
        assert campaign.reviewer is None

    def test_empty_command_raises(self, tmp_path):
        config = _write_campaign_toml(tmp_path, '[reviewer]\ncommand = ""')
        with pytest.raises(ConfigError, match="non-empty.*command"):
            load_campaign(config)

    def test_empty_reviewer_section_raises(self, tmp_path):
        config = _write_campaign_toml(tmp_path, "[reviewer]")
        with pytest.raises(ConfigError, match="non-empty.*command"):
            load_campaign(config)

    def test_negative_max_rounds_raises(self, tmp_path):
        script = _make_reviewer_script(tmp_path)
        config = _write_campaign_toml(
            tmp_path,
            f'[reviewer]\ncommand = "{script}"\nmax_rounds = -1',
        )
        with pytest.raises(ConfigError, match="max_rounds"):
            load_campaign(config)

    def test_nonexistent_command_raises(self, tmp_path):
        config = _write_campaign_toml(tmp_path, '[reviewer]\ncommand = "/nonexistent/reviewer"')
        with pytest.raises(ConfigError, match="executable not found"):
            load_campaign(config)

    def test_malformed_command_raises_config_error(self, tmp_path):
        config = _write_campaign_toml(tmp_path, """[reviewer]\ncommand = "unclosed 'quote" """)
        with pytest.raises(ConfigError, match="malformed command"):
            load_campaign(config)

    def test_command_with_spaces_preserved(self, tmp_path):
        script = _make_reviewer_script(tmp_path, "review.sh")
        config = _write_campaign_toml(
            tmp_path,
            f"[reviewer]\ncommand = \"{script} 'arg with spaces'\"",
        )
        campaign = load_campaign(config)
        import shlex

        tokens = shlex.split(campaign.reviewer.command)
        assert tokens[-1] == "arg with spaces"


class TestSessionOptsToCli:
    def test_yolo_flag(self):
        args = _session_opts_to_cli_args({"yolo": True})
        assert "--yolo" in args

    def test_yolo_false_not_added(self):
        args = _session_opts_to_cli_args({"yolo": False})
        assert "--yolo" not in args

    def test_allowed_commands_comma_separated(self):
        args = _session_opts_to_cli_args({"allowed_commands": ["python", "uv", "git"]})
        idx = args.index("--allowed-commands")
        assert args[idx + 1] == "python,uv,git"

    def test_skills_dir_repeated(self):
        args = _session_opts_to_cli_args({"skills_dir": ["/a", "/b"]})
        assert args.count("--skills-dir") == 2
        idx1 = args.index("--skills-dir")
        assert args[idx1 + 1] == "/a"
        idx2 = args.index("--skills-dir", idx1 + 1)
        assert args[idx2 + 1] == "/b"

    def test_allowed_dirs_uses_add_dir(self):
        args = _session_opts_to_cli_args({"allowed_dirs": ["/x"]})
        assert "--add-dir" in args
        assert "/x" in args

    def test_temperature_as_value(self):
        args = _session_opts_to_cli_args({"temperature": 0.7})
        idx = args.index("--temperature")
        assert args[idx + 1] == "0.7"

    def test_no_read_guard(self):
        args = _session_opts_to_cli_args({"read_guard": False})
        assert "--no-read-guard" in args

    def test_read_guard_true_not_added(self):
        args = _session_opts_to_cli_args({"read_guard": True})
        assert "--no-read-guard" not in args

    def test_proactive_summaries(self):
        args = _session_opts_to_cli_args({"proactive_summaries": True})
        assert "--proactive-summaries" in args

    def test_proactive_summaries_false_not_added(self):
        args = _session_opts_to_cli_args({"proactive_summaries": False})
        assert "--proactive-summaries" not in args

    def test_extra_body_json(self):
        body = {"key": "val"}
        args = _session_opts_to_cli_args({"extra_body": body})
        idx = args.index("--extra-body")
        assert json.loads(args[idx + 1]) == body

    def test_no_skills_flag(self):
        args = _session_opts_to_cli_args({"no_skills": True})
        assert "--no-skills" in args

    def test_no_instructions_flag(self):
        args = _session_opts_to_cli_args({"no_instructions": True})
        assert "--no-instructions" in args

    def test_verbose_not_mapped(self):
        args = _session_opts_to_cli_args({"verbose": True})
        assert "--verbose" not in args

    def test_unknown_key_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _session_opts_to_cli_args({"unknown_thing": 42})
            assert len(w) == 1
            assert "unknown_thing" in str(w[0].message).lower()

    def test_skipped_keys_not_mapped(self):
        args = _session_opts_to_cli_args(
            {
                "history": False,
                "config_dir": "/tmp",
                "base_dir": "/tmp",
                "provider": "test",
                "model": "m",
                "max_turns": 10,
                "mcp_servers": {},
            }
        )
        assert args == []

    def test_seed_mapped(self):
        args = _session_opts_to_cli_args({"seed": 42})
        idx = args.index("--seed")
        assert args[idx + 1] == "42"


class TestWriteCliMcpConfig:
    def test_wraps_in_mcp_servers(self, tmp_path):
        servers = {"my-server": {"command": "node", "args": ["server.js"]}}
        path = _write_cli_mcp_config(servers, tmp_path)
        data = json.loads(path.read_text())
        assert "mcpServers" in data
        assert data["mcpServers"] == servers


class TestMakeIsolatedEnv:
    def test_xdg_config_home_set(self):
        env, xdg_dir = _make_isolated_env()
        try:
            assert "XDG_CONFIG_HOME" in env
            assert Path(env["XDG_CONFIG_HOME"]).is_dir()
            assert list(Path(env["XDG_CONFIG_HOME"]).iterdir()) == []
        finally:
            import shutil

            shutil.rmtree(xdg_dir, ignore_errors=True)


class TestReviewerVerdict:
    def test_accepted(self):
        report = {"timeline": [{"type": "review", "exit_code": 0}]}
        assert _reviewer_verdict(report) is True

    def test_rejected(self):
        report = {"timeline": [{"type": "review", "exit_code": 1}]}
        assert _reviewer_verdict(report) is False

    def test_error(self):
        report = {"timeline": [{"type": "review", "exit_code": 2}]}
        assert _reviewer_verdict(report) is None

    def test_no_review_events(self):
        report = {"timeline": [{"type": "llm_call"}]}
        assert _reviewer_verdict(report) is None

    def test_empty_timeline(self):
        report = {"timeline": []}
        assert _reviewer_verdict(report) is None

    def test_multiple_rounds_uses_last(self):
        report = {
            "timeline": [
                {"type": "review", "exit_code": 1},
                {"type": "review", "exit_code": 1},
                {"type": "review", "exit_code": 0},
            ]
        }
        assert _reviewer_verdict(report) is True


class TestClassifyCliFailure:
    """Exhaustive 9-case matrix for CLI failure classification."""

    def test_exit0_with_report(self):
        report = {"result": {"outcome": "success"}, "stats": {}}
        result = _classify_cli_failure(0, "", report, timed_out=False, verified=True)
        assert result is None

    def test_exit1_report_tool_failure(self):
        report = {
            "result": {"outcome": "error"},
            "stats": {"tool_calls_failed": 3},
        }
        result = _classify_cli_failure(1, "", report, timed_out=False, verified=False)
        assert result == "tool"

    def test_exit1_report_error_stderr_rate_limit(self):
        report = {"result": {"outcome": "error"}, "stats": {"tool_calls_failed": 0}}
        result = _classify_cli_failure(
            1, "error: rate limit exceeded", report, timed_out=False, verified=False
        )
        assert result == "provider"

    def test_exit1_report_error_empty_stderr(self):
        report = {"result": {"outcome": "error"}, "stats": {"tool_calls_failed": 0}}
        result = _classify_cli_failure(1, "", report, timed_out=False, verified=False)
        assert result == "task"

    def test_exit1_no_report_stderr_429(self):
        result = _classify_cli_failure(
            1, "HTTP 429 Too Many Requests", None, timed_out=False, verified=None
        )
        assert result == "provider"

    def test_exit1_no_report_empty_stderr(self):
        result = _classify_cli_failure(1, "", None, timed_out=False, verified=None)
        assert result == "task"

    def test_exit2_report_exhausted(self):
        report = {"result": {"outcome": "exhausted"}, "stats": {}}
        result = _classify_cli_failure(2, "", report, timed_out=False, verified=None)
        assert result == "task"

    def test_timeout_partial_report(self):
        report = {"result": {"outcome": "success"}, "stats": {}}
        result = _classify_cli_failure(-1, "", report, timed_out=True, verified=None)
        assert result == "timeout"

    def test_timeout_no_report(self):
        result = _classify_cli_failure(-1, "", None, timed_out=True, verified=None)
        assert result == "timeout"


class TestWorkspaceIsolation:
    def test_swival_toml_deleted_in_cli_path(self, tmp_path):
        """swival.toml from env/ should be deleted before CLI launch."""
        task = _task(tmp_path)
        (task.env_dir / "swival.toml").write_text("[agent]\nmodel = 'bad'")

        spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)
        workdir = setup_workspace(spec, spec.variant)

        assert (workdir / "swival.toml").exists()

        (workdir / "swival.toml").unlink()
        assert not (workdir / "swival.toml").exists()

        import shutil

        shutil.rmtree(workdir)


class TestRunTrialCli:
    def test_constructs_correct_argv(self, tmp_path):
        task = _task(tmp_path)
        reviewer = ReviewerConfig(command="/usr/bin/true", max_rounds=3)
        campaign = _campaign(reviewer=reviewer)
        spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)

        with patch("calibra.runner.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            run_trial_cli(spec, campaign, keep_workdirs=False)

            call_args = mock_popen.call_args
            argv = call_args[0][0]

            assert argv[0] == "swival"
            assert "--quiet" in argv
            assert "--no-history" in argv
            assert "--reviewer" in argv
            assert "/usr/bin/true" in argv
            assert "--max-review-rounds" in argv
            assert "3" in argv
            assert "--no-mcp" in argv
            assert call_args[1]["start_new_session"] is True

    def test_yolo_default_true_in_cli_path(self, tmp_path):
        """CLI path must default to --yolo like Session path (finding #1)."""
        task = _task(tmp_path)
        reviewer = ReviewerConfig(command="/usr/bin/true", max_rounds=3)
        campaign = _campaign(reviewer=reviewer)
        spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)

        with patch("calibra.runner.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            run_trial_cli(spec, campaign, keep_workdirs=False)

            argv = mock_popen.call_args[0][0]
            assert "--yolo" in argv

    def test_yolo_false_with_allowed_commands(self, tmp_path):
        """CLI path must auto-disable yolo when allowed_commands is set."""
        task = _task(tmp_path)
        reviewer = ReviewerConfig(command="/usr/bin/true", max_rounds=3)
        campaign = _campaign(reviewer=reviewer)
        spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)

        with patch("calibra.runner.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            run_trial_cli(
                spec,
                campaign,
                keep_workdirs=False,
                merged_session_opts={"allowed_commands": ["python"]},
            )

            argv = mock_popen.call_args[0][0]
            assert "--yolo" not in argv
            assert "--allowed-commands" in argv

    def test_report_read_and_verdict(self, tmp_path):
        task = _task(tmp_path)
        reviewer = ReviewerConfig(command="/usr/bin/true", max_rounds=3)
        campaign = _campaign(reviewer=reviewer)
        spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)

        report_data = {
            "result": {"outcome": "success"},
            "stats": {"review_rounds": 2},
            "timeline": [
                {"type": "review", "exit_code": 1},
                {"type": "review", "exit_code": 0},
            ],
        }

        def fake_communicate(timeout=None):
            return (b"", b"")

        with patch("calibra.runner.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate = fake_communicate
            mock_proc.returncode = 0
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            def write_report(*args, **kwargs):
                call_argv = mock_popen.call_args[0][0]
                report_idx = call_argv.index("--report")
                report_path = Path(call_argv[report_idx + 1])
                report_path.write_text(json.dumps(report_data))
                return (b"", b"")

            mock_proc.communicate = write_report

            result = run_trial_cli(spec, campaign, keep_workdirs=False)

            assert result.verified is True
            assert result.failure_class is None
            assert result.report is not None


class TestWriteTrialReportReviewer:
    def test_includes_reviewer_fields(self, tmp_path):
        task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
        variant = _variant()
        spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
        report = {
            "stats": {"review_rounds": 2},
            "timeline": [
                {"type": "review", "exit_code": 1},
                {"type": "review", "exit_code": 0},
            ],
        }
        result = TrialResult(
            spec=spec,
            report=report,
            verified=True,
            failure_class=None,
            wall_time_s=5.0,
            error_message=None,
            attempts=1,
        )
        reviewer = ReviewerConfig(command="/usr/bin/true", max_rounds=3)
        campaign = _campaign(reviewer=reviewer)
        write_trial_report(tmp_path, result, campaign)

        path = tmp_path / "hello" / f"{variant.label}_0.json"
        data = json.loads(path.read_text())
        assert data["calibra"]["review_rounds"] == 2
        assert data["calibra"]["reviewer_verdict"] == "accepted"

    def test_no_reviewer_fields_without_config(self, tmp_path):
        task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
        variant = _variant()
        spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
        result = TrialResult(
            spec=spec,
            report={"result": {"outcome": "success"}},
            verified=True,
            failure_class=None,
            wall_time_s=5.0,
            error_message=None,
            attempts=1,
        )
        campaign = _campaign(reviewer=None)
        write_trial_report(tmp_path, result, campaign)

        path = tmp_path / "hello" / f"{variant.label}_0.json"
        data = json.loads(path.read_text())
        assert "review_rounds" not in data["calibra"]
        assert "reviewer_verdict" not in data["calibra"]


class TestAnalysisReviewRounds:
    def _trial_metrics(self, review_rounds=0, verified=True):
        return TrialMetrics(
            task="hello",
            variant_label="v1",
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
            review_rounds=review_rounds,
        )

    def test_aggregate_with_reviews(self):
        metrics = [
            self._trial_metrics(review_rounds=2),
            self._trial_metrics(review_rounds=3),
            self._trial_metrics(review_rounds=1),
        ]
        agg = aggregate_variant(metrics)
        assert agg.review_rounds is not None
        assert agg.review_rounds.mean == 2.0

    def test_aggregate_without_reviews(self):
        metrics = [
            self._trial_metrics(review_rounds=0),
            self._trial_metrics(review_rounds=0),
        ]
        agg = aggregate_variant(metrics)
        assert agg.review_rounds is None

    def test_extract_metrics_review_rounds(self):
        report = {
            "result": {"outcome": "success"},
            "stats": {"turns": 5},
            "timeline": [],
            "calibra": {
                "task": "hello",
                "variant": "v1",
                "wall_time_s": 2.0,
                "verified": True,
                "review_rounds": 3,
            },
        }
        m = extract_metrics(report, 2.0, True, None)
        assert m.review_rounds == 3

    def test_extract_metrics_no_review_rounds(self):
        report = {
            "result": {"outcome": "success"},
            "stats": {"turns": 5},
            "timeline": [],
            "calibra": {
                "task": "hello",
                "variant": "v1",
                "wall_time_s": 2.0,
            },
        }
        m = extract_metrics(report, 2.0, True, None)
        assert m.review_rounds == 0
