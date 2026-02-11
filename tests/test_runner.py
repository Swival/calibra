"""Tests for runner.py: workspace setup, trial execution, resume."""

import json
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from calibra.config import (
    AgentInstructionsVariant,
    BudgetConfig,
    Campaign,
    ConfigError,
    EnvironmentVariant,
    McpVariant,
    ModelVariant,
    RetryConfig,
    SamplingConfig,
    SkillsVariant,
)
from calibra.matrix import Variant
from calibra.tasks import Task
from calibra.runner import (
    TrialSpec,
    TrialResult,
    _deep_merge,
    _resolve_yolo,
    _validate_merged_options,
    build_all_specs,
    compute_trial_seed,
    result_exists,
    run_single_trial,
    setup_workspace,
    trial_report_path,
    write_trial_report,
)


def _variant(model_label="m0"):
    return Variant(
        model=ModelVariant(provider="test", model="test-model", label=model_label),
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
    (env_dir / "starter.py").write_text("print('hi')")
    return Task(name=name, prompt="Say hello.", env_dir=env_dir, verify_script=None, meta={})


def _campaign():
    return Campaign(
        name="test",
        description="",
        repeat=2,
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


def test_trial_seed_deterministic():
    s1 = compute_trial_seed(42, "hello", "m0_default", 0)
    s2 = compute_trial_seed(42, "hello", "m0_default", 0)
    assert s1 == s2


def test_trial_seed_varies():
    s1 = compute_trial_seed(42, "hello", "m0_default", 0)
    s2 = compute_trial_seed(42, "hello", "m0_default", 1)
    assert s1 != s2


def test_build_all_specs(tmp_path):
    campaign = _campaign()
    task = _task(tmp_path)
    variant = _variant()
    specs = build_all_specs(campaign, [variant], [task])
    assert len(specs) == 2  # repeat=2
    assert specs[0].repeat_index == 0
    assert specs[1].repeat_index == 1


def test_setup_workspace(tmp_path):
    task = _task(tmp_path)
    agents_md = tmp_path / "agents.md"
    agents_md.write_text("Test instructions")

    variant = _variant()
    variant.agent_instructions = AgentInstructionsVariant(label="default", agents_md=str(agents_md))

    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    workdir = setup_workspace(spec, variant)

    assert (workdir / "starter.py").exists()
    assert (workdir / "AGENTS.md").exists()
    assert (workdir / "AGENTS.md").read_text() == "Test instructions"

    import shutil

    shutil.rmtree(workdir)


def test_setup_workspace_with_overlay(tmp_path):
    task = _task(tmp_path)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "extra.txt").write_text("overlay content")
    (overlay / "starter.py").write_text("print('overridden')")

    variant = _variant()
    variant.environment = EnvironmentVariant(label="custom", overlay=str(overlay))

    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    workdir = setup_workspace(spec, variant)

    assert (workdir / "extra.txt").read_text() == "overlay content"
    assert (workdir / "starter.py").read_text() == "print('overridden')"

    import shutil

    shutil.rmtree(workdir)


def test_trial_report_path():
    task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    path = trial_report_path(Path("/output"), spec)
    assert path == Path("/output/hello/m0_default_none_none_base_0.json")


def test_write_trial_report(tmp_path):
    task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)
    result = TrialResult(
        spec=spec,
        report={"version": 1, "result": {"outcome": "success"}},
        verified=True,
        failure_class=None,
        wall_time_s=1.5,
        error_message=None,
        attempts=1,
    )
    campaign = _campaign()
    write_trial_report(tmp_path, result, campaign)

    path = trial_report_path(tmp_path, spec)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["calibra"]["config_hash"] == "abc123"
    assert data["calibra"]["task"] == "hello"
    assert data["calibra"]["variant"] == variant.label
    assert data["calibra"]["verified"] is True


def test_result_exists(tmp_path):
    task = Task(name="hello", prompt="", env_dir=Path("/tmp"), verify_script=None)
    variant = _variant()
    spec = TrialSpec(task=task, variant=variant, repeat_index=0, trial_seed=42)

    assert not result_exists(tmp_path, spec, "abc123")

    result = TrialResult(
        spec=spec,
        report={"version": 1, "result": {"outcome": "success"}},
        verified=None,
        failure_class=None,
        wall_time_s=1.0,
        error_message=None,
        attempts=1,
    )
    campaign = _campaign()
    write_trial_report(tmp_path, result, campaign)

    assert result_exists(tmp_path, spec, "abc123")
    assert not result_exists(tmp_path, spec, "different_hash")


