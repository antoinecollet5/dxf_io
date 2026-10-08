# Contributing to dxf_io

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/antoinecollet5/dxf_io
cd dxf_io

# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install development dependencies
make install-dev

# Run tests
make test

# Run linting
make lint
```

## Making Changes

1. Create a new branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Run linting: `make lint`
4. Run tests: `make test`
5. Commit with descriptive message
6. Push and open a Pull Request

## Code Style

- Python: Use `ruff` for formatting and linting
- Rust: Use `rustfmt` (configured in `Cargo.toml`)
- Type hints: Use `ty` for type checking

## Testing

Always include tests for new features:

```bash
pytest -v tests/
```

## Reporting Issues

Use GitHub Issues to report bugs or suggest features.
