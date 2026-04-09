# Log

## 2026-04-09

**Asked**: Update swival to 0.11.0, watch for breaking changes.

**Did**: Reviewed the 0.10.13→0.11.0 diff. No breaking changes in the Session API — two new optional params added (`trace_dir`, `command_middleware`). New `--oneshot-commands` CLI flag from 0.10.14 was also missing. Updated `pyproject.toml` to `swival>=0.11.0`, added `trace_dir`/`command_middleware` to `_CLI_VALUE_MAP` and `oneshot_commands` to `_CLI_FLAG_MAP` in runner.py. The AGENTS.md ancestor-loading behavior change doesn't affect calibra since workspaces live in `/tmp/`. All 488 tests pass.

## 2026-04-07

**Asked**: Update swival to 0.10.13, watch for breaking API changes.

**Did**: Investigated all changes between 0.10.5 and 0.10.13 via git diff on the swival repo. No breaking changes found — all additive: new `approved_buckets` Session param (with default), new `"ask"` value for `commands`, optional `security` section in reports, `run_command`/`run_shell_command` tool split, `edit_file` gains `line_number` param, pre-flight transcript pruning. Updated `pyproject.toml` from `>=0.10.5` to `>=0.10.13`. All 488 tests pass.

## 2026-03-03 (session 13)

**Asked**: Add `--task` flag to `calibra run`, then update all documentation.

**Did**:
- Added `--task` CLI flag to `calibra run` (repeatable via `action="append"`) that filters tasks by name. Unknown task names print available tasks and exit.
- Added 3 tests in `tests/test_cli.py`: single task filter, multiple tasks, unknown task error.
- Updated docs: `docs.md/cli-reference.md` (synopsis, options table, examples), `docs.md/running.md` (new "Filtering tasks" section, updated "Combining flags" example), `docs.md/advanced.md` (added `--task` to large matrix strategies), `CLAUDE.md` (added example command).

## 2026-03-03 (session 12)

**Asked**: Add blank lines between paragraphs in `docs.md/*.md` files to improve readability.

**Did**: Added paragraph breaks across all 8 documentation files (advanced.md, index.md, tasks.md, running.md, analysis.md, configuration.md, web-dashboard.md, cli-reference.md, quickstart.md) where dense paragraphs covered multiple distinct concepts. ~20 splits total, focusing on places where conceptual shifts within a paragraph hurt scanability (e.g., CLI failure classification scenarios, retry guidance per failure class, workspace setup steps vs. conclusion, session option description vs. merging semantics).

## 2026-03-03 (session 11)

**Asked**: Make sure all documentation is accurate and up to date, including everything in the docs.md directory.

**Did**: Audited all documentation files (docs.md/, README.md, CLAUDE.md, AGENTS.md) against the actual source code. Found and fixed three issues:

- `docs.md/cli-reference.md`: Added missing `--export FILE` option to the `calibra diff` command documentation (the flag existed in code but was undocumented).
- `CLAUDE.md`: Removed reference to non-existent `[web]` optional extras in the install command comment. Web dependencies (FastAPI, uvicorn, Jinja2) are core dependencies; only `[charts]` exists as an optional extra.
- `docs.md/configuration.md`: Fixed minimal config description that incorrectly said agent_instructions was required. It's optional and defaults to `label="default"` with empty `agents_md`. Updated the defaults note to mention all four optional dimensions.
- Rebuilt the `docs/` static site via `build.py` to reflect the updated docs.md content.

Everything else verified as accurate: failure classification priorities, trial seed computation, Cliff's delta thresholds, ranking logic, CLI flags, config validation, web API endpoints, task structure, retry behavior, and session option handling.

## 2026-03-03 (session 10)

**Asked**: Add `--export` flag to `calibra diff` so it can produce a self-contained static HTML file instead of launching a server. Plan was iterated through two review rounds addressing `| safe` for inlined JS/CSS, inert brand link, precise self-contained assertions, and error message parity.

**Did**: Implemented the plan from `plans/diff-export.md`:

- `calibra/web/templates/base.html`: Added `inline_assets` conditional — when true, emits `<script>` / `<style>` tags with `| safe` for Tailwind JS, HTMX JS, and style.css instead of external `src`/`href` references. Made Calibra brand link inert (`href="#"`) when `static_export` is set.
- `calibra/web/templates/diff.html`: Wrapped file-picker in `{% if not static_export %}`. Made "All campaigns" nav link and "Campaigns" breadcrumb conditional on `static_export`.
- `calibra/web/export.py`: Added `load_diff_report(path, label)` shared validation helper preserving existing CLI error message wording. Added `export_diff(path_a, path_b, output)` that loads both files, computes `TrialDiff`, reads vendor JS/CSS from disk, renders `diff.html` with all assets inlined into a single self-contained HTML file.
- `calibra/cli.py`: Added `--export FILE` argument to diff subparser. Refactored `cmd_diff()` to use `load_diff_report()` for validation. When `--export` is provided, validates output path (not a dir, parent exists), calls `export_diff()`, prints path, and exits.
- `tests/test_web_diff.py`: Added `TestLoadDiffReport` (5 tests), `TestDiffExport` (7 tests including brand link, self-contained regex checks, no file-picker, labels), and 3 CLI export tests in `TestDiffCli`.

All 483 tests pass, lint clean.

## 2026-03-03 (session 9)

**Asked**: Add a `/diff` feature to compare two arbitrary Swival JSON report files side-by-side in the web UI.

**Did**: Wrote a plan (`plans/trial-diff.md`) and iterated through two review rounds addressing division-by-zero handling, defensive parsing, tool usage shape, security posture, error ordering, and template polarity. Then implemented:

- `calibra/web/viewdata.py`: Added `KpiDelta`, `ToolDiffEntry`, `TrialDiff` dataclasses and `build_trial_diff()` function. All numeric extraction uses `safe_num()`, zero-baseline `pct` returns `None`. Added `_safe_dict()` helper to handle non-dict field values defensively.
- `calibra/web/__init__.py`: Added `GET /diff` route with query params `a`/`b` (absolute file paths). Validates A-first then B-second for deterministic error ordering. Returns 200 with inline error banner on failure, both inputs always prefilled. Rejects non-dict JSON root values.
- `calibra/web/templates/diff.html`: Side-by-side comparison page with KPI tiles (lower-is-better polarity: negative delta = green, positive = red), settings diff table, tool usage table with only-in badges, dual timelines, dual raw JSON panels. Shows provider/model info.
- `calibra/cli.py`: Added `calibra diff <file_a> <file_b> [--port]` command. Hard-codes `host=127.0.0.1` with no `--host` flag for security. Case-insensitive `.json` extension check. Rejects non-dict JSON root.
- `tests/test_web_diff.py`: 47 tests covering KpiDelta, build_trial_diff, route, template rendering, malformed data, and CLI.

All 469 tests pass, lint clean.

**Asked**: Update all documentation to reflect the new diff feature.

**Did**: Audited and updated 6 documentation files:
- `CLAUDE.md`: Added `calibra diff` to Commands section, updated web dashboard description to mention trial diff route.
- `README.md`: Added `calibra diff` to CLI Reference list.
- `docs.md/cli-reference.md`: Added full `calibra diff` section with signature, options, security note, and examples.
- `docs.md/web-dashboard.md`: Added "Trial diff" subsection to Pages section.
- `docs.md/installation.md`: Added `diff` to the subcommand list in "Verify the installation".
- `docs.md/analysis.md`: Added "Diffing individual trials" section distinguishing trial-level diff from campaign-level compare.

## 2026-03-03 (session 8)

**Asked**: 900s timeout is too short for the fastly-eval campaign.

**Did**: Inspected trial results — two `services-by-bandwidth` trials hit the 900s wall exactly (timeout failures), and several others were 500-600s. Bumped `timeout_s` from 900 to 1800 in `experiments/fastly-eval/fastly-eval.toml`.

## 2026-03-03 (session 7)

**Asked**: Audit all documentation in `docs.md/` for accuracy against the source code.

**Did**: Ran 6 parallel audit agents to compare every claim in the docs against the actual codebase. Found and fixed ~40 discrepancies across 10 files:

