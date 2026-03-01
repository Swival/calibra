# Quick Start

This guide walks you through creating a task, writing a campaign config, running it, and viewing the results.

## 1. Create a task

Tasks live in a directory (typically `tasks/`). Each task needs at minimum a prompt file and a workspace directory.

```bash
mkdir -p tasks/hello-world/env
```

Write the prompt:

```bash
cat > tasks/hello-world/task.md << 'EOF'
Write a Python script called `hello.py` that prints "Hello, World!" to stdout.
EOF
```

Add a verification script:

```bash
cat > tasks/hello-world/verify.sh << 'EOF'
#!/bin/sh
python3 hello.py | grep -qx "Hello, World!"
EOF
chmod +x tasks/hello-world/verify.sh
```

The `env/` directory is empty here because the task starts from a blank workspace. For tasks that need starter files, you'd put them in `env/`.

## 2. Write a campaign config

Campaign configs are TOML files. Create `experiments/my-first-campaign.toml`:

```toml
[campaign]
name = "my-first-campaign"
description = "Testing a single model on hello-world"
tasks_dir = "tasks"
repeat = 3
timeout_s = 120

[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"

[[matrix.agent_instructions]]
label = "default"
agents_md = "AGENTS.md"
```

This is the simplest possible campaign: one model, one set of instructions, no skills, no MCP, no environment overlay. The three optional dimensions (skills, mcp, environment) get default values of `none`, `none`, and `base`. Setting `repeat = 3` runs each variant+task combination three times to measure consistency.

## 3. Validate the config

Before running, check that everything is wired up correctly:

```bash
uv run calibra validate experiments/my-first-campaign.toml
```

This checks the config structure, discovers tasks, expands the matrix, and reports the trial plan:

```
Config valid. 1 variants x 1 tasks x 3 repeats = 3 trials.
```

## 4. Dry run

See exactly what would execute without running anything:

```bash
uv run calibra run experiments/my-first-campaign.toml --dry-run
```

This prints each trial that would be executed: task name, variant label, and repeat index.

## 5. Run the campaign

```bash
uv run calibra run experiments/my-first-campaign.toml --workers 2
```

Calibra sets up an isolated workspace for each trial, runs the Swival agent with the configured model, executes `verify.sh` to check the result, and writes a JSON report. Results land in `results/my-first-campaign/hello-world/`.

## 6. Inspect a trial

Look at a single trial result:

```bash
uv run calibra show results/my-first-campaign/hello-world/sonnet_default_none_none_base_0.json
```

This shows a formatted summary with the task name, variant, outcome, verification status, wall time, turns, tool calls, and more. The file naming convention is `{variant_label}_{repeat_index}.json`, where the variant label joins dimension labels with underscores: `model_agent_skills_mcp_environment`.

## 7. Analyze the campaign

Generate aggregate reports:

```bash
uv run calibra analyze results/my-first-campaign
```

This produces three files in `results/my-first-campaign/`: `summary.json` (machine-readable aggregate metrics), `summary.md` (a human-readable Markdown report with rankings), and `summary.csv` (spreadsheet-friendly format).

## 8. View in the web dashboard

For a richer experience, launch the interactive dashboard:

```bash
uv run calibra web serve results/ --open
```

This starts a local server at `http://127.0.0.1:8118` and opens your browser. You'll see your campaign with charts, heatmaps, and drill-down views.

## Next steps

From here, read [Writing Tasks](tasks.md) to learn how to build more complex tasks, [Campaign Configuration](configuration.md) to explore all config options, [Running Campaigns](running.md) for parallelism, filtering, and resuming, or [Advanced Topics](advanced.md) for constraints, sampling modes, and budgets.
