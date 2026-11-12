"""Scenario-step success rings in the HTML report.

Rates are the share of stored PASS assessments. The G1 fixture is 12, 13, 19 and 20
passes out of 20: lateral 60%, wall 65%, exit 95%, fall 100%. The run ring uses the
stored k of n. The stored Wilson interval is muted text under that rate, not a headline
and not a ring. Markdown keeps its interval column; those snapshots do not change.
"""

import re
from pathlib import Path

from click.testing import CliRunner

from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import render
from livingproof_capability_report.hallway import _interval
from livingproof_capability_report.steps import durations_by_result
from test_sections import bundle, report
from test_trial_labels import BUNDLE, stored, visible_html

ROBOTS = Path(__file__).parent / "fixtures/robots"
LOSSLESS = "<details class='lossless'>"


def _visible(page):
    return page[: page.index(LOSSLESS)]


def _step(page, title):
    start = page.rindex("<article class='step'>", 0, page.index(title))
    return page[start : page.index("</article>", start) + len("</article>")]


def _row(block, trial):
    token = f"<td data-label='Trial'>{trial}</td>"
    start = block.rindex("<tr", 0, block.index(token))
    return block[start : block.index("</tr>", start) + len("</tr>")]


def _rings(page):
    return re.findall(r"<svg class='success-ring'[^>]*aria-label='([^']*)'", page)


def test_g1_fixture_step_rates_are_60_65_95_and_100():
    """Counted from results[].assessments on the shipped G1 bundle, not from the mock."""
    data = bundle("g1")
    counts = {}
    for result in data["results"]:
        for assessment in result["assessments"]:
            counts.setdefault(assessment["evaluator"], {"PASS": 0, "n": 0})
            counts[assessment["evaluator"]]["n"] += 1
            if assessment["status"] == "PASS":
                counts[assessment["evaluator"]]["PASS"] += 1
    assert {name: (item["PASS"], round(100 * item["PASS"] / item["n"])) for name, item in counts.items()} == {
        "hallway-lateral-limit": (12, 60),
        "hallway-wall-contact": (13, 65),
        "hallway-exit-reached": (19, 95),
        "hallway-fall": (20, 100),
    }
    page = _visible(render(report(data), "html"))
    order = [
        ("Stay near centreline", "60% success", "12 of 20 trials"),
        ("No wall contact", "65% success", "13 of 20 trials"),
        ("Exit reached", "95% success", "19 of 20 trials"),
        ("Stay upright", "100% success", "20 of 20 trials"),
    ]
    positions = []
    for title, rate, count in order:
        block = _step(page, title)
        assert f"<span class='rate'>{rate}</span>" in block
        assert count in block
        positions.append(page.index(title))
        assert f"aria-label='{title}: {rate}'" in block
    assert positions == sorted(positions)
    upright = _step(page, "Stay upright")
    assert "visibility='visible'" in upright
    assert "Stored as complete success for every trial." in upright
    assert "visibility='hidden'" in _step(page, "Stay near centreline")
    assert "<p class='pct'>60% success</p>" in page
    assert "12 of 20 trials" in page
    assert "Stored overall status: FAIL" in page


def test_headline_and_rings_do_not_carry_the_wilson_interval():
    page = render(report(bundle("g1")), "html")
    verdict = page[page.index("<section class='verdict'") : page.index("<section id='summary'>")]
    summary = page[page.index("<section id='summary'>") : page.index("<section class='run-detail'>")]
    assert "Wilson" not in verdict and "95% interval" not in verdict and "39–78%" not in verdict
    assert "<dt>Wilson" not in summary and "39–78%" not in summary
    for label in _rings(page):
        assert "success" in label
        assert "interval" not in label.lower() and "wilson" not in label.lower() and "–" not in label
    stored_report = report(bundle("g1"))
    text = (
        "95% confidence range for the success rate: "
        f"{_interval(stored_report['summaries'][0]['wilson95'])}"
    )
    assert text == "95% confidence range for the success rate: 39–78%"
    assert f"<p class='confidence'>{text}</p>" in page
    # Under the rate, outside the ring. The spec's stored grading sentence may still say Wilson.
    hero = page[page.index("<div class='run-hero'>") : page.index("<p class='confidence'>")]
    assert "39–78%" not in hero and "Wilson" not in hero
    stored_report["summaries"][0].pop("wilson95")
    quiet = render(stored_report, "html")
    assert "confidence range" not in quiet
    assert "39–78%" not in _visible(quiet)


