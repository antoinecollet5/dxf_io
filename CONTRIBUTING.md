# Contributing to dxf_io

Thank you for your interest in contributing!

## Development setup

You need a [Rust toolchain](https://rustup.rs) and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/antoinecollet5/dxf_io
cd dxf_io
uv sync                 # builds the extension (editable) and installs the dev tools
uv run pre-commit install
```

`uv sync` and `uv run` rebuild the extension (in release mode) whenever the Rust code
changed, so there is no separate build step.

Use uv's `.venv` on its own: if a conda environment is active, run `conda deactivate`
first (maturin refuses to run when both `VIRTUAL_ENV` and `CONDA_PREFIX` are set).

## Checks

```bash
make lint               # ruff check, ruff format, ty, codespell, rustfmt, clippy
make test               # pytest + cargo test
make benchmark          # timings on a synthetic file
```

CI runs the same checks on Linux, macOS and Windows for every supported Python version.

## Documentation

The documentation (Sphinx, in `docs/sources`) is published on
<https://dxf-io.readthedocs.io> for every push to `master`. Build it locally with
`make docs` (no Rust build needed: the compiled extension is mocked; without network
access, set `DXF_IO_DOCS_OFFLINE=1`). The API reference
is generated from the docstrings (NumPy style) of the functions listed in
`python/dxf_io/__init__.py`.

## Code style

- Python: formatted and linted with `ruff`, type-checked with `ty`.
- Rust: `cargo fmt` and `cargo clippy -- -D warnings`.
- New features come with tests (`tests/` for Python, `#[cfg(test)]` in `src/lib.rs`
  for Rust internals).

## Releasing

The version lives in `Cargo.toml` only (`pyproject.toml` and `dxf_io.__version__`
read it).

1. Bump `version` in `Cargo.toml`, run `cargo check` to update `Cargo.lock`, and move
   the "Unreleased" entries of `CHANGELOG.md` under the new version.
2. Commit, then tag and push: `git tag v0.2.0 && git push origin master v0.2.0`.
3. The `Release` workflow builds the sdist and the wheels for every platform, tests the
   wheels, publishes them to PyPI (trusted publishing) and creates a GitHub release.

One-time PyPI setup: on <https://pypi.org/manage/account/publishing/>, add a pending
trusted publisher with owner `antoinecollet5`, repository `dxf_io`, workflow
`release.yml` and environment `pypi`; then create the `pypi` environment in the GitHub
repository settings (optionally with required reviewers).

To try the pipeline first, run the `Release` workflow manually (Actions tab, "Run
workflow"): it builds and tests everything without publishing.

## Reporting issues

Use GitHub Issues to report bugs or suggest features.
