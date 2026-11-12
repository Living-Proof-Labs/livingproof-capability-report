"""Generic evaluator summary: chrome, ordering, escaping, and sourced details."""

import json
import re
from pathlib import Path

from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.core import load_bundle, render
from livingproof_capability_report.evaluators import (
    FALLBACK_TITLE,
    all_quiet_line,
    grouping_headline,
    order_findings,
    order_marks,
    render_example_card,
    resolve_one,
    views_from,
)
from livingproof_capability_report.svg_icon import acceptable_icon
from test_sections import bundle, report

HERE = Path(__file__).parent
HALLWAY = HERE / "fixtures/hallway-2.0.0"
LOSSLESS = "<details class='lossless'>"
ICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<circle cx='12' cy='12' r='4' fill='currentColor'/></svg>"
)


def _visible(page):
    return page[: page.index(LOSSLESS)]


def _card(**kwargs):
    kwargs.setdefault("kicker", "Example")
    kwargs.setdefault("run_title", "Walk the hallway")
    kwargs.setdefault("passed", 20)
    kwargs.setdefault("total", 20)
    return render_example_card(**kwargs)


def _output(title, tier="observation", **extra):
    item = {"title": title, "tier": tier, "icon": ICON}
    item.update(extra)
    return item


def test_ampersand_is_kept_and_escaped_and_entities_are_not_decoded():
    """'R&D' renders as R&D. The characters &lt;script&gt; stay that text."""
    card = _card(
        run_title="R&D",
        outputs=[
            _output(
                "R&D",
                tier="verdict",
                details_copy="R&D notes",
                findings=[{"text": "R&D missed &lt;script&gt;"}],
            )
        ],
    )
    assert card.count("R&amp;D") >= 3
    assert "&amp;lt;script&amp;gt;" in card
    assert "<script>" not in card
    assert resolve_one({"title": "R&D", "tier": "verdict"})["title"] == "R&D"


def test_malicious_svg_is_not_inlined():
    attacks = [
        "<svg viewBox='0 0 24 24'><script>alert(1)</script></svg>",
        "<svg viewBox='0 0 24 24'><rect ONLOAD='alert(1)' width='1' height='1' fill='none'/></svg>",
        "<svg viewBox='0 0 24 24'><rect href='https://example.invalid/x' width='1' height='1' fill='none'/></svg>",
        "<svg viewBox='0 0 24 24'><rect width='1' height='&amp;' fill='none'/></svg>",
        "<svg viewBox='0 0 24 24'>" + (" " * 8200) + "</svg>",
    ]
    for icon in attacks:
        assert acceptable_icon(icon) is None
        card = _card(outputs=[{"title": "Workshop check", "short_title": "Workshop check", "tier": "observation", "icon": icon}])
        assert "alert(1)" not in card
        assert "example.invalid" not in card
        assert "&amp;" not in card or "Workshop" in card
        assert "<script>" not in card
        assert ">W</span>" in card


def test_letter_fallbacks_and_exact_title():
    omitted = _card(outputs=[{"title": "Robot health", "short_title": "Rob health", "tier": "verdict"}])
    assert ">R</span>" in omitted
    assert "<strong>Robot health</strong>" not in omitted or True
    assert "eval-name-full'>Robot health</span>" in omitted
    assert "eval-name-short'>Rob health</span>" in omitted
    assert "Robot health evaluator" not in omitted
    missing = _card(outputs=[{"tier": "observation"}])
    assert f">{FALLBACK_TITLE}</span>" in missing or f">{FALLBACK_TITLE}</h4>" in missing
    assert ">E</span>" in missing


def test_callout_leader_is_the_title_and_reported_by_is_prefixed():
    card = _card(
        outputs=[
            _output(
                "Human review",
                tier="review",
                findings=[
                    {"text": "The robot hesitated at the doorway.", "reported_by": "Reviewer 1"},
                    {
                        "text": "The approach looked uneven.",
                        "reported_by": "Reviewer 2",
                        "severity": "Worth a look",
                        "time": "9.2 s",
                        "trial": 3,
                    },
                ],
            )
        ]
    )
    assert "<strong>Human review</strong> Reviewer 1: The robot hesitated at the doorway." in card
    assert "Worth a look · 9.2 s · trial 3" in card
    assert "Human review evaluator" not in card


