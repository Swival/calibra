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

    def dim_labels(self) -> dict[str, str]:
        return {
            "model": self.model.label,
            "agent_instructions": self.agent_instructions.label,
            "skills": self.skills.label,
            "mcp": self.mcp.label,
            "environment": self.environment.label,
        }

    @property
    def label(self) -> str:
        return "_".join(self.dim_labels().values())


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
        labels = variant.dim_labels()
        return all(labels.get(dim) == label for dim, label in pairs.items())

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
        baseline_labels = baseline.dim_labels()
        result = [baseline]
        for v in variants[1:]:
            diffs = sum(1 for d, lbl in v.dim_labels().items() if lbl != baseline_labels[d])
            if diffs == 1:
                result.append(v)
        if sampling.max_variants > 0:
            return result[: sampling.max_variants]
        return result

    return variants


DIMENSIONS = ("model", "agent_instructions", "skills", "mcp", "environment")


def apply_filter(variants: list[Variant], filter_expr: str) -> list[Variant]:
    from calibra.config import ConfigError

    pairs = {}
    for part in filter_expr.split(","):
        key, _, value = part.strip().partition("=")
        pairs[key.strip()] = value.strip()

    unknown = set(pairs.keys()) - set(DIMENSIONS)
    if unknown:
        raise ConfigError(
            f"Unknown filter dimension(s): {', '.join(sorted(unknown))}. "
            f"Valid dimensions: {', '.join(sorted(DIMENSIONS))}"
        )

    result = []
    for v in variants:
        labels = v.dim_labels()
        if all(labels[dim] == label for dim, label in pairs.items()):
            result.append(v)
    return result
