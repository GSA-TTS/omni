.PHONY: check

check:
	uv sync --locked
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy harness
	uv run pytest --cov=harness --cov-report=term-missing -q
	uv run pip-audit
