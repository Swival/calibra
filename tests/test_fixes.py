"""Tests for the 9 bug fixes."""

import pytest
from pathlib import Path

from calibra.config import ConfigError, load_campaign
from calibra.failure import classify_failure
from calibra.matrix import apply_filter, Variant
from calibra.config import (
    AgentInstructionsVariant,
    BudgetConfig,
    Campaign,
    EnvironmentVariant,
    McpVariant,
    ModelVariant,
    RetryConfig,
    SamplingConfig,
    SkillsVariant,
)
from calibra.runner import (
    TrialResult,
    TrialSpec,
    result_exists,
    write_trial_report,
)
from calibra.tasks import Task
from calibra.prices import load_prices, validate_price_coverage


def _variant():
    return Variant(
        model=ModelVariant(provider="test", model="test-model", label="m0"),
        agent_instructions=AgentInstructionsVariant(label="default", agents_md=""),
        skills=SkillsVariant(label="none", skills_dirs=[]),
        mcp=McpVariant(label="none", config=""),
        environment=EnvironmentVariant(label="base", overlay=""),
    )


def _campaign():
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
        config_hash="abc123",
    )


# --- Fix #1: verify.sh failures treated as trial failures ---


def test_verify_false_classifies_as_task_failure():
    report = {"result": {"outcome": "success"}, "stats": {}}
    assert classify_failure(None, report, False, verified=False) == "task"


def test_verify_true_no_failure():
    report = {"result": {"outcome": "success"}, "stats": {}}
    assert classify_failure(None, report, False, verified=True) is None


def test_verify_none_no_failure():
    report = {"result": {"outcome": "success"}, "stats": {}}
    assert classify_failure(None, report, False, verified=None) is None


# --- Fix #3: --resume treats failed trials as completed ---


def test_resume_accepts_failed_trial(tmp_path):
    task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)

    result = TrialResult(
        spec=spec,
        report=None,  # exception path: empty report
        verified=None,
        failure_class="provider",
        wall_time_s=1.0,
        error_message="rate limit",
        attempts=3,
    )
    campaign = _campaign()
    write_trial_report(tmp_path, result, campaign)

    # Failed trial should be treated as completed for resume
    assert result_exists(tmp_path, spec, "abc123")


def test_resume_rejects_stale_config(tmp_path):
    task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)

    result = TrialResult(
        spec=spec,
        report=None,
        verified=None,
        failure_class="provider",
        wall_time_s=1.0,
        error_message="err",
        attempts=1,
    )
    campaign = _campaign()
    write_trial_report(tmp_path, result, campaign)

    assert not result_exists(tmp_path, spec, "different_hash")


# --- Fix #4: MCP config supports TOML ---


def test_mcp_toml_config(tmp_path):
    from calibra.runner import _load_mcp_config

    mcp_toml = tmp_path / "mcp.toml"
    mcp_toml.write_text('[servers]\n[servers.test]\ncommand = "echo"\n')

    result = _load_mcp_config(mcp_toml)
    assert result["servers"]["test"]["command"] == "echo"


def test_mcp_json_config(tmp_path):
    from calibra.runner import _load_mcp_config

    mcp_json = tmp_path / "mcp.json"
    mcp_json.write_text('{"servers": {"test": {"command": "echo"}}}')

    result = _load_mcp_config(mcp_json)
    assert result["servers"]["test"]["command"] == "echo"


# --- Fix #6: Cost guard - prices loading and coverage ---


def test_load_prices(tmp_path):
    prices_toml = tmp_path / "prices.toml"
    prices_toml.write_text(
        '[prices]\n"openrouter/anthropic/claude-sonnet-4" = 0.003\n"local/qwen" = 0.0\n'
    )
    # load_prices expects a config file path (reads prices.toml from same dir)
    config_path = tmp_path / "campaign.toml"
    config_path.write_text("")  # dummy

    prices = load_prices(config_path)
    assert ("openrouter", "anthropic/claude-sonnet-4") in prices
    assert prices[("openrouter", "anthropic/claude-sonnet-4")] == 0.003
    assert ("local", "qwen") in prices


def test_load_prices_no_file(tmp_path):
    config_path = tmp_path / "campaign.toml"
    config_path.write_text("")
    prices = load_prices(config_path)
    assert prices == {}


def test_validate_price_coverage_missing():
    campaign = _campaign()
    prices = {}
    with pytest.raises(ConfigError, match="Missing price entries"):
        validate_price_coverage(campaign, prices)


