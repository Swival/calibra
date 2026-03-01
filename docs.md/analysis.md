# Analyzing Results

After a campaign finishes, Calibra can aggregate trial data into statistical summaries, rankings, and reports.

## Running analysis

```bash
uv run calibra analyze results/model-shootout
```

This reads all trial JSON files in the campaign directory and produces three output files: `summary.json` (machine-readable aggregate data), `summary.md` (a human-readable report with tables), and `summary.csv` (spreadsheet format).

You can write outputs to a different directory:

```bash
uv run calibra analyze results/model-shootout --output reports/
```

## Inspecting a single trial

Before looking at aggregates, you might want to examine individual trials:

```bash
uv run calibra show results/model-shootout/hello-world/sonnet_minimal_none_none_base_0.json
```

This prints a formatted table using Rich:

```
┌────────────────────────────────────┐
│ Task:     hello-world              │
│ Variant:  sonnet_minimal_none_none │
│ Outcome:  success                  │
│ Verified: true                     │
│ Time:     12.3s                    │
├──────────────┬─────────────────────┤
│ Turns        │ 3                   │
│ LLM Calls    │ 3                   │
│ Tool Calls   │ 2 (0 failed)        │
│ LLM Time     │ 8.1s                │
│ Tool Time    │ 2.4s                │
│ Compactions  │ 0                   │
├──────────────┴─────────────────────┤
│ Tool Usage                         │
│   write_file: 1 ok, 0 fail         │
│   run_command: 1 ok, 0 fail        │
└────────────────────────────────────┘
```

## Metrics collected

Calibra extracts these metrics from each trial report:

| Metric                    | Description                                                                            |
| ------------------------- | -------------------------------------------------------------------------------------- |
| `outcome`                 | Agent result: `"success"`, `"error"`, `"exhausted"`                                    |
| `verified`                | Whether verification passed (true/false/null). Set by `verify.sh` or reviewer verdict. |
| `turns`                   | Number of conversation turns                                                           |
| `tool_calls_total`        | Total tool invocations                                                                 |
| `tool_calls_failed`       | Tool invocations that returned errors                                                  |
| `llm_time_s`              | Time spent in LLM API calls                                                            |
| `tool_time_s`             | Time spent executing tools                                                             |
| `wall_time_s`             | Total wall-clock time                                                                  |
| `compactions`             | Number of context compactions (long conversations)                                     |
| `prompt_tokens_est`       | Estimated total prompt tokens                                                          |
| `failure_class`           | `"infra"`, `"provider"`, `"tool"`, `"timeout"`, `"task"`, or null                      |
| `tool_usage`              | Per-tool breakdown of succeeded/failed calls                                           |
| `skills_used`             | List of skills invoked during the trial                                                |
| `guardrail_interventions` | Number of guardrail interventions                                                      |
| `review_rounds`           | Number of reviewer retry rounds (0 when no reviewer configured)                        |

## Per-variant aggregation

Calibra groups trials by variant label and computes several statistics.

### Pass rate

The pass rate is simply the fraction of trials where `verified` is true:

```
pass_rate = count(verified == true) / total_trials
```

Rounded to 4 decimal places.

### Statistical summaries

For each numeric metric (turns, tool_calls_total, tool_calls_failed, llm_time_s, tool_time_s, wall_time_s, compactions, prompt_tokens_est, and conditionally review_rounds), Calibra computes the mean, median, standard deviation, min, max, 90th percentile, and the lower and upper bounds of a 95% confidence interval. All values are rounded to 3 decimal places. The `review_rounds` stat summary is only included when at least one trial in the variant has review_rounds > 0.

The 95% confidence interval uses the formula `mean ± 1.96 × (std / sqrt(n))`.

### Derived metrics

Two efficiency metrics are computed from the aggregates. **score_per_1k_tokens** is `pass_rate × 1000 / tokens.mean`, which tells you how many tasks you solve per 1,000 tokens spent. **pass_rate_per_minute** is `pass_rate × 60 / wall_time.mean`, which tells you how many tasks you solve per minute of wall time.

### Outcome counts

A breakdown of how many trials ended in each outcome state:

```json
"outcome_counts": {
  "success": 8,
  "error": 1,
  "exhausted": 1
}
```

## Rankings

Variants are ranked by pass rate first (higher is better), then by tokens (fewer is better), then by turns (fewer is better), and finally by LLM time (less is better). The ranking tells you which variant configuration is most effective overall.

## Pareto front

The Pareto front identifies variants that are not dominated by any other variant on two dimensions: pass rate (higher is better) and token usage (lower is better). A variant is on the Pareto front if no other variant has both a higher pass rate and lower token usage. These are the "efficient" configurations: you can't improve one metric without sacrificing the other.

## Instability warnings

Calibra flags variants with high variance that may need more repeats. A variant gets a warning if its coefficient of variation (std/mean) exceeds 0.5 on turns, LLM time, or token usage, which indicates inconsistent behavior. Variants with fewer than 3 trials also get a warning since the data is insufficient for reliable statistics. These warnings appear in the Markdown report and suggest increasing `repeat` in your config.

## Weighted pass rate

When computing an overall campaign pass rate across variants with different trial counts, Calibra uses a weighted average:

```
weighted_pass_rate = sum(variant_pass_rate × variant_n_trials) / sum(variant_n_trials)
```

This prevents a variant with 2 trials from having the same influence as one with 20.

## Report formats

### summary.json

The full machine-readable output:

```json
{
  "variants": [
    {
      "variant_label": "sonnet_minimal_none_none_base",
      "n_trials": 15,
      "pass_rate": 0.8667,
      "outcome_counts": {"success": 13, "error": 1, "exhausted": 1},
      "turns": {"mean": 4.2, "median": 4.0, "std": 1.1, ...},
      "tool_calls_total": {"mean": 3.8, ...},
      "wall_time_s": {"mean": 14.5, ...},
      "prompt_tokens_est": {"mean": 2100.0, ...},
      "review_rounds": {"mean": 1.5, "median": 1.0, "std": 0.8, "...": "..."},
      "score_per_1k_tokens": 0.413,
      "pass_rate_per_minute": 3.585
    }
  ],
  "trials": [
    {
      "task": "hello-world",
      "variant_label": "sonnet_minimal_none_none_base",
      "repeat": 0,
      "outcome": "success",
      "verified": true,
      "turns": 3,
      "wall_time_s": 12.3,
      ...
    }
  ]
}
```

### summary.md

A Markdown report with variant rankings (sorted by rank), Pareto-efficient variants highlighted, instability warnings, and per-task pass rates.

### summary.csv

A flat table with one row per variant and columns for key metrics, suitable for importing into spreadsheets or data tools. When any variant has reviewer data, a `review_rounds_mean` column is included.

## Comparing campaigns

To compare two campaign runs (for example, before and after a change):

```bash
uv run calibra compare results/run-a results/run-b
```

This finds variants common to both campaigns and computes the pass rate delta (run_b minus run_a), Cliff's delta effect size with magnitude classification (negligible, small, medium, large), and a token usage comparison. See [Advanced Topics](advanced.md#comparing-campaigns) for details.
