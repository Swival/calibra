"""Matrix expansion, constraint filtering, and sampling."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from calibra.config import (
    AgentInstructionsVariant,
    Campaign,
    EnvironmentVariant,
    McpVariant,
    ModelVariant,
    SamplingConfig,
    SkillsVariant,
)


@dataclass
class Variant:
    model: ModelVariant
    agent_instructions: AgentInstructionsVariant
    skills: SkillsVariant
    mcp: McpVariant
    environment: EnvironmentVariant

    @property
    def label(self) -> str:
        return "_".join(
            [
                self.model.label,
                self.agent_instructions.label,
                self.skills.label,
                self.mcp.label,
                self.environment.label,
            ]
        )


def expand_matrix(campaign: Campaign) -> list[Variant]:
    return [
        Variant(model=m, agent_instructions=a, skills=s, mcp=mc, environment=e)
        for m, a, s, mc, e in itertools.product(
            campaign.models,
            campaign.agent_instructions,
            campaign.skills,
            campaign.mcp,
            campaign.environments,
        )
    ]


def apply_constraints(variants: list[Variant], constraints: list[dict]) -> list[Variant]:
    def matches(variant: Variant, pairs: dict) -> bool:
        dim_map = {
            "model": variant.model.label,
            "agent_instructions": variant.agent_instructions.label,
            "skills": variant.skills.label,
            "mcp": variant.mcp.label,
            "environment": variant.environment.label,
        }
        return all(dim_map.get(dim) == label for dim, label in pairs.items())

    result = []
    for v in variants:
        excluded = False
        for c in constraints:
            if matches(v, c["when"]) and matches(v, c["exclude"]):
                excluded = True
                break
        if not excluded:
            result.append(v)
    return result


def apply_screening(variants: list[Variant], sampling: SamplingConfig, seed: int) -> list[Variant]:
    if sampling.mode == "full":
        if sampling.max_variants > 0:
            return variants[: sampling.max_variants]
        return variants

    if sampling.mode == "random":
        rng = random.Random(seed)
        k = sampling.max_variants if sampling.max_variants > 0 else len(variants)
        k = min(k, len(variants))
        return rng.sample(variants, k)

    if sampling.mode == "ablation":
        if not variants:
            return []
        baseline = variants[0]
        result = [baseline]
        for v in variants[1:]:
            diffs = 0
            if v.model.label != baseline.model.label:
                diffs += 1
            if v.agent_instructions.label != baseline.agent_instructions.label:
                diffs += 1
            if v.skills.label != baseline.skills.label:
                diffs += 1
            if v.mcp.label != baseline.mcp.label:
                diffs += 1
            if v.environment.label != baseline.environment.label:
                diffs += 1
            if diffs == 1:
                result.append(v)
        if sampling.max_variants > 0:
            return result[: sampling.max_variants]
        return result

    return variants


def apply_filter(variants: list[Variant], filter_expr: str) -> list[Variant]:
    from calibra.config import ConfigError

    pairs = {}
    for part in filter_expr.split(","):
        key, _, value = part.strip().partition("=")
        pairs[key.strip()] = value.strip()

    dim_attr = {
        "model": lambda v: v.model.label,
        "agent_instructions": lambda v: v.agent_instructions.label,
        "skills": lambda v: v.skills.label,
        "mcp": lambda v: v.mcp.label,
        "environment": lambda v: v.environment.label,
    }

    unknown = set(pairs.keys()) - set(dim_attr.keys())
    if unknown:
        raise ConfigError(
            f"Unknown filter dimension(s): {', '.join(sorted(unknown))}. "
            f"Valid dimensions: {', '.join(sorted(dim_attr.keys()))}"
        )

    result = []
    for v in variants:
        match = True
        for dim, label in pairs.items():
            if dim_attr[dim](v) != label:
                match = False
                break
        if match:
            result.append(v)
    return result
