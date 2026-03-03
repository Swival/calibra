# Installation

Calibra requires Python 3.13 or later, [uv](https://docs.astral.sh/uv/) as its package manager, and [Swival](https://swival.dev) as the underlying agent framework.

## Install Calibra

Clone the repository and install with `uv`:

```bash
git clone <repo-url> calibra
cd calibra
uv sync
```

This installs the core package with its dependencies: `swival` (the agent framework), `rich` (for terminal formatting), `fastapi`, `uvicorn`, and `jinja2` (for the web dashboard).

## Optional extras

For chart generation in reports, install `matplotlib`:

```bash
uv sync --extra charts
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
  __init__.py     # Package init
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
  verbose.py      # Verbose output formatting
  utils.py        # Shared utilities
  web/            # Web dashboard
experiments/      # Campaign config files
tasks/            # Task definitions
results/          # Trial output (generated)
```
