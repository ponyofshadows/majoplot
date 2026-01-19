# majoplot tests

This folder contains **pytest** tests added without modifying any production code.

## Quick start

If you use `uv`:

```bash
uv sync --extra test
uv run pytest
```

If you use `pip`:

```bash
pip install -e .
pip install pytest
pytest
```

## Test scope

- `tests/domain/`: Pure-logic tests (no GUI, no Origin COM). These should run on any OS.

## Notes

- We intentionally avoid testing Origin COM and GUI here because they are environment-dependent.
  A recommended next step is to add optional smoke tests behind a marker, e.g. `@pytest.mark.origin`.
