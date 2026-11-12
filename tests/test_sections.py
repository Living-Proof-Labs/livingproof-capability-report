"""Reporter #39 header and #40 context card, failure section and trial grid.

``fixtures/robots/*-bundle.json.gz`` are real bundle 1.1.0 manifests exported by
capability-verifier v1.12.0 (662f390, specs v1.9.0 d677bd9 locked) from 20-seed
livingproof-sim-mujoco v1.8.3 runs of G1 stock, Go1 playground and T1 stock. The trial
evidence files are not shipped (the evidence digest checks are covered by
test_assessed.py), so these tests mark them verified. Set LIVINGPROOF_UPDATE_SNAPSHOTS=1
to rewrite the snapshots after an intended change.
"""

import copy
import gzip
import json
import os
import re
import shutil
from html import escape
from pathlib import Path

import pytest

from livingproof_capability_report import assessed
from livingproof_capability_report.core import digest, load_bundle, render

HERE = Path(__file__).parent
ROBOTS = HERE / "fixtures/robots"
UPDATE = os.environ.get("LIVINGPROOF_UPDATE_SNAPSHOTS") == "1"


def bundle(name):
    return json.loads(gzip.decompress((ROBOTS / f"{name}-bundle.json.gz").read_bytes()))


def report(data):
    state = {r["id"]: {e["id"]: "verified" for e in r["evidence"]} for r in data["results"]}
    return assessed.report_from_bundle({"bundle": data, "evidence_state": state})


def top(page):
    """The visible page: everything before the collapsed lossless report."""
    return page[: page.index("<details class='lossless'>")]


@pytest.mark.parametrize("name", ["g1", "go1", "t1"])
def test_robot_snapshots(name):
    stored = report(bundle(name))
    outputs = {
        f"{name}.html": top(render(stored, "html")) + "\n",
        f"{name}.md": render(stored, "markdown"),
    }
    for file, text in outputs.items():
        path = ROBOTS / file
        if UPDATE:
            path.write_text(text, encoding="utf-8")
        assert text == path.read_text(encoding="utf-8"), file


def test_html_embeds_dm_sans_and_keeps_body_text_above_the_contrast_floor():
    """The report carries its own font and license, and link text is darker than the brand teal."""
    page = render(report(bundle("g1")), "html")
    assert "fonts.googleapis.com" not in page and "fonts.gstatic.com" not in page
    assert "data:font/woff2;base64," in page
    assert "SIL Open Font License, Version 1.1" in page
    assert "Copyright 2014 The DM Sans Project Authors" in page
    assert "<script" not in page
    # Body-sized links and the Show control use these, not #0e8785 (4.35:1 / 3.79:1).
    assert "--link: #0b6e6c" in page and "--link: #64dfc7" in page
    assert "summary::after" in page and "color: var(--link)" in page


def test_test_context_scroll_region_is_keyboard_focusable():
    """The card that holds Test context can scroll at a narrow width, so it is a named region."""
    page = render(report(bundle("g1")), "html")
    region = "<div class='card' tabindex='0' role='region' aria-label='Test context'>"
    assert page.count(region) == 1
    assert (
        region + "<section class='run-detail'><section class='context'><h3>Test context</h3>"
        in page
    )
    assert page.count("tabindex='0'") == 1
    assert "<script" not in page
    assert '.card[role="region"]:focus-visible' in page
    assert "outline: 3px solid var(--focus)" in page
    assert "outline-offset: 3px" in page