- **configuration.md**: `model` field now documented as optional, `agents_md` default shown, budget tracking clarified as estimated prompt tokens only, yolo/allowed_commands behavior corrected
- **cli-reference.md**: Added missing `--verbose`/`-v` flag, fixed `web build --output` default from `dist/` to `<results_dir>/web`, fixed `show` output description, removed references to nonexistent `[web]` optional extra
- **analysis.md**: CV threshold corrected from 0.5 to 1.0, removed false claim about per-task pass rates in summary.md, fixed show output format to match actual Rich tables, fixed derived metric rounding (4dp), clarified Cliff's delta is computed on tokens with equal-size requirement, added comparison.md output filename
- **tasks.md**: Corrected "exact text" to note whitespace stripping, added non-empty constraint to task.md, fixed meta.toml claim (not written to reports), documented timeout/OSError verify.sh behavior, noted empty tasks_dir error
- **running.md**: Fixed progress output format to match both verbose and non-verbose modes, corrected stdout vs stderr, fixed yolo behavior description, documented `--quiet` conditionality, fixed dry-run description (prints variants not trials)
- **installation.md**: Web deps (FastAPI, Uvicorn, Jinja2) are core not optional — removed nonexistent `[web]` extra, fixed from "two optional groups" to one (`charts`), added `verbose.py` and `__init__.py` to project structure
- **advanced.md**: Fixed "alphabetical sort" claims to "Cartesian product order", clarified Cliff's delta on tokens with equal-size requirement, added name/description exclusion to config hash description, fixed `--quiet` conditionality
- **web-dashboard.md**: Fixed static export from "single HTML file" to multi-page site, removed `[web]` extra references, corrected "auto-refresh" to "manual cache refresh"
- **index.md** + **installation.md**: Fixed Swival link from `github.com/anthropics/swival` to `swival.dev`
- **quickstart.md**: Fixed dry-run description

Also changed `max_turns` default from 50 to 250.

## 2026-03-03 (session 5)

**Asked**: "Loading chart..." placeholder never disappears in the web dashboard.

**Did**: The root cause was a Plotly.js v3 breaking change: string shorthand for `title` attributes (e.g., `title: 'Pass Rate (%)'`) was removed in v3. All axis and colorbar titles must now use the object form `title: { text: '...' }`. The old form caused Plotly.newPlot() to throw an error, preventing chart rendering and leaving the placeholder visible. Fixed 7 occurrences across 4 templates (campaign.html, variant.html, tasks.html, compare.html).

## 2026-03-02 (session 4)

**Asked**: Web export (`calibra web build`) only generates an index.html page, not the detail pages available in `web serve`. Make export identical to serve.

**Did**: Rewrote the static site exporter to produce a multi-page site using the same Jinja2 templates as the FastAPI server:

1. **Templates**: Added `{{ root_path }}` prefix to all URLs in all 7 templates (base, campaigns, campaign, tasks, variant, trial, compare). Added `CALIBRA_ROOT` JS variable for JavaScript-constructed URLs.
2. **Serve mode**: Set `root_path=""` as Jinja2 global in `__init__.py` so serve mode is unaffected.
3. **`export.py`**: Complete rewrite. New `_SiteBuilder` class renders all page types (campaigns list, campaign detail, task matrix, variant detail, trial inspector) using the same templates. Uses depth-based relative paths (`_root_path(depth)`) for static assets and navigation links.
4. **Generated structure**: `index.html` (campaigns list), `campaign/{name}/index.html` (detail), `campaign/{name}/tasks/index.html` (matrix), `campaign/{name}/variant/{label}/index.html` (variant), `campaign/{name}/trial/{task}/{variant}/{repeat}/index.html` (trial inspector).
5. **Tests**: Rewrote `test_web_export.py` (24 tests) and updated `test_web_dashboard.py` + `test_web_compare.py` export assertions. All 423 tests pass.

## 2026-03-02 (session 3)

**Asked**: Align docs/index.html with README.md.

**Did**: Updated the landing page to match the README's content and messaging:

1. **Hero**: Replaced generic tagline with README's "Stop guessing which models and settings are best. Measure them." + provider-agnostic description (Anthropic, OpenAI, LM Studio, Ollama).
2. **Why Calibra**: Replaced mismatched feature cards with README's 4 points: five-dimensional testing, statistically rigorous, works with open models, completely free and open source.
3. **Web Dashboard**: Added new section with 4 cards (campaign overview, variant rankings, task heatmap, trial inspector) matching README's dashboard description.
4. **Features**: Added section with failure classification, budget tracking, campaign comparison, and reproducibility cards.
5. **Quick Start**: Added the local model variant (qwen3.5-local via LM Studio) to the campaign config example. Simplified steps to match README flow.
6. **CLI Reference**: Added full CLI reference section from README.
7. **Task Format**: Added task directory structure section from README.
8. **Meta tags**: Updated title and descriptions to match README's messaging.

## 2026-03-02 (session 2)

**Asked**: Add the static website creator from Swival to Calibra.

**Did**: Copied Swival's static site generator and adapted it for Calibra:

1. **`build.py`**: Adapted from Swival's `build.py` with Calibra's NAV structure (9 doc pages across 3 groups: Getting Started, Usage, Reference), branding, and URLs. Same architecture: Markdown → HTML conversion, link rewriting, link validation, favicon generation.
2. **`docs/css/style.css`**: Copied from Swival with updated comment header.
3. **`docs/index.html`**: Landing page with Calibra-specific hero, features (matrix experiments, failure classification, statistical analysis, web dashboard), and quickstart.
4. **`docs/.nojekyll`**: GitHub Pages signal file.
5. **`pyproject.toml`**: Added `website` dependency group (`markdown`, `pillow`).
6. **`Makefile`**: Added `website` target (`uv run --group website python build.py`).

Build produces `docs/` with landing page, 9 doc pages, docs hub, CSS, logo, and favicon. All links validated.

## 2026-03-02

