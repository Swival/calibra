"""Tests for CLI commands: validate, dry-run, filter."""

import pytest

from calibra.cli import main


CAMPAIGN_TOML = """\
[campaign]
name = "cli-test"
tasks_dir = "tasks"
seed = 42

[[matrix.model]]
provider = "test"
model = "test-model-a"
label = "model-a"

[[matrix.model]]
provider = "test"
model = "test-model-b"
label = "model-b"

[[matrix.agent_instructions]]
label = "default"
agents_md = "agents.md"
"""


def _setup(tmp_path):
    task_dir = tmp_path / "tasks" / "hello"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("Say hello.")
    (task_dir / "env").mkdir()

    (tmp_path / "agents.md").write_text("You are a helpful assistant.")

    config = tmp_path / "campaign.toml"
    config.write_text(CAMPAIGN_TOML)
    return config


def test_validate_success(tmp_path, capsys):
    config = _setup(tmp_path)
    main(["validate", str(config)])
    out = capsys.readouterr().out
    assert "Config valid" in out
    assert "2 variants" in out
    assert "1 tasks" in out


def test_validate_bad_config(tmp_path):
    config = tmp_path / "bad.toml"
    config.write_text('[campaign]\nname = "x"\n')
    with pytest.raises(SystemExit):
        main(["validate", str(config)])


def test_dry_run(tmp_path, capsys):
    config = _setup(tmp_path)
    main(["run", str(config), "--dry-run"])
    out = capsys.readouterr().out
    assert "Campaign: cli-test" in out
    assert "model-a_default_none_none_base" in out
    assert "model-b_default_none_none_base" in out
    assert "Total trials: 2" in out


def test_filter_dry_run(tmp_path, capsys):
    config = _setup(tmp_path)
    main(["run", str(config), "--dry-run", "--filter", "model=model-a"])
    out = capsys.readouterr().out
    assert "Variants: 1" in out
    assert "model-a_default_none_none_base" in out
    assert "model-b" not in out
