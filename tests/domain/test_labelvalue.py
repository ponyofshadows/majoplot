"""Tests for the `LabelValue` type.

These tests focus on *ordering* and *string formatting* because those behaviors
feed directly into grouping, sorting, and legend/label generation.

Why this matters
----------------
In plotting pipelines, subtle ordering bugs tend to appear as "random" or
"inverted" style application (e.g., legend labels swapped, colors applied to the
wrong curve). Deterministic ordering in foundational types like `LabelValue`
reduces such systemic issues.

We do NOT attempt to change production behavior here.
If a test fails, that's a signal that the current implementation is inconsistent
with the behavior we want to rely on.
"""

from __future__ import annotations

import pytest

from majoplot.domain.base import LabelValue


def test_labelvalue_str_no_unit() -> None:
    """If unit is None, __str__ should be just the value."""

    lv = LabelValue(3.14)
    assert str(lv) == "3.14"


def test_labelvalue_str_unit_postfix() -> None:
    """If unit is set and unit_as_postfix=True, unit should be appended."""

    lv = LabelValue(10, "K", True)
    assert str(lv) == "10K"


def test_labelvalue_str_unit_prefix() -> None:
    """If unit_as_postfix=False, unit should be placed before the value."""

    lv = LabelValue(10, "K", False)
    assert str(lv) == "K10"


def test_labelvalue_numeric_vs_numeric_same_unit_orders_by_value() -> None:
    """Numeric values with the same unit should compare by numeric value."""

    a = LabelValue(1, "K")
    b = LabelValue(2, "K")
    assert a < b


def test_labelvalue_numeric_unit_none_sorts_before_with_unit() -> None:
    """Implementation detail: unit=None is considered "smaller" than unit!=None.

    English comment:
    This matches the current implementation (unit=None returns True in the
    ordering logic when comparing numeric values with different units).
    """

    a = LabelValue(1, None)
    b = LabelValue(1, "K")
    assert a < b


def test_labelvalue_numeric_unit_lexicographic_when_units_differ() -> None:
    """When both are numeric but units differ, ordering falls back to unit string."""

    a = LabelValue(1, "A")
    b = LabelValue(1, "B")
    assert a < b


def test_labelvalue_numeric_always_less_than_non_numeric() -> None:
    """Current rule: numeric values compare as smaller than non-numeric values."""

    a = LabelValue(1, "K")
    b = LabelValue("foo", None)
    assert a < b


def test_labelvalue_non_numeric_compares_by_string() -> None:
    """Non-numeric values are compared by their string representation."""

    a = LabelValue("A")
    b = LabelValue("B")
    assert a < b


@pytest.mark.parametrize(
    "value",
    [True, False],
)
def test_labelvalue_bool_is_unsupported_and_ordering_is_undefined(value: bool) -> None:
    """The docstring says bool is unsupported.

    English comment:
    We don't enforce a hard failure (production code does not raise).
    We only document the boundary by asserting that the type is bool.
    """

    lv = LabelValue(value)
    assert isinstance(lv.value, bool)
