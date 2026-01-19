"""Tests for `InsertAxesSpec.default`.

`InsertAxesSpec.default` computes a rectangle (in figure-relative coordinates)
where an inset axes can be placed without overlapping existing data points.

Why this matters
----------------
Inset placement is a visually sensitive feature. If the algorithm returns
nonsensical coordinates (negative, >1, zero size) you will see glitches like:
- inset axes outside the figure
- inset axes covering data points
- random-looking inset placement

These tests focus on *invariants* rather than exact numeric outputs.
Exact coordinates may change as the algorithm is improved.
"""

from __future__ import annotations

import numpy as np

from majoplot.domain.base import Axes, AxesSpec, Data, IgnoreOutlierSpec, LabelDict, fail_signal
from majoplot.domain.muti_axes_spec import InsertAxesSpec


def _mk_data(points: np.ndarray) -> Data:
    """Helper: create a minimal Data instance."""

    return Data(
        labels=LabelDict({}),
        _headers=("x", "y"),
        points=points.astype(float),
        ignore_outliers=None,
    )


def _mk_axes(points: np.ndarray) -> Axes:
    """Helper: create a minimal Axes instance holding exactly one Data."""

    spec = AxesSpec(x_axis_title="x", y_axis_title="y")
    return Axes(spec=spec, labels=LabelDict({}), data_pool=[_mk_data(points)])


def test_insert_axes_spec_returns_fail_when_more_than_two_axes() -> None:
    """Design rule: current implementation refuses len(axes_pool) > 2."""

    axes_pool = [_mk_axes(np.array([[0.0, 0.0], [1.0, 1.0]])) for _ in range(3)]

    res = InsertAxesSpec.default(figure_size=(3.4, 2.6), axes_pool=axes_pool)
    assert res is fail_signal


def test_insert_axes_spec_basic_invariants() -> None:
    """Basic invariants for a valid inset rectangle.

    English comment:
    - x, y are left-bottom anchor in normalized figure coordinates.
    - width, height are normalized sizes.
    - They should lie within [0, 1] and be positive.

    We place a few points near the bottom-left corner so there is free space
    elsewhere for the algorithm to pick.
    """

    pts = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.05],
            [0.2, 0.1],
            [0.3, 0.2],
        ]
    )

    axes_pool = [_mk_axes(pts)]

    res = InsertAxesSpec.default(figure_size=(3.4, 2.6), axes_pool=axes_pool)

    assert res is not fail_signal
    assert isinstance(res, InsertAxesSpec)

    # English comment: Geometry must be meaningful.
    assert 0.0 <= res.x <= 1.0
    assert 0.0 <= res.y <= 1.0
    assert res.width > 0.0
    assert res.height > 0.0

    # English comment: The inset should not start beyond the figure.
    assert res.x + res.width <= 1.0 + 1e-6
    assert res.y + res.height <= 1.0 + 1e-6
