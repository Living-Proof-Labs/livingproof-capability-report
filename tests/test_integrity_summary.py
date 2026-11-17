"""Run-level integrity results belong on the evaluator summary (#85).

``source_bundle.assessment.integrity_results`` is keyed by ``evaluator.id``.
The fixtures are the real livingproof-evaluator-result/1.1.0 shape produced by
livingproof-run-integrity v1.0.0: success, failed/inconclusive, absent, and
two run groups so a result is bound to the matching ``run_id`` only.
"""

import copy
import json
from pathlib import Path

from livingproof_capability_report.evaluators import (
    documents_for_summary,
    markdown_line,
    summary_front,
)

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures/integrity"
SUCCESS = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
FAILED = json.loads((FIXTURES / "failed.json").read_text(encoding="utf-8"))
SCENARIO = json.loads((FIXTURES / "scenario.json").read_text(encoding="utf-8"))

RUN_ID = SUCCESS["integrity"]["run"]["id"]
OTHER_RUN_ID = "walk-corner-other-system-20261117T000000Z"
RESULT_ID = "stock-seed-01"


def _visible(page):
    """The marks and panels; these tests never render a lossless JSON dump."""
    return page


def _ids(docs):
    found = []
    for doc in docs:
        evaluator = doc.get("evaluator") if isinstance(doc.get("evaluator"), dict) else {}
        found.append(evaluator.get("id"))
    return found


def _result():
    return {
        "id": RESULT_ID,
        "evaluator_results": [copy.deepcopy(SCENARIO)],
    }


def _summary(run_id, result_ids=None, grade="PASS"):
    return {
        "run_id": run_id,
        "result_ids": list(result_ids or [RESULT_ID]),
        "grade": grade,
        "k": 1,
        "n": 1,
    }


def _report(*, integrity=None, summaries=None, grade="PASS"):
    assessment = {}
    if integrity is not None:
        assessment["integrity_results"] = copy.deepcopy(integrity)
    return {
        "source_bundle": {
            "results": [_result()],
            "assessment": assessment,
        },
        "summaries": summaries
        or [_summary(SUCCESS["integrity"]["run"]["id"] if integrity else RUN_ID, grade=grade)],
    }


def _success_map():
    return {"livingproof-run-integrity": copy.deepcopy(SUCCESS)}


def test_a_successful_integrity_result_is_shown_next_to_scenario():
    report = _report(integrity=_success_map())
    summary = report["summaries"][0]
    docs = documents_for_summary(report, summary)
    assert _ids(docs) == ["livingproof-scenario", "livingproof-run-integrity"]

    front = _visible(summary_front(report, ""))
    assert "--eval-count:2" in front
    assert "eval-name-full'>Scenario</span>" in front
    assert "eval-name-full'>Run Integrity</span>" in front
    assert "1.0.0" in front
    assert "Status: COMPLETED" in front
    assert "100%" in front
    # The capability grade is not replaced by the integrity result; no findings invented.
    assert "Planned trial" not in front
    line = markdown_line(report)
    assert line == "**Evaluators:** Scenario 1.3.0 · Run Integrity 1.0.0"


def test_a_failed_integrity_result_is_shown_and_does_not_change_the_grade():
    report = _report(
        integrity={"livingproof-run-integrity": copy.deepcopy(FAILED)},
        grade="PASS",
    )
    docs = documents_for_summary(report, report["summaries"][0])
    assert _ids(docs) == ["livingproof-scenario", "livingproof-run-integrity"]

    front = _visible(summary_front(report, "<p class='stored-status'>Stored overall status: PASS</p>"))
    assert "eval-name-full'>Run Integrity</span>" in front
    assert "Status: ERROR" in front
    assert "0%" in front or "0.0%" in front
    assert "Planned trial trial-01 has no trial evidence." in front
    assert "Needs attention" in front
    # The stored capability grade is unchanged; integrity stays a test-system status.
    assert "Stored overall status: PASS" in front
    assert "Stored overall status: INCONCLUSIVE" not in front
    assert report["summaries"][0]["grade"] == "PASS"


def test_a_report_with_no_integrity_result_does_not_imply_one_ran():
    report = _report()
    assert "integrity_results" not in report["source_bundle"]["assessment"]
    docs = documents_for_summary(report, report["summaries"][0])
    assert _ids(docs) == ["livingproof-scenario"]

    front = _visible(summary_front(report, ""))
    assert "--eval-count:1" in front
    assert "eval-name-full'>Scenario</span>" in front
    assert "Run Integrity" not in front
    assert "Status: COMPLETED" not in front
    assert markdown_line(report) == "**Evaluators:** Scenario 1.3.0"


def test_an_integrity_result_is_bound_to_the_matching_run_only():
    matching = _summary(RUN_ID, result_ids=[RESULT_ID])
    other = _summary(OTHER_RUN_ID, result_ids=[RESULT_ID])
    report = _report(integrity=_success_map(), summaries=[matching, other])

    assert _ids(documents_for_summary(report, matching)) == [
        "livingproof-scenario",
        "livingproof-run-integrity",
    ]
    assert _ids(documents_for_summary(report, other)) == ["livingproof-scenario"]

    # A second stored result for a different run must not appear on the first.
    second = copy.deepcopy(SUCCESS)
    second["evaluator"] = dict(second["evaluator"])
    second["evaluator"]["id"] = "livingproof-run-integrity-other"
    second["descriptor"] = dict(second["descriptor"])
    second["descriptor"]["title"] = "Other Integrity"
    second["integrity"] = dict(second["integrity"])
    second["integrity"]["run"] = dict(second["integrity"]["run"], id=OTHER_RUN_ID)
    report["source_bundle"]["assessment"]["integrity_results"][
        "livingproof-run-integrity-other"
    ] = second

    assert _ids(documents_for_summary(report, matching)) == [
        "livingproof-scenario",
        "livingproof-run-integrity",
    ]
    assert _ids(documents_for_summary(report, other)) == [
        "livingproof-scenario",
        "livingproof-run-integrity-other",
    ]
