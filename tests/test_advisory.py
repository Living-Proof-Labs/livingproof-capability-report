"""Advisory results stored on the bundle render as peer cards (#136).

Read from ``source_bundle.assessment.advisory_results``, the object keyed by
``evaluator.id`` that capability-verifier#265 is adding. A value is one result
or a list. The caller builds no presentation.
"""

import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import render
from provenance_snapshot import legacy_provenance
from test_sections import ROBOTS, bundle, report, top

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures/advisory"
EXAMPLE = HERE.parent / "examples/bundle"
SCENARIO = json.loads((HERE / "fixtures/integrity/scenario.json").read_text(encoding="utf-8"))
INTEGRITY = json.loads((HERE / "fixtures/integrity/success.json").read_text(encoding="utf-8"))
TABLE_SHA256 = {
    "g1": "63d1fe1a044e8881f6db802dd471f84f61558e11b44a696502757e839185f24a",
    "go1": "3169528e4ac00e8ad35398cb313762e1c1471f8300d21c6c770554f74e4a9100",
    "t1": "641e8b33988bf52274b51f0f2f55f1c74c2c943ac922e2f626c825045f45b745",
}
VENDORED = {
    "result.json": "b1d66c7c005d471972857c9716377d9303245b1a7ff3394ba2758d509898c3e5",
    "notes.txt": "672452afe3c3af41a8580455addb04c6e6696ce19e3117e4446a962fb448d7bc",
}


def load_advisory(name):
    return json.loads((FIXTURES / name / "result.json").read_text(encoding="utf-8"))


def with_advisory(data, mapping):
    data = copy.deepcopy(data)
    data["assessment"]["advisory_results"] = mapping
    return report(data)


def with_peers(data):
    """Scenario and Run Integrity cards, so an advisory peer can be compared to them."""
    data = copy.deepcopy(data)
    data["results"][0]["evaluator_results"] = [copy.deepcopy(SCENARIO)]
    integrity = copy.deepcopy(INTEGRITY)
    integrity["integrity"]["run"]["id"] = data["assessment"]["runs"][0]["run_id"]
    data["assessment"]["integrity_results"] = {"livingproof-run-integrity": integrity}
    return data


def both(data=None):
    """Battery thermal as one result, gait noise as a one-item list under another key."""
    data = bundle("g1") if data is None else data
    return with_advisory(
        data,
        {
            "battery-thermal": load_advisory("battery-thermal"),
            "not-the-id": [load_advisory("gait-noise")],
        },
    )


def _element(page, start, tag):
    open_token = f"<{tag}"
    close_token = f"</{tag}>"
    depth = 0
    index = start
    while index < len(page):
        next_open = page.find(open_token, index)
        next_close = page.find(close_token, index)
        if next_close < 0:
            raise AssertionError(f"unclosed {tag}")
        if next_open != -1 and next_open < next_close:
            depth += 1
            index = next_open + len(open_token)
        else:
            depth -= 1
            index = next_close + len(close_token)
            if depth == 0:
                return page[start:index]
    raise AssertionError(f"unclosed {tag}")


def _card(page, identity):
    anchor = f"id='evaluator-{identity}'"
    at = page.index(anchor)
    details = _element(page, page.rindex("<details", 0, at), "details")
    controls = re.search(r"aria-controls='([^']+)'", details).group(1)
    panel_at = page.index(f"id='{controls}'")
    panel = _element(page, page.rindex("<div", 0, panel_at), "div")
    # The hosted run record includes the lossless bundle. Advisory results live
    # in that bundle, so the comparison is the mark and its own panel.
    stored = panel.find("<div class='stored-run'>")
    if stored >= 0:
        panel = panel[:stored]
    return details + panel


def _grades(page):
    chunks = []
    start = 0
    while True:
        at = page.find("<div class='grade'>", start)
        if at < 0:
            return "".join(chunks)
        chunks.append(_element(page, at, "div"))
        start = at + 1


def test_vendored_battery_thermal_bytes_match_evaluator_v1_10_0():
    root = FIXTURES / "battery-thermal"
    for name, digest in VENDORED.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    note = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "v1.10.0" in note
    assert "d46062a9300611e32ad76749e67a8f035489ebce" in note
    for digest in VENDORED.values():
        assert digest in note


def test_reads_advisory_results_from_the_bundle():
    page = render(both(), "html")
    assert "id='evaluator-battery-thermal'" in page
    assert "id='evaluator-gait-noise'" in page
    assert "id='evaluator-not-the-id'" not in page
    assert "Advisory observations only; does not change the grade." in page

    misplaced = copy.deepcopy(bundle("g1"))
    misplaced["assessment"]["integrity_results"] = {
        "battery-thermal": load_advisory("battery-thermal")
    }
    assert "Battery thermal" not in top(render(report(misplaced), "html"))


@pytest.mark.parametrize("name", ["battery-thermal", "gait-noise"])
def test_each_advisory_card_shows_its_own_descriptor_title_purpose_and_summary(name):
    document = load_advisory(name)
    descriptor = document["descriptor"]
    page = render(both(), "html")
    card = _card(page, document["evaluator"]["id"])
    assert descriptor["title"] in card
    assert descriptor["purpose"] in card
    assert document["advisory"]["summary"] in card or document["advisory"]["summary"].replace(
        "&", "&amp;"
    ) in card
    other = "Gait noise" if name == "battery-thermal" else "Battery thermal"
    assert other not in card


