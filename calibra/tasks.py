"""Task discovery and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from calibra.config import ConfigError


@dataclass
class Task:
    name: str
    prompt: str
    env_dir: Path
    verify_script: Path | None
    meta: dict = field(default_factory=dict)


def discover_tasks(tasks_dir: str | Path) -> list[Task]:
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.is_dir():
        raise ConfigError(f"Tasks directory not found: {tasks_dir}")

    tasks = []
    for entry in sorted(tasks_dir.iterdir()):
        if not entry.is_dir():
            continue

        task_md = entry / "task.md"
        if not task_md.exists():
            raise ConfigError(f"Task '{entry.name}' missing task.md")

        prompt = task_md.read_text().strip()
        if not prompt:
            raise ConfigError(f"Task '{entry.name}' has empty task.md")

        env_dir = entry / "env"
        if not env_dir.is_dir():
            raise ConfigError(f"Task '{entry.name}' missing env/ directory")

        verify_script = entry / "verify.sh"
        if verify_script.exists():
            if not verify_script.stat().st_mode & 0o111:
                raise ConfigError(f"Task '{entry.name}' verify.sh is not executable")
        else:
            verify_script = None

        meta = {}
        meta_path = entry / "meta.toml"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta = tomllib.load(f)

        tasks.append(
            Task(
                name=entry.name,
                prompt=prompt,
                env_dir=env_dir,
                verify_script=verify_script,
                meta=meta,
            )
        )

    if not tasks:
        raise ConfigError(f"No tasks found in {tasks_dir}")

    return tasks
