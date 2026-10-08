.PHONY: clean clean-test clean-pyc clean-build docs help install-dev
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

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -fr .ruff_cache

install-dev: ## install the package in development mode
	pip install maturin
	maturin develop -r

build: clean ## build Rust extension in release mode
	maturin build --release

test: ## run tests quickly with the default Python
	pytest

test-cov: ## run tests with coverage report
	pytest --cov=dxf_io --cov-report=html --cov-report=term
	$(BROWSER) htmlcov/index.html

lint: ## run linting with ruff and ty
	ruff check python tests --fix
	ruff format python tests
	ty check .
	codespell python tests docs README.rst

docs: ## generate documentation (if available)
	@echo "Documentation available in README.rst"

dist: clean ## builds source and wheel package
	maturin build --release
	ls -lh target/wheels/

upload-test: dist ## upload to TestPyPI
	python -m twine upload --repository testpypi target/wheels/*

upload: dist ## upload to PyPI
	python -m twine upload target/wheels/*

install-wheel: dist ## install from built wheel
	pip install target/wheels/*.whl

benchmark: ## run performance benchmark
	python benchmark.py

.PHONY: all
all: clean lint test dist