**Asked**: Make the `model` field optional in campaign config (it's auto-detected by swival for the lmstudio provider).

**Did**: Made `model` optional across 4 files:

1. **`calibra/config.py`**: Changed `ModelVariant.model` type from `str` to `str | None`. Replaced `_require(m, "model", ...)` with `m.get("model")`.
2. **`calibra/runner.py`**: Session API path now builds kwargs dict and only includes `model` when not None. CLI path conditionally adds `--model` flag.
3. **`calibra/prices.py`**: `validate_price_coverage` skips models with `model=None`.
4. **`tests/test_config.py`**: Added `test_model_optional` verifying a model entry without `model` field parses correctly with `model=None`.

---

**Asked**: Add `--verbose` mode to `calibra run`.

**Did**: Implemented verbose output across 4 files with 12 new tests:

1. **`calibra/verbose.py`** (new): Three pure formatting functions — `format_progress_header()`, `format_trial_line()` (enhanced completion line with progress counter, timing, turns, tools, tokens, pass/fail tally), `format_trial_detail()` (timeline walk with LLM calls, tool calls, compactions, tool usage summary).

2. **`calibra/runner.py`**: Added `stderr_capture` field to `TrialResult`. Threaded `verbose: bool` through `run_campaign` → `run_trial_with_retry` → `_run_trial_impl` → `run_single_trial`/`run_trial_cli`. When verbose: injects `verbose=True` into Session kwargs, omits `--quiet` from CLI argv, captures stderr always. `run_campaign` now tracks completed/passed/failed counters with a print lock, uses `format_trial_line` + `format_trial_detail` in verbose mode. Live Swival streaming only with single worker (`trial_verbose = verbose and workers == 1`).

3. **`calibra/cli.py`**: Added `-v`/`--verbose` argument to run subparser.

4. **`tests/test_verbose.py`** (new): 10 tests covering all formatting functions.

5. **`tests/test_runner.py`**: 2 new tests verifying verbose injection into Session kwargs.

---

**Asked**: Implement the reviewer support plan from `plans/reviewer-support.md`.

**Did**: Implemented reviewer support across 4 files with 49 new tests:

1. **`calibra/config.py`**: Added `ReviewerConfig` dataclass (`command`, `max_rounds=5`). Added `reviewer: ReviewerConfig | None` to `Campaign`. Parses `[reviewer]` TOML section with validation (non-empty command, max_rounds >= 0, executable existence via `shutil.which()` + fallback to resolved path).

2. **`calibra/runner.py`**: Added 7 new functions:
   - `_session_opts_to_cli_args()` — maps session options to Swival CLI flags (verified against 0.1.12)
   - `_write_cli_mcp_config()` — wraps MCP config in `{"mcpServers": {...}}` for CLI
   - `_make_isolated_env()` — creates empty XDG_CONFIG_HOME to isolate from user config
   - `_kill_tree()` — POSIX process group kill via `os.killpg(SIGKILL)`
   - `_reviewer_verdict()` — determines pass/fail from review timeline events
   - `_classify_cli_failure()` — maps subprocess exit codes + stderr + report to failure taxonomy
   - `run_trial_cli()` — full CLI-mode trial execution with `subprocess.Popen`
   - `_run_trial_impl()` — dispatch routing (CLI when reviewer configured, Session otherwise)

   Updated `run_trial_with_retry()` to use `_run_trial_impl()`. Updated `write_trial_report()` to include `review_rounds` and `reviewer_verdict` fields.

3. **`calibra/analyze.py`**: Added `review_rounds` field to `TrialMetrics` (default 0) and `AggregateMetrics` (conditional `StatSummary | None`). Rankings table conditionally shows Reviews column.

4. **`calibra/report.py`**: MD rankings table conditionally includes Reviews column. CSV conditionally includes `review_rounds_mean` column.

5. **`tests/test_reviewer.py`**: 49 tests covering config parsing, CLI flag mapping, MCP config wrapping, env isolation, reviewer verdict (6 cases), CLI failure classification (9-case exhaustive matrix), workspace isolation, CLI trial execution with mocked subprocess, report field writing, and analysis integration.

All 194 tests pass. Lint and format clean.

**Asked**: Review found 4 issues (2 high, 1 medium, 1 low).

**Did**: Fixed all 4:
1. **High — yolo default missing in CLI path**: `run_trial_cli()` now calls `_resolve_yolo()` and adds `--yolo` when appropriate, matching `run_single_trial()` behavior.
2. **High — command normalization drops quoting**: Changed `" ".join()` to `shlex.join()` so arguments with spaces are properly quoted.
3. **Medium — malformed command raises raw ValueError**: Wrapped `shlex.split()` in try/except, re-raises as `ConfigError`.
4. **Low — testing gap**: Added 3 new tests: yolo default in CLI path, yolo auto-disable with allowed_commands, malformed command raises ConfigError, and command with spaces preserved through shlex.join.

198 tests pass. Lint clean.

**Asked**: Fix empty `[reviewer]` section silently disabling reviewer mode.

**Did**: Changed `if reviewer_raw:` to `if reviewer_raw is not None:` in config.py so an empty `[reviewer]` table (`{}`) enters validation and raises ConfigError for missing `command`. Added test for the case.

**Asked**: Update all documentation including docs directory.

**Did**: Updated 9 files:
- **CLAUDE.md**: Updated architecture (mentions CLI invocation for reviewer), trial runner description (mentions CLI helpers), trial output layout (mentions `review_rounds` and `reviewer_verdict` fields).
- **AGENTS.md**: Added "Reviewer Support Conventions" section covering CLI invocation rationale, config isolation (XDG, swival.toml deletion), MCP format conversion, verdict semantics (intentional divergences), review_rounds metric, CLI failure classification, verify.sh skipping, yolo default parity.
- **docs.md/configuration.md**: Added full `[reviewer]` section with field table, example, command parsing details, and verdict semantics explanation.
- **docs.md/running.md**: Split "Trial execution flow" into Session mode and Reviewer mode subsections. Reviewer mode documents CLI invocation, XDG isolation, swival.toml deletion, report reading, and verdict determination.
- **docs.md/analysis.md**: Added `review_rounds` to metrics table. Updated statistical summaries paragraph. Added `review_rounds` to summary.json example. Updated CSV description to mention conditional `review_rounds_mean` column. Updated `verified` description to mention reviewer verdict.
- **docs.md/tasks.md**: Added note that `verify.sh` is skipped when reviewer is configured.
- **docs.md/advanced.md**: Added "CLI mode failure classification" subsection explaining report-first classification with stderr provider override.
- **docs.md/index.md**: Mentioned reviewer in the "how it works" description.
- **docs.md/web-dashboard.md**: Mentioned conditional review rounds column in campaign detail.

## 2026-03-01

**Asked**: Create an implementation plan for `plans/calibra.md`.

**Did**: Read the full Calibra design document (592 lines) and explored both the sweval and swival codebases thoroughly. Examined Swival's Session API (`session.py`), report format (`report.py`), configuration system (`config.py`), skills system, MCP client, and test infrastructure. Wrote a detailed implementation plan at `plans/init-cc.md` covering all 19 steps across 4 phases, with concrete dataclass definitions, function signatures, Swival API integration details, testing strategy, and risk callouts.

**Asked**: Review init-oi.md (user-written plan). Read and compared it to init-cc.md. Noted it's a stronger project plan (milestones, exit criteria) while init-cc.md is a stronger technical reference.

**Asked**: Apply six fixes to init-cc.md based on user code review.

**Did**: Fixed all six issues:
1. **Concurrency/timeout**: Replaced the inconsistent ProcessPool→ThreadPool waffling with a single decision: subprocess-based isolation via `subprocess.Popen`. Threads only manage subprocess lifecycle. Hard kill on timeout.
2. **Retry bug**: Removed the reference to `spec_failure_class` before first attempt. Now runs first attempt unconditionally, classifies failure, then checks per-class retry limit.
3. **Cost model keying**: Changed price dict from `model -> price` to `(provider, model) -> price`. TOML keys use `provider/model` format, split on first `/`.
4. **TOML dependency**: Removed `tomli` from dependencies. Python 3.13 has `tomllib` in stdlib, so no fallback is needed.
5. **verify.sh contract**: Standardized on cwd-based execution (`cwd=tmpdir`, no `$1` argument). Updated both the runner step and the example tasks to match.
6. **Resume check**: Now validates config_hash, task name, variant label, and repeat index, not just "has version and result keys". Stale artifacts from different configs are re-run.

**Asked**: Implement the plan in `plans/init-oi.md`.

**Did**: Implemented all milestones (M0–M4) of Calibra v1:

- **M0: Bootstrap**: `pyproject.toml`, package scaffold, CLI entrypoint with 5 subcommands (`validate`, `run`, `analyze`, `show`, `compare`).
- **M1: Config & Matrix**: `config.py` with TOML parsing, validation, 9 dataclasses, SHA-256 config hashing. `matrix.py` with cartesian expansion, constraint filtering, 3 sampling modes (full/random/ablation), variant filtering. `tasks.py` with task discovery and validation.
- **M2: Runner**: `runner.py` with workspace setup (env copy, overlay, AGENTS.md), Swival Session integration, verify.sh execution, trial seed computation, ThreadPoolExecutor orchestration, trial JSON output with calibra metadata block.
- **M3: Reliability**: `failure.py` with 5-class failure classification. Retry logic with per-class limits and exponential backoff. `budget.py` with token/cost tracking using (provider, model) price keying. Resume support validating config_hash + identity.
- **M4: Analysis & Reporting**: `analyze.py` with metric extraction, statistical aggregation (StatSummary with CI), paired bootstrap CI, Cliff's delta, permutation test, instability flags, ranking, Pareto front. `report.py` with JSON/MD/CSV exporters. `compare.py` for cross-campaign diffs. `show.py` for rich trial display.
- **Examples**: 2 tasks (hello-world, fix-typo) with verify scripts, 2 campaign configs (model-shootout, skill-ablation).
- **Tests**: 78 tests across 7 test files, all passing. Ruff lint clean.

**Asked**: Fix 9 logic/behavior bugs found in code review.

**Did**: Fixed all 9 issues, added 16 regression tests (94 total, all passing):

1. **verify.sh failures not treated as trial failures**: Added `verified` param to `classify_failure()`. `verified=False` now returns `FailureClass.TASK`. Runner passes verification result to classifier.
2. **timeout_s not enforced for agent execution**: Wrapped `Session.run()` in a `ThreadPoolExecutor` with `future.result(timeout=campaign.timeout_s)`. On timeout, sets `timed_out=True` and raises `TimeoutError`, which `classify_failure` correctly maps to `TIMEOUT`.
3. **--resume reruns persistent failures**: Removed `version == 1` and `"result" in report` checks from `result_exists()`. Now only checks calibra metadata identity (config_hash, task, variant, repeat). Failed trials are treated as completed artifacts.
4. **MCP config parsing expects JSON**: Added `_load_mcp_config()` helper that dispatches on file extension: `.toml` uses `tomllib`, everything else uses `json.load()`.
5. **Budget early-stop drops in-flight results**: Removed `break` after budget exceeded. Loop continues to collect all completed futures; only cancels pending ones.
6. **Cost guard unimplemented**: Added `calibra/prices.py` with `load_prices()` (reads `prices.toml` from config dir) and `validate_price_coverage()`. Wired into `run_campaign` and `cmd_validate`. Added `config_path` param to `run_campaign`.
7. **Config validation misses path checks**: Added `_validate_path_exists` calls for `skills_dirs`, `mcp.config`, and `environment.overlay`. Created `skills/` directory for example config.
8. **--keep-workdirs ignored**: Threaded `keep_workdirs` through `run_trial_with_retry` → `run_single_trial`. `finally` block now conditionally deletes based on flag.
9. **--filter silently ignores unknown dimensions**: `apply_filter()` now validates dimension names upfront and raises `ConfigError` with helpful message listing valid dimensions.

**Asked**: Fix 3 more bugs found in follow-up review.

**Did**: Fixed all 3, added 3 regression tests (97 total, all passing):

1. **Timeout still not effective wall-clock kill**: `ThreadPoolExecutor.__exit__` blocks waiting for the worker thread, defeating the timeout. Replaced with a daemon `threading.Thread` + `worker.join(timeout=campaign.timeout_s)`. Daemon threads are abandoned immediately when the function returns.
2. **Budget-stop crashes with CancelledError**: After budget exceeded, `f.cancel()` on pending futures causes `CancelledError` when iterating `as_completed`. Added `from concurrent.futures import CancelledError` and `try/except CancelledError: continue` around `future.result()`.
3. **cmd_validate type bug**: `load_prices(args.config)` passes a `str` but `load_prices` expects `Path` (calls `.parent`). Wrapped `args.config` in `Path()` in `cmd_validate`.

## 2026-03-02

**Asked**: Create a plan for a web interface to view experiment results.

**Did**: Created `plans/webc.md` (my plan) with FastAPI + Jinja2 + HTMX + Plotly stack. User also wrote `plans/webo.md` with React + Vite approach. Compared both, then merged the best of each into `plans/web.md`, keeping webo's milestone structure, product requirements, and schema versioning with webc's concrete page specs, API endpoints, and Python-first stack. Applied six fixes (compare.py refactor, path security, caching, vendored assets, automated tests, responsive layout). Added further refinements: trial URL split `{variant}/{repeat}`, performance acceptance targets, paginated trial endpoint, comparison flow clarity, stale data handling, chart config tests, migration trigger criteria, browser support.

**Asked**: Implement M0 (Prerequisite Refactors + Scaffolding).

**Did**: Completed all M0 deliverables:

1. **compare.py refactor**: Extracted `compute_comparison()` → `ComparisonResult` dataclass with `VariantComparison` members. `compare_campaigns()` is now a thin wrapper. 5 regression tests.
2. **Dependencies**: Added `fastapi>=0.135.1`, `uvicorn[standard]>=0.41.0`, `jinja2>=3.1.6` as optional `[web]` extras in `pyproject.toml`.
3. **Vendored frontend deps**: Downloaded Tailwind CSS Browser 4.2.1, Plotly.js 3.4.0, HTMX 2.0.8, Lucide 0.575.0 into `calibra/web/static/vendor/`. Created `scripts/update-vendor.sh`.
4. **Web package skeleton**: Created `calibra/web/` with `__init__.py` (app factory), `server.py` (uvicorn launcher), `api.py` (6 JSON endpoints), `cache.py` (in-memory index), `security.py` (allowlist + path containment), `export.py` (stub).
5. **Templates**: `base.html` (nav, dark mode, vendored assets) and `campaigns.html` (card grid with pass rate badges).
6. **CLI commands**: `calibra web serve` and `calibra web build` wired into `cli.py`.
7. **Security tests**: 24 tests covering segment validation, path containment, symlink escape, API traversal prevention, valid routes, and empty results dir.

All 126 tests pass. Ruff lint clean.

**Asked**: Fix 5 findings from M0 code review.

**Did**: Fixed all 5:

1. **HIGH: Path containment bypass**: `str.startswith()` allows `/tmp/results-evil` when root is `/tmp/results`. Replaced with `Path.relative_to()` which raises ValueError for non-children. Added `test_same_prefix_escape` regression test.
2. **MEDIUM: Campaign cards link to nonexistent page**: Added `/campaign/{name}` route in `__init__.py` and `campaign.html` template with KPI tiles + variant rankings table.
3. **LOW: Vendor script silent failures**: Added `--fail` flag to curl and SHA-256 checksum verification for each downloaded file.
4. **LOW: `__pycache__` not globally ignored**: Fixed `.gitignore` to use `__pycache__/` and `*.pyc` globally.
5. **LOW: `web build` NotImplementedError**: Intentional M0 stub, documented for M1.

**Asked**: Continue with M1 (Data Layer + Campaign List).

**Did**: Completed all M1 deliverables:

1. **`export.py` full implementation**: Replaced stub with complete static site builder. Defines `SCHEMA_VERSION = 1`. Scans results dir for campaigns, builds structured data bundles (campaign, variants, tasks, trials, meta), generates `index.html` with 5 inlined `<script type="application/json">` blocks, copies vendored assets. Client-side JS renders variant rankings table from inlined data with schema compatibility check. Handles corrupt/missing summary.json with clear error messages.
2. **Schema versioning**: `meta` block includes `schema_version` integer, `generated_at` timestamp, and `generator` identifier. Static JS checks schema compatibility on load and shows upgrade message if version is too new.
3. **Task aggregates**: `_build_task_aggregates()` groups trials by (task, variant) and computes per-cell pass rates, feeding both the export and heatmap views.
4. **`tests/test_web_cache.py`**: 20 tests covering CampaignIndex properties (n_variants, n_tasks, n_trials, pass_rate weighted calculation, fallback to file count) and ResultCache operations (scan, reload, get, hidden dir skip, corrupt summary handling, mtime tracking).
5. **`tests/test_web_api.py`**: 21 tests across 7 test classes: campaigns endpoint (shape, counts, sorting), campaign detail, heatmap (cell shape, pass rate calculation, failed trials), trial retrieval, compare endpoint, reload (picks up new campaigns), and page routes (home, campaign detail, 404).
6. **`tests/test_web_export.py`**: 22 tests across 6 test classes: bundle building (structure, data, meta, error handling), task aggregates (grouping, pass rates, sorting), static site generation (files, assets, inlined blocks, schema version, custom output dir, error cases), single campaign build, and determinism verification.

All 190 tests pass. Ruff lint clean.

**Asked**: Fix 3 findings from M1 code review.

**Did**: Fixed all 3:

1. **HIGH: Script/HTML injection in static export**: Two vectors fixed. (a) JSON inlined in `<script type="application/json">` blocks can contain `</script>` which breaks the tag. Fixed by replacing `</` with `<\/` in serialized JSON (standard mitigation). (b) Variant labels inserted via `innerHTML` allow HTML injection. Fixed by adding a JS `esc()` helper that uses `textContent`→`innerHTML` escaping for all data values. Campaign name in title/h1 was already `_html_escape()`'d. Added 3 regression tests proving `</script>` payloads, `<img onerror>` payloads, and HTML-in-campaign-names are all neutralized.
2. **MEDIUM: `calibra web build` fails for single campaign path**: `build_static_site()` now detects if the given path itself contains `summary.json` and delegates to `build_single_campaign()` instead of only scanning child directories. `results/model-shootout` now works directly. Added 2 regression tests.
3. **LOW: Non-deterministic `generated_at`**: Replaced `datetime.now(timezone.utc)` with `summary.json` file mtime. Output is now fully byte-identical across runs for identical inputs. Determinism test upgraded from partial block comparison to full `html1 == html2` assertion, plus explicit mtime verification.

All 195 tests pass. Ruff lint clean.

**Asked**: Fix remaining XSS path where non-string values (e.g. `turns.mean`) are inserted via innerHTML without escaping.

**Did**: Hardened all dynamic value rendering in the static export JS:

1. Added `num()` helper that coerces any value through `Number()`. Non-numeric strings become `NaN` → `0`.
2. Added `stat()` helper that safely accesses nested stat objects (e.g. `v.turns.mean`) with type checking.
3. Every cell value now goes through `esc()` after formatting, not just `variant_label` but also pass rate, turns, tokens, LLM time, and wall time cells.
4. Schema version error message now uses DOM `textContent` instead of innerHTML concatenation.
5. Added regression test `test_all_cell_values_escaped` that injects HTML into a `turns.mean` field and verifies the JS uses `esc(stat(...))` for all numeric cells.

All 196 tests pass. Ruff lint clean.

**Asked**: Implement M2 (Core Dashboard).

**Did**: Completed all M2 deliverables:

1. **Enhanced KPI tiles**: Added median turns and failure rate KPIs to the campaign dashboard (6 tiles total: pass rate, variants, tasks, total trials, median turns, failure rate). Both server-rendered template and static export.
2. **Pass Rate Bar Chart**: Horizontal Plotly bar chart showing pass rate per variant, sorted ascending, color-coded (teal ≥80%, amber ≥50%, red <50%). Responsive, dark-mode aware.
3. **Efficiency Scatter with Pareto Front**: Plotly scatter plot with X=mean tokens, Y=pass rate. Hover shows variant details. Pareto front drawn as dotted teal line with diamond markers (only when >1 Pareto point). Pareto computed by sorting variants by tokens ascending and tracking best pass rate.
4. **Warnings Panel**: JS-computed instability flags shown in amber panel. Detects high coefficient of variation (CV > 0.5) for turns, LLM time, and tokens. Flags variants with fewer than 3 repeats. Panel hidden when no warnings.
5. **Sortable Table with URL-State**: Variant rankings table with clickable column headers for sorting. Added Score/1k column. Sort state persisted in URL query params (`?sort=pass_rate&dir=desc`) via `history.replaceState`. Both server-rendered (data attributes + JS) and static export (full JS re-render).
6. **Static Export Update**: `export.py` updated to include Plotly.js script tag, enhanced KPI grid, warnings panel, chart containers, bar chart, efficiency scatter, Pareto front, and sortable table with URL persistence. All XSS protections preserved.
7. **Tests**: 28 new tests in `test_web_dashboard.py` covering server KPIs, charts, sorting, warnings, export features, edge cases (single variant, zero pass rate), and XSS preservation.

All 224 tests pass. Ruff lint clean.

**Asked**: Fix server-side campaign table not ranked by default.

**Did**: Added `_rank_variants()` in `__init__.py` that sorts variants by pass_rate desc, tokens asc, turns asc before passing to the template. Now `loop.index` in the Jinja template always reflects correct ranking on initial page load. No JS sort needed for default view. Added 2 regression tests: one proving worst-first input gets reordered, one proving tiebreak logic (same pass rate → fewer tokens wins).

All 226 tests pass. Ruff lint clean.

**Asked**: Fix `_rank_variants()` crash on malformed/non-numeric summary data.

**Did**: Three fixes across cache, app factory, and template:

1. **`_rank_variants()` in `__init__.py`**: Added `_num()` helper that wraps `float()` with try/except. All sort key values coerced through it.
2. **`CampaignIndex.pass_rate` in `cache.py`**: Wrapped arithmetic in `float()` calls with try/except `(TypeError, ValueError)` → returns `None`.
3. **`campaign.html` template**: Added `_safe_num` as a Jinja `|num` filter. All numeric values in the table row (`pass_rate`, `turns.mean`, `tokens.mean`, etc.) now go through `{% set pr = v.pass_rate|num %}` before any arithmetic or formatting. Prevents Jinja template crashes on non-numeric data.
4. **Regression test**: `test_non_numeric_pass_rate_no_500` with `pass_rate: "not_a_number"`, `turns.mean: "oops"`, `tokens.mean: None`, confirming 200 response.

All 227 tests pass. Ruff lint clean.

**Asked**: Implement M3 (Drilldown Experience).

**Did**: Completed all M3 deliverables: three drilldown pages enabling any failed trial to be traced in 3 clicks from the campaign dashboard:

1. **`repeat` field on `TrialMetrics`**: Added `repeat: int` to the dataclass (after `variant_label`). `extract_metrics()` reads `calibra.repeat` from trial JSON. Updated existing test helpers in `test_analyze.py` and `test_report.py`.
2. **Campaign dashboard navigation**: Variant labels in the table are now clickable links to `/campaign/{name}/variant/{label}`. Added "Task Matrix" link in the subtitle area.
3. **Task Matrix page** (`GET /campaign/{name}/tasks`): Route handler groups trials by (task, variant), computes per-cell pass_rate/mean_turns/mean_tokens. Template renders a Plotly heatmap (red→amber→teal), click navigates to variant detail with `?task=` filter. Breadcrumb back to campaign.
4. **Variant Detail page** (`GET /campaign/{name}/variant/{label}`): Shows 4 KPI tiles (pass rate, trials, turns, tokens), per-task stats table with outcome dots, Plotly box plots for turns distribution, failure pie chart (hidden if no failures), tool usage stacked bar. Trial list table with each row linking to trial inspector. Supports `?task=` query param for pre-filtering.
5. **Trial Inspector page** (`GET /campaign/{name}/trial/{task}/{variant}/{repeat}`): Renders 5 KPI tiles (wall time, turns, tokens, LLM time, tool time). Vertical CSS timeline with distinct rendering per event type (llm_call: gray, tool_call: green/red, compaction: amber, guardrail: purple, review: blue). Collapsible settings panel and raw JSON viewer (uses `textContent` for XSS safety). Path traversal protection via `validate_path()`.
6. **Tests**: 36 new tests in `test_web_drilldown.py` across 4 classes (TestTaskMatrix, TestVariantDetail, TestTrialInspector, TestNavigation) including 3-click path verification.

All 263 tests pass. Ruff lint clean.

**Asked**: Fix 4 findings from M3 code review.

**Did**: Fixed all 4, added 8 regression tests (271 total, all passing):

1. **HIGH: Wrong timeline event keys**: Trial template used `event.get("tool")`, `event.get("success")`, `event.get("retry")` but real Swival artifacts use `name`, `succeeded`, `is_retry`. Fixed all three: tool name now reads `event.get("name", "tool")`, success reads `event.get("succeeded", true)`, retry reads `event.get("is_retry")`. Added 4 regression tests proving tool name renders, ok/fail badges are correct, and retry badge appears.
2. **MEDIUM: Token KPI always 0**: Trial template read `stats.get("prompt_tokens_est", 0)` but report token estimates live on timeline `llm_call` events. Replaced with Jinja namespace loop summing `prompt_tokens_est` from all `llm_call` events. Added regression test confirming 500+300=800 tokens rendered.
3. **MEDIUM: 500 on malformed numeric fields**: `float()` conversions in task_matrix and variant_detail route handlers crash on non-numeric values. Extracted `_to_float()` helper with try/except returning 0.0, replaced all 5 bare `float()` calls. Added 2 regression tests with `turns="not_a_number"` and `wall_time_s="broken"`.
4. **MEDIUM: Heatmap click logic incorrect**: `variants[pt.x]` and `tasks[pt.y]` treated Plotly categorical axis values as array indices. For heatmap categorical axes, `pt.x`/`pt.y` are already the category strings. Changed to `var variant = pt.x; var task = pt.y;`. Added regression test asserting no array indexing in click handler.

All 271 tests pass. Ruff lint clean.

**Asked**: Fix trial inspector crashing on malformed numeric fields in trial JSON.

**Did**: Applied `|num` filter to all 6 numeric format sites in `trial.html`, added 3 regression tests (274 total, all passing):

- `cal.get("wall_time_s", 0)` → `cal.get("wall_time_s", 0)|num`
- `stats.get("total_llm_time_s", 0)` → `stats.get("total_llm_time_s", 0)|num`
- `stats.get("total_tool_time_s", 0)` → `stats.get("total_tool_time_s", 0)|num`
- Token sum: `ev.get("prompt_tokens_est", 0)` → `ev.get("prompt_tokens_est", 0)|num`
- Both `event.duration_s` format calls → `event.duration_s|num`
- Token total display: `{{ token_total.v }}` → `{{ token_total.v|int }}` (avoids 800.0 rendering)

Regression tests write a trial with `wall_time_s="oops"`, `total_llm_time_s="bad"`, `total_tool_time_s=None`, `prompt_tokens_est="not_int"`, `duration_s="slow"`, all returning 200.

All 274 tests pass. Ruff lint clean.

**Asked**: Implement M4 (Comparison + Static Export).

**Did**: Completed all M4 deliverables:

1. **`/compare` route handler** in `calibra/web/__init__.py`: Added `GET /compare` with optional `a`/`b` query params. Passes `campaign_names` for picker dropdowns. When both params present: validates segments, checks campaigns exist (404 if not), calls `compute_comparison()`, serializes result via `dataclasses.asdict()`. Handles missing common variants with error message.
2. **`compare.html` template**: Extends `base.html`. Campaign picker with two `<select>` dropdowns pre-selected to current values. Summary tiles (common variants count, biggest improvement, biggest regression). Comparison table with columns: Variant, Pass A, Pass B, Delta (green/red color-coded), Effect Size with magnitude label, Tokens A, Tokens B. Diverging delta chart via Plotly horizontal bar (green right for positive, red left for negative). Empty state and error state handling.
3. **"Compare" navigation link**: Added to `campaigns.html` next to the page title with `data-nav="compare-link"` pointing to `/compare`.
4. **Static export verification**: Confirmed existing `build_static_site()` works correctly. No code changes needed per plan (comparison is computed on-demand, not during export).
5. **Tests**: 24 new tests in `test_web_compare.py` across 4 classes: TestComparePage (15 tests: 200 responses, picker rendering, table/chart presence, pass rates, delta colors, summary tiles, breadcrumb, inlined data, preselected dropdowns), TestCompareErrors (3 tests: 404s and no-common-variants error), TestCompareNavigation (2 tests: link presence and URL), TestStaticExportVerification (4 tests: index.html, data blocks, schema version, assets).

All 298 tests pass. Ruff lint clean.

**Asked**: Fix compare flow crashing on malformed numeric trial data (500 instead of graceful handling).

**Did**: Added `_safe_num()` coercion helper to `calibra/analyze.py` and applied it at both crash sites:

1. **`extract_metrics` line 71**: `sum(e.get("prompt_tokens_est", 0) ...)`). Wrapped each value in `_safe_num()` so string/None values coerce to 0.0 instead of causing `TypeError`. Also wrapped all other numeric `stats.get()` and `cal.get()` reads (turns, tool_calls_total, tool_calls_failed, llm_time_s, tool_time_s, wall_time_s, compactions, guardrail_interventions).
2. **`aggregate_variant` line 138**: `float(getattr(m, attr))` in `vals()`. Replaced `float()` with `_safe_num()` so any non-numeric `TrialMetrics` field coerces to 0.0 instead of raising `ValueError`.