def test_g1_header_context_failures_and_grid():
    page = top(render(report(bundle("g1")), "html"))
    verdict = page[page.index("<section class='verdict'") : page.index("<section id='summary'>")]
    for text in (
        "unitree-g1 · stock 1.1.0 — Walk the hallway in the Open hallway",
        "<strong>FAIL</strong>",
        "12 successes, 60%; overall FAIL",
        "90% required",
        "<strong>Expected:</strong> The robot starts at the hallway entrance",
        "<strong>Actual:</strong> 8 failures, 40%; primary failure: "
        "hallway-lateral-limit in 8 (seeds 4, 5, 7, 9, 12, 14, 15, 18).",
    ):
        assert escape(text, quote=False) in verdict or text in verdict, text
    assert "PASS" not in verdict  # #39: no PASS wording on a FAIL result
    assert "Wilson" not in verdict and "95% interval" not in verdict
    assert verdict and page.index("<section class='verdict'") < page.index("<table class='failed'")
    # Context card: stored limits, unrounded, with their formulas and inputs.
    assert (
        "unitree-g1 · stock may drift up to 0.49 m either side of the centreline: half the "
        "1.5 m hallway, minus half its 0.52 m width." in page
    )
    assert "lateral limit: 0.49 m = clear_width / 2 - robot_width / 2" in page
    assert "time limit: 27 s = 2 * route_length / command_speed + 5 s" in page
    assert "0.52 + 2 x 0.05 = 0.620 m &lt;= 1.5 m" in page
    assert "walls in the MuJoCo simulation are visual only" not in page
    assert "<code>left_hallway</code>" not in page
    # Failure section: stored counts and worst values with seed and time.
    assert "<td>hallway-lateral-limit</td><td>8</td><td>4, 5, 7, 9, 12, 14, 15, 18</td>" in page
    assert (
        "<td>hallway-lateral-limit</td><td>highest</td><td>0.6887 m</td><td>12</td><td>11.42 s</td>"
        in page
    )
    # Grid: each failed trial once, primary then muted secondary; passes as chips.
    assert page.count("<tr><td title='stock-seed-") == 8
    assert (
        "drifted 0.58 m &gt; 0.49 m from the centreline at 10.56 s<br><span class='muted'>"
        "then touched the left wall at 10.62 s (0.005 m in); then touched the left wall at "
        "11.10 s (0.036 m in)</span>" in page
    )
    assert "then left the hallway through the left wall at 10.44 s" in page  # seed 15
    assert page.count("<li class='chip pass'") == 12
    assert "Environment</th>" not in page and "{&quot;id&quot;" not in page


def test_t1_failures_are_shown_in_full():
    page = top(render(report(bundle("t1")), "html"))
    assert "0 successes, 0%; overall FAIL" in page
    assert "hallway-lateral-limit</td><td>20</td>" in page
    assert page.count("then left the hallway through the right wall") == 20
    assert "&gt; 0.4795 m from the centreline" in page  # stored limit, unrounded
    assert "half its 0.541 m width" in page
    assert "no exit time, 20 failures, 100%" in page
    assert "chip pass" not in page


def test_go1_limits_come_from_the_bundle():
    page = top(render(report(bundle("go1")), "html"))
    assert "may drift up to 0.609 m" in page and "half its 0.282 m width" in page
    assert "0.282 + 2 x 0.1" in page  # quadruped clearance, as the verifier stored it
    assert "15 successes, 75%; overall FAIL" in page


def test_stored_values_are_shown_not_recomputed():
    data = bundle("g1")
    run = data["assessment"]["runs"][0]
    run["failure_summary"]["by_primary"][0]["seeds"] = [99]
    run["worst"][0]["observed"] = 9.87
    data["results"][3]["decision"]["primary_failure"]["observed"] = 1.23
    data["results"][3]["provenance"]["limits"]["lateral_limit"]["value"] = 0.4
    page = top(render(report(data), "html"))
    assert "hallway-lateral-limit in 8 (seeds 99)" in page and "<td>9.87 m</td>" in page
    assert "<td>9.87 m</td>" in page and "drifted 1.23 m" in page
    # Trials disagreeing on their limits: none is picked, the card says so.
    assert "may drift up to" not in page and "store different limits" in page


def test_description_text_is_escaped_and_templates_fill_known_names_only():
    data = bundle("g1")
    data["description"]["mission"]["description"] = "<script>x</script>"
    data["description"]["limits"]["lateral_limit"]["sentence"] = "{robot} {0.__class__} {value}"
    page = top(render(report(data), "html"))
    assert "<script>x" not in page and "&lt;script&gt;x&lt;/script&gt;" in page
    assert "unitree-g1 · stock {0.__class__} 0.49" in page


