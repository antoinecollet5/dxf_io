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

After changing Rust code, rebuild with `uv run maturin develop --release`
(or `make install-dev`).

## Checks

```bash
make lint               # ruff check, ruff format, ty, codespell, rustfmt, clippy
make test               # pytest + cargo test
make benchmark          # timings on a synthetic file
```

CI runs the same checks on Linux, macOS and Windows for every supported Python version.

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
2. Commit, then tag and push: `git tag v0.2.0 && git push origin main v0.2.0`.
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