def test_close_labels_mark_steps_one_trial_apart_and_ties_share_a_place():
    page = _visible(render(report(bundle("g1")), "html"))
    for title in ("Stay near centreline", "No wall contact", "Exit reached", "Stay upright"):
        assert "<span class='chip chip-muted'>Close</span>" in _step(page, title)
    assert (
        "Stay near centreline and No wall contact are one trial apart, "
        "so they are not distinguishable from each other." in page
    )
    assert (
        "Exit reached and Stay upright are one trial apart, "
        "so they are not distinguishable from each other." in page
    )
    small = _visible(render(stored(), "html"))
    assert "<span class='place tie'>=3</span>" in small
    assert "required_passes" not in small[small.index("scenario-steps") : small.index("Scenario steps")]
    assert "pass bar" not in small.lower()


def test_wall_margin_is_clearance_on_a_pass_and_penetration_on_a_fail():
    page = render(report(bundle("g1")), "html")
    wall = _step(page, "No wall contact")
    capped = _row(wall, 1)
    real = _row(wall, 6)
    failed = _row(wall, 4)
    assert "Capped at 0.25 m, not a real measurement" in capped
    assert "Capped, not a real measurement" in capped
    assert "Closest clearance" not in capped
    assert "clearance" not in capped.lower()
    assert "Closest clearance 0.0861 m" in real
    assert "Penetration depth 0.0361 m" in failed
    assert "clearance" not in failed.lower()
    assert "Not met" in failed
    assert "2 contacts (limit 0)" in failed
    assert "First contact" in failed
    lateral = _row(_step(page, "Stay near centreline"), 1)
    assert "0.2535 m (limit 0.49 m)" in lateral
    assert "Largest offset" in lateral
    assert "Success" in lateral
    missed = _row(_step(page, "Exit reached"), 15)
    assert "Not met" in missed
    assert "— (limit 27.00 s)" in missed
    assert "10.44 s" in missed
    assert "First missed" in missed


def test_trial_number_is_the_stored_seed_and_duration_comes_from_the_observation():
    data = bundle("g1")
    data["results"][0]["original_result"]["seed"] = 41
    page = render(report(data), "html")
    assert "<td data-label='Trial'>41</td>" in _step(page, "Stay near centreline")
    assert page.count("<td data-label='Duration'><span class='cell-value'>—</span>") == 80
    durations = durations_by_result(
        __import__("json").loads((BUNDLE / "manifest.json").read_text()), BUNDLE
    )
    assert set(durations.values()) == {12.0}
    cell = "<td data-label='Duration'><span class='cell-value'>12.00 s</span>"
    observed = render(stored(), "html", observations=durations)
    assert observed.count(cell) == 12
    rendered = CliRunner().invoke(cli, ["render", str(BUNDLE / "manifest.json"), "--format", "html"])
    assert rendered.exit_code == 0, rendered.output
    assert rendered.output.count(cell) == 12
    assert "<script" not in rendered.output


def test_insufficient_evidence_is_named_and_values_are_escaped():
    data = bundle("g1")
    data["results"][0]["assessments"][1]["status"] = "INSUFFICIENT_EVIDENCE"
    data["results"][0]["assessments"][1]["evaluator"] = "hallway-lateral-limit"
    page = render(report(data), "html")
    row = _row(_step(page, "Stay near centreline"), 1)
    assert "Insufficient evidence" in row
    assert "Not met" not in row
    data = bundle("g1")
    data["results"][0]["assessments"][0]["evaluator"] = "<script>alert(1)</script>"
    escaped = render(report(data), "html")
    assert "<script>" not in escaped
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in escaped


def test_no_pass_bar_without_required_passes_and_markdown_snapshots_stay():
    data = bundle("g1")
    for result in data["results"]:
        result["provenance"]["plan"].pop("required_passes")
    page = _visible(render(report(data), "html"))
    block = page[page.index("scenario-steps") : page.index("<section class='verdict'")]
    assert "required_passes" not in block
    assert "k-of-n" not in block
    assert "<p class='pct'>60% success</p>" in block
    full = render(report(bundle("g1")), "html")
    assert "<span class='nowrap'>18 of 20</span>" in full
    assert "required_passes" in full
    for name in ("g1", "go1", "t1"):
        markdown = render(report(bundle(name)), "markdown")
        assert markdown == (ROBOTS / f"{name}.md").read_text(encoding="utf-8")
        assert "| 95% interval |" in markdown
    # Evidence 2.0.0 still must not say "seed" in reader-visible HTML.
    assert "seed" not in visible_html(render(stored(), "html")).lower()