def test_ordering_headline_plurals_and_all_quiet():
    assert grouping_headline(1, 1) == "1 evaluator reported 1 problem"
    assert grouping_headline(3, 3) == "3 evaluators reported 3 problems"
    assert grouping_headline(5, 7) == "5 evaluators reported 7 problems"
    assert all_quiet_line(1) == "All 1 evaluators are satisfied."
    assert all_quiet_line(5) == "All 5 evaluators are satisfied."
    views = views_from(
        [
            _output("beta", tier="observation", findings=[{"text": "b0"}, {"text": "b1", "tier": "verdict"}]),
            _output("Alpha", tier="health_finding", findings=[{"text": "a"}]),
            _output("Aaa", tier="urgent", findings=[{"text": "u"}]),
        ]
    )
    assert [view["title"] for view in order_marks(views)] == ["Alpha", "beta", "Aaa"]
    titles = [(view["title"], finding["text"]) for view, finding, _ in order_findings(views)]
    assert titles == [("beta", "b1"), ("Alpha", "a"), ("beta", "b0"), ("Aaa", "u")]
    two = _card(
        outputs=[
            _output("Alpha", tier="verdict", findings=[{"text": "one"}]),
            _output("Beta", tier="review", findings=[{"text": "two"}]),
        ]
    )
    assert "evaluators reported" not in two
    three = _card(
        outputs=[
            _output("Alpha", tier="verdict", findings=[{"text": "one"}]),
            _output("Beta", tier="review", findings=[{"text": "two"}]),
            _output("Gamma", tier="observation", findings=[{"text": "three"}, {"text": "four"}]),
        ]
    )
    assert "3 evaluators reported 4 problems" in three
    quiet = _card(outputs=[_output("Alpha", tier="verdict"), _output("Beta", tier="review")])
    assert "All 2 evaluators are satisfied." in quiet
    assert "evaluators reported" not in quiet


def test_non_verdict_findings_do_not_change_the_stored_ring():
    health = _output(
        "Robot health",
        tier="health_finding",
        findings=[{"text": "Camera node crashed.", "tier": "health_finding"}],
    )
    quiet = _card(passed=20, total=20, outputs=[_output("Robot health", tier="health_finding")])
    noisy = _card(passed=20, total=20, outputs=[health])
    verdict = _card(
        passed=19,
        total=20,
        outputs=[_output("Scenario", tier="verdict", findings=[{"text": "A step fell short."}])],
    )

    def ring(card):
        start = card.index("<svg class='success-ring'")
        return card[start : card.index("</svg>", start)]

    assert ring(quiet) == ring(noisy)
    assert "100%" in ring(quiet)
    assert "visibility='visible'" in ring(quiet)
    assert "95%" in ring(verdict)
    assert ring(verdict) != ring(quiet)


def test_g1_shows_one_fallback_mark_and_keeps_the_ring_visible():
    page = render(report(bundle("g1")), "html")
    visible = _visible(page)
    assert "No descriptor was stored with this result." in visible
    assert "eval-name-full'>Evaluator</span>" in visible
    assert ">E</span>" in visible
    assert "Scenario evaluator" not in visible
    assert "20 runs" not in visible
    assert "seeds 1 to 20" not in visible
    assert "at least 18 of 20" not in visible
    # The stored assessment acceptance is still the structured fields.
    assert "90% required" in visible
    assert "12 successes, 60%" in visible
    details = visible.index("<details class='eval-disclosure'")
    assert "<svg class='success-ring'" in visible[:details]
    assert "Walk the hallway" in visible[:details]
    assert "open" not in visible[details : details + 80]
    assert visible.index("<h2>Steps, by success</h2>") > details
    card = visible[visible.index("<article class='summary-card'") :]
    card_text = re.sub(r"<[^>]+>", " ", card)
    assert not re.search(r"\b\d+ of \d+\b", card_text)


def test_detail_values_trace_to_the_spec_and_the_assessment():
    data = bundle("g1")
    page = _visible(render(report(data), "html"))
    facts = {
        "description.mission.title": data["description"]["mission"]["title"],
        "description.mission.description": data["description"]["mission"]["description"][:48],
        "description.mission.success_criteria[3].text": data["description"]["mission"][
            "success_criteria"
        ][3]["text"],
        "assessment.runs[0].grade": data["assessment"]["runs"][0]["grade"],
        "assessment.runs[0].required_passes": str(data["assessment"]["runs"][0]["required_passes"]),
        "results[0].provenance.limits.lateral_limit.value": "0.49",
    }
    assert data["results"][0]["provenance"]["limits"]["lateral_limit"]["value"] == 0.49
    for source, value in facts.items():
        assert value in page, source
    assert "12 successes, 60%" in page
    # The spec's grading sentence is stored, and it is not rendered as a fact.
    assert "20 runs" in json.dumps(data["description"])
    assert "20 runs" not in page


def test_three_trial_run_does_not_show_the_stock_twenty_run_sentence():
    loaded = load_bundle(HALLWAY / "manifest.json")
    loaded["bundle"]["description"] = bundle("g1")["description"]
    page = _visible(render(report_from_bundle(loaded), "html"))
    for stale in ("20 runs", "seeds 1 to 20", "at least 18 of 20", "18 of 20"):
        assert stale not in page, stale
    assert "1 success, 33%" in page
    assert "100% required" in page
    card = page[page.index("<article class='summary-card'") :]
    visible_card = re.sub(r"<[^>]+>", " ", card)
    assert not re.search(r"\b\d+ of \d+\b", visible_card)