Added 5 regression tests:
- `test_extract_metrics_malformed_numeric_fields`: verifies `"not_a_number"`, `None`, `"garbage"` in stats/timeline all coerce to 0.
- `test_aggregate_variant_malformed_numeric_fields`: verifies string/None `TrialMetrics` fields don't crash aggregation.
- `test_compare_page_survives_malformed_data`: `/compare?a=good&b=bad` returns 200 with comparison table.
- `test_api_compare_survives_malformed_data`: `/api/compare?a=good&b=bad` returns 200 with correct variant.
- `test_malformed_tokens_coerced_to_zero`: verifies bad tokens value yields `tokens_mean_b == 0.0`.

All 303 tests pass. Ruff lint clean.

**Asked**: Fix `_safe_num` accepting non-finite values (`"nan"`, `"inf"`) that break JSON serialization in `/api/compare` and produce invalid inlined JSON in `/compare`.

**Did**: Added `math.isfinite()` guard to `_safe_num()` in `calibra/analyze.py`. After `float()` succeeds, checks `math.isfinite(x)` and returns `default` if not. This catches `float("nan")`, `float("inf")`, `float("-inf")`, and actual `float('nan')`/`float('inf')` values.

Added 4 regression tests:
- `test_extract_metrics_non_finite_values`: `"nan"`, `"inf"`, `"-inf"`, `float("nan")` in stats/timeline/calibra all coerce to 0.
- `test_aggregate_variant_non_finite_values`: `float("nan")`, `float("inf")` in TrialMetrics fields coerce to 0 during aggregation.
- `test_api_compare_survives_nan_inf`: `/api/compare` returns 200 with valid JSON (no `ValueError: Out of range float values`).
- `test_compare_page_survives_nan_inf`: `/compare` returns 200 with no `NaN` or `Infinity` in the HTML output.

