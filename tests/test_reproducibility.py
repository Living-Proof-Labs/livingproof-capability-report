"""Compared repeats are one outcome plus the stored statement.

Fixtures are capability-verifier output at 209db38c3c7b14760cd969a370be46722f01dbe6
(pull request 85). ``identical``, ``disagreeing`` and ``single`` were exported by
``tools/verify_hallway.py --bundle-version 1.1.0`` from
``tests/fixtures/hallway/evidence-2.0.0``. The disagreement edits trial 2 and sets
the finding the way ``test_a_reproducibility_finding_is_not_a_robot_fail`` does.
The single trial sets ``compared`` false the way ``test_one_trial_is_not_a_comparison``
does. ``seeded`` is that commit's 1.0.0 plan from ``test_plan_comes_from_evidence``
(seeds 4, 5 and 6, seed 5 past the lateral limit). ``pause`` is
``Aggregator.aggregate`` on the released pause result plus that evidence record,
as ``test_compared_repeats_aggregate_for_a_pause_capability`` does. ``robot-fail``
is that commit's ``test_a_robot_fail_stays_a_robot_fail_beside_the_finding``:
trial 2's lateral value is 0.62 m and the same reproducibility finding is set,
so the grade is FAIL. The hallway
bundles carry robot-capability-specs ``description.json`` at d677bd9
(sha256 74413a9e7e00d722af5ac63a511d3d7df7619381addf244693af965253eb239c).
"""

import json
import re
from html import unescape
from pathlib import Path

from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.core import load_bundle, render
from livingproof_capability_report.narrative import _interval

FIXTURES = Path(__file__).parent / "fixtures/repeats"
HALLWAY = Path(__file__).parent / "fixtures/hallway-2.0.0"
LOSSLESS = "<details class='lossless'>"
DISCLOSURE = "<details class='eval-disclosure'"
RATE = re.compile(r"\d+ successes?, \d+%")
RING = re.compile(r"success-ring")
RANGE = "95% confidence range"
NOT_STORED = "Success rate not stored"


def _report(name):
    return report_from_bundle(load_bundle(FIXTURES / name / "manifest.json"))


def _run(name):
    bundle = json.loads((FIXTURES / name / "manifest.json").read_text())
    return bundle["assessment"]["runs"][0]


def _visible(page):
    page = page[: page.index(LOSSLESS)]
    page = re.sub(r"<style\b[^>]*>.*?</style>", "", page, flags=re.DOTALL)
    return unescape(re.sub(r"<[^>]+>", "\n", page))


def _face(page):
    return page[: page.index(DISCLOSURE)]


def _details(page):
    return page[page.index(DISCLOSURE) : page.index(LOSSLESS)]


def test_summary_keeps_reproducibility_only_when_the_assessment_has_it():
    identical = _report("identical")["summaries"][0]
    stored = _run("identical")["reproducibility"]
    assert identical["reproducibility"] == stored
    assert identical["k"] is None and identical["n"] is None
    assert identical["wilson95"] == [None, None]
    seeded = _report("seeded")["summaries"][0]
    assert "reproducibility" not in seeded
    assert (seeded["k"], seeded["n"], seeded["grade"]) == (2, 3, "FAIL")
    older = report_from_bundle(load_bundle(HALLWAY / "manifest.json"))["summaries"][0]
    assert "reproducibility" not in older
    assert older["k"] == 1 and older["n"] == 3


def test_identical_repeats_show_the_statement_and_no_rate():
    report = _report("identical")
    statement = report["summaries"][0]["reproducibility"]["statement"]
    assert statement == "3 of 3 repeats agree"
    page = render(report, "html")
    face, details, visible = _face(page), _details(page), _visible(page)
    markdown = render(report, "markdown")
    for where in (face, details, markdown):
        assert statement in where
    assert "Stored overall status: PASS" in face
    assert "<p class='assessment-failure'" not in face
    assert "<section class='verdict'" in details
    assert f"<li>{statement}</li>" in details
    assert "3 repeats" in markdown
    assert "N=" not in markdown and "N=" not in visible
    for banned in (NOT_STORED, RANGE, "successes,", "% success", "100%"):
        assert banned not in visible, banned
    assert RATE.search(visible) is None
    assert RING.search(face) is None and RING.search(details) is None
    assert "Steps, by success" not in details
    assert ">Steps</h2>" in details
    assert "hallway-exit-reached · v1.0.0" in details
    assert "3 successes, 100%" not in details


