"""An ERROR integrity status is not shown with the passing tick (#106).

Found by Vera while verifying PR 105: when Run Integrity is ERROR but the report otherwise
passes (the result stores no findings), the collapsed mark still showed the check pip. ERROR
now shows a failing mark with no tick and a matching aria-label. COMPLETED, INCONCLUSIVE and
unknown statuses look as they did after PR 105.
"""

import copy
import json
from pathlib import Path

from livingproof_capability_report.evaluators import summary_front

FIXTURES = Path(__file__).parent / "fixtures/integrity"
FAILED = json.loads((FIXTURES / "failed.json").read_text(encoding="utf-8"))
COMPLETED = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
INCONCLUSIVE = json.loads((FIXTURES / "all-not-applicable.json").read_text(encoding="utf-8"))
SCENARIO = json.loads((FIXTURES / "scenario.json").read_text(encoding="utf-8"))


def _quiet_error() -> dict:
    document = copy.deepcopy(FAILED)
    document["descriptor"]["findings"] = []
    return document


def _front(document: dict) -> str:
    run_id = document["integrity"]["run"]["id"]
    report = {
        "source_bundle": {
            "results": [{"id": "stock-seed-01", "evaluator_results": [copy.deepcopy(SCENARIO)]}],
            "assessment": {"integrity_results": {"livingproof-run-integrity": document}},
        },
        "summaries": [
            {"run_id": run_id, "result_ids": ["stock-seed-01"], "grade": "PASS", "k": 1, "n": 1}
        ],
    }
    return summary_front(report, "<p class='stored-status'>Stored overall status: PASS</p>")


def _mark(front: str) -> str:
    end = front.index("eval-name-full'>Run Integrity</span>")
    start = front.rindex("<summary class='eval-mark", 0, end)
    return front[start : front.index("</summary>", end)]


def test_an_error_mark_has_no_pass_tick_and_a_matching_label():
    front = _front(_quiet_error())
    mark = _mark(front)
    assert "class='pip'" not in mark
    assert "pip-fail" in mark
    assert "aria-label='Run Integrity: error'" in mark
    assert "eval-mark is-quiet is-error" in mark
    assert "satisfied" not in front


def test_a_completed_mark_keeps_its_tick():
    mark = _mark(_front(copy.deepcopy(COMPLETED)))
    assert "class='pip'" in mark
    assert "pip-fail" not in mark
    assert "is-error" not in mark


def test_inconclusive_and_unknown_marks_are_as_after_pr_105():
    for status in ("INCONCLUSIVE", "PARTIAL"):
        document = copy.deepcopy(INCONCLUSIVE)
        document["integrity"]["run"]["test_system_status"] = status
        mark = _mark(_front(document))
        assert "class='pip'" not in mark and "pip-fail" not in mark
        assert "aria-label='Run Integrity, not graded'" in mark
        assert "is-error" not in mark
