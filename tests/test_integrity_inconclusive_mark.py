"""The collapsed mark of a not-graded run must not read as a pass (#104)."""

import copy

import pytest
from test_integrity_inconclusive import COMPLETED, INCONCLUSIVE, _front


def _mark_summary(front: str) -> str:
    start = front.index("<summary class='eval-mark")
    return front[start : front.index("</summary>", start)]


def test_a_quiet_completed_run_keeps_its_check_pip():
    assert "class='pip'" in _mark_summary(_front(copy.deepcopy(COMPLETED)))


def test_an_inconclusive_run_stays_quiet_with_no_satisfied_line():
    front = _front(copy.deepcopy(INCONCLUSIVE))
    assert "is-quiet" in _mark_summary(front)
    assert "satisfied" not in front


@pytest.mark.xfail(
    strict=True,
    reason="#104: the collapsed INCONCLUSIVE mark shows the same check pip as a pass",
)
def test_an_inconclusive_mark_has_no_check_pip():
    assert "class='pip'" not in _mark_summary(_front(copy.deepcopy(INCONCLUSIVE)))


@pytest.mark.xfail(
    strict=True,
    reason="#104: the collapsed unrecognised-status mark shows the same check pip as a pass",
)
def test_an_unrecognised_status_mark_has_no_check_pip():
    document = copy.deepcopy(INCONCLUSIVE)
    document["integrity"]["run"]["test_system_status"] = "PARTIAL"
    assert "class='pip'" not in _mark_summary(_front(document))
