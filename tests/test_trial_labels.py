"""Evidence 2.0.0 reports say trial; evidence 1.0.0 reports keep saying seed.

``fixtures/hallway-2.0.0`` is a bundle 1.1.0 manifest exported by capability-verifier
v1.16.1 (67bb6bbc330645f9fee66b9ab16f6c055cd313f8) from livingproof-hallway-evidence/2.0.0.
The observations start from that verifier's G1 stock fixture. Trials 2 and 3 were given
a lateral drift past the stored limit (trial 2 also touches the left wall) so the export
records failures, then ``tools/verify_hallway.py --bundle-version 1.1.0`` wrote this
bundle. The catalog description is omitted: specs v1.9.0's grading sentence still says
"seeds" and is shown unchanged when a bundle carries it. This is not a simulator run.
"""

import re
from html import unescape
from pathlib import Path

from livingproof_capability_report import hallway
from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.core import load_bundle, render

BUNDLE = Path(__file__).parent / "fixtures/hallway-2.0.0"
ROBOTS = Path(__file__).parent / "fixtures/robots"
EXPECTED = Path(__file__).parent / "fixtures/hallway-expected"
VIDEO = "https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/9/artifacts/"


def visible_html(page):
    """Reader-visible text. Drops CSS, element attributes and the lossless ``<pre>``."""
    page = re.sub(r"<style\b[^>]*>.*?</style>", "", page, flags=re.DOTALL)
    page = re.sub(r"<pre\b[^>]*>.*?</pre>", "", page, flags=re.DOTALL)
    return unescape(re.sub(r"<[^>]+>", "\n", page))


def stored():
    links = {
        "links": [
            {"label": "video", "url": VIDEO + "2", "kind": "video", "seed": 2, "status": "FAIL"},
            {"label": "video", "url": VIDEO + "1", "kind": "video", "seed": 1, "status": "PASS"},
        ]
    }
    return report_from_bundle(load_bundle(BUNDLE / "manifest.json"), [links])


def test_repeat_name_uses_index_or_a_trials_dict_not_the_seed_number():
    """2.0.0 stores seed == index, so the number cannot tell the models apart."""
    numbered = {
        "original_result": {"seed": 2},
        "provenance": {"plan": {"trials": 3, "seeds": [1, 2, 3]}},
    }
    assert hallway.repeat_name(numbered) == "seed"
    assert hallway.repeat_name(numbered, plural=True, capital=True) == "Seeds"
    by_index = {
        "original_result": {"seed": 2, "index": 2},
        "provenance": {"plan": {"trials": 3, "seeds": [1, 2, 3]}},
    }
    by_plan = {
        "original_result": {"seed": 2},
        "provenance": {"plan": {"trials": {"count": 3}}},
    }
    assert hallway.repeat_name(by_index) == "trial"
    assert hallway.repeat_name(by_plan) == "trial"
    assert hallway.repeat_name(by_plan, plural=True, capital=True) == "Trials"


def test_plan_count_renders_for_a_trials_dict():
    result = stored()["source_bundle"]["results"][0]
    assert hallway.canonical_plan(result) == "walk-hallway@0.1.0 · N=3 · 0.50 m/s"
    copied = {
        **result,
        "provenance": {
            **result["provenance"],
            "plan": {**result["provenance"]["plan"], "required_passes": 3},
        },
    }
    assert hallway.canonical_plan(copied) == (
        "walk-hallway@0.1.0 · N=3 · 0.50 m/s · pass bar 3/3"
    )


def test_evidence_2_report_says_trial_and_keeps_seed_contracts():
    report = stored()
    page = render(report, "html")
    md = render(report, "markdown")
    text = visible_html(page)
    for where, body in (("html", text), ("markdown", md)):
        assert "seed" not in body and "Seed" not in body, where
        assert "trial 2" in body and "trial 1" in body, where
    assert "N=3" in md and "N={'count'" not in md and 'N={"count"' not in md
    assert "## walk-hallway@0.1.0 · N=3 · 0.50 m/s" in md
    assert "(trials 2, 3)" in md and "(trial 2)" in md
    assert "Per-trial failures" in md and "| Trial |" in md
    assert "per-seed" not in md and "Per-seed" not in md
    assert f"- ▶️ trial 2 (fail): [video]({VIDEO}2)" in md
    assert f"- ▶️ trial 1 (pass): [video]({VIDEO}1)" in md
    assert "<th>Seeds</th>" not in page and "<th>Seed</th>" not in page
    assert "<th>Trials</th>" in page and "<th>Trial</th>" in page
    assert "trial 2 (FAIL): video" in text
    # Contracts stay: result ids, the link field, and report.json keys.
    assert "title='stock-seed-02'" in page and "title='stock-seed-01'" in page
    pre = page.split("<pre>", 1)[1].split("</pre>", 1)[0]
    assert "stock-seed-02" in pre and "&quot;seed&quot;:" in pre and "&quot;seeds&quot;:" in pre
    assert report["evidence_links"]["links"][0]["seed"] == 2
    assert report["source_bundle"]["results"][1]["original_result"]["seed"] == 2
    assert report["source_bundle"]["results"][1]["id"] == "stock-seed-02"


def test_fallback_failure_lines_follow_the_same_word():
    result = stored()["source_bundle"]["results"][1]
    described = hallway._describe(
        {
            "check": "hallway-lateral-limit",
            "observed": 0.62,
            "limit": 0.49,
            "unit": "m",
            "t": 10.26,
            "seed": 2,
        },
        result,
    )
    assert described == "0.62 > 0.49 m at 10.26 s (trial 2)"
    failures = [
        {
            "check": check,
            "observed": None if check == "hallway-exit-reached" else 1.0,
            "limit": 0.5,
            "unit": "s" if check == "hallway-exit-reached" else "m",
            "t": 1.0,
            "seed": index + 1,
            "wall": "wall-left",
        }
        for index, check in enumerate(hallway.ORDER)
    ]
    lines = hallway.why_failed({"failures": failures}, result=result)
    assert lines[-1] == "- 1× other first failures; see the per-trial details"
    assert all("(trial " in line or line.endswith("details") for line in lines)


def test_seed_model_goldens_still_say_seed():
    for name in ("g1", "go1", "t1"):
        page = (ROBOTS / f"{name}.html").read_text(encoding="utf-8")
        md = (ROBOTS / f"{name}.md").read_text(encoding="utf-8")
        assert "<th>Seeds</th>" in page and "<th>Seed</th>" in page
        assert "seed 1" in page and "(seeds " in page
        assert "Per-seed failures" in md and "(seed " in md and "seeds " in md
    older = (EXPECTED / "report.md").read_text(encoding="utf-8")
    linked = (EXPECTED / "report-with-links.md").read_text(encoding="utf-8")
    assert "per-seed details" in older and "Per-seed failures" in older
    assert "(seed 18)" in older and "| Seed |" in older
    assert "N=20" in older and "N={'count'" not in older
    assert "- ▶️ seed 4 (fail):" in linked and "- ▶️ seed 1 (pass):" in linked
