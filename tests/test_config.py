"""Tests for config.py: TOML parsing, validation, Campaign dataclass."""

import pytest
from pathlib import Path

from calibra.config import load_campaign, ConfigError


def _write_campaign(tmp_path, toml_content, tasks=True, agents=True):
    if tasks:
        task_dir = tmp_path / "tasks" / "hello"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.md").write_text("Say hello.")
        (task_dir / "env").mkdir(exist_ok=True)

    if agents:
        agents_md = tmp_path / "agents.md"
        agents_md.write_text("You are a helpful assistant.")

    config = tmp_path / "campaign.toml"
    config.write_text(toml_content)
    return config


VALID_TOML = """\
[campaign]
name = "test"
description = "A test campaign"
tasks_dir = "tasks"
repeat = 2
max_turns = 10
timeout_s = 60
seed = 123

[[matrix.model]]
provider = "openrouter"
model = "test/model-a"
label = "model-a"

[[matrix.model]]
provider = "openrouter"
model = "test/model-b"
label = "model-b"

[[matrix.agent_instructions]]
label = "default"
agents_md = "agents.md"
"""


def test_valid_config(tmp_path):
    config = _write_campaign(tmp_path, VALID_TOML)
    campaign = load_campaign(config)
    assert campaign.name == "test"
    assert campaign.repeat == 2
    assert campaign.max_turns == 10
    assert campaign.seed == 123
    assert len(campaign.models) == 2
    assert campaign.models[0].label == "model-a"
    assert len(campaign.agent_instructions) == 1
    assert len(campaign.skills) == 1  # default "none"
    assert len(campaign.mcp) == 1  # default "none"
    assert len(campaign.environments) == 1  # default "base"


def test_missing_name(tmp_path):
    toml = """\
[campaign]
tasks_dir = "tasks"

[[matrix.model]]
provider = "test"
model = "m"
label = "m"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="name"):
        load_campaign(config)


def test_missing_tasks_dir(tmp_path):
    toml = """\
[campaign]
name = "test"

[[matrix.model]]
provider = "test"
model = "m"
label = "m"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="tasks_dir"):
        load_campaign(config)


def test_no_models(tmp_path):
    toml = """\
[campaign]
name = "test"
tasks_dir = "tasks"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="model"):
        load_campaign(config)


def test_duplicate_labels(tmp_path):
    toml = """\
[campaign]
name = "test"
tasks_dir = "tasks"

[[matrix.model]]
provider = "test"
model = "m1"
label = "same"

[[matrix.model]]
provider = "test"
model = "m2"
label = "same"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="Duplicate label"):
        load_campaign(config)


def test_invalid_constraint_dimension(tmp_path):
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

[[constraints]]
when = {bogus = "m"}
exclude = {model = "m"}
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="Invalid dimension"):
        load_campaign(config)


def test_invalid_constraint_label(tmp_path):
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

[[constraints]]
when = {model = "nonexistent"}
exclude = {model = "m"}
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="Unknown label"):
        load_campaign(config)


def test_config_hash_deterministic(tmp_path):
    config = _write_campaign(tmp_path, VALID_TOML)
    c1 = load_campaign(config)
    c2 = load_campaign(config)
    assert c1.config_hash == c2.config_hash
    assert len(c1.config_hash) == 64  # SHA-256 hex


def test_config_hash_ignores_name_description(tmp_path):
    config1 = _write_campaign(tmp_path, VALID_TOML)
    c1 = load_campaign(config1)

    modified = VALID_TOML.replace('name = "test"', 'name = "different"')
    modified = modified.replace('description = "A test campaign"', 'description = "changed"')
    config2 = tmp_path / "campaign2.toml"
    config2.write_text(modified)
    c2 = load_campaign(config2)

    assert c1.config_hash == c2.config_hash


def test_path_resolution(tmp_path):
    config = _write_campaign(tmp_path, VALID_TOML)
    campaign = load_campaign(config)
    assert Path(campaign.tasks_dir).is_absolute()
    assert Path(campaign.agent_instructions[0].agents_md).is_absolute()


def test_defaults(tmp_path):
    minimal = """\
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
"""
    config = _write_campaign(tmp_path, minimal)
    campaign = load_campaign(config)
    assert campaign.repeat == 1
    assert campaign.max_turns == 50
    assert campaign.timeout_s == 300
    assert campaign.seed == 42
    assert campaign.sampling.mode == "full"
    assert campaign.retry.provider == 3


def test_invalid_sampling_mode(tmp_path):
    toml = """\
[campaign]
name = "test"
tasks_dir = "tasks"

[sampling]
mode = "bogus"

[[matrix.model]]
provider = "test"
model = "m"
label = "m"

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
"""
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="Invalid sampling mode"):
        load_campaign(config)


