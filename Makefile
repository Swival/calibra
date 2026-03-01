.PHONY: install test lint format check website clean

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check calibra/ tests/

format:
	uv run ruff format calibra/ tests/

check: lint
	uv run ruff format --check calibra/ tests/

website:
	uv run --group website python build.py

clean:
	rm -rf .pytest_cache __pycache__ calibra/__pycache__ tests/__pycache__
