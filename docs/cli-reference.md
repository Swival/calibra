# CLI Reference

```
calibra <command> [options]
```

## calibra validate

Validate a campaign configuration file without running anything.

```
calibra validate <config>
```

The `config` argument is a path to a campaign TOML file.

Validation checks TOML syntax and required fields, task directory structure (that task.md exists, env/ is a directory, verify.sh is executable), uniqueness of matrix dimension labels, validity of constraint references, session option keys and types (rejecting harness-managed keys, unknown keys, and type mismatches), and price coverage if `require_price_coverage = true`.

```bash
uv run calibra validate experiments/model-shootout.toml
```

Output on success:

```
Config valid. 10 variants x 5 tasks x 5 repeats = 250 trials.
```

---

## calibra run

Execute a campaign.

```
calibra run <config> [--workers N] [--dry-run] [--filter EXPR] [--resume] [--output DIR] [--keep-workdirs]
```

The `config` argument is a path to a campaign TOML file.

| Option            | Default   | Description                                          |
| ----------------- | --------- | ---------------------------------------------------- |
| `--workers N`     | `1`       | Number of parallel worker threads                    |
| `--dry-run`       | off       | Print trial plan without executing                   |
| `--filter EXPR`   | none      | Filter variants (e.g., `"model=sonnet,skills=full"`) |
| `--resume`        | off       | Skip trials with existing valid results              |
| `--output DIR`    | `results` | Output directory for trial reports                   |
| `--keep-workdirs` | off       | Preserve temporary workspace directories             |

```bash
# Basic run
uv run calibra run experiments/config.toml

# Parallel with filtering
uv run calibra run experiments/config.toml --workers 4 --filter "model=sonnet"

# Resume an interrupted run
uv run calibra run experiments/config.toml --resume --workers 4

# Dry run to preview
uv run calibra run experiments/config.toml --dry-run

# Debug a failing trial
uv run calibra run experiments/config.toml --keep-workdirs --filter "model=haiku"
```

---

## calibra analyze

Aggregate trial results into statistical summaries.

```
calibra analyze <results_dir> [--output DIR]
```

The `results_dir` argument is a path to a campaign's results directory.

| Option         | Default               | Description                  |
| -------------- | --------------------- | ---------------------------- |
| `--output DIR` | same as `results_dir` | Where to write summary files |

Produces three files: `summary.json` (full machine-readable aggregate data), `summary.md` (human-readable Markdown report), and `summary.csv` (spreadsheet format).

```bash
uv run calibra analyze results/model-shootout
uv run calibra analyze results/model-shootout --output reports/
```

---

## calibra show

Pretty-print a single trial report.

```
calibra show <report.json>
```

The argument is a path to a trial JSON file. Output includes the task name, variant label, outcome, verification status, wall time, turns, LLM calls, tool calls (succeeded/failed), LLM time, tool time, compactions, and a tool usage breakdown.

```bash
uv run calibra show results/model-shootout/hello-world/sonnet_default_none_none_base_0.json
```

---

## calibra compare

Compare two campaign result directories.

```
calibra compare <dir_a> <dir_b> [--output DIR]
```

| Option         | Default           | Description                      |
| -------------- | ----------------- | -------------------------------- |
| `--output DIR` | parent of `dir_a` | Where to write comparison output |

Finds variants common to both campaigns and computes the pass rate delta (B minus A), Cliff's delta effect size and magnitude, and a token usage comparison.

```bash
uv run calibra compare results/run-v1 results/run-v2
```

---

## calibra web serve

Launch the interactive web dashboard. Requires the `[web]` optional dependencies (`uv sync --extra web`).

```
calibra web serve <results_dir> [--port N] [--host ADDR] [--open]
```

The `results_dir` argument is the directory containing campaign result folders.

| Option        | Default     | Description                |
| ------------- | ----------- | -------------------------- |
| `--port N`    | `8118`      | Port to bind               |
| `--host ADDR` | `127.0.0.1` | Host address to bind       |
| `--open`      | off         | Open browser automatically |

```bash
uv run calibra web serve results/ --open
uv run calibra web serve results/ --host 0.0.0.0 --port 9000
```

---

## calibra web build

Export a static HTML dashboard. Requires the `[web]` optional dependencies.

```
calibra web build <results_dir> [--output DIR]
```

| Option         | Default | Description                      |
| -------------- | ------- | -------------------------------- |
| `--output DIR` | `dist/` | Output directory for static HTML |

```bash
uv run calibra web build results/ --output docs/dashboard/
```

---

## Exit codes

Calibra exits with 0 on success and 1 on error, whether that's a configuration problem (invalid TOML, missing files, bad constraints) or a runtime failure (all trials failed, budget exceeded).

## Environment variables

Calibra inherits environment variables for provider authentication. The specific variables depend on which providers you use in your matrix. For example, `ANTHROPIC_API_KEY` for Anthropic models.
