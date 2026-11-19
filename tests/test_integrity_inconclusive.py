"""An INCONCLUSIVE run reads as not graded, with no percentage (#104).

livingproof-evaluator#38 / PR 51, result format 1.2.0: when no check applies the
run is INCONCLUSIVE with no percentage. The fixture is PR 51's
examples/integrity/all-not-applicable/result.json. A 1.x minor may add run
statuses, and a consumer treats any status it does not recognise as not graded.
"""

import copy
import json
from pathlib import Path

from livingproof_capability_report.evaluators import summary_front

FIXTURES = Path(__file__).parent / "fixtures/integrity"
INCONCLUSIVE = json.loads((FIXTURES / "all-not-applicable.json").read_text(encoding="utf-8"))
SCENARIO = json.loads((FIXTURES / "scenario.json").read_text(encoding="utf-8"))
COMPLETED = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
RUN_ID = INCONCLUSIVE["integrity"]["run"]["id"]
RESULT_ID = "stock-seed-01"
COPY = "Not graded"


def _front(document, grade="PASS"):
    report = {
        "source_bundle": {
            "results": [{"id": RESULT_ID, "evaluator_results": [copy.deepcopy(SCENARIO)]}],
            "assessment": {"integrity_results": {"livingproof-run-integrity": document}},
        },
        "summaries": [
            {
                "run_id": document["integrity"]["run"]["id"],
                "result_ids": [RESULT_ID],
                "grade": grade,
                "k": 1,
                "n": 1,
            }
        ],
    }
    return summary_front(report, "<p class='stored-status'>Stored overall status: PASS</p>")


def _panel(front):
    start = front.index("eval-name-full'>Run Integrity</span>")
    return front[start:]


def test_the_fixture_is_the_pr51_shape():
    run = INCONCLUSIVE["integrity"]["run"]
    assert INCONCLUSIVE["format"] == "livingproof-evaluator-result/1.2.0"
    assert run["test_system_status"] == "INCONCLUSIVE"
    assert "percentage" not in run


def test_an_inconclusive_run_shows_the_label_and_copy_and_no_percentage():
    front = _front(copy.deepcopy(INCONCLUSIVE))
    assert "Status: INCONCLUSIVE" in front
    assert "Not graded: no integrity check applied to this run." in front
    assert "%</p>" not in _panel(front)
    # The stored capability grade is unchanged and is not shown as a failure.
    assert "Stored overall status: PASS" in front
    assert "Needs attention" not in front
    assert "satisfied" not in front


def test_an_unrecognised_status_is_shown_and_not_graded():
    document = copy.deepcopy(INCONCLUSIVE)
    document["format"] = "livingproof-evaluator-result/1.3.0"
    document["integrity"]["run"]["test_system_status"] = "PARTIAL"
    front = _front(document)
    assert "Status: PARTIAL" in front
    assert "Not graded: this report does not recognise the status." in front
    assert "Needs attention" not in front
    assert "satisfied" not in front


def test_recognised_statuses_get_no_not_graded_copy():
    front = _front(copy.deepcopy(COMPLETED))
    assert "Status: COMPLETED" in front
    assert COPY not in front
