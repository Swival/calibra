"""Tests for matrix.py: expansion, constraints, sampling."""

from calibra.config import (
    AgentInstructionsVariant,
    Campaign,
    BudgetConfig,
    EnvironmentVariant,
    McpVariant,
    ModelVariant,
    RetryConfig,
    SamplingConfig,
    SkillsVariant,
)
from calibra.matrix import (
    apply_constraints,
    apply_filter,
    apply_screening,
    expand_matrix,
)


def _campaign(
    models=2,
    agents=1,
    skills=1,
    mcps=1,
    envs=1,
    sampling_mode="full",
    max_variants=0,
    seed=42,
    constraints=None,
):
    return Campaign(
        name="test",
        description="",
        repeat=1,
        max_turns=10,
        timeout_s=60,
        seed=seed,
        tasks_dir="/tmp/tasks",
        budget=BudgetConfig(),
        retry=RetryConfig(),
        sampling=SamplingConfig(mode=sampling_mode, max_variants=max_variants),
        models=[ModelVariant(provider="p", model=f"m{i}", label=f"m{i}") for i in range(models)],
        agent_instructions=[
            AgentInstructionsVariant(label=f"a{i}", agents_md=f"/a{i}.md") for i in range(agents)
        ],
        skills=[SkillsVariant(label=f"s{i}", skills_dirs=[]) for i in range(skills)],
        mcp=[McpVariant(label=f"mcp{i}", config="") for i in range(mcps)],
        environments=[EnvironmentVariant(label=f"e{i}", overlay="") for i in range(envs)],
        constraints=constraints or [],
    )


def test_2x2():
    c = _campaign(models=2, agents=2)
    variants = expand_matrix(c)
    assert len(variants) == 4


def test_3x2x2():
    c = _campaign(models=3, agents=2, skills=2)
    variants = expand_matrix(c)
    assert len(variants) == 12


def test_variant_label():
    c = _campaign(models=1, agents=1)
    variants = expand_matrix(c)
    assert variants[0].label == "m0_a0_s0_mcp0_e0"


def test_constraint_prunes():
    c = _campaign(
        models=2,
        agents=2,
        constraints=[
            {"when": {"model": "m0"}, "exclude": {"agent_instructions": "a1"}},
        ],
    )
    variants = expand_matrix(c)
    filtered = apply_constraints(variants, c.constraints)
    assert len(filtered) == 3  # 4 - 1 pruned


def test_constraint_no_match():
    c = _campaign(
        models=2,
        agents=1,
        constraints=[
            {"when": {"model": "m0"}, "exclude": {"model": "m1"}},
        ],
    )
    variants = expand_matrix(c)
    filtered = apply_constraints(variants, c.constraints)
    assert len(filtered) == 2  # nothing pruned (when and exclude don't match same variant)


def test_random_deterministic():
    c = _campaign(models=4, sampling_mode="random", max_variants=2, seed=42)
    v1 = apply_screening(expand_matrix(c), c.sampling, c.seed)
    v2 = apply_screening(expand_matrix(c), c.sampling, c.seed)
    assert [v.label for v in v1] == [v.label for v in v2]
    assert len(v1) == 2


def test_ablation_count():
    c = _campaign(models=3, agents=2, skills=2, sampling_mode="ablation")
    variants = expand_matrix(c)
    ablated = apply_screening(variants, c.sampling, c.seed)
    # baseline + (3-1) + (2-1) + (2-1) + 0 + 0 = 1 + 2 + 1 + 1 = 5
    assert len(ablated) == 5


def test_full_max_variants():
    c = _campaign(models=4, sampling_mode="full", max_variants=2)
    variants = expand_matrix(c)
    screened = apply_screening(variants, c.sampling, c.seed)
    assert len(screened) == 2


def test_filter():
    c = _campaign(models=3, agents=2)
    variants = expand_matrix(c)
    filtered = apply_filter(variants, "model=m1")
    assert len(filtered) == 2
    assert all(v.model.label == "m1" for v in filtered)


def test_filter_multiple():
    c = _campaign(models=3, agents=2)
    variants = expand_matrix(c)
    filtered = apply_filter(variants, "model=m1,agent_instructions=a0")
    assert len(filtered) == 1
    assert filtered[0].model.label == "m1"
    assert filtered[0].agent_instructions.label == "a0"