def test_disagreement_is_called_out_and_the_differing_repeats_stay_closed():
    report = _report("disagreeing")
    block = report["summaries"][0]["reproducibility"]
    detail = block["finding"]["detail"]
    assert report["summaries"][0]["grade"] == "INSUFFICIENT_EVIDENCE"
    assert "statement" not in block and block["finding"]["kind"] == "test-system"
    page = render(report, "html")
    face, details, visible = _face(page), _details(page), _visible(page)
    callout = f"<p class='assessment-failure'>Overall INSUFFICIENT_EVIDENCE. {detail}</p>"
    assert callout in face
    assert face.index(callout) < face.index("Evaluators")
    opened = page.index(DISCLOSURE)
    assert " open" not in page[opened : opened + 90]
    for row in block["differing"]:
        assert row["sha256"] not in face
        assert row["sha256"] in details
        assert f"index {row['index']}" in details
        assert row["outcome"] in details
    assert "Differing repeats" in details and "Differing repeats" not in face
    shown = page[: page.index(LOSSLESS)]
    for banned in (NOT_STORED, RANGE, "successes,", "% success", "repeats agree"):
        assert banned not in visible, banned
    assert RATE.search(visible) is None
    assert RING.search(shown) is None
    markdown = render(report, "markdown")
    assert detail in markdown
    verdict = next(line for line in markdown.splitlines() if line.startswith("unitree"))
    assert verdict.endswith("FAIL.") and not verdict.endswith("..")
    assert "N=" not in markdown and "3 repeats" in markdown
    assert "| — |" in markdown


def test_a_single_trial_keeps_the_stored_rate():
    report = _report("single")
    summary = report["summaries"][0]
    assert "reproducibility" not in summary
    assert (summary["k"], summary["n"], summary["required_passes"]) == (1, 1, 1)
    interval = _run("single")["interval"]
    assert summary["wilson95"] == [interval["lower"], interval["upper"]]
    page = render(report, "html")
    visible = _visible(page)
    assert "1 success, 100%" in visible
    assert "100% required" in visible
    assert f"95% confidence range for the success rate: {_interval(summary['wilson95'])}" in page
    assert "repeats agree" not in visible
    assert NOT_STORED not in visible
    markdown = render(report, "markdown")
    assert "1 success, 100%" in markdown
    assert "N=1" in markdown
    assert "repeats agree" not in markdown


def test_a_seeded_run_keeps_k_of_n_as_a_percentage():
    report = _report("seeded")
    summary = report["summaries"][0]
    assert "reproducibility" not in summary
    assert summary["wilson95"] == [
        _run("seeded")["interval"]["lower"],
        _run("seeded")["interval"]["upper"],
    ]
    page = render(report, "html")
    visible = _visible(page)
    assert "2 successes, 67%" in visible
    assert "% success" in visible
    assert f"95% confidence range for the success rate: {_interval(summary['wilson95'])}" in page
    assert "repeats agree" not in visible
    assert NOT_STORED not in visible
    markdown = render(report, "markdown")
    assert "2 successes, 67%" in markdown
    assert "N=3" in markdown
    assert "repeats" not in markdown


def test_evidence_without_reproducibility_matches_the_current_wording():
    """Older bundles have numeric k and n and no reproducibility key."""
    report = report_from_bundle(load_bundle(HALLWAY / "manifest.json"))
    assert "reproducibility" not in report["summaries"][0]
    page = render(report, "html")
    visible = _visible(page)
    markdown = render(report, "markdown")
    assert "1 success, 33%" in visible
    assert "100% required" in page
    assert "repeats agree" not in visible and "repeats agree" not in markdown
    assert NOT_STORED not in visible
    assert "N=3" in markdown and " repeats" not in markdown


def test_a_pause_run_uses_the_same_statement_and_names_no_scenario():
    report = _report("pause")
    statement = report["summaries"][0]["reproducibility"]["statement"]
    assert report["summaries"][0]["capability"] == "pause"
    page = render(report, "html")
    visible = _visible(page)
    assert statement in _face(page) and statement in _details(page)
    assert "hallway" not in visible.lower()
    assert "hallway" not in render(report, "markdown").lower()
    for banned in (NOT_STORED, RANGE, "successes,", "% success"):
        assert banned not in visible, banned
    assert RING.search(page[: page.index(LOSSLESS)]) is None