def test_card_text_comes_from_the_descriptor_and_payload():
    document = load_advisory("gait-noise")
    page = render(both(), "html")
    card = _card(page, "gait-noise")
    assert "Gait noise" in card
    assert document["descriptor"]["purpose"] in card
    assert document["advisory"]["summary"] in card
    assert document["advisory"]["details"] in card
    assert "0.2.0" in card
    assert "Noise meter" not in card
    assert "9.9.9" not in card
    battery = _card(page, "battery-thermal")
    assert "href='notes.txt'" in battery
    assert "The notes file lists the peak temperature" in battery
    assert "notes.txt" not in card


def test_two_advisory_evaluators_render_as_separate_cards_and_lines():
    stored = both()
    page = render(stored, "html")
    assert page.index("id='evaluator-battery-thermal'") < page.index("id='evaluator-gait-noise'")
    markdown = render(stored, "markdown")
    text = render(stored, "table")
    assert markdown.splitlines().count(
        "**Advisory:** Battery thermal 0.1.0 · Pack & cell temperatures stayed within the recorded range."
    ) == 1
    assert markdown.splitlines().count(
        "**Advisory:** Gait noise 0.2.0 · Footfall noise stayed within the recorded band."
    ) == 1
    assert text.splitlines().count(
        "Advisory: Battery thermal 0.1.0 · Pack & cell temperatures stayed within the recorded range."
    ) == 1
    assert text.splitlines().count(
        "Advisory: Gait noise 0.2.0 · Footfall noise stayed within the recorded band."
    ) == 1


def test_grade_and_sibling_cards_stay_byte_identical():
    base_data = with_peers(bundle("g1"))
    base = report(base_data)
    advised = with_advisory(
        base_data,
        {
            "battery-thermal": load_advisory("battery-thermal"),
            "gait-noise": [load_advisory("gait-noise")],
        },
    )
    assert base["summaries"] == advised["summaries"]
    before = render(base, "html")
    after = render(advised, "html")
    assert _grades(before) == _grades(after)
    assert _grades(before)
    for identity in ("livingproof-scenario", "livingproof-run-integrity"):
        assert _card(before, identity) == _card(after, identity)
    assert "Battery thermal" in after

    def without_advisory_lines(text):
        kept = [
            line
            for line in text.splitlines()
            if not line.startswith("**Advisory:**") and not line.startswith("Advisory: ")
        ]
        return "\n".join(kept) + "\n"

    assert without_advisory_lines(render(advised, "markdown")) == render(base, "markdown")
    assert without_advisory_lines(render(advised, "table")) == render(base, "table")


@pytest.mark.parametrize("name", ["g1", "go1", "t1"])
def test_bundle_without_advisory_results_matches_existing_fixtures(name):
    stored = report(bundle(name))
    assert "advisory_results" not in stored["source_bundle"]["assessment"]
    html = legacy_provenance(top(render(stored, "html")) + "\n")
    markdown = legacy_provenance(render(stored, "markdown"))
    assert html == legacy_provenance((ROBOTS / f"{name}.html").read_text(encoding="utf-8"))
    assert markdown == legacy_provenance((ROBOTS / f"{name}.md").read_text(encoding="utf-8"))
    table = render(stored, "table")
    assert hashlib.sha256(table.encode()).hexdigest() == TABLE_SHA256[name]
    assert "Advisory:" not in table and "**Advisory:**" not in markdown


def test_source_does_not_name_health_except_the_existing_tier():
    root = Path(__file__).resolve().parents[1] / "src" / "livingproof_capability_report"
    found = []
    for path in sorted(root.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"health", line, re.IGNORECASE):
                found.append((path.name, number, line.strip()))
    assert found == [
        ("evaluators.py", 32, '"health_finding",'),
        ("evaluators.py", 39, '"health_finding": "Health finding",'),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "Pack <hot>"),
        ("details", "line\nbreak"),
        ("summary", "bad\x7ftext"),
    ],
)
def test_marked_up_advisory_text_is_refused(field, value):
    document = load_advisory("battery-thermal")
    document["advisory"][field] = value
    stored = with_advisory(bundle("g1"), {"battery-thermal": document})
    for fmt in ("html", "markdown", "table"):
        with pytest.raises(ValueError, match="bounded plain text"):
            render(stored, fmt)


def test_clashing_evaluator_id_is_refused():
    document = load_advisory("battery-thermal")
    document["evaluator"]["id"] = "livingproof-scenario"
    stored = with_advisory(
        with_peers(bundle("g1")),
        {"livingproof-scenario": document},
    )
    for fmt in ("html", "markdown", "table"):
        with pytest.raises(ValueError, match="cannot replace"):
            render(stored, fmt)


def test_cli_render_shows_each_advisory_result(tmp_path):
    dest = tmp_path / "bundle"
    shutil.copytree(EXAMPLE, dest)
    manifest = dest / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["assessment"]["advisory_results"] = {
        "battery-thermal": load_advisory("battery-thermal"),
        "gait-noise": load_advisory("gait-noise"),
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    runner = CliRunner()
    expected = {
        "html": "eval-name-full'>Battery thermal</span>",
        "markdown": "**Advisory:** Battery thermal 0.1.0",
        "table": "Advisory: Gait noise 0.2.0",
    }
    for fmt, needle in expected.items():
        result = runner.invoke(cli, ["render", str(manifest), "--format", fmt])
        assert result.exit_code == 0, result.output
        assert needle in result.output
        assert "Gait noise" in result.output
        assert "Battery thermal" in result.output
    marked = copy.deepcopy(data)
    marked["assessment"]["advisory_results"]["battery-thermal"]["advisory"]["summary"] = "x<y"
    manifest.write_text(json.dumps(marked), encoding="utf-8")
    refused = runner.invoke(cli, ["render", str(manifest), "--format", "html"])
    assert refused.exit_code != 0
    assert "bounded plain text" in refused.output
    assert "<script" not in refused.output
    assert "x<y" not in refused.stdout