All 307 tests pass. Ruff lint clean.

**Asked**: Implement M5 (Polish + Quality Gates).

**Did**: Completed all M5 deliverables, the final polish pass for production readiness:

1. **Chart container CSS classes** in `style.css`: Added `.chart-container` (300px) and `.chart-container-lg` (400px) to replace all inline `style="height: Npx"`.
2. **Responsive table wrappers**: Changed `overflow-hidden` to `overflow-x-auto` on table wrapper divs in `campaign.html`, `variant.html` (2 tables), and `compare.html`. Preserves rounded borders while enabling horizontal scroll on narrow viewports.
3. **Chart loading placeholders**: Replaced inline height styles with chart-container classes across all 7 chart divs. Added centered "Loading chart..." fallback text inside each. Plotly.newPlot() replaces inner content automatically; if JS fails, user sees the fallback.
4. **Keyboard shortcuts** in `base.html`: Global keydown listener. `/` focuses `[data-shortcut-search]` element, `Esc` blurs focused input or calls `history.back()`.
5. **Variant filter input** on campaign dashboard: Text input with `data-shortcut-search` between charts and table. Client-side JS filters table rows by matching `data-variant-label` attribute. Makes `/` shortcut immediately useful.
6. **Empty/error states**: (a) `variant.html`, conditional `{% if not trials %}` block with `data-test="empty-trials"` message. (b) `tasks.html`, wraps heatmap in `{% if cells_json != "[]" %}` with `data-test="empty-heatmap"` fallback. (c) `trial.html` + `__init__.py`, try/except `(json.JSONDecodeError, OSError)` in trial_inspector renders error panel with `data-test="error-message"` instead of 500.
7. **Tests**: 13 new tests in `test_web_polish.py` across 4 classes (TestResponsiveTables, TestChartContainers, TestKeyboardShortcuts, TestEmptyErrorStates).