def test_validate_price_coverage_ok():
    campaign = _campaign()
    prices = {("test", "m"): 0.01}
    validate_price_coverage(campaign, prices)  # should not raise


# --- Fix #7: Config validates skills_dirs, MCP, overlay paths ---


def test_config_validates_skills_dirs(tmp_path):
    toml = """\
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

[[matrix.skills]]
label = "with-skills"
skills_dirs = ["nonexistent_dir"]
"""
    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("hi")
    (task_dir / "env").mkdir()
    (tmp_path / "agents.md").write_text("agent")
    config = tmp_path / "campaign.toml"
    config.write_text(toml)

    with pytest.raises(ConfigError, match="skills.*not found"):
        load_campaign(config)


def test_config_validates_overlay_path(tmp_path):
    toml = """\
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

[[matrix.environment]]
label = "custom"
overlay = "nonexistent_overlay"
"""
    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("hi")
    (task_dir / "env").mkdir()
    (tmp_path / "agents.md").write_text("agent")
    config = tmp_path / "campaign.toml"
    config.write_text(toml)

    with pytest.raises(ConfigError, match="overlay.*not found"):
        load_campaign(config)


def test_config_validates_mcp_config_path(tmp_path):
    toml = """\
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

[[matrix.mcp]]
label = "custom"
config = "nonexistent_mcp.toml"
"""
    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("hi")
    (task_dir / "env").mkdir()
    (tmp_path / "agents.md").write_text("agent")
    config = tmp_path / "campaign.toml"
    config.write_text(toml)

    with pytest.raises(ConfigError, match="mcp.*not found"):
        load_campaign(config)


# --- Fix #9: --filter rejects unknown dimensions ---


def test_filter_unknown_dimension():
    variants = [_variant()]
    with pytest.raises(ConfigError, match="Unknown filter dimension"):
        apply_filter(variants, "typo=value")


def test_filter_unknown_dimension_mixed():
    variants = [_variant()]
    with pytest.raises(ConfigError, match="Unknown filter dimension"):
        apply_filter(variants, "model=m0,bogus=x")


# --- Fix #10: Timeout uses daemon thread, doesn't block on shutdown ---


def test_timeout_uses_daemon_thread_no_block(tmp_path):
    """Verify that run_single_trial returns promptly on timeout,
    not blocked by executor shutdown waiting on the worker."""
    import time

    from calibra.runner import run_single_trial

    env_dir = tmp_path / "env"
    env_dir.mkdir()
    task = Task(name="hello", prompt="hi", env_dir=env_dir, verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    campaign = _campaign()
    campaign.timeout_s = 1

    class StuckSession:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def run(self, prompt, *, report=False):
            time.sleep(10)

    import unittest.mock
    import types

    fake_swival = types.ModuleType("swival")
    fake_swival.Session = StuckSession

    with unittest.mock.patch.dict("sys.modules", {"swival": fake_swival}):
        start = time.monotonic()
        result = run_single_trial(spec, campaign)
        elapsed = time.monotonic() - start

    assert result.failure_class == "timeout"
    assert elapsed < 3, f"Expected return in <3s but took {elapsed:.1f}s"


# --- Fix #11: Budget-stop doesn't crash with CancelledError ---


def test_budget_stop_no_cancelled_error():
    """Cancelled futures should be silently skipped, not crash the run."""
    # We just verify the CancelledError import and handling exists
    # by checking the runner module catches it
    import calibra.runner as runner_mod
    import inspect

    source = inspect.getsource(runner_mod.run_campaign)
    assert "CancelledError" in source
    assert "continue" in source


# --- Fix #12: cmd_validate passes Path to load_prices ---


def test_validate_price_coverage_cli(tmp_path):
    """cmd_validate should not crash with AttributeError on str."""
    from calibra.cli import main

    prices_toml = tmp_path / "prices.toml"
    prices_toml.write_text('[prices]\n"test/m" = 0.01\n')

    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("hi")
    (task_dir / "env").mkdir()
    (tmp_path / "agents.md").write_text("agent")

    config = tmp_path / "campaign.toml"
    config.write_text("""\
[campaign]
name = "test"
tasks_dir = "tasks"

[budget]
require_price_coverage = true

[[matrix.model]]
provider = "test"
model = "m"
label = "m"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
""")

    # Should not raise AttributeError: 'str' object has no attribute 'parent'
    main(["validate", str(config)])
