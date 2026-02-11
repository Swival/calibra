"""Shared test fixtures."""

from __future__ import annotations

import pytest
from pathlib import Path


MINIMAL_TOML = """\
[campaign]
name = "test-campaign"
tasks_dir = "{tasks_dir}"

[[matrix.model]]
provider = "test"
model = "test-model"
label = "test-model"

[[matrix.agent_instructions]]
label = "default"
agents_md = "{agents_md}"
"""


@pytest.fixture
def minimal_campaign(tmp_path: Path) -> Path:
    tasks_dir = tmp_path / "tasks" / "hello"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "task.md").write_text("Say hello.")
    (tasks_dir / "env").mkdir()

    agents_md = tmp_path / "agents.md"
    agents_md.write_text("You are a helpful assistant.")

    config = tmp_path / "campaign.toml"
    config.write_text(
        MINIMAL_TOML.format(
            tasks_dir=str(tmp_path / "tasks"),
            agents_md=str(agents_md),
        )
    )
    return config