All 320 tests pass. Ruff lint clean.

**Asked**: Fix 2 findings from M5 code review.

**Did**: Fixed both, added 2 regression tests (322 total, all passing):

1. **MEDIUM: Invalid UTF-8 trial files crash with 500**: `trial_path.read_text()` raises `UnicodeDecodeError` which wasn't caught. Added `UnicodeDecodeError` to the except clause in `trial_inspector`.
2. **LOW: Empty heatmap JS errors on missing DOM node**: Heatmap container is conditionally rendered but the script block always calls `Plotly.newPlot('heatmap', ...)`. Added early guard `if (!heatmapEl) return;` at the top of the script.

**Asked**: Write comprehensive multi-page user documentation for Calibra in a `docs/` directory.

**Did**: Created 9 documentation pages in `docs/`:

1. `index.md`: Overview, core concepts (campaign, task, matrix, variant, trial, repeat), the 5 matrix dimensions, doc navigation
2. `installation.md`: Requirements, install with uv, optional extras (charts, web), dev deps, project structure
3. `quickstart.md`: End-to-end tutorial: create a task, write a config, validate, dry run, execute, inspect, analyze, web dashboard
4. `tasks.md`: Task directory structure, task.md writing tips, env/ workspace, verify.sh contract (exit codes, timeout, chmod), meta.toml, task discovery rules, real-world examples (generation, bug fix, refactoring, multi-file)
5. `configuration.md`: Full TOML reference: [campaign], all 5 matrix dimensions, variant label format, [budget] + prices.toml, [retry], [sampling], [[constraints]], complete example
6. `running.md`: Validation, dry runs, parallel workers, output paths, --keep-workdirs, --filter syntax, --resume identity checks, workspace setup order, trial execution flow, monitoring progress
7. `analysis.md`: calibra analyze + show commands, metrics collected (12 fields), per-variant aggregation, StatSummary (8 statistics), derived metrics, rankings, Pareto front, instability warnings, weighted pass rate, report formats (JSON/MD/CSV), campaign comparison
8. `web-dashboard.md`: Setup, launching, all 6 pages (campaign list, detail, heatmap, variant detail, trial inspector, comparison), static HTML export, REST API endpoints (6 routes), dashboard features (dark mode, keyboard shortcuts, sorting)
9. `cli-reference.md`: Every subcommand with arguments, options, examples: validate, run, analyze, show, compare, web serve, web build. Exit codes, environment variables.
10. `advanced.md`: Constraints, sampling modes, budget management, failure classification, retry behavior, trial seed determinism, campaign comparison, config hashing, large matrix strategies.

