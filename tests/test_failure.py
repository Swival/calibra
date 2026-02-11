"""Tests for failure.py and budget.py."""

from calibra.failure import classify_failure
from calibra.budget import BudgetTracker
from calibra.config import BudgetConfig, ModelVariant
from calibra.matrix import Variant
from calibra.config import (
    AgentInstructionsVariant,
    EnvironmentVariant,
    McpVariant,
    SkillsVariant,
)
from calibra.runner import TrialResult, TrialSpec
from calibra.tasks import Task
from pathlib import Path


def test_no_failure():
    assert classify_failure(None, None, False) is None


def test_timeout():
    assert classify_failure(None, None, True) == "timeout"


def test_infra_oserror():
    assert classify_failure(OSError("disk full"), None, False) == "infra"


def test_infra_permission():
    assert classify_failure(PermissionError("denied"), None, False) == "infra"


def test_provider_rate_limit():
    assert classify_failure(Exception("rate limit exceeded"), None, False) == "provider"


def test_provider_429():
    assert classify_failure(Exception("HTTP 429"), None, False) == "provider"


def test_tool_failure():
    report = {
        "result": {"outcome": "error"},
        "stats": {"tool_calls_failed": 3},
    }
    assert classify_failure(None, report, False) == "tool"


def test_task_exhausted():
    report = {
        "result": {"outcome": "exhausted"},
        "stats": {},
    }
    assert classify_failure(None, report, False) == "task"


def test_task_error_no_tool_failures():
    report = {
        "result": {"outcome": "error"},
        "stats": {"tool_calls_failed": 0},
    }
    assert classify_failure(None, report, False) == "task"


def test_default_fallback():
    assert classify_failure(Exception("unknown"), None, False) == "task"


def _make_result(tokens=1000, provider="test", model="m"):
    variant = Variant(
        model=ModelVariant(provider=provider, model=model, label="m"),
        agent_instructions=AgentInstructionsVariant(label="d", agents_md=""),
        skills=SkillsVariant(label="n", skills_dirs=[]),
        mcp=McpVariant(label="n", config=""),
        environment=EnvironmentVariant(label="b", overlay=""),
    )
    task = Task(name="t", prompt="", env_dir=Path("/tmp"), verify_script=None)
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    report = {
        "timeline": [
            {"type": "llm_call", "prompt_tokens_est": tokens},
        ],
    }
    return TrialResult(
        spec=spec,
        report=report,
        verified=None,
        failure_class=None,
        wall_time_s=1.0,
        error_message=None,
        attempts=1,
    )


def test_budget_token_limit():
    budget = BudgetConfig(max_total_tokens=500, max_cost_usd=0)
    tracker = BudgetTracker(budget=budget, prices={})

    r = _make_result(tokens=400)
    assert not tracker.update(r)
    assert tracker.cumulative_tokens == 400

    r2 = _make_result(tokens=200)
    assert tracker.update(r2)
    assert tracker.exceeded
    assert "Token budget" in tracker.reason


def test_budget_cost_limit():
    budget = BudgetConfig(max_total_tokens=0, max_cost_usd=1.0)
    prices = {("test", "m"): 0.01}  # $0.01 per 1k tokens
    tracker = BudgetTracker(budget=budget, prices=prices)

    r = _make_result(tokens=50000)
    assert not tracker.update(r)  # $0.50

    r2 = _make_result(tokens=60000)
    assert tracker.update(r2)  # $0.60 more = $1.10 total
    assert "Cost budget" in tracker.reason


def test_budget_no_limit():
    budget = BudgetConfig(max_total_tokens=0, max_cost_usd=0)
    tracker = BudgetTracker(budget=budget, prices={})

    r = _make_result(tokens=1000000)
    assert not tracker.update(r)
