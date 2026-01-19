"""Tests for `Data.ignore_outliers` behavior.

The `Data` class can optionally filter outliers using a sliding-window heuristic.
This is a pure, deterministic transformation of the `points` array.

Why this matters
----------------
Outlier filtering changes plotted points and therefore impacts:
- axis limits
- marker/line appearance (dense vs sparse)
- derived downstream computations

These tests intentionally use small arrays so expected outputs are easy to verify.
"""

from __future__ import annotations

import numpy as np

from majoplot.domain.base import Data, IgnoreOutlierSpec, LabelDict


def _mk_data(points: np.ndarray, *, ignore: IgnoreOutlierSpec | None = None) -> Data:
    """Helper: build a Data object with minimal required fields."""

    return Data(
        labels=LabelDict({}),
        _headers=("x", "y"),
        points=points.astype(float),
        ignore_outliers=ignore,
    )


def test_points_for_plot_no_ignore_outliers_returns_original_points() -> None:
    """If ignore_outliers is None, points_for_plot should be the original array."""

    pts = np.array([[0, 0], [1, 1], [2, 2]], dtype=float)
    d = _mk_data(pts, ignore=None)

    # English comment: We expect identity or at least identical values.
    assert np.allclose(d.points_for_plot, pts)


def test_ignore_outliers_drops_middle_spike() -> None:
    """A large spike at the middle element should be dropped.

    The algorithm (in production code) inspects triples (p0, p1, p2) and checks
    whether the middle y-value is an outlier compared to endpoints.

    We craft points where:
    - p0 -> p2 is small change
    - p0 -> p1 is huge change

    Under those conditions, p1 is removed.
    """

    pts = np.array(
        [
            [0.0, 0.0],
            [1.0, 100.0],  # outlier
            [2.0, 1.0],
            [3.0, 2.0],
        ]
    )

    d = _mk_data(pts, ignore=IgnoreOutlierSpec(min_gap_base=1.0, min_gap_multiple=20.0))

    filtered = d.points_for_plot

    # English comment: The outlier point [1, 100] should not appear.
    assert filtered.shape[0] == 3
    assert not np.any((filtered == np.array([1.0, 100.0])).all(axis=1))


def test_ignore_outliers_cache_refreshes_when_spec_changes() -> None:
    """Changing ignore_outliers spec should refresh the cached filtered points."""

    pts = np.array(
        [
            [0.0, 0.0],
            [1.0, 100.0],
            [2.0, 1.0],
        ]
    )

    d = _mk_data(pts, ignore=IgnoreOutlierSpec(min_gap_base=1.0, min_gap_multiple=20.0))

    first = d.points_for_plot.copy()

    # English comment: Make the filter less aggressive so it may keep the middle.
    d.ignore_outliers = IgnoreOutlierSpec(min_gap_base=1.0, min_gap_multiple=2000.0)

    second = d.points_for_plot

    # English comment: We don't mandate the exact output; we only require that
    # the cache was recomputed (i.e., values can differ).
    assert not np.array_equal(first, second) or second.shape != first.shape
