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
import shutil
from html import escape
from pathlib import Path

import pytest

from livingproof_capability_report import assessed
from livingproof_capability_report.core import load_bundle, render

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
    return page[: page.index("<details>")]


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
        "12 of 20 trials passed; overall FAIL",
        "18 of 20 required",
        "95% interval 39–78% (Wilson, stored, rounded to whole percent)",
        "<strong>Expected:</strong> The robot starts at the hallway entrance",
        "<strong>Actual:</strong> 8 of 20 trials failed; primary failure: lateral limit "
        "exceeded in 8 (seeds 4, 5, 7, 9, 12, 14, 15, 18).",
    ):
        assert escape(text, quote=False) in verdict or text in verdict, text
    assert "PASS" not in verdict  # #39: no PASS wording on a FAIL result
    assert verdict and page.index("<section class='verdict'") < page.index("<table")
    # Context card: stored limits, unrounded, with their formulas and inputs.
    assert (
        "unitree-g1 · stock may drift up to 0.49 m either side of the centreline: half the "
        "1.5 m hallway, minus half its 0.52 m width." in page
    )
    assert "lateral limit: 0.49 m = clear_width / 2 - robot_width / 2" in page
    assert "time limit: 27 s = 2 * route_length / command_speed + 5 s" in page
    assert "0.52 + 2 x 0.05 = 0.620 m &lt;= 1.5 m" in page
    assert "walls in the MuJoCo simulation are visual only" in page
    assert "<code>left_hallway</code>" in page
    # Failure section: stored counts and worst values with seed and time.
    assert "<td>lateral limit exceeded</td><td>8</td><td>4, 5, 7, 9, 12, 14, 15, 18</td>" in page
    assert (
        "<td>Lateral drift</td><td>highest</td><td>0.6887 m</td><td>12</td><td>11.42 s</td>" in page
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
    assert "0 of 20 trials passed; overall FAIL" in page
    assert "lateral limit exceeded</td><td>20</td>" in page
    assert page.count("then left the hallway through the right wall") == 20
    assert "&gt; 0.4795 m from the centreline" in page  # stored limit, unrounded
    assert "half its 0.541 m width" in page
    assert "no exit time in 20 of 20 trials" in page
    assert "chip pass" not in page


def test_go1_limits_come_from_the_bundle():
    page = top(render(report(bundle("go1")), "html"))
    assert "may drift up to 0.609 m" in page and "half its 0.282 m width" in page
    assert "0.282 + 2 x 0.1" in page  # quadruped clearance, as the verifier stored it
    assert "15 of 20 trials passed; overall FAIL" in page


def test_stored_values_are_shown_not_recomputed():
    data = bundle("g1")
    run = data["assessment"]["runs"][0]
    run["failure_summary"]["by_primary"][0]["seeds"] = [99]
    run["worst"][0]["observed"] = 9.87
    data["results"][3]["decision"]["primary_failure"]["observed"] = 1.23
    data["results"][3]["provenance"]["limits"]["lateral_limit"]["value"] = 0.4
    page = top(render(report(data), "html"))
    assert "(seed 99)" in page and "<td>99</td>" in page
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
    assert "12 of 20 trials passed; overall FAIL" in page
    assert "no scenario description stored in this bundle" in page
    assert "No resolved limits stored for this run" in page
    assert "No failure summary stored in this bundle" in page
    assert "no primary failure stored" in page  # grid falls back to the stored reason
    assert "visual only" not in page  # no stored MuJoCo provenance, no wall note
    assert "Expected:" in page and "does not pass walk-hallway" in page
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
        for fmt in ("html", "markdown", "table"):
            assert "0 of 20 trials passed" in render(stored, fmt), (cut, fmt)


def test_terminal_wording():
    text = render(report(bundle("g1")), "table")
    assert (
        "Run unitree-g1/stock: 12 of 20 trials passed; overall FAIL. 18 of 20 required; "
        "95% interval 39–78% (Wilson, stored [0.3866, 0.7812])" in text
    )
    assert "  Actual: 8 of 20 trials failed; primary failure: lateral limit exceeded in 8" in text
    assert "12/20 PASS" not in text


def test_markdown_header_is_above_the_table():
    md = render(report(bundle("t1")), "markdown")
    assert md.index("**Expected:**") < md.index("| Robot · configuration |")
    assert md.index("**Actual · booster-t1 · stock:** 20 of 20 trials failed") < md.index("|---|")
    assert "- 20× lateral limit exceeded (primary) — seeds 1, 2," in md
    assert "visual only (no collision)" in md
