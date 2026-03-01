"""Campaign configuration parsing and validation."""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
import shlex
import shutil
import tomllib
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union, get_args, get_origin


class ConfigError(Exception):
    """Raised for invalid campaign configuration."""


@dataclass
class ReviewerConfig:
    command: str
    max_rounds: int = 5


@dataclass
class ModelVariant:
    provider: str
    model: str
    label: str
    session_options: dict = field(default_factory=dict)


@dataclass
class AgentInstructionsVariant:
    label: str
    agents_md: str


@dataclass
class SkillsVariant:
    label: str
    skills_dirs: list[str]


@dataclass
class McpVariant:
    label: str
    config: str


@dataclass
class EnvironmentVariant:
    label: str
    overlay: str


@dataclass
class BudgetConfig:
    max_total_tokens: int = 0
    max_cost_usd: float = 0.0
    require_price_coverage: bool = False


@dataclass
class RetryConfig:
    infra: int = 2
    provider: int = 3
    tool: int = 1
    timeout: int = 0
    task: int = 0
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0


@dataclass
class SamplingConfig:
    mode: str = "full"
    max_variants: int = 0


@dataclass
class Campaign:
    name: str
    description: str
    repeat: int
    max_turns: int
    timeout_s: int
    seed: int
    tasks_dir: str
    budget: BudgetConfig
    retry: RetryConfig
    sampling: SamplingConfig
    models: list[ModelVariant]
    agent_instructions: list[AgentInstructionsVariant]
    skills: list[SkillsVariant]
    mcp: list[McpVariant]
    environments: list[EnvironmentVariant]
    constraints: list[dict] = field(default_factory=list)
    session_options: dict = field(default_factory=dict)
    reviewer: ReviewerConfig | None = None
    config_hash: str = ""


def _require(d: dict, key: str, context: str) -> object:
    if key not in d:
        raise ConfigError(f"Missing required field '{key}' in {context}")
    return d[key]


def _check_labels_unique(items: list, dimension: str):
    labels = [item.label for item in items]
    seen = set()
    for label in labels:
        if label in seen:
            raise ConfigError(f"Duplicate label '{label}' in {dimension}")
        seen.add(label)


def _resolve(base: Path, p: str) -> str:
    if not p:
        return ""
    resolved = (base / p).resolve()
    return str(resolved)


def _validate_path_exists(path: str, description: str):
    if path and not Path(path).exists():
        raise ConfigError(f"{description} not found: {path}")


_REJECTED_SESSION_KEYS = frozenset(
    {
        "base_dir",
        "provider",
        "model",
        "max_turns",
        "seed",
        "history",
        "skills_dir",
        "mcp_servers",
        "config_dir",
    }
)

_BLOCKED_SESSION_KEYS = frozenset(
    {
        "system_prompt",
        "no_system_prompt",
        "no_instructions",
    }
)

_MODEL_KNOWN_KEYS = frozenset({"provider", "model", "label", "session"})


@functools.lru_cache(maxsize=1)
def _get_session_param_types() -> dict[str, type | tuple]:
    from swival import Session

    hints = typing.get_type_hints(Session.__init__)
    hints.pop("return", None)
    return hints


def _unwrap_optional(tp):
    origin = get_origin(tp)
    if origin is Union:
        args = get_args(tp)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return tp


def _type_matches(value, expected_type) -> bool:
    if expected_type is type(None):
        return value is None
    origin = get_origin(expected_type)
    if origin is Union:
        return any(_type_matches(value, a) for a in get_args(expected_type))
    if origin is list:
        if not isinstance(value, list):
            return False
        elem_args = get_args(expected_type)
        if elem_args:
            return all(_type_matches(item, elem_args[0]) for item in value)
        return True
    if origin is dict:
        return isinstance(value, dict)
    if expected_type is float:
        return isinstance(value, (int, float))
    if isinstance(expected_type, type):
        return isinstance(value, expected_type)
    return True


