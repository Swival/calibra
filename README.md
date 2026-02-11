# Calibra

A benchmarking harness for coding agents. Built for [Swival](https://github.com/swival/swival).

Calibra runs structured experiments to evaluate coding agents across models,
instructions, skills, MCP servers, and environments. You define a matrix of
configurations and a set of coding tasks, and Calibra runs every combination,
classifies failures, retries transient errors, tracks your budget, and produces
statistical reports. It's designed to give you reproducible, comparable results
without manual bookkeeping.

## Quickstart

Install:

```sh
uv sync
```

Create a task:

```sh
mkdir -p tasks/hello-world/env

cat > tasks/hello-world/task.md << 'EOF'
Write a Python script called `hello.py` that prints "Hello, World!" to stdout.
EOF

cat > tasks/hello-world/verify.sh << 'EOF'
#!/bin/sh
python3 hello.py | grep -qx "Hello, World!"
EOF
chmod +x tasks/hello-world/verify.sh
```

Write a campaign config (`experiments/first.toml`):

```toml
[campaign]
name = "first"
tasks_dir = "tasks"
repeat = 3
timeout_s = 120

[session]
allowed_commands = ["python", "uv"]

[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"

[[matrix.agent_instructions]]
label = "default"
agents_md = "AGENTS.md"
```

Validate, then run:

```sh
uv run calibra validate experiments/first.toml
uv run calibra run experiments/first.toml --workers 2
```

Analyze results:

```sh
uv run calibra analyze results/first
uv run calibra web serve results/ --open
```

## How it works

You give Calibra a TOML config that defines a **matrix** of five dimensions:
which models to test, which agent instructions to use, which skills and MCP
servers to enable, and which environment overlays to apply. Calibra takes the
Cartesian product, runs each combination against each task (optionally multiple
times), and writes structured JSON reports.

Each trial gets an isolated temp workspace with the task's starter files, any
environment overlay, and the agent instructions. Calibra computes a
deterministic seed per trial so results are reproducible. Failures are
classified (infra, provider, tool, timeout, task) and retried according to
per-class limits. A budget tracker can cancel remaining trials when token or
cost limits are hit.

After running, `calibra analyze` aggregates metrics per variant with means,
medians, confidence intervals, rankings, and a Pareto front. `calibra compare`
does side-by-side campaign comparisons with effect sizes.

## What it does

**Matrix-driven experiments.** Define five dimensions (model, agent
instructions, skills, MCP, environment) and Calibra tests every combination.
Constraints exclude known-bad combos, and sampling modes (full, random,
ablation) manage scale.

**Session options.** Pass Swival `Session` parameters like `temperature`,
`allowed_commands`, `extra_body`, and `api_key` at the campaign level or
per-model. Per-model values deep-merge on top of campaign defaults, so nested
dicts like `extra_body` combine rather than replace.

**Failure classification and retry.** Five failure classes (infra, provider,
tool, timeout, task) with independent retry limits and exponential backoff.
Provider rate limits get retried automatically; wrong answers don't.

**Budget tracking.** Set token or dollar limits. When a limit is hit, in-flight
trials finish but no new ones start. Resume later with `--resume`.

**Verification.** Each task can include a `verify.sh` script that checks the
agent's output. Exit code 0 means pass.

**Statistical analysis.** Per-variant aggregation with mean, median, standard
deviation, p90, 95% confidence intervals. Variant ranking, Pareto front
(pass rate vs. token cost), and instability detection.

**Campaign comparison.** Compare two runs with `calibra compare`. Computes pass
rate deltas and Cliff's delta effect sizes across common variants.

**Web dashboard.** An interactive FastAPI + HTMX dashboard for browsing
campaigns, drilling into variants and trials, viewing heatmaps, and comparing
runs. Also exports to static HTML.

## Commands

```sh
calibra validate <config>                    # check config without running
calibra run <config> [--workers N] [--resume] [--filter EXPR] [--dry-run]
calibra analyze <results_dir>                # aggregate metrics
calibra show <report.json>                   # inspect one trial
calibra compare <dir_a> <dir_b>              # side-by-side comparison
calibra web serve <results_dir> [--open]     # interactive dashboard
calibra web build <results_dir>              # static HTML export
```

## Documentation

- [Quick Start](docs/quickstart.md) -- first campaign in a few minutes
- [Writing Tasks](docs/tasks.md) -- prompts, starter files, verification
  scripts
- [Campaign Configuration](docs/configuration.md) -- full TOML reference for
  all sections and dimensions
- [Running Campaigns](docs/running.md) -- parallel execution, filtering,
  resumption
- [Analyzing Results](docs/analysis.md) -- metrics, rankings, reports
- [Web Dashboard](docs/web-dashboard.md) -- interactive browsing and static
  export
- [Advanced Topics](docs/advanced.md) -- constraints, sampling, budgets,
  retries, comparisons, seed determinism
- [CLI Reference](docs/cli-reference.md) -- every command and flag
