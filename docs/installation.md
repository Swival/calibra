# Installation

Calibra requires Python 3.13 or later, [uv](https://docs.astral.sh/uv/) as its package manager, and [Swival](https://github.com/anthropics/swival) as the underlying agent framework.

## Install Calibra

Clone the repository and install with `uv`:

```bash
git clone <repo-url> calibra
cd calibra
uv sync
```

This installs the core package with two dependencies: `swival` (the agent framework) and `rich` (for terminal formatting).

## Optional extras

Calibra ships with two optional dependency groups. For chart generation in reports, install `matplotlib`:

```bash
uv sync --extra charts
```

For the interactive web dashboard (FastAPI, Uvicorn, Jinja2):

```bash
uv sync --extra web
```

Or grab everything at once:

```bash
uv sync --extra charts --extra web
```

## Development dependencies

If you plan to contribute or run the test suite, install the dev group to get `pytest` and `ruff`:

```bash
uv sync --group dev
```

## Verify the installation

Make sure the CLI works:

```bash
uv run calibra --help
```

You should see a list of subcommands: `validate`, `run`, `analyze`, `show`, `compare`, and `web`.

## Project structure

```
calibra/
  cli.py          # CLI entrypoint
  config.py       # TOML config parsing
  matrix.py       # Variant expansion
  tasks.py        # Task discovery
  runner.py       # Trial execution
  failure.py      # Failure classification
  budget.py       # Token/cost tracking
  prices.py       # Price loading
  analyze.py      # Results aggregation
  report.py       # Report generation
  compare.py      # Campaign comparison
  show.py         # Trial pretty-printing
  utils.py        # Shared utilities
  web/            # Web dashboard (optional)
experiments/      # Campaign config files
tasks/            # Task definitions
results/          # Trial output (generated)
```
