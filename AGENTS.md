# Repository Guidelines

## Project Structure & Module Organization
- `calibra/`: core package (`cli.py`, runner, matrix/config, analysis/reporting, and web dashboard code in `calibra/web/`).
- `tests/`: pytest suite covering CLI, runner, analysis, and web routes/security.
- `tasks/`: benchmark tasks. Each task directory should include `task.md`, `env/`, and usually `verify.sh`.
- `experiments/`: campaign TOML files and experiment-specific task sets.
- `results/`: generated trial JSON files plus `summary.{json,md,csv}` outputs.
- `docs.md/`: project documentation; `scripts/`: maintenance utilities.

## Build, Test, and Development Commands
- `uv sync`: install dependencies from `pyproject.toml`/`uv.lock`.
- `make test` (or `uv run pytest`): run the full test suite.
- `make lint`: run Ruff checks on `calibra/` and `tests/`.
- `make format`: format code with Ruff.
- `make check`: lint + formatting check (CI-style gate).
- `uv run calibra validate experiments/<campaign>.toml`: validate a campaign before execution.
- `uv run calibra run experiments/<campaign>.toml --workers 2`: execute a campaign locally.

## Coding Style & Naming Conventions
- Target Python `>=3.13`; use 4-space indentation and keep lines <=100 chars (`ruff` setting).
- Use snake_case for modules/functions/variables and PascalCase for classes.
- Prefer explicit, small functions and type-aware interfaces in core logic.
- Test modules should follow `tests/test_<area>.py`.
- Variant labels must be underscore-joined as `model_agent_skills_mcp_environment` because they are used in paths, endpoints, and cache keys.

## Testing Guidelines
- Framework: `pytest` (shared fixtures in `tests/conftest.py`).
- Add/update tests for every behavior change, especially runner retries, failure classification, and web security checks.
- For new tasks, ensure `verify.sh` is executable and returns exit code `0` when passing.
- During development, run targeted tests (example: `uv run pytest tests/test_runner.py`) and run full tests before opening a PR.

## Reviewer Support Conventions

- When `[reviewer]` is configured in the campaign, Calibra switches from the Swival Session API to CLI invocation with `--report` and `--reviewer` flags. This is because `Session.ask()` returns `report=None`, making retry round data invisible to metrics and budget tracking.
- Config isolation: CLI trials set `XDG_CONFIG_HOME` to an empty temp directory and delete any `swival.toml` from the workspace to prevent user/project config leakage. `--no-mcp` is passed unless an MCP variant provides explicit config.
- MCP format conversion: Calibra's flat `{"server": {...}}` format is wrapped in `{"mcpServers": {...}}` for CLI mode, since Swival CLI expects the wrapper.
- Reviewer verdict semantics (intentional divergence from Swival): max-rounds-hit with rejection sets `verified=False` (Swival accepts as-is). Reviewer error (exit 2+) sets `verified=None` (Swival accepts as-is). Rationale: in a benchmark, "the reviewer says this is wrong" should not count as a pass.
- `review_rounds` metric is extracted from `stats.review_rounds` or `calibra.review_rounds` in trial reports. It is conditionally included in analysis output (rankings, CSV, MD) only when any variant has review_rounds > 0.
- `reviewer_verdict` is one of `"accepted"` (exit 0), `"rejected"` (exit 1 at max rounds), or `"error"` (exit 2+).
- CLI failure classification (`_classify_cli_failure`) uses report-based classification first, with a stderr provider-pattern override when the report says "task" but the exit code is non-zero. This preserves tool-failure detection from reports while still catching provider errors surfaced only in stderr.
- `verify.sh` is skipped when a reviewer is configured; the reviewer determines pass/fail.
- The yolo default in CLI mode matches Session mode: `_resolve_yolo()` is called, defaulting to `--yolo` unless `allowed_commands` is set.

## Commit & Pull Request Guidelines
- Keep commit subjects short, imperative, and specific (matching existing history like `Factorize`, `Add some example tasks`).
- Make focused commits; avoid mixing unrelated refactors and feature changes.
- PRs should include a concise change summary, rationale, impacted configs/commands, and test evidence (commands run and results). Include UI screenshots only for dashboard/template changes.
