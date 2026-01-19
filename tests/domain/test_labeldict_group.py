"""Tests for `LabelDict.group`.

This is one of the most important pure-logic utilities in majoplot.
It groups arbitrary elements based on a subset of labels.

Why this matters
----------------
Downstream plotting logic often assumes:
- Grouping is deterministic.
- Sorting within a group is deterministic.
- Group member limiting (subgrouping) produces stable subgroup ids.

If any of these assumptions break, you may observe symptoms like:
- Styles seemingly "randomly" applied to curves.
- Legend items not matching curve order.

We keep tests small and explicit so a failure immediately pinpoints the issue.
"""

from __future__ import annotations

from majoplot.domain.base import LabelDict, LabelValue


def _ld(**kwargs: object) -> LabelDict:
    """Helper: build a LabelDict from simple key=value inputs.

    English comment:
    - Values are wrapped into LabelValue.
    - This keeps test data compact.
    """

    return LabelDict({k: (v if isinstance(v, LabelValue) else LabelValue(v)) for k, v in kwargs.items()})


def test_group_basic_two_groups() -> None:
    """Elements should be partitioned by the group label values."""

    pairs = [
        (_ld(a=1, b=10), "e1"),
        (_ld(a=1, b=11), "e2"),
        (_ld(a=2, b=20), "e3"),
    ]

    groups, remains = LabelDict.group(
        pairs,
        group_label_names=["a"],
        summary_label_names=["a"],
    )

    assert remains == []

    # English comment: `LabelDict.group` returns pairs of
    # (group_label_dict: LabelDict, members: list[Any]).
    # The group_label_dict directly stores the grouping labels.
    by_a = {g["a"].value: members for g, members in groups}
    assert by_a[1] == ["e1", "e2"]
    assert by_a[2] == ["e3"]


def test_group_missing_label_goes_to_remains() -> None:
    """If a LabelDict is missing any group label, the element goes to remains."""

    pairs = [
        (_ld(a=1), "ok"),
        (_ld(b=2), "missing"),
    ]

    groups, remains = LabelDict.group(
        pairs,
        group_label_names=["a"],
    )

    assert [m for m in remains] == ["missing"]
    assert len(groups) == 1


def test_group_sorting_within_group_is_deterministic() -> None:
    """sort_label_names should sort group members by the specified label(s)."""

    pairs = [
        (_ld(g=1, s=3), "e3"),
        (_ld(g=1, s=1), "e1"),
        (_ld(g=1, s=2), "e2"),
    ]

    groups, remains = LabelDict.group(
        pairs,
        group_label_names=["g"],
        sort_label_names=("s",),
    )

    assert remains == []
    assert len(groups) == 1

    (_group_labels, members) = groups[0]
    assert members == ["e1", "e2", "e3"]


def test_group_member_limit_creates_subgroups_with_ids() -> None:
    """group_member_limit should split a group into multiple subgroups.

    English comment:
    - subgroup id is derived from position // limit.
    - the returned LabelDict should carry that subgroup id.
    """

    pairs = [(_ld(g=1, s=i), f"e{i}") for i in range(5)]

    groups, remains = LabelDict.group(
        pairs,
        group_label_names=["g"],
        sort_label_names=("s",),
        group_member_limit=2,
    )

    assert remains == []

    # NOTE: The current implementation has a known behavior/bug:
    # it only cuts the first subgroup at exactly the limit, and then puts the
    # remaining members into a second subgroup.
    #
    # We assert the CURRENT behavior here so the test suite is stable and can
    # catch unintentional changes.
    assert [members for (_lbl, members) in groups] == [["e0", "e1"], ["e2", "e3", "e4"]]
    # English comment:
    # The current implementation assigns subgroup id based on the *last* element
    # index of the subgroup, because the subgroup LabelDict is re-created on
    # each iteration and the last created one is stored when the subgroup is
    # appended. For members [2,3,4], the last index is 4, and 4//2 == 2.
    assert [lbl.subgroup for (lbl, _members) in groups] == [0, 2]


def test_group_member_limit_expected_chunking_documented_as_xfail() -> None:
    """Desired behavior for subgrouping (documented as xfail).

    English comment:
    The more intuitive behavior is to chunk each group into blocks of size
    `group_member_limit`:
        [0,1], [2,3], [4]

    The current production implementation does not do this yet.
    We mark this as xfail to record the intended contract for future fixes.
    """

    import pytest

    pairs = [(_ld(g=1, s=i), f"e{i}") for i in range(5)]

    groups, remains = LabelDict.group(
        pairs,
        group_label_names=["g"],
        sort_label_names=("s",),
        group_member_limit=2,
    )

    assert remains == []

    pytest.xfail("Known issue: subgroup chunking does not fully respect the limit.")

    assert [members for (_lbl, members) in groups] == [["e0", "e1"], ["e2", "e3"], ["e4"]]
    assert [lbl.subgroup for (lbl, _members) in groups] == [0, 1, 2]
