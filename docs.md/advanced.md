# Advanced Topics

## Constraints

Constraints let you exclude specific variant combinations from the matrix. This is useful when certain combinations don't make sense, for example a small model paired with an expensive skill set.

### How constraints work

Each constraint has two parts: `when` (conditions that must all match) and `exclude` (additional conditions that, combined with `when`, trigger exclusion). A variant is excluded only if it matches both. Think of it as: "when this is true, also exclude variants where that is true."

```toml
[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }
```

This removes variants where model is "haiku" AND skills is "full". Haiku with other skill levels is kept, and other models with full skills are kept.

### Multiple conditions

Both `when` and `exclude` support multiple conditions using AND logic:

```toml
[[constraints]]
when = { model = "haiku", environment = "production" }
exclude = { skills = "full", mcp = "heavy" }
```

This only excludes variants matching all four conditions simultaneously.

### Stacking constraints

Multiple constraint blocks are independent: a variant is excluded if it matches any single constraint:

```toml
# Don't run haiku with full skills
[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }

# Don't run any model without MCP in production
[[constraints]]
when = { environment = "production" }
exclude = { mcp = "none" }
```

### Verifying constraints

Use `--dry-run` to see which variants survive constraint filtering:

```bash
uv run calibra run experiments/config.toml --dry-run
```

## Sampling modes

When a full matrix has too many variants, sampling reduces the set without manually picking.

### Full mode (default)

Runs every variant. If `max_variants` is set, it caps the list at the first N in Cartesian product order (determined by the order of entries in the config):

```toml
[sampling]
mode = "full"
max_variants = 50  # 0 = unlimited
```

### Random mode

Randomly samples from the full variant list using a seeded RNG, so the selection is deterministic. The seed comes from the campaign's `seed` field, meaning the same config always selects the same subset:

```toml
[sampling]
mode = "random"
max_variants = 20
```

### Ablation mode

Tests one dimension at a time. It starts with a baseline (the first variant in Cartesian product order), then includes only variants that differ from the baseline in exactly one dimension:

```toml
[sampling]
mode = "ablation"
```

This is useful for isolating the effect of each dimension.

If your baseline is `sonnet_default_none_none_base`, ablation includes `haiku_default_none_none_base` (model differs), `codex_default_none_none_base` (model differs), `sonnet_detailed_none_none_base` (instructions differ), `sonnet_default_full_none_base` (skills differ), and so on. But it would not include `haiku_detailed_none_none_base`, because two dimensions differ from the baseline.

## Budget management

For expensive campaigns, budget limits prevent runaway costs.

### Token budget

Cancel the campaign after consuming a total number of tokens:

```toml
[budget]
max_total_tokens = 5000000  # 5M tokens
```

### Cost budget

Cancel after reaching a dollar amount (requires price data):

```toml
[budget]
max_cost_usd = 50.0
require_price_coverage = true
```

### Price configuration

Create a `prices.toml` file in the same directory as your campaign config:

```toml
[prices]
"anthropic/claude-sonnet-4.6" = 3.0
"anthropic/claude-haiku-4.5" = 0.25
"openrouter/openai/gpt-5.3-codex" = 1.25
```

Keys are `"provider/model"` strings matching your matrix model entries. Values are cost per 1,000 estimated prompt tokens. When `require_price_coverage = true`, validation fails if any model in the matrix is missing from prices.toml.

### What happens when budget is exceeded

When a limit is hit, the current trial finishes, all pending trials in the thread pool are cancelled, and the budget tracker records which limit was hit and how much was used. Already-completed trial results are preserved. You can resume after adjusting the budget:

```bash
uv run calibra run experiments/config.toml --resume
```

## Failure classification

When a trial fails, Calibra classifies the failure to determine whether to retry and how long to wait. Classifications are checked in priority order:

| Priority | Class      | Trigger                                        | Typical cause                             |
| -------- | ---------- | ---------------------------------------------- | ----------------------------------------- |
| 1        | `timeout`  | Wall-clock timeout exceeded                    | Task too hard, model stuck in a loop      |
| 2        | `infra`    | OSError, PermissionError                       | Disk full, network down, file permissions |
| 3        | `provider` | Rate limit, 429, 502, 503, auth errors         | API overloaded, bad credentials           |
| 4        | `tool`     | Tools failed, error outcome with tool failures | Broken tool, missing dependency           |
| 5        | `task`     | Wrong answer, exhausted turns                  | Agent gave incorrect solution             |

The first matching class wins. If nothing matches, the trial is considered successful.

### CLI mode failure classification

When a reviewer is configured, trials run via the `swival` CLI subprocess. Failure classification in this mode works differently: if the subprocess times out, it's classified as `timeout`. If exit code is 0, report-based classification is used (same as Session mode).

