"""Tests for tasks.py: task discovery and validation."""

import pytest

from calibra.config import ConfigError
from calibra.tasks import discover_tasks


def _make_task(tmp_path, name="hello", prompt="Say hello.", verify=False, meta=None):
    task_dir = tmp_path / name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(prompt)
    (task_dir / "env").mkdir(exist_ok=True)
    if verify:
        script = task_dir / "verify.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
    if meta:
        (task_dir / "meta.toml").write_text(meta)
    return task_dir


def test_basic_discovery(tmp_path):
    _make_task(tmp_path, "hello")
    _make_task(tmp_path, "world")
    tasks = discover_tasks(tmp_path)
    assert len(tasks) == 2
    assert tasks[0].name == "hello"
    assert tasks[1].name == "world"


def test_task_prompt(tmp_path):
    _make_task(tmp_path, "hello", prompt="Do something.")
    tasks = discover_tasks(tmp_path)
    assert tasks[0].prompt == "Do something."


def test_missing_task_md(tmp_path):
    task_dir = tmp_path / "bad"
    task_dir.mkdir()
    (task_dir / "env").mkdir()
    with pytest.raises(ConfigError, match="missing task.md"):
        discover_tasks(tmp_path)


def test_empty_task_md(tmp_path):
    task_dir = tmp_path / "empty"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("")
    (task_dir / "env").mkdir()
    with pytest.raises(ConfigError, match="empty task.md"):
        discover_tasks(tmp_path)


def test_missing_env(tmp_path):
    task_dir = tmp_path / "noenv"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("Do it.")
    with pytest.raises(ConfigError, match="missing env/"):
        discover_tasks(tmp_path)


def test_verify_script(tmp_path):
    _make_task(tmp_path, "hello", verify=True)
    tasks = discover_tasks(tmp_path)
    assert tasks[0].verify_script is not None
    assert tasks[0].verify_script.name == "verify.sh"


def test_no_verify_script(tmp_path):
    _make_task(tmp_path, "hello", verify=False)
    tasks = discover_tasks(tmp_path)
    assert tasks[0].verify_script is None


def test_verify_not_executable(tmp_path):
    task_dir = _make_task(tmp_path, "hello")
    script = task_dir / "verify.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o644)
    with pytest.raises(ConfigError, match="not executable"):
        discover_tasks(tmp_path)


def test_meta_toml(tmp_path):
    _make_task(tmp_path, "hello", meta='[meta]\ndifficulty = "easy"\n')
    tasks = discover_tasks(tmp_path)
    assert tasks[0].meta["meta"]["difficulty"] == "easy"


def test_no_tasks(tmp_path):
    with pytest.raises(ConfigError, match="No tasks found"):
        discover_tasks(tmp_path)


def test_ignores_files(tmp_path):
    _make_task(tmp_path, "hello")
    (tmp_path / "README.md").write_text("ignore me")
    tasks = discover_tasks(tmp_path)
    assert len(tasks) == 1