def _stored(name):
    return json.loads((FIXTURES / name / "manifest.json").read_text())


def _with_verified_evidence(bundle):
    state = {
        result["id"]: {item["id"]: "verified" for item in result["evidence"]}
        for result in bundle["results"]
    }
    return report_from_bundle({"bundle": bundle, "evidence_state": state})


def test_every_format_of_a_compared_run_names_the_statement_and_no_rate():
    """HTML, markdown, JSON and the terminal line carry the statement. CSV is per decision."""
    report = _report("identical")
    statement = report["summaries"][0]["reproducibility"]["statement"]
    rendered = {fmt: render(report, fmt) for fmt in ("html", "markdown", "json", "csv", "table")}
    visible = _visible(rendered["html"])
    assert statement in visible
    assert statement in rendered["markdown"]
    assert statement in rendered["json"]
    assert f"PASS. {statement}." in rendered["table"]
    assert statement not in rendered["csv"]
    assert "PASS" in rendered["csv"]
    for fmt, text in rendered.items():
        body = visible if fmt == "html" else text
        for banned in (NOT_STORED, RANGE, "3 successes, 100%"):
            assert banned not in body, (fmt, banned)


def test_a_compared_run_stays_beside_a_seeded_rate():
    """One bundle can hold both. The seeded run keeps its percentage; the repeats do not borrow it."""
    identical, seeded = _stored("identical"), _stored("seeded")
    bundle = {
        "schema_version": "1.1.0",
        "producer": identical["producer"],
        "description": identical["description"],
        "results": identical["results"] + seeded["results"],
        "assessment": {
            "format": identical["assessment"]["format"],
            "policy": identical["assessment"]["policy"],
            "aggregation": identical["assessment"]["aggregation"],
            "decisions": identical["assessment"]["decisions"] + seeded["assessment"]["decisions"],
            "runs": identical["assessment"]["runs"] + seeded["assessment"]["runs"],
        },
    }
    report = _with_verified_evidence(bundle)
    assert report["summaries"][0]["reproducibility"]["statement"] == "3 of 3 repeats agree"
    assert "reproducibility" not in report["summaries"][1]
    assert (report["summaries"][1]["k"], report["summaries"][1]["n"]) == (2, 3)
    page = render(report, "html")
    starts = [match.start() for match in re.finditer("<h2>This run</h2>", page)]
    assert len(starts) == 2
    compared = page[starts[0] : starts[1]]
    seeded_card = page[starts[1] : page.index("<section class='verdict'")]
    assert "3 of 3 repeats agree" in compared and "success-ring" not in compared
    assert "2 successes, 67%" not in compared and NOT_STORED not in compared
    assert "2 successes, 67%" in seeded_card and "success-ring" in seeded_card
    assert "3 of 3 repeats agree" not in seeded_card
    assert NOT_STORED not in _visible(page)


def test_a_robot_fail_stays_a_fail_beside_the_finding():
    report = _report("robot-fail")
    summary = report["summaries"][0]
    detail = summary["reproducibility"]["finding"]["detail"]
    assert summary["grade"] == "FAIL"
    assert summary["k"] is None and summary["wilson95"] == [None, None]
    assert "statement" not in summary["reproducibility"]
    assert [row["index"] for row in summary["reproducibility"]["differing"]] == [1, 2, 3]
    page = render(report, "html")
    face, visible = _face(page), _visible(page)
    assert f"<p class='assessment-failure'>Overall FAIL. {detail}</p>" in face
    for row in summary["reproducibility"]["differing"]:
        assert row["sha256"] not in face
        assert row["sha256"] in _details(page)
    for banned in (NOT_STORED, RANGE, "successes,", "% success", "repeats agree"):
        assert banned not in visible, banned
    assert RING.search(page[: page.index(LOSSLESS)]) is None
    markdown = render(report, "markdown")
    assert detail in markdown and "does not pass" in markdown
    assert "successes," not in markdown and NOT_STORED not in markdown
    table = render(report, "table")
    assert "overall FAIL." in table
    assert NOT_STORED not in table and "successes," not in table
