"""Walk-hallway rendering from the verifier's stored decisions (bundle 1.1.0); no grading.

The fixture is ``examples/bundle``: 20 seeded G1 stock trials, 12 PASS, as the capability
verifier writes them, with its per-trial decisions and the run assessment.
"""

import json
import shutil
from pathlib import Path

import pytest

from livingproof_capability_report import hallway
from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.core import digest, load_bundle, render

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/bundle"
EXPECTED = Path(__file__).parent / "fixtures/hallway-expected"


def example(tmp_path, **provenance):
    """A copy of the example 1.1.0 bundle; ``provenance`` is added to every result."""
    dest = tmp_path / "bundle"
    shutil.copytree(EXAMPLE, dest)
    manifest = dest / "manifest.json"
    if provenance:
        data = json.loads(manifest.read_text())
        for r in data["results"]:
            r["provenance"].update(provenance)
        manifest.write_text(json.dumps(data))
    return manifest


def stored(manifest, links=None):
    return report_from_bundle(load_bundle(manifest), links)


def test_markdown_follows_arts_layout(tmp_path):
    md = render(stored(example(tmp_path)), "markdown")
    assert md == (EXPECTED / "report.md").read_text()
    lines = md.splitlines()
    assert lines[0] == "<!-- livingproof-verification -->"  # 1: stable marker
    assert "draft" not in md.lower()
    assert lines[1] == (
        "## walk-hallway@0.1.0 · N=20 · 0.50 m/s · pass bar 90% · "
        "`verification.lock.json @ abcdef1`"
    )  # 2: header
    assert "| Robot · configuration | Grade | Passed | Needs |" in md  # 3
    assert "95% interval" not in md
    assert "| unitree-g1 · stock 1.1.0 | **❌ FAIL** | 12 successes, 60% | 90% required |" in md
    assert (
        "unitree-g1 · stock does not pass walk-hallway: "
        "12 successes, 60%; overall FAIL. 90% required." in md
    )  # 4
    # 5: each failing seed once, under its first failure. Seed 7 touched the wall at 4.50 s
    # before crossing the lateral limit at 10.26 s, so it counts as a wall contact.
    assert "- 3× lateral limit exceeded — worst: 0.62 > 0.49 m at 10.26 s (seed 18)" in md
    assert "- 3× touched a wall — worst: touched left wall at 4.50 s (seed 12)" in md
    assert "- 1× exit not reached in time — worst: not reached by 27.00 s (seed 15)" in md
    assert "- 1× other first failures; see the per-seed details" in md  # the fall, beyond 3 bullets
    assert md.index("Why runs failed") < md.index("<details>")
    assert "| 7 | touched left wall at 4.50 s |" in md  # 6: wall contacts, no observed/limit
    assert "![" not in md  # 7: no stored assets, no thumbnails
    assert "Full report" not in md  # 8: no links given, no links row
    assert "<details><summary>Per-seed failures · unitree-g1 · stock</summary>" in md  # 9
    assert lines[-1].startswith(
        "<sub>Policy all-required-v1@1.0.0 · catalog v1.6.0 @ b4ba31e · run run-1 · "
    )
    assert lines[-1].endswith(
        "stored decisions, no regrading · simulation evidence, not hardware validation</sub>"
    )


def test_markdown_close_call_keeps_minimal_extra_digit():
    f = {
        "check": "hallway-lateral-limit",
        "observed": 0.492,
        "limit": 0.49,
        "unit": "m",
        "t": 9.2,
        "seed": 17,
    }
    assert hallway._describe(f) == "0.492 > 0.490 m at 9.20 s (seed 17)"
    assert hallway._describe(dict(f, observed=0.62)) == "0.62 > 0.49 m at 9.20 s (seed 17)"


def test_markdown_thumbnails_links_and_prototype_line(tmp_path):
    m = example(
        tmp_path,
        prototype="PROTOTYPE: unreleased catalog",
        assets={"thumbnail": "t.png", "clip": "c.mp4"},
    )
    data = json.loads(m.read_text())
    for run in data["assessment"]["runs"]:
        run["prototype"] = "PROTOTYPE: unreleased catalog"
    m.write_text(json.dumps(data))
    md = render(stored(m), "markdown", {"report": "r.html", "clips": "clips/", "lock_diff": None})
    assert "[![worst fail stock-seed-04](t.png)](c.mp4) [![pass stock-seed-01](t.png)](c.mp4)" in md
    assert "[Full report](r.html) · [All clips](clips/)" in md and "Lock diff" not in md
    assert md.splitlines()[-1] == "<sub>PROTOTYPE: unreleased catalog</sub>"


