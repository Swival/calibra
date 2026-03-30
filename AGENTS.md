## Workflow

- install: `make install`
- build: `make website`
- test all: `make test`
- test file: `uv run pytest tests/test_config.py`
- test case: `uv run pytest tests/test_config.py::test_name`
- lint: `make lint`
- format: `make format`
- after every edit: `make check && make test`
- debug: `uv run calibra validate experiments/model-shootout.toml`; `uv run calibra run experiments/model-shootout.toml --dry-run`; `uv run calibra run experiments/model-shootout.toml -v`; `uv run calibra run experiments/model-shootout.toml --keep-workdirs`; reviewer mode isolates config via temp `XDG_CONFIG_HOME` and removes copied `swival.toml`

## Conventions

- Variant labels are always `{model}_{agent_instructions}_{skills}_{mcp}_{environment}` in that order. Those labels are reused in filenames, filters, API paths, and reports.
- Omitted matrix dimensions default to `agent_instructions=default`, `skills=none`, `mcp=none`, and `environment=base`. These defaults affect variant names and output paths.
- Tasks are only discovered one level deep under `tasks_dir`, sorted alphabetically. Every direct child directory must contain non-empty `task.md`, `env/`, and executable `verify.sh` if present.
- Trial workspaces are assembled in a fixed order: copy `env/`, then apply environment overlay, then copy `AGENTS.md`. Later steps override earlier files on conflicts.
- With `[reviewer]`, Calibra runs `swival` CLI instead of Session mode and skips `verify.sh`. `verified` comes from reviewer outcomes, and reports add `review_rounds` plus `reviewer_verdict`.
- `--resume` only skips a trial when `config_hash`, `task`, `variant`, and `repeat` all match the existing JSON. Config changes intentionally invalidate prior results.
- Trial JSON lives at `results/<campaign>/<task>/<variant>_<repeat>.json`. Analysis writes `summary.json`, `summary.md`, and `summary.csv`, and web/cache code depends on that layout.
- Every trial report must include a `calibra` block with `config_hash`, `task`, `variant`, `repeat`, `trial_seed`, `wall_time_s`, and `attempts`. Other modules read those fields back during resume, analysis, and web rendering.
- Project-written JSON uses `indent=2` with a trailing newline. Keep that formatting when adding generated JSON.
- Session options are deep-merged from campaign-level `[session]` and per-model overrides. If `commands` is set without explicit `yolo`, Calibra forces `yolo = false` so the allowlist takes effect.
- `prices.toml` keys use `"provider/model"` strings. Budget and price coverage logic depend on that exact format.