def test_deep_merge_no_overlap():
    assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_deep_merge_partial_overlap():
    assert _deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_deep_merge_nested_dicts():
    base = {"x": {"a": 1, "b": {"c": 2, "d": 3}}}
    override = {"x": {"b": {"d": 99, "e": 4}}}
    result = _deep_merge(base, override)
    assert result == {"x": {"a": 1, "b": {"c": 2, "d": 99, "e": 4}}}


def test_deep_merge_scalar_overrides_dict():
    assert _deep_merge({"a": {"b": 1}}, {"a": "flat"}) == {"a": "flat"}


def test_deep_merge_dict_overrides_scalar():
    assert _deep_merge({"a": "flat"}, {"a": {"b": 1}}) == {"a": {"b": 1}}


def test_merge_session_options_campaign_only():
    assert _deep_merge({"temperature": 0.5}, {}) == {"temperature": 0.5}


def test_merge_session_options_model_only():
    assert _deep_merge({}, {"verbose": True}) == {"verbose": True}


def test_merge_session_options_both_with_overlap():
    result = _deep_merge({"temperature": 0.5, "top_p": 0.9}, {"temperature": 0.7})
    assert result == {"temperature": 0.7, "top_p": 0.9}


def test_merge_session_options_deep_merge_extra_body():
    result = _deep_merge(
        {"extra_body": {"a": 1, "nested": {"x": 10}}},
        {"extra_body": {"b": 2, "nested": {"y": 20}}},
    )
    assert result == {"extra_body": {"a": 1, "b": 2, "nested": {"x": 10, "y": 20}}}


def test_validate_merged_allowed_commands_plus_yolo_warns():
    opts = {"allowed_commands": ["python"], "yolo": True}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _validate_merged_options(opts, [_variant()])
        assert len(w) == 1
        assert "yolo" in str(w[0].message)


def test_validate_merged_no_skills_with_skills_dirs_raises():
    v = _variant()
    v.skills = SkillsVariant(label="full", skills_dirs=["/some/path"])
    opts = {"no_skills": True}
    with pytest.raises(ConfigError, match="no_skills"):
        _validate_merged_options(opts, [v])


def test_validate_merged_no_skills_empty_skills_ok():
    v = _variant()
    v.skills = SkillsVariant(label="none", skills_dirs=[])
    opts = {"no_skills": True}
    _validate_merged_options(opts, [v])


def test_resolve_yolo_defaults_true():
    yolo, opts = _resolve_yolo({})
    assert yolo is True
    assert opts == {}


def test_resolve_yolo_with_allowlist_auto_false():
    yolo, opts = _resolve_yolo({"allowed_commands": ["python"]})
    assert yolo is False
    assert opts == {"allowed_commands": ["python"]}


def test_resolve_yolo_explicit_overrides_allowlist():
    yolo, opts = _resolve_yolo({"allowed_commands": ["python"], "yolo": True})
    assert yolo is True
    assert "yolo" not in opts
    assert opts == {"allowed_commands": ["python"]}


def test_resolve_yolo_does_not_mutate_input():
    original = {"yolo": False, "temperature": 0.5}
    _resolve_yolo(original)
    assert "yolo" in original


def _run_with_mock_session(tmp_path, merged_session_opts):
    task = _task(tmp_path)
    spec = TrialSpec(task=task, variant=_variant(), repeat_index=0, trial_seed=42)
    with patch("swival.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_cls.return_value = mock_session
        mock_result = MagicMock()
        mock_result.report = {"version": 1}
        mock_session.run.return_value = mock_result

        run_single_trial(
            spec, _campaign(), keep_workdirs=False, merged_session_opts=merged_session_opts
        )
        _, kwargs = mock_session_cls.call_args
    return kwargs


def test_yolo_auto_flip_with_allowed_commands(tmp_path):
    kwargs = _run_with_mock_session(tmp_path, {"allowed_commands": ["python"]})
    assert kwargs["yolo"] is False
    assert kwargs["allowed_commands"] == ["python"]


def test_yolo_explicit_true_with_allowed_commands(tmp_path):
    kwargs = _run_with_mock_session(tmp_path, {"allowed_commands": ["python"], "yolo": True})
    assert kwargs["yolo"] is True
    assert kwargs["allowed_commands"] == ["python"]


def test_yolo_default_true_without_allowed_commands(tmp_path):
    kwargs = _run_with_mock_session(tmp_path, {})
    assert kwargs["yolo"] is True


def test_session_receives_merged_opts(tmp_path):
    kwargs = _run_with_mock_session(
        tmp_path,
        {
            "temperature": 0.5,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    )
    assert kwargs["temperature"] == 0.5
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert kwargs["yolo"] is True