RUN = "https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7"
ART = RUN + "/artifacts/"


def _links(**extra):
    return {
        "run": RUN,
        "links": [
            {"label": "evidence", "url": ART + "1", "kind": "artifact"},
            {"label": "MCAP, all trials", "url": ART + "2", "kind": "mcap"},
            {"label": "video", "url": ART + "3", "kind": "video", "seed": 1, "status": "PASS"},
            {"label": "MCAP", "url": ART + "4", "kind": "mcap", "seed": 1, "status": "PASS"},
            {"label": "video", "url": ART + "5", "kind": "video", "seed": 4, "status": "FAIL"},
            {"label": "video", "url": "", "kind": "video", "seed": 2, "status": "FAIL"},
        ],
        **extra,
    }


def test_evidence_links_stored_in_report_and_rendered(tmp_path):
    report = stored(example(tmp_path), [_links()])
    links = report["evidence_links"]
    assert links["run"] == RUN
    assert len(links["links"]) == 5  # the empty URL (skipped upload) is dropped
    assert report["source_bundle_sha256"] == digest(report["source_bundle"])  # no digest change
    md = render(report, "markdown")
    assert md == (EXPECTED / "report-with-links.md").read_text()
    assert f"**Evidence:** [CI run]({RUN}) · [evidence]({ART}1) · [MCAP, all trials]({ART}2)" in md
    assert f"- ▶️ seed 4 (fail): [video]({ART}5)" in md
    assert f"- ▶️ seed 1 (pass): [video]({ART}3) · [MCAP]({ART}4)" in md
    assert md.index("seed 4 (fail)") < md.index("seed 1 (pass)") < md.index("<details>")
    page = render(report, "html")
    assert "seed 4 (FAIL): video" in page
    assert ART not in page and "artifact" not in page.lower()
    assert json.loads(render(report, "json"))["evidence_links"] == links


def test_evidence_links_absent_leaves_markdown_unchanged(tmp_path):
    report = stored(example(tmp_path))
    assert "Evidence:" not in render(report, "markdown") and "evidence_links" not in report


def test_evidence_link_status_must_match_stored_decision(tmp_path):
    bad = _links()
    bad["links"][2] = dict(bad["links"][2], seed=4)  # seed 4 failed; a "pass" video is a lie
    report = stored(example(tmp_path), [bad])
    with pytest.raises(ValueError, match="seed 4 says PASS, stored decision is FAIL"):
        render(report, "markdown")


@pytest.mark.parametrize(
    "entry",
    [
        {"label": "x", "url": "http://insecure", "kind": "artifact"},
        {"label": "x](javascript:1)", "url": ART + "1", "kind": "artifact"},
        {"label": "x", "url": ART + "1 extra", "kind": "artifact"},
        {"label": "x", "url": ART + "1", "kind": "zip"},
        {"label": "x", "url": ART + "1", "kind": "video", "seed": 1},
        {"label": "x", "url": ART + "1", "kind": "artifact", "note": "?"},
    ],
)
def test_evidence_links_rejected(tmp_path, entry):
    with pytest.raises(ValueError):
        stored(example(tmp_path), [{"links": [entry]}])


def test_evidence_links_files_merge_and_must_agree_on_run(tmp_path):
    m = example(tmp_path)
    first = {"run": RUN, "links": [{"label": "a", "url": ART + "1", "kind": "artifact"}]}
    second = {"links": [{"label": "b", "url": ART + "2", "kind": "artifact"}]}
    merged = stored(m, [first, second])["evidence_links"]
    assert [e["label"] for e in merged["links"]] == ["a", "b"] and merged["run"] == RUN
    with pytest.raises(ValueError, match="different CI runs"):
        stored(m, [first, {"run": RUN + "0", "links": []}])


def test_the_reporter_has_no_grading_code():
    """Reporter #30: grade, rationale and intervals come from the verifier only."""
    import livingproof_capability_report as package
    from livingproof_capability_report import core

    for name in ("grade", "decide", "wilson", "summaries", "members_supported"):
        assert not hasattr(hallway, name) and not hasattr(core, name), name
    assert not hasattr(package, "grade")
    src = Path(package.__file__).parent
    assert not (src / "policy.py").exists() and not (src / "human.schema.json").exists()