**Asked**: Make documentation feel more human-written.

**Did**: Rewrote all 10 documentation files in `docs/`. Replaced bullet-point lists with flowing English prose throughout. Converted enumerated lists into natural sentences. Added paragraph breaks between ideas. Kept all technical content, code blocks, tables, and examples intact. Verified all default values and formulas against the source code before rewriting.

**Asked**: Implement session options passthrough (PLAN-session-options.md).

**Did**: Implemented the full plan across 4 files:

1. **`calibra/config.py`**: Added `session_options: dict` field to `ModelVariant` and `Campaign` dataclasses. Added `_validate_session_options()` with: rejected keys check (9 harness-managed keys), blocked keys check (system_prompt, no_system_prompt, no_instructions), unknown key rejection (validated against `Session.__init__` via `typing.get_type_hints`), type validation (unwraps Optional/Union, checks element types for parameterized lists), and conditional `no_skills` conflict guard. Parsing in `load_campaign()` reads `raw.get("session", {})` and `m.get("session", {})` (not `.pop()`, preserving raw dict for hash).
2. **`calibra/runner.py`**: Added `_deep_merge()` (recursive dict merge), `_merge_session_options()`, `_validate_merged_options()` (warns on allowed_commands + yolo=true, raises on no_skills + non-empty skills_dirs). `run_campaign()` precomputes merged options per model before scheduling. `run_single_trial()` accepts `merged_session_opts`, implements yolo/allowed_commands interplay, and splats remaining opts into `Session(**session_opts)`.
3. **`tests/test_config.py`**: 16 new tests covering campaign/per-model parsing, rejected keys, unknown keys, empty defaults, config hash sensitivity, type validation (wrong type, list elements), conflict guards (no_instructions, no_system_prompt, system_prompt, no_skills conditional), valid allowed_commands.
4. **`tests/test_runner.py`**: 14 new tests covering _deep_merge (5 cases: no overlap, partial overlap, nested 3 levels, scalar↔dict override), merge_session_options (3 cases: campaign-only, model-only, overlap + deep merge), validate_merged_options (3 cases: warn, raise, ok), yolo auto-flip (3 cases), Session kwargs forwarding via mock.

All 354 tests pass. Ruff lint clean.

**Asked**: Update all model references in documentation to only use allowed OpenRouter models.

**Did**: Replaced all model references across docs, plans, README, and code comments. Old models (`claude-sonnet-4-20250514`, `claude-haiku-3-20241022`, `google/gemini-2.5-pro`, `o3`, `qwen3-coder-next`) replaced with the four allowed models: `anthropic/claude-sonnet-4.6`, `anthropic/claude-haiku-4.5`, `openai/gpt-5.3-codex`, `z-ai/glm-5`. Updated labels, prices.toml examples, filter expressions, summary tables, and ablation examples across 9 files: `docs/configuration.md`, `docs/advanced.md`, `docs/quickstart.md`, `README.md`, `plans/calibra.md`, `plans/init-cc.md`, `PLAN-session-options.md`, `calibra/cli.py`.

**Asked**: Create a Fastly service evaluation campaign testing 5 tasks (list services, list active services, order by VCL size, order by bandwidth, list backends) across 3 models (haiku, sonnet, GLM-5) with/without Fastly skills and MCP server.

