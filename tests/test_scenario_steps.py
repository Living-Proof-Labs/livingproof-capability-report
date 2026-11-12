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
from livingproof_capability_report.html_theme import success_badge
from livingproof_capability_report.steps import describe_success, durations_by_result, esc
from test_sections import bundle, report
from test_trial_labels import BUNDLE, stored, visible_html

ROBOTS = Path(__file__).parent / "fixtures/robots"
LOSSLESS = "<details class='lossless'>"


def _label(name, check):
    data = bundle(name)
    for item in data["description"]["mission"]["success_criteria"]:
        if item["evaluator"] == check:
            return item["text"]
    raise KeyError(check)


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
    # Step names are the feature spec's success_criteria text, not a built-in glossary.
    criteria = {
        item["evaluator"]: item["text"]
        for item in data["description"]["mission"]["success_criteria"]
    }
    order = [
        (criteria["hallway-lateral-limit"], "60% success", "12 of 20 trials"),
        (criteria["hallway-wall-contact"], "65% success", "13 of 20 trials"),
        (criteria["hallway-exit-reached"], "95% success", "19 of 20 trials"),
        (criteria["hallway-fall"], "100% success", "20 of 20 trials"),
    ]
    positions = []
    for title, rate, count in order:
        block = _step(page, title)
        assert f"<span class='rate'>{rate}</span>" in block
        assert count in block
        positions.append(page.index(title))
        assert f"aria-label='{title}: {rate}'" in block
    assert positions == sorted(positions)
    upright = _step(page, criteria["hallway-fall"])
    assert "visibility='visible'" in upright
    assert "Stored as complete success for every trial." in upright
    assert "visibility='hidden'" in _step(page, criteria["hallway-lateral-limit"])
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
    data = bundle("g1")
    criteria = {
        item["evaluator"]: item["text"]
        for item in data["description"]["mission"]["success_criteria"]
    }
    for title in criteria.values():
        assert "<span class='chip chip-muted'>Close</span>" in _step(page, title)
    lateral, wall = criteria["hallway-lateral-limit"], criteria["hallway-wall-contact"]
    exit_name, fall = criteria["hallway-exit-reached"], criteria["hallway-fall"]
    assert (
        f"{lateral} and {wall} are one trial apart, "
        "so they are not distinguishable from each other." in page
    )
    assert (
        f"{exit_name} and {fall} are one trial apart, "
        "so they are not distinguishable from each other." in page
    )
    small = _visible(render(stored(), "html"))
    assert "<span class='place tie'>=3</span>" in small
    assert "required_passes" not in small[small.index("scenario-steps") : small.index("Steps, by success")]
    assert "pass bar" not in small.lower()


def test_wall_margin_is_clearance_on_a_pass_and_penetration_on_a_fail():
    page = render(report(bundle("g1")), "html")
    criteria = {
        item["evaluator"]: item["text"]
        for item in bundle("g1")["description"]["mission"]["success_criteria"]
    }
    wall = _step(page, criteria["hallway-wall-contact"])
    capped = _row(wall, 1)
    real = _row(wall, 6)
    failed = _row(wall, 4)
    assert "Capped at 0.25 m, not a real measurement" in capped
    assert "Capped, not a real measurement" in capped
    assert "Closest clearance" not in capped
    assert "clearance" not in capped.lower()
    assert "Closest clearance 0.0861 m" in real
    assert "Deepest penetration 0.0361 m at 11.10 s" in failed
    assert "Penetration depth" not in failed
    assert "clearance" not in failed.lower()
    # The time column stays the first contact, which is not the deepest one.
    assert "10.62 s" in failed and "First contact" in failed
    assert "Not met" in failed
    assert "2 contacts (limit 0)" in failed
    lateral = _row(_step(page, criteria["hallway-lateral-limit"]), 1)
    assert "0.2535 m (limit 0.49 m)" in lateral
    assert "Largest offset" in lateral
    assert "Success" in lateral
    missed = _row(_step(page, criteria["hallway-exit-reached"]), 15)
    assert "Not met" in missed
    assert "— (limit 27.00 s)" in missed
    assert "10.44 s" in missed
    assert "First missed" in missed


def test_trial_number_is_the_stored_seed_and_duration_comes_from_the_observation():
    data = bundle("g1")
    data["results"][0]["original_result"]["seed"] = 41
    page = render(report(data), "html")
    assert "<td data-label='Trial'>41</td>" in _step(page, _label("g1", "hallway-lateral-limit"))
    assert page.count("<td data-label='Duration'><span class='cell-value'>—</span>") == 80
    durations = durations_by_result(
        __import__("json").loads((BUNDLE / "manifest.json").read_text()), BUNDLE
    )
    assert durations == {
        "stock-seed-01": 11.5,
        "stock-seed-02": 13.25,
        "stock-seed-03": 8.75,
    }
    observed = render(stored(), "html", observations=durations)
    for text, count in (("11.50 s", 4), ("13.25 s", 4), ("8.75 s", 4)):
        cell = f"<td data-label='Duration'><span class='cell-value'>{text}</span>"
        assert observed.count(cell) == count
    assert "<td data-label='Duration'><span class='cell-value'>12.00 s</span>" not in observed
    rendered = CliRunner().invoke(cli, ["render", str(BUNDLE / "manifest.json"), "--format", "html"])
    assert rendered.exit_code == 0, rendered.output
    assert rendered.output.count("<td data-label='Duration'><span class='cell-value'>11.50 s</span>") == 4
    assert rendered.output.count("<td data-label='Duration'><span class='cell-value'>13.25 s</span>") == 4
    assert rendered.output.count("<td data-label='Duration'><span class='cell-value'>8.75 s</span>") == 4
    assert "<script" not in rendered.output


