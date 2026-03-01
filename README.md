<p align="center">
  <img src=".media/logo.png" alt="Calibra" width="280">
</p>

<h3 align="center">Stop guessing which models and settings are best. Measure them.</h3>

<p align="center">
Free, open-source benchmarking for coding agents.<br>
Test models, prompts, skills, and MCP servers - side by side, at scale.
</p>

---

Calibra is a benchmarking harness that tells you *exactly* how your coding agent performs across models, instructions, skills, MCP servers, and environments. Define a matrix, run it, and get hard numbers - pass rates, token costs, timing, failure breakdowns, and statistical rankings - all in an interactive web dashboard you can share with your team.

It works with any provider: OpenAI, HuggingFace, or your own self-hosted models via LM Studio, Ollama, or any OpenAI-compatible endpoint. Run thousands of evaluations against local models for free.

Built for [Swival](https://github.com/swival/swival).

## Why Calibra

**You're flying blind without it.** Switching models? Adding an MCP server? Changing your agent's system prompt? You need to know if that actually made things better. Calibra gives you a controlled experiment instead of a gut feeling.

- **Five-dimensional testing** - vary model, agent instructions, skills, MCP servers, and environment overlays in any combination. Calibra runs the full matrix automatically.
- **Statistically rigorous** - repeat trials, confidence intervals, Pareto fronts, effect sizes. Not just "it seemed faster."
- **Works with open models** - bring your own LM Studio, Ollama, or any OpenAI-compatible endpoint. Run thousands of evals for zero API cost.
- **Your data stays yours** - runs entirely on your machine. No results, prompts, or code are sent to third-party eval platforms.
- **Completely free and open source** - no license keys, no usage limits, no telemetry.

## The Web Dashboard

Calibra ships with an interactive dashboard that makes results actually useful.

**Campaign overview** - see pass rates, variant counts, and trial totals at a glance. KPI tiles highlight what matters: median turns, failure rate, token efficiency.

**Variant rankings** - a sortable, filterable table ranked by pass rate, token cost, and speed. Instantly spot which model + skill + MCP combo wins.

**Pass rate charts** - horizontal bar charts color-coded by performance. A scatter plot maps token cost against pass rate, with the Pareto front drawn on top so you can see the efficiency frontier.

**Task heatmap** - a full matrix of tasks vs. variants, colored from red to teal. Click any cell to drill into that specific combination.

**Variant deep dive** - per-task breakdowns with outcome dots, box plots of turn distributions, failure category pie charts (infra / provider / tool / timeout / task), and tool usage bar charts showing success vs. failure rates per tool.

**Trial inspector** - a full chronological timeline of a single trial: every LLM call (with duration and token count), every tool invocation (with arguments and pass/fail), compactions, guardrail interventions, and reviewer feedback. Expand any event to see the raw details.

**Campaign comparison** - pick two runs and see deltas: pass rate changes, Cliff's delta effect sizes, and a bar chart of improvements and regressions across all common variants.

**Dark mode** included. The whole thing exports to **static HTML** - share results without running a server.

## Quick Start

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

Write a campaign config:

```toml
# experiments/first.toml
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

[[matrix.model]]
provider = "lmstudio"
model = "qwen3.5-27b"
label = "qwen3.5-local"
base_url = "http://localhost:1234"

[[matrix.agent_instructions]]
label = "default"
agents_md = "AGENTS.md"
```

Run it:

```sh
uv run calibra run experiments/first.toml --workers 4
uv run calibra analyze results/first
uv run calibra web serve results/ --open
```

## Features

### Matrix-Driven Experiments

Define variants across five dimensions and Calibra tests every combination:

| Dimension              | What it controls                                    |
| ---------------------- | --------------------------------------------------- |
| **model**              | Provider, model name, temperature, token limits     |
| **agent_instructions** | The system prompt / AGENTS.md given to the agent    |
| **skills**             | Tool sets and capabilities available to the agent   |
| **mcp**                | MCP server configurations                           |
| **environment**        | Workspace file overlays (different starting states) |

Add constraints to exclude bad combinations. Use sampling modes (full, random, ablation) to manage scale. Filter at runtime with `--filter "model=sonnet,skills=full"`.

### Failure Classification and Smart Retries

Every failure is classified into one of five categories - infra, provider, tool, timeout, or task - each with independent retry limits and exponential backoff. Rate limits get retried automatically. Wrong answers don't.

### Budget Tracking

Set token or dollar limits. Calibra cancels remaining trials when the budget is exceeded. Resume later with `--resume` and pick up right where you left off. Prices are configured per model in a simple `prices.toml`.

### Statistical Analysis

Per-variant aggregation with mean, median, standard deviation, p90, and 95% confidence intervals. Variant ranking by composite score. Pareto front analysis (pass rate vs. token cost). Instability detection flags unreliable results. Bootstrap CIs and permutation tests for serious comparisons.

### Campaign Comparison

Compare two runs side by side. See pass rate deltas and Cliff's delta effect sizes across every common variant. Find out if that prompt change actually helped.

### Reproducibility

Every trial gets a deterministic seed derived from the campaign seed, task, variant, and repeat index. Same config, same results.

## CLI Reference

```sh
calibra validate <config>              # check config without running
calibra run <config> [--workers N]     # run trials in parallel
                     [--resume]        # skip completed trials
                     [--filter EXPR]   # limit variants at runtime
                     [--dry-run]       # show plan without executing
calibra analyze <results_dir>          # aggregate metrics and write reports
calibra show <report.json>             # inspect a single trial
calibra compare <dir_a> <dir_b>        # side-by-side comparison
calibra web serve <results_dir>        # launch interactive dashboard
calibra web build <results_dir>        # export static HTML
```

## Task Format

```
tasks/my-task/
  task.md       # prompt sent to the agent (required)
  env/          # starter workspace files (required)
  verify.sh     # exit-code pass/fail check (optional)
  meta.toml     # arbitrary metadata (optional)
```

## Documentation

- [Quick Start](docs.md/quickstart.md)
- [Writing Tasks](docs.md/tasks.md)
- [Campaign Configuration](docs.md/configuration.md)
- [Running Campaigns](docs.md/running.md)
- [Analyzing Results](docs.md/analysis.md)
- [Web Dashboard](docs.md/web-dashboard.md)
- [Advanced Topics](docs.md/advanced.md)
- [CLI Reference](docs.md/cli-reference.md)