**Did**: Created plan at `plans/PLAN-fastly-eval.md` and implemented the full campaign at `experiments/fastly-eval/`. After multiple rounds of review, fixed: provider from `anthropic` to `openrouter` (swival doesn't support anthropic directly), added two-tier verification (structural + ground-truth comparison), moved to dedicated `tasks-fastly/` then self-contained `experiments/fastly-eval/tasks/` for correct path resolution, moved `expected.json` out of `env/` to prevent leaking ground truth to the agent, froze bandwidth time window with concrete timestamps in task.md, strengthened verifiers to check all fields (not just IDs), and switched from `yolo=true` to `allowed_commands` list to prevent sandbox escape to read ground truth files.

Files created:
- `experiments/fastly-eval/fastly-eval.toml` — campaign config (12 variants x 5 tasks = 60 trials)
- `experiments/fastly-eval/fastly-agents.md` — minimal agent instructions
- `experiments/fastly-eval/fastly-mcp.json` — MCP server config for fastly-mcp2
- `experiments/fastly-eval/tasks/*/task.md` — 5 task prompts
- `experiments/fastly-eval/tasks/*/verify.sh` — 5 verification scripts with field-by-field ground truth comparison
- `experiments/fastly-eval/scripts/generate-fastly-ground-truth.sh` — generates expected.json files via Fastly CLI/API

Config validates: `uv run calibra validate experiments/fastly-eval/fastly-eval.toml` → 12 variants x 5 tasks x 1 repeat = 60 trials. Next step: run `generate-fastly-ground-truth.sh` with FASTLY_API_TOKEN set, then execute the campaign.

**Asked**: Make `calibra analyze` recursive and more verbose.

**Did**: Two changes to `calibra/analyze.py`:

1. **Recursive campaign detection**: `analyze_campaign()` now auto-detects whether the given path is a single campaign directory or a parent containing multiple campaigns. Added `_is_campaign_dir()` (checks for trial JSONs in immediate subdirs) and `_find_campaigns()` (returns list of campaign dirs). `calibra analyze results/` now analyzes each campaign separately instead of lumping all trials together.
2. **Verbose stdout output**: Replaced the single "Analysis written to X" line with a full terminal report via `_print_results()`. Shows: trial/variant/task counts, per-task pass rate bars, ranked variant table (pass rate, turns, tokens, LLM/wall time), per-variant task breakdown matrix, Pareto front, efficiency metrics (score/1k tokens, pass/min), and instability warnings.

All 358 tests pass. Ruff lint clean.

**Asked**: Support `base_url` as inline property on `[[matrix.model]]` entries.

**Did**: Two changes:

1. **`calibra/config.py`**: Model parsing now collects any extra keys on `[[matrix.model]]` entries (beyond `provider`, `model`, `label`, `session`) and merges them into `session_options`. The explicit `session = { ... }` sub-table takes precedence over inline keys.
2. **`tests/test_config.py`**: Added 3 tests: inline-only, inline+session merged, and session sub-table wins on conflict.

Then updated all documentation to match:
- **`docs/configuration.md`**: Documented inline session options on model entries (both in the model section and the session options section), added example with `base_url` directly on model entry.
- **`docs/advanced.md`**: Fixed comparison output description (was JSON, actually writes `comparison.md` Markdown file).
- **`docs/cli-reference.md`**: Fixed compare `--output` default (was "current directory", actually parent of `dir_a`). Fixed validate output format to match actual code.
- **`docs/quickstart.md`** and **`docs/running.md`**: Fixed validate output format to match actual code.
- **`docs/analysis.md`**: Added missing metrics (`skills_used`, `guardrail_interventions`) to the metrics table.
- **`CLAUDE.md`**: Updated config description to mention inline model session options.

All 361 tests pass. Ruff lint clean.

**Asked**: Create a plan for adding reviewer support to Calibra.

**Did**: Explored Swival's reviewer feature thoroughly (CLI-only, not in Session API). Wrote initial plan at `plans/reviewer-support.md` using Session.run()/Session.ask() approach.

**Asked**: Review of plan found 5 issues (2 high, 3 medium).

**Did**: Revised `plans/reviewer-support.md` addressing all 5 findings:

1. **HIGH: Session.ask() returns report=None**: Switched approach from Session API to CLI invocation (`swival --report --reviewer`). When reviewer is configured, Calibra runs swival as a subprocess instead of using the Session API. Swival handles the full reviewer loop internally and the `--report` JSON includes all timeline events, tokens, and review events across all rounds. Budget tracking works because the report is complete.
2. **HIGH: Max-round rejection semantics**: Intentional divergence from Swival — documented. Swival exits 0 on max-rounds-hit ("accepts answer as-is"). Calibra inspects the last `review` event in the timeline: if `exit_code=1`, sets `verified=False`. Rationale: in a benchmark, "reviewer says wrong but we gave up" is not a pass.
3. **MEDIUM: Timeout not covering reviewer rounds**: Single `campaign.timeout_s` deadline wraps the entire `subprocess.Popen` + `communicate(timeout)` call. Naturally covers initial run + all reviewer rounds + reviewer subprocesses. Cleaner than the thread join approach.
4. **MEDIUM: Command validation underspecified**: Added explicit validation mirroring Swival's `agent.py:2280-2301`: `shlex.split()`, first-token extraction, `shutil.which()` fallback to `Path.resolve().is_file()` + `os.access(X_OK)`.
5. **MEDIUM: review_rounds display scope**: Specified exactly where it appears: summary.json, summary.md (conditional column), summary.csv, terminal output (conditional column), web dashboard variant table, variant detail KPI, static export JSON.

**Asked**: Second review found 6 more issues (3 high, 3 medium) plus 2 open questions.

**Did**: Revised plan again addressing all 6 findings:

1. **HIGH: reviewer.timeout_s unenforceable**: Removed `timeout_s` from `ReviewerConfig`. Swival hardcodes reviewer subprocess timeout at 3600s with no CLI override. The campaign-level `timeout_s` on the outer `subprocess.Popen` provides the overall bound. Documented this limitation.
2. **HIGH: CLI flag-shape mismatches**: Verified every flag against Swival's argparse definitions. Fixed `--allowed-commands` to single comma-separated string (not multiple positional values). Fixed `--allowed-dirs`/`--allowed-dirs-ro` to `--add-dir`/`--add-dir-ro`. Built complete mapping table with correct formats.
3. **HIGH: Config contamination from global/project swival config**: Added `_make_isolated_env()` that sets `XDG_CONFIG_HOME` to a temp empty directory, preventing `~/.config/swival/config.toml` from loading. Workspace is built from scratch (no `swival.toml`). Pass `--no-mcp` when no MCP variant to prevent `.mcp.json` discovery.
4. **MEDIUM: Provider retry classification**: No changes to `classify_failure()` needed. Exit code 1 stderr text is passed as `RuntimeError(stderr_text)` — existing pattern matching for "rate limit", "429", "503" etc. works on the error message string.
5. **MEDIUM: MCP config format conversion**: Added `_write_cli_mcp_config()` that wraps Calibra's flat format in `{"mcpServers": {...}}` before passing to `--mcp-config`. Swival's `load_mcp_json()` expects this wrapper.
6. **MEDIUM: Subprocess tree kill**: Changed from `proc.kill()` to `start_new_session=True` + `os.killpg(proc.pid, signal.SIGKILL)` to kill the entire process group (swival + reviewer subprocesses + their children).

Open questions resolved: reviewer exit 2+ now sets `verified=None` (unverified, not True) for benchmarking integrity. Config isolation via XDG override is strict by default.

**Asked**: Third review found 4 more issues (1 high, 3 medium).

**Did**: Revised plan addressing all 4:

1. **HIGH: `--verbose` and `--sandbox` flag mismatches**: `--verbose` doesn't exist in Swival CLI (it's derived from `--quiet`). Removed `verbose` from mapping. Calibra always passes `--quiet` for benchmark trials. `--sandbox` was actually correct (verified against argparse: `choices=["builtin", "agentfs"]`) — kept it.
2. **MEDIUM: swival.toml in workspace from env/overlay**: `setup_workspace()` copies task env/ and overlay verbatim — could include a `swival.toml`. Added explicit deletion of `<tmpdir>/swival.toml` after workspace setup, before launching CLI.
3. **MEDIUM: exit-code-1 suppresses tool classification**: When passing `RuntimeError(stderr)` as error, `classify_failure()` takes the `error is not None` branch and skips report-based tool detection. Added `_classify_cli_failure()` helper that tries report-based classification first (error=None), only falling back to stderr pattern matching when report says success but exit code disagrees.
4. **MEDIUM: POSIX-specific process group kill**: Added `_popen_kwargs()` and `_kill_tree()` helpers with `os.name == "posix"` branching. POSIX uses `start_new_session=True` + `os.killpg(SIGKILL)` with OSError fallback. Windows uses `CREATE_NEW_PROCESS_GROUP` + `proc.kill()`.

**Asked**: Fourth review: 3 findings. Claims `--sandbox` and `sandbox` Session param don't exist; Windows inconsistency.

**Did**: Verified against actual Swival source at `~/src/swival` (HEAD) and found `--sandbox` exists there. However, I was checking HEAD, not the pinned version. Two of three findings were incorrect *for HEAD*. Fixed the one valid issue: removed Windows `CREATE_NEW_PROCESS_GROUP`/`taskkill` references — Calibra targets POSIX. Simplified to `start_new_session=True` + `os.killpg()` only.

**Asked**: Fifth review: `--sandbox` and `sandbox` Session param don't exist in the *pinned* swival 0.1.12 — I was reading HEAD at `~/src/swival`, not the installed version.

**Did**: Confirmed by running `uv run swival --help` (no `--sandbox`) and inspecting `Session.__init__` params (no `sandbox`). The root cause: I kept referencing `~/src/swival` (development HEAD) instead of the version pinned in `uv.lock` (0.1.12). Removed `sandbox` from the CLI mapping table. Added version pin header at top of plan: "Target Swival version: 0.1.12". Added note that the mapping table is verified against 0.1.12 and unknown keys from future versions are warned and skipped.

**Asked**: Sixth review: 2 findings (1 high, 1 medium).

**Did**: Fixed both:

1. **HIGH: Provider failures misclassified as "task"**: In `_classify_cli_failure()`, when the report says "task" (outcome="error", tool_calls_failed=0) but exit code is non-zero, now also checks stderr for provider patterns. If stderr matches, "provider" overrides "task".
2. **MEDIUM: Unmapped CLI flags**: Added `read_guard=False` → `--no-read-guard` and `proactive_summaries=True` → `--proactive-summaries` to the mapping table. Fixed notes: `config_dir` managed via XDG isolation, `history` forced off via `--no-history`.

**Feedback**: `--quiet` means stderr may be empty for provider errors, weakening detection.

**Did**: Expanded `_classify_cli_failure()` test spec to an exhaustive matrix covering report-present/missing × stderr-present/empty × each exit code. Added explicit empty-stderr cases: exit 1 + report + empty stderr → "task" (no provider signal), exit 1 + no report + empty stderr → "task".