def test_insufficient_evidence_is_named_and_values_are_escaped():
    data = bundle("g1")
    data["results"][0]["assessments"][1]["status"] = "INSUFFICIENT_EVIDENCE"
    data["results"][0]["assessments"][1]["evaluator"] = "hallway-lateral-limit"
    page = render(report(data), "html")
    row = _row(_step(page, _label("g1", "hallway-lateral-limit")), 1)
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


def _face(passed, total):
    shown = describe_success(passed, total)
    badge = success_badge(
        shown["face"], shown["phrase"], esc, complete=shown["complete"], fill=shown["fill"]
    )
    text = re.search(r"<text[^>]*>([^<]*)</text>", badge).group(1)
    return shown, badge, text


def test_percent_text_is_not_zero_padded_and_a_check_needs_every_trial():
    """0 and 5 are not 00 and 05. 199/200 is not a complete 100."""
    zero, zero_badge, zero_text = _face(0, 20)
    five, five_badge, five_text = _face(1, 20)
    full, full_badge, _full_text = _face(20, 20)
    almost, almost_badge, almost_text = _face(199, 200)
    rare, _rare_badge, rare_text = _face(1, 200)
    assert (zero["face"], zero_text) == ("0%", "0%")
    assert "00%" not in zero_badge and ">00</text>" not in zero_badge
    assert (five["face"], five_text) == ("5%", "5%")
    assert "05%" not in five_badge
    assert full["complete"] and "visibility='visible'" in full_badge
    assert "100% success" == full["phrase"]
    assert almost["face"] == ">99%" and not almost["complete"]
    assert almost_text == "&gt;99%"
    assert "visibility='hidden'" in almost_badge
    assert rare["face"] == "<1%" and rare_text == "&lt;1%"
    # The same words are what the report draws, including the run ring.
    stored_report = report(bundle("g1"))
    stored_report["summaries"][0]["k"] = 199
    stored_report["summaries"][0]["n"] = 200
    page = render(stored_report, "html")
    hero = page[page.index("<div class='run-hero'>") : page.index("<h2>Steps, by success")]
    assert "&gt;99% success" in hero
    assert "199 of 200 trials" in hero
    assert "visibility='visible'" not in hero
    assert "complete success" not in hero
    from livingproof_capability_report.steps import _article

    step = {
        "id": "hallway-fall",
        "name": "Stay upright",
        "kind": "fall",
        "passed": 199,
        "total": 200,
        "version": "1.0.0",
    }
    partial = _article(step, 1, False, False, [], {})
    assert "&gt;99% success" in partial
    assert "199 of 200 trials" in partial
    assert "visibility='visible'" not in partial
    assert "Stored as complete success" not in partial
    done = _article({**step, "passed": 20, "total": 20}, 1, False, False, [], {})
    assert "100% success" in done
    assert "visibility='visible'" in done
    assert "Stored as complete success for every trial." in done
    # A rendered 0% step does not pad the ring.
    quiet = _step(render(report(bundle("t1")), "html"), _label("t1", "hallway-lateral-limit"))
    assert ">0%</text>" in quiet and ">00</text>" not in quiet and "0% success" in quiet


def test_a_missing_step_says_not_assessed_and_depth_omits_an_unknown_time():
    data = bundle("g1")
    data["results"][0]["assessments"] = [
        item for item in data["results"][0]["assessments"] if item["evaluator"] != "hallway-lateral-limit"
    ]
    missing = _row(_step(render(report(data), "html"), _label("g1", "hallway-lateral-limit")), 1)
    assert "Not assessed" in missing
    assert "step-result-neutral'>—</span>" not in missing
    data = bundle("g1")
    for result in data["results"]:
        if result["original_result"]["seed"] != 4:
            continue
        for assessment in result["assessments"]:
            if assessment["evaluator"] != "hallway-wall-contact":
                continue
            for failure in assessment["provenance"]["details"].get("failures") or []:
                failure.pop("t", None)
    untimed = _row(_step(render(report(data), "html"), _label("g1", "hallway-wall-contact")), 4)
    assert "Deepest penetration 0.0361 m" in untimed
    assert "at 11.10 s" not in untimed
    assert "First contact" in untimed
