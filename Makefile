.PHONY: clean clean-test clean-pyc clean-build help install-dev
.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys
from urllib.request import pathname2url
webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys
for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

BROWSER := python -c "$$BROWSER_PYSCRIPT"

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} + 2>/dev/null || true
	find . -name '*.egg' -exec rm -f {} + 2>/dev/null || true
	find . -name '*.so' -exec rm -f {} + 2>/dev/null || true

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} + 2>/dev/null || true
	find . -name '__marimo__' -exec rm -fr {} + 2>/dev/null || true

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -fr .ruff_cache

install-dev: ## install the package in development mode (release build)
	uv sync
	uv run maturin develop --release

build: clean ## build a release wheel for the current platform
	uv run maturin build --release

test: ## run the Python and Rust tests
	uv run pytest
	cargo test --release

test-cov: ## run tests with coverage report
	uv run pytest --cov=dxf_io --cov-report=html --cov-report=term
	$(BROWSER) htmlcov/index.html

lint: ## lint and format-check everything (ruff, ty, codespell, rustfmt, clippy)
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	uv run codespell python tests src README.rst CHANGELOG.md CONTRIBUTING.md
	cargo fmt --check
	cargo clippy --all-targets -- -D warnings

format: ## auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .
	cargo fmt

dist: clean ## build the sdist and a release wheel for the current platform
	uv run maturin sdist -o dist
	uv run maturin build --release -o dist
	ls -lh dist/

benchmark: ## run performance benchmark
	uv run python benchmark.py --synthetic 300

.PHONY: all build test test-cov lint format dist benchmark
all: clean lint test dist
