"""The Markdown report and PR comment name the evaluators that contributed (#55).

Built from each evaluator result's descriptor: its title, plus its version when
known. Problems are mentioned only when an evaluator reported some. A bundle with no
evaluator entries renders exactly as before.
"""

import copy

from provenance_snapshot import legacy_provenance
import json
from pathlib import Path

from livingproof_capability_report.core import render
from test_sections import ROBOTS, bundle, report

HERE = Path(__file__).parent
# The scenario evaluator result from the published G1 playground run 43830552305.
SCENARIO = json.loads((HERE / "fixtures/evaluator-result-scenario.json").read_text())


def _second(findings=()):
    other = copy.deepcopy(SCENARIO)
    other["evaluator"] = {"id": "example-safety", "version": "0.2.0", "display_name": "Safety"}
    other["descriptor"] = {
        "title": "Safety observer",
        "purpose": "Notes anything unsafe in the trial.",
        "version": "0.2.0",
        "tier": "observation",
        "findings": [{"text": text} for text in findings],
    }
    return other


def _with(data, *documents):
    data = copy.deepcopy(data)
    for result in data["results"]:
        result["evaluator_results"] = [copy.deepcopy(d) for d in documents]
    return data


def _markdown(data):
    return render(report(data), "markdown")


def _evaluator_lines(text):
    return [line for line in text.splitlines() if line.startswith("**Evaluators:**")]


def test_one_evaluator_is_named_with_its_version():
    text = _markdown(_with(bundle("g1"), SCENARIO))
    version = SCENARIO["descriptor"]["version"]
    assert _evaluator_lines(text) == [f"**Evaluators:** Scenario {version}"]
    assert "problem" not in _evaluator_lines(text)[0]


def test_two_evaluators_are_both_named_and_problems_only_when_reported():
    quiet = _markdown(_with(bundle("g1"), SCENARIO, _second()))
    version = SCENARIO["descriptor"]["version"]
    assert _evaluator_lines(quiet) == [
        f"**Evaluators:** Scenario {version} · Safety observer 0.2.0"
    ]
    noisy = _markdown(_with(bundle("g1"), SCENARIO, _second(["Brushed the wall at 3.2 s"])))
    # Findings from every trial are grouped by evaluator; the g1 bundle has several trials.
    trials = len(bundle("g1")["results"])
    problems = "1 problem" if trials == 1 else f"{trials} problems"
    assert _evaluator_lines(noisy) == [
        f"**Evaluators:** Scenario {version} · Safety observer 0.2.0 ({problems})"
    ]


def test_a_version_that_is_not_known_is_left_out():
    unversioned = copy.deepcopy(SCENARIO)
    unversioned["descriptor"].pop("version", None)
    unversioned["evaluator"].pop("version", None)
    assert _evaluator_lines(_markdown(_with(bundle("g1"), unversioned))) == [
        "**Evaluators:** Scenario"
    ]


def test_a_bundle_with_no_evaluator_entries_renders_exactly_as_before():
    for name in ("g1", "go1", "t1"):
        data = bundle(name)
        assert not any(r.get("evaluator_results") for r in data["results"])
        text = _markdown(data)
        assert legacy_provenance(text) == (ROBOTS / f"{name}.md").read_text(encoding="utf-8")
        assert not _evaluator_lines(text)
