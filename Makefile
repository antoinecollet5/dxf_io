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

# Only the project's own folders are cleaned: never the virtual environment (.venv).
SRC_DIRS := python tests examples

clean-build: ## remove build artifacts (including the compiled extension of the dev install)
	rm -fr build/ dist/ .eggs/ target/wheels/
	find $(SRC_DIRS) -name '*.egg-info' -exec rm -fr {} + 2>/dev/null || true
	rm -f python/dxf_io/_dxf_io*.so python/dxf_io/_dxf_io*.pyd

clean-pyc: ## remove Python file artifacts
	find $(SRC_DIRS) \( -name '*.pyc' -o -name '*.pyo' -o -name '*~' \) -exec rm -f {} +
	find $(SRC_DIRS) \( -name '__pycache__' -o -name '__marimo__' \) -exec rm -fr {} + 2>/dev/null || true

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/ .coverage .coverage.* htmlcov/ .pytest_cache .ruff_cache
	rm -fr docs/build/ docs/sources/_autosummary/

install-dev: ## install the package and the dev tools (rebuilds the extension when the Rust code changed)
	uv sync

build: ## build a release wheel for the current platform
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
	uv run codespell python tests src docs/sources README.rst CHANGELOG.md CONTRIBUTING.md
	cargo fmt --check
	cargo clippy --all-targets -- -D warnings

format: ## auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .
	cargo fmt

dist: ## build the sdist and a release wheel for the current platform
	rm -fr dist/
	uv run maturin sdist -o dist
	uv run maturin build --release -o dist
	ls -lh dist/

docs: ## generate the Sphinx HTML documentation, including the API reference
	rm -fr docs/build/ docs/sources/_autosummary/
	uv run --only-group docs python -m sphinx -W --keep-going -b html docs/sources docs/build/html
	$(BROWSER) docs/build/html/index.html

benchmark: ## run performance benchmark
	uv run python benchmark.py --synthetic 300

.PHONY: all build test test-cov lint format dist docs benchmark
all: lint test dist ## lint, test and build the distributions