def test_older_bundle_without_the_new_fields_still_renders(tmp_path):
    """examples/bundle predates capability-verifier v1.12.0 and specs v1.9.0."""
    dest = tmp_path / "bundle"
    shutil.copytree(HERE.parent / "examples/bundle", dest)
    stored = assessed.report_from_bundle(load_bundle(dest / "manifest.json"))
    assert "description" not in stored["source_bundle"]
    page = top(render(stored, "html"))
    assert "12 successes, 60%; overall FAIL" in page
    assert "no scenario description stored in this bundle" not in page
    assert "No resolved limits stored for this run" not in page
    assert "No failure summary stored in this bundle" not in page
    assert "no primary failure stored" not in page
    assert "visual only" not in page
    assert "20 runs" not in page and "seeds 1 to 20" not in page
    assert "12 successes, 60%" in page
    assert "90% required" in page
    for fmt in ("markdown", "table", "csv", "json"):
        render(stored, fmt)


def test_each_new_field_can_be_missing_alone():
    base = bundle("t1")
    cuts = [
        lambda d: d.pop("description"),
        lambda d: d["assessment"]["runs"][0].pop("failure_summary"),
        lambda d: d["assessment"]["runs"][0].pop("worst"),
        lambda d: [r["provenance"].pop("limits") for r in d["results"]],
        lambda d: [r["decision"].pop("primary_failure") for r in d["results"]],
    ]
    for cut in cuts:
        data = copy.deepcopy(base)
        cut(data)
        stored = report(data)
        assert "0 successes, 0%" in render(stored, "html"), cut
        for fmt in ("markdown", "table"):
            text = render(stored, fmt)
            assert "0 successes, 0%" in text, (cut, fmt)
            assert "0 of 20" not in text, (cut, fmt)


def test_terminal_wording():
    text = render(report(bundle("g1")), "table")
    assert "Run unitree-g1/stock: 12 successes, 60%; overall FAIL. 90% required." in text
    assert "  Actual: 8 failures, 40%; primary failure: lateral limit exceeded in 8" in text
    assert "95% interval" not in text
    assert "12/20 PASS" not in text


def test_markdown_header_is_above_the_table():
    md = render(report(bundle("t1")), "markdown")
    assert md.index("**Expected:**") < md.index("| Robot · configuration |")
    assert md.index("**Actual · booster-t1 · stock:** 20 failures, 100%") < md.index("|---|")
    assert "- 20× lateral limit exceeded (primary) — seeds 1, 2," in md
    assert "visual only (no collision)" in md


_OF_N = re.compile(r"\b\d+ of \d+\b")


def test_text_summaries_never_say_k_of_n_or_quote_the_interval(tmp_path):
    """Markdown, the terminal run line and the PR-comment body share these words.

    A rounded 100% is not written as complete success. Zero trials add no percentage.
    """
    from livingproof_capability_report import comment
    from test_hallway import example, stored

    reports = [report(bundle(name)) for name in ("g1", "go1", "t1")]
    reports.append(stored(example(tmp_path)))
    for stored_report in reports:
        markdown = render(stored_report, "markdown")
        terminal = render(stored_report, "table")
        posted = comment.body([markdown])
        for label, text in (("markdown", markdown), ("terminal", terminal), ("comment", posted)):
            assert _OF_N.search(text) is None, label
        assert "95% interval" not in markdown
        assert "95% interval" not in terminal

    almost = report(bundle("g1"))
    almost["summaries"][0]["k"] = 199
    almost["summaries"][0]["n"] = 200
    for fmt in ("markdown", "table"):
        text = render(almost, fmt)
        assert "199 successes, >99%" in text
        assert "199 successes, 100%" not in text
        assert _OF_N.search(text) is None

    zero = report(bundle("g1"))
    summary = zero["summaries"][0]
    summary["k"] = 0
    summary["n"] = 0
    summary["required_passes"] = 0
    for fmt in ("markdown", "table"):
        text = render(zero, fmt)
        assert _OF_N.search(text) is None, fmt
        assert "95% interval" not in text
        assert "%" not in text
        assert "0 successes" not in text

    clear = report(bundle("g1"))
    run = clear["source_bundle"]["assessment"]["runs"][0]
    run["failure_summary"]["failed_trials"] = 0
    clear["source_bundle_sha256"] = digest(clear["source_bundle"])
    for fmt in ("markdown", "table"):
        text = render(clear, fmt)
        assert "No trial failed: 12 successes, 60%." in text
        assert _OF_N.search(text) is None