For non-zero exit codes with a report, the report drives classification first - this preserves tool-failure detection from `tool_calls_failed > 0`. However, if the report says `task` but stderr contains provider patterns (rate limit, 429, etc.), the stderr signal overrides to `provider`. When no report is available, stderr pattern matching is the sole classification input.

When `--quiet` is passed (the default unless verbose mode is active), stderr may be empty in some failure cases, resulting in a `task` classification as a fallback.

### Retry behavior

Each failure class has its own retry count:

```toml
[retry]
infra = 2      # retry infra errors twice
provider = 3   # retry provider errors three times
tool = 1       # retry tool errors once
timeout = 0    # don't retry timeouts
task = 0       # don't retry wrong answers
```

Between retries, Calibra waits using exponential backoff: `min(backoff_base_s × 2^(attempt-1), backoff_max_s)`. With the defaults (base=1.0, max=60.0), that's 1s after the first failure, 2s after the second, 4s after the third, 8s after the fourth, and so on up to 60s.

### When to retry what

Provider errors are almost always worth retrying; rate limits and server errors are transient. Infrastructure errors are usually worth retrying too, since network hiccups and temporary disk issues tend to resolve themselves. Tool errors are sometimes worth retrying if the tool was temporarily unavailable.

Timeouts are rarely worth retrying, because if the model can't finish in time, retrying usually gives the same result. Task failures (wrong answers) are usually not worth retrying unless you're specifically measuring variance. A wrong answer is a signal, not an error.

## Trial seed determinism

Calibra computes a deterministic seed for each trial using `SHA256("base_seed:task_name:variant_label:repeat_index")`, taking the first 4 bytes as an integer.

This means the same (task, variant, repeat) triple always gets the same seed, changing the base seed changes all trial seeds, adding a new task or variant doesn't affect existing seeds, and results are reproducible given the same seed and model.

## Comparing campaigns

Compare two campaign runs to measure the effect of a change:

```bash
uv run calibra compare results/before results/after
```

### What gets compared

Calibra finds variants present in both campaigns and computes the pass rate delta (`after - before`, where positive means improvement), Cliff's delta on token usage (a non-parametric effect size measure with magnitudes: negligible for |d| < 0.147, small for < 0.33, medium for < 0.474, and large for >= 0.474), and mean token usage in each campaign. Cliff's delta is only computed when both campaigns have the same number of trials per variant and more than one trial.

### Use cases

Comparison is useful for model upgrades (run the same tasks with a new model version and compare pass rates), instruction tuning (test different AGENTS.md files and see which improves results), skill evaluation (add a skill set and measure its impact), and regression testing (re-run after changing the agent framework to verify no regressions).

### Comparison output

The comparison writes a `comparison.md` Markdown file to the output directory (defaults to the parent of `dir_a`):

```markdown
# Campaign Comparison

A: before
B: after

| Variant                       | Pass A | Pass B | Delta  | Effect        | Tokens A | Tokens B |
| ----------------------------- | ------ | ------ | ------ | ------------- | -------- | -------- |
| sonnet_default_none_none_base | 70.0%  | 85.0%  | +15.0% | 0.42 (medium) | 2100     | 1850     |
```

## Config hashing and reproducibility

Calibra computes a SHA-256 hash of the campaign configuration and embeds it in every trial report. This serves two purposes. First, when using `--resume`, only trials with matching config hashes are considered complete, so any config change invalidates previous results. Second, it provides an audit trail: you can verify that a set of results came from a specific config, even if the TOML file has since been modified.

The hash is computed from the normalized config content (with `name` and `description` excluded), so cosmetic changes (whitespace, comments) and name/description edits don't affect it, but any other semantic change does.

## Working with large matrices

A matrix of 5 models × 3 instructions × 3 skills × 2 MCP × 2 environments gives you 180 variants. With 5 repeats and 10 tasks, that's 9,000 trials. Here are some strategies for managing scale.

Start with ablation mode to identify which dimensions actually matter:

```toml
[sampling]
mode = "ablation"
```

Use constraints to eliminate known-bad combinations:

```toml
[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }
```

Run subsets to iterate quickly using `--filter`:

```bash
# Test one model first
uv run calibra run config.toml --filter "model=sonnet" --workers 4

# Then add another
uv run calibra run config.toml --filter "model=haiku" --resume
```

Put a safety net on cost:

```toml
[budget]
max_cost_usd = 200.0
```

Scale up concurrency to reduce wall time:

```bash
uv run calibra run config.toml --workers 8
```

And always use `--resume` after the first run so completed trials aren't re-executed:

```bash
uv run calibra run config.toml --resume --workers 4
```
