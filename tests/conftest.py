"""Pytest configuration for majoplot.

Important constraints
---------------------
- We do NOT edit or patch any production source files.
- We only add tests.

Why we touch sys.path
---------------------
This repository uses a `src/` layout (package code lives under `src/majoplot`).
When running tests from a plain source checkout, Python may not automatically
find `src/` on the import path.

Adding `src/` to `sys.path` inside tests is a common, minimal approach that
keeps tests runnable without requiring an editable install.

If you prefer, you can remove this file and run tests after an editable install:
    uv pip install -e .
    uv run pytest
"""

from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    """Add the repository's `src/` directory to `sys.path`.

    English comment: This makes `import majoplot` work in a fresh checkout.
    """

    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    # English comment: Insert at the front so local sources win over any
    # globally-installed `majoplot` package the developer might have.
    sys.path.insert(0, str(src_dir))