def _validate_session_options(opts: dict, skills: list, context: str):
    if not opts:
        return

    param_hints = _get_session_param_types()
    valid_keys = set(param_hints.keys()) - {"self"}

    for key in opts:
        if key in _REJECTED_SESSION_KEYS:
            raise ConfigError(
                f"Session option '{key}' in {context} is managed by Calibra and cannot be set"
            )
        if key in _BLOCKED_SESSION_KEYS:
            raise ConfigError(
                f"Session option '{key}' in {context} conflicts with Calibra's dimension system"
            )
        if key not in valid_keys:
            raise ConfigError(f"Unknown session option '{key}' in {context}")

    if opts.get("no_skills") is True:
        has_nonempty_skills = any(sk.skills_dirs for sk in skills)
        if has_nonempty_skills:
            raise ConfigError(
                f"Session option 'no_skills = true' in {context} conflicts with skills "
                "variants that have non-empty skills_dirs"
            )

    for key, value in opts.items():
        if key in param_hints:
            expected = _unwrap_optional(param_hints[key])
            if value is not None and not _type_matches(value, expected):
                raise ConfigError(
                    f"Session option '{key}' in {context} has wrong type: "
                    f"expected {expected}, got {type(value).__name__}"
                )


def compute_config_hash(raw_toml: dict) -> str:
    d = copy.deepcopy(raw_toml)
    if "campaign" in d:
        d["campaign"].pop("name", None)
        d["campaign"].pop("description", None)
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_campaign(path: str | Path) -> Campaign:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    base = path.parent

    camp = raw.get("campaign", {})
    name = _require(camp, "name", "[campaign]")
    description = camp.get("description", "")
    repeat = camp.get("repeat", 1)
    max_turns = camp.get("max_turns", 50)
    timeout_s = camp.get("timeout_s", 300)
    seed = camp.get("seed", 42)
    tasks_dir = _resolve(base, _require(camp, "tasks_dir", "[campaign]"))

    _validate_path_exists(tasks_dir, "tasks_dir")

    budget_raw = raw.get("budget", {})
    budget = BudgetConfig(
        max_total_tokens=budget_raw.get("max_total_tokens", 0),
        max_cost_usd=budget_raw.get("max_cost_usd", 0.0),
        require_price_coverage=budget_raw.get("require_price_coverage", False),
    )

    retry_raw = raw.get("retry", {})
    retry = RetryConfig(
        infra=retry_raw.get("infra", 2),
        provider=retry_raw.get("provider", 3),
        tool=retry_raw.get("tool", 1),
        timeout=retry_raw.get("timeout", 0),
        task=retry_raw.get("task", 0),
        backoff_base_s=retry_raw.get("backoff_base_s", 1.0),
        backoff_max_s=retry_raw.get("backoff_max_s", 60.0),
    )

    sampling_raw = raw.get("sampling", {})
    sampling_mode = sampling_raw.get("mode", "full")
    if sampling_mode not in ("full", "random", "ablation"):
        raise ConfigError(f"Invalid sampling mode: {sampling_mode}")
    sampling = SamplingConfig(
        mode=sampling_mode,
        max_variants=sampling_raw.get("max_variants", 0),
    )

    matrix = raw.get("matrix", {})

    models_raw = matrix.get("model", [])
    if not models_raw:
        raise ConfigError("At least one [[matrix.model]] is required")
    models = []
    for m in models_raw:
        inline = {k: v for k, v in m.items() if k not in _MODEL_KNOWN_KEYS}
        session = m.get("session", {})
        merged = {**inline, **session}
        models.append(
            ModelVariant(
                provider=_require(m, "provider", "[[matrix.model]]"),
                model=_require(m, "model", "[[matrix.model]]"),
                label=_require(m, "label", "[[matrix.model]]"),
                session_options=merged,
            )
        )
    _check_labels_unique(models, "model")

    ai_raw = matrix.get("agent_instructions", [])
    if not ai_raw:
        raise ConfigError("At least one [[matrix.agent_instructions]] is required")
    agent_instructions = [
        AgentInstructionsVariant(
            label=_require(a, "label", "[[matrix.agent_instructions]]"),
            agents_md=_resolve(base, _require(a, "agents_md", "[[matrix.agent_instructions]]")),
        )
        for a in ai_raw
    ]
    _check_labels_unique(agent_instructions, "agent_instructions")
    for ai in agent_instructions:
        _validate_path_exists(ai.agents_md, f"agent_instructions '{ai.label}' agents_md")

    sk_raw = matrix.get("skills", [{"label": "none", "skills_dirs": []}])
    skills = [
        SkillsVariant(
            label=_require(s, "label", "[[matrix.skills]]"),
            skills_dirs=[_resolve(base, d) for d in s.get("skills_dirs", [])],
        )
        for s in sk_raw
    ]
    _check_labels_unique(skills, "skills")
    for sk in skills:
        for sd in sk.skills_dirs:
            _validate_path_exists(sd, f"skills '{sk.label}' skills_dir")

    mcp_raw = matrix.get("mcp", [{"label": "none", "config": ""}])
    mcps = [
        McpVariant(
            label=_require(m, "label", "[[matrix.mcp]]"),
            config=_resolve(base, m.get("config", "")),
        )
        for m in mcp_raw
    ]
    _check_labels_unique(mcps, "mcp")
    for mc in mcps:
        _validate_path_exists(mc.config, f"mcp '{mc.label}' config")

    env_raw = matrix.get("environment", [{"label": "base", "overlay": ""}])
    environments = [
        EnvironmentVariant(
            label=_require(e, "label", "[[matrix.environment]]"),
            overlay=_resolve(base, e.get("overlay", "")),
        )
        for e in env_raw
    ]
    _check_labels_unique(environments, "environment")
    for env in environments:
        _validate_path_exists(env.overlay, f"environment '{env.label}' overlay")

    campaign_session_opts = raw.get("session", {})
    _validate_session_options(campaign_session_opts, skills, "[session]")
    for m_variant in models:
        if m_variant.session_options:
            _validate_session_options(
                m_variant.session_options,
                skills,
                f"[[matrix.model]] '{m_variant.label}' session",
            )

    constraints = raw.get("constraints", [])
    valid_dims = {"model", "agent_instructions", "skills", "mcp", "environment"}
    dim_labels = {
        "model": {m.label for m in models},
        "agent_instructions": {a.label for a in agent_instructions},
        "skills": {s.label for s in skills},
        "mcp": {m.label for m in mcps},
        "environment": {e.label for e in environments},
    }
    for c in constraints:
        for section in ("when", "exclude"):
            if section not in c:
                raise ConfigError(f"Constraint missing '{section}' key")
            for dim, label in c[section].items():
                if dim not in valid_dims:
                    raise ConfigError(f"Invalid dimension '{dim}' in constraint {section}")
                if label not in dim_labels[dim]:
                    raise ConfigError(
                        f"Unknown label '{label}' for dimension '{dim}' in constraint {section}"
                    )

    reviewer = None
    reviewer_raw = raw.get("reviewer")
    if reviewer_raw is not None:
        rev_command = reviewer_raw.get("command")
        if not rev_command or not isinstance(rev_command, str) or not rev_command.strip():
            raise ConfigError("[reviewer] requires a non-empty 'command'")

        rev_max_rounds = reviewer_raw.get("max_rounds", 5)
        if not isinstance(rev_max_rounds, int) or rev_max_rounds < 0:
            raise ConfigError("[reviewer] max_rounds must be a non-negative integer")

        try:
            tokens = shlex.split(rev_command)
        except ValueError as e:
            raise ConfigError(f"[reviewer] malformed command string: {e}") from e
        executable = tokens[0]
        resolved_exe = shutil.which(executable)
        if resolved_exe is None:
            candidate = (base / executable).resolve()
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                raise ConfigError(f"[reviewer] command executable not found: {executable}")
            resolved_exe = str(candidate)

        rev_command_resolved = shlex.join([resolved_exe] + tokens[1:])
        reviewer = ReviewerConfig(command=rev_command_resolved, max_rounds=rev_max_rounds)

    config_hash = compute_config_hash(raw)

    return Campaign(
        name=name,
        description=description,
        repeat=repeat,
        max_turns=max_turns,
        timeout_s=timeout_s,
        seed=seed,
        tasks_dir=tasks_dir,
        budget=budget,
        retry=retry,
        sampling=sampling,
        models=models,
        agent_instructions=agent_instructions,
        skills=skills,
        mcp=mcps,
        environments=environments,
        constraints=constraints,
        session_options=campaign_session_opts,
        reviewer=reviewer,
        config_hash=config_hash,
    )
