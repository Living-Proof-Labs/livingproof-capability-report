"""Reviewer tests for #88: run integrity is a test-system status, never a capability grade (#85)."""

import copy

import pytest
import test_integrity_summary as t

from livingproof_capability_report.evaluators import (
    documents_for_summary,
    resolve_one,
    summary_front,
)


@pytest.mark.parametrize("stored", [t.SUCCESS, t.FAILED], ids=["success", "failed"])
def test_integrity_card_carries_no_grade(stored):
    report = t._report(integrity={"livingproof-run-integrity": copy.deepcopy(stored)})
    summary = report["summaries"][0]
    integrity = [
        doc
        for doc in documents_for_summary(report, summary)
        if doc["evaluator"]["id"] == "livingproof-run-integrity"
    ]
    assert len(integrity) == 1
    assert resolve_one(integrity[0])["grade"] is None

    front = summary_front(report, "")
    assert "% grade" not in front
    assert summary["grade"] == "PASS"