_BASE_TOML = """\
[campaign]
name = "test"
tasks_dir = "tasks"

{extra}

[[matrix.model]]
provider = "test"
model = "m"
label = "m"
{model_extra}

[[matrix.agent_instructions]]
label = "d"
agents_md = "agents.md"
{skills_section}
"""


def _session_toml(session="", model_session="", skills_section=""):
    return _BASE_TOML.format(
        extra=session,
        model_extra=model_session,
        skills_section=skills_section,
    )


def test_session_campaign_level_parsed(tmp_path):
    toml = _session_toml(session="[session]\ntemperature = 0.5\ntop_p = 0.9")
    config = _write_campaign(tmp_path, toml)
    campaign = load_campaign(config)
    assert campaign.session_options == {"temperature": 0.5, "top_p": 0.9}


def test_session_per_model_parsed(tmp_path):
    toml = _session_toml(model_session="session = { verbose = true }")
    config = _write_campaign(tmp_path, toml)
    campaign = load_campaign(config)
    assert campaign.models[0].session_options == {"verbose": True}


def test_session_empty_defaults(tmp_path):
    toml = _session_toml()
    config = _write_campaign(tmp_path, toml)
    campaign = load_campaign(config)
    assert campaign.session_options == {}
    assert campaign.models[0].session_options == {}


def test_session_rejected_key_base_dir(tmp_path):
    toml = _session_toml(session='[session]\nbase_dir = "/tmp/bad"')
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="managed by Calibra"):
        load_campaign(config)


def test_session_rejected_key_provider(tmp_path):
    toml = _session_toml(model_session='session = { provider = "openai" }')
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="managed by Calibra"):
        load_campaign(config)


def test_session_rejected_key_config_dir(tmp_path):
    toml = _session_toml(session='[session]\nconfig_dir = "/home/user/.config"')
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="managed by Calibra"):
        load_campaign(config)


def test_session_unknown_key(tmp_path):
    toml = _session_toml(session="[session]\nnonexistent_param = 42")
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="Unknown session option"):
        load_campaign(config)


def test_session_config_hash_changes(tmp_path):
    toml1 = _session_toml()
    config1 = _write_campaign(tmp_path, toml1)
    c1 = load_campaign(config1)

    toml2 = _session_toml(session="[session]\ntemperature = 0.5")
    config2 = tmp_path / "campaign2.toml"
    config2.write_text(toml2)
    c2 = load_campaign(config2)

    assert c1.config_hash != c2.config_hash


def test_session_type_validation_wrong_type(tmp_path):
    toml = _session_toml(session='[session]\ntemperature = "hot"')
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="wrong type"):
        load_campaign(config)


def test_session_type_validation_list_elements(tmp_path):
    toml = _session_toml(session="[session]\nallowed_commands = [1, 2]")
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="wrong type"):
        load_campaign(config)


def test_session_conflict_no_instructions(tmp_path):
    toml = _session_toml(session="[session]\nno_instructions = true")
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="conflicts with.*dimension"):
        load_campaign(config)


def test_session_conflict_no_system_prompt(tmp_path):
    toml = _session_toml(session="[session]\nno_system_prompt = true")
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="conflicts with.*dimension"):
        load_campaign(config)


def test_session_conflict_system_prompt(tmp_path):
    toml = _session_toml(session='[session]\nsystem_prompt = "custom"')
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="conflicts with.*dimension"):
        load_campaign(config)


def test_session_conflict_no_skills_with_nonempty_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skills = f"""
[[matrix.skills]]
label = "full"
skills_dirs = ["{skills_dir}"]
"""
    toml = _session_toml(session="[session]\nno_skills = true", skills_section=skills)
    config = _write_campaign(tmp_path, toml)
    with pytest.raises(ConfigError, match="no_skills.*conflicts.*skills"):
        load_campaign(config)


def test_session_no_skills_allowed_when_all_empty(tmp_path):
    skills = """
[[matrix.skills]]
label = "none"
skills_dirs = []
"""
    toml = _session_toml(session="[session]\nno_skills = true", skills_section=skills)
    config = _write_campaign(tmp_path, toml)
    campaign = load_campaign(config)
    assert campaign.session_options["no_skills"] is True


def test_session_valid_allowed_commands(tmp_path):
    toml = _session_toml(session='[session]\nallowed_commands = ["python", "uv"]')
    config = _write_campaign(tmp_path, toml)
    campaign = load_campaign(config)
    assert campaign.session_options["allowed_commands"] == ["python", "uv"]
