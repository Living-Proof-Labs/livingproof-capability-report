"""The collapsed mark of a not-graded run must not read as a pass (#104)."""

import copy

from test_integrity_inconclusive import COMPLETED, INCONCLUSIVE, _front


def _mark_summary(front: str) -> str:
    # The front also holds the Scenario mark, which is first and keeps its pip. Take the
    # Run Integrity summary: the last summary that ends with that name.
    end = front.index("eval-name-full'>Run Integrity</span>")
    start = front.rindex("<summary class='eval-mark", 0, end)
    return front[start : front.index("</summary>", end)]


def test_a_quiet_completed_run_keeps_its_check_pip():
    assert "class='pip'" in _mark_summary(_front(copy.deepcopy(COMPLETED)))


def test_an_inconclusive_run_stays_quiet_with_no_satisfied_line():
    front = _front(copy.deepcopy(INCONCLUSIVE))
    assert "is-quiet" in _mark_summary(front)
    assert "satisfied" not in front


def test_an_inconclusive_mark_has_no_check_pip():
    assert "class='pip'" not in _mark_summary(_front(copy.deepcopy(INCONCLUSIVE)))


def test_an_unrecognised_status_mark_has_no_check_pip():
    document = copy.deepcopy(INCONCLUSIVE)
    document["integrity"]["run"]["test_system_status"] = "PARTIAL"
    assert "class='pip'" not in _mark_summary(_front(document))


def test_a_not_graded_mark_is_labelled_not_graded():
    for status in ("INCONCLUSIVE", "PARTIAL"):
        document = copy.deepcopy(INCONCLUSIVE)
        document["integrity"]["run"]["test_system_status"] = status
        assert "aria-label='Run Integrity, not graded'" in _mark_summary(_front(document))
    assert "not graded" not in _mark_summary(_front(copy.deepcopy(COMPLETED)))
