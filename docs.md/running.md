# Running Campaigns

## Validation

Always validate before running. This catches config errors, missing files, and dimension mismatches without burning any API tokens:

```bash
uv run calibra validate experiments/model-shootout.toml
```

Validation checks TOML syntax and required fields, task directory structure (that `task.md` exists, `env/` is a directory, and `verify.sh` is executable), that matrix dimension labels are unique within each dimension, that constraint references point to existing labels, and price coverage if `require_price_coverage = true`.

On success you'll see something like:

```
Config valid. 10 variants x 5 tasks x 5 repeats = 250 trials.
```

## Dry run

To see the full trial plan without executing anything:

```bash
uv run calibra run experiments/model-shootout.toml --dry-run
```

This expands the matrix, applies constraints and sampling, then prints every variant label along with summary counts (tasks, repeats, total trials). It's useful for verifying that filters and constraints produce the expected set of variants.

## Running a campaign

Basic execution:

```bash
uv run calibra run experiments/model-shootout.toml
```

### Parallel workers

By default, Calibra runs one trial at a time. Use `--workers` to run trials in parallel:

```bash
uv run calibra run experiments/model-shootout.toml --workers 4
```

Calibra uses a `ThreadPoolExecutor`, so workers share the same process. Provider rate limits tend to be the main bottleneck. Start with 2-4 workers and increase if your provider allows higher concurrency.

### Output directory

Results go to `results/` by default. Override with `--output`:

```bash
uv run calibra run experiments/model-shootout.toml --output my-results
```

The output structure looks like:

```
results/
  model-shootout/
    hello-world/
      sonnet_minimal_none_none_base_0.json
      sonnet_minimal_none_none_base_1.json
      ...
    fix-typo/
      sonnet_minimal_none_none_base_0.json
      ...
```

Files are named `{variant_label}_{repeat_index}.json`.

### Keeping work directories

Normally, the temporary workspace for each trial is deleted after execution. To preserve them for debugging:

```bash
uv run calibra run experiments/model-shootout.toml --keep-workdirs
```

This lets you inspect exactly what the agent saw and produced.

## Filtering variants

The `--filter` flag lets you run a subset of variants without modifying the config:

```bash
# Only run the sonnet model
uv run calibra run experiments/model-shootout.toml --filter "model=sonnet"

# Only run sonnet with detailed instructions
uv run calibra run experiments/model-shootout.toml --filter "model=sonnet,agent_instructions=detailed"

# Only run variants with full skills
uv run calibra run experiments/model-shootout.toml --filter "skills=full"
```

The syntax is comma-separated `dimension=label` pairs, and all conditions must match (AND logic). Valid dimension names are `model`, `agent_instructions`, `skills`, `mcp`, and `environment`. Filtering is applied after constraints and sampling, so it further reduces an already-processed set of variants.

## Resuming campaigns

Long campaigns may be interrupted by network issues, budget limits, or manual cancellation. The `--resume` flag skips trials that already have valid results:

```bash
uv run calibra run experiments/model-shootout.toml --resume
```

A trial is considered complete only if all identity fields in the existing JSON match the current run: `config_hash`, `task`, `variant`, and `repeat`. If you change the config (even slightly), the config hash changes and all trials re-run. This prevents stale results from mixing with new ones.

## Workspace setup

For each trial, Calibra sets up an isolated workspace in a specific order. First, it creates a temp directory with prefix `calibra_{task_name}_`. Then it copies the `env/` files from the task directory. Next, it applies the environment overlay (if the variant has one), overwriting any conflicting files. Finally, it copies `AGENTS.md` from the agent instructions path. 
This ordering matters: the overlay can override env files, and `AGENTS.md` is always the last file placed.

## Trial execution flow

For each trial, Calibra sets up the workspace as described above, then computes a deterministic trial seed from `SHA256(seed:task:variant:repeat)`.

### Session mode (default)

When no `[reviewer]` is configured, Calibra creates a Swival session with the variant's model, skills, and MCP config, plus any [session options](configuration.md#session-options) (campaign defaults deep-merged with per-model overrides). When `allowed_commands` is set without explicitly setting `yolo`, it defaults to `false` so the allowlist takes effect.

Calibra runs the agent within the `max_turns` and `timeout_s` limits, then runs `verify.sh` in the workspace if it exists (with a 30-second timeout). Any failures are classified, and the trial is retried if the failure class allows it (see [retry config](configuration.md#retry-section)). Finally, the JSON report is written.

### Reviewer mode

When a `[reviewer]` is configured, Calibra runs the `swival` CLI as a subprocess instead of using the Session API. This is necessary because the reviewer feature is CLI-only in Swival, and `Session.ask()` returns `report=None` so retry round data would be invisible to metrics and budget tracking.

The CLI invocation includes `--report` (to get the full JSON report with timeline events), `--reviewer` (the reviewer command), `--max-review-rounds`, `--no-history`, and all session options mapped to their CLI flag equivalents. `--quiet` is included unless `calibra run` was invoked with `--verbose`. Swival handles the full reviewer loop internally - initial run plus up to `max_rounds` retry rounds.

To prevent user or project config from leaking into trials, Calibra sets `XDG_CONFIG_HOME` to an empty temp directory (preventing `~/.config/swival/config.toml` from loading), deletes any `swival.toml` that may have been copied from the task's `env/` or overlay, and passes `--no-mcp` unless the variant has explicit MCP config.

After the subprocess completes, Calibra reads the report JSON, determines `verified` from the last review event in the timeline (exit 0 = true, exit 1 = false, exit 2+ = null), and classifies failures using the report data first with a stderr fallback. `verify.sh` is skipped in reviewer mode.

## Monitoring progress

Calibra prints progress to stdout as trials complete. By default, a compact format is used:

```
  [PASS] hello-world / sonnet_minimal_none_none_base #0
  [PASS] hello-world / sonnet_minimal_none_none_base #1
  [TASK] hello-world / sonnet_minimal_none_none_base #2
```

The status label reflects the failure class (e.g., `PASS`, `TASK`, `PROVIDER`, `TIMEOUT`).

With `-v`/`--verbose`, each line includes a progress counter, timing, and per-trial stats:

```
  [1/250] [PASS] hello-world / sonnet_minimal_none_none_base #0  (12.3s | 3 turns | 2 tools | 2.1k tok)  [1P/0F]
  [2/250] [PASS] hello-world / sonnet_minimal_none_none_base #1  (11.8s | 3 turns | 2 tools | 1.9k tok)  [2P/0F]
  [3/250] [TASK] hello-world / sonnet_minimal_none_none_base #2  (15.1s | 5 turns | 4 tools | 3.2k tok)  [2P/1F]
```

Verbose mode also prints a per-event timeline (LLM calls, tool calls, compactions) below each trial.

## Combining flags

Flags can be combined freely:

```bash
uv run calibra run experiments/model-shootout.toml \
  --workers 4 \
  --filter "model=sonnet" \
  --resume \
  --keep-workdirs \
  --output results-v2
```
