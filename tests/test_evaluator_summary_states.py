"""Pin the seven example-data states for the multi-evaluator summary card.

States A, B1–B5 and C are the labelled example cards in
docs/evaluator-summary/fixtures.html. These tests regenerate each card from
the example descriptors and check it against that page. They pin the current
renderer (successes and a percentage, descriptor titles with no added
suffix). They do not take screenshots or compare pixels to Art's
09-evaluator-summary mock.
"""

import re
from pathlib import Path

from livingproof_capability_report.evaluators import render_example_card

ROOT = Path(__file__).resolve().parents[1]
ICONS = {
    path.stem: path.read_text(encoding="utf-8")
    for path in (ROOT / "docs/evaluator-summary/icons").glob("*.svg")
}
FIXTURES = ROOT / "docs/evaluator-summary/fixtures.html"
PURPOSE = {
    "Robot health": (
        "Reads the robot's own health reports and reports what happened inside the robot."
    ),
    "Scenario": "Grades each required step of the mission against written requirements.",
    "Run Integrity": "Judges whether the test system was sound, not how the robot performed.",
    "Human review": "One or more people approve the run or report an issue they observed.",
    "Agent review": "An agent inspects the run's records and gives a grade.",
}
ICON_KEY = {
    "Robot health": "health",
    "Scenario": "scenario",
    "Run Integrity": "integrity",
    "Human review": "human",
    "Agent review": "agent",
}


def _stored_run_body():
    text = FIXTURES.read_text(encoding="utf-8")
    match = re.search(r"(<!--lp-stored-run-->.*?)</div></details>", text, re.S)
    assert match, "fixtures.html is missing the stored G1 stock run body"
    return match.group(1)


def _example(title, short=None, tier="verdict", **extra):
    item = {
        "title": title,
        "tier": tier,
        "icon": ICONS[ICON_KEY[title]],
        "icon_accessible_name": title,
        "version": "1.0.0" if title == "Scenario" else "version to be confirmed (placeholder)",
        "purpose": PURPOSE[title],
        "source": (
            "Example descriptor. The detail below is the stored G1 stock run."
            if title == "Scenario"
            else "Example descriptor"
        ),
    }
    if short:
        item["short_title"] = short
    if title == "Scenario":
        item["body_html"] = _stored_run_body()
    item.update(extra)
    if title == "Scenario" and "body_html" not in extra:
        item["body_html"] = _stored_run_body()
    return item


def _health_ok():
    return _example(
        "Robot health",
        "Rob health",
        success_copy="Joint temperatures were within the written limit.",
    )


def _scenario(**extra):
    return _example("Scenario", **extra)


def _integrity(**extra):
    return _example("Run Integrity", "Run Integ", tier="test_system_status", **extra)


def _human(**extra):
    return _example("Human review", tier="review", **extra)


def _agent(**extra):
    return _example("Agent review", tier="observation", **extra)


def example_states():
    health_ok = _health_ok()
    scenario = _scenario()
    integrity = _integrity()
    human = _human()
    agent = _agent()
    return [
        {
            "id": "A",
            "kicker": "A. Everything succeeds",
            "run_title": "Walk the hallway",
            "passed": 20,
            "total": 20,
            "compact": False,
            "group": "card-a",
            "outputs": [health_ok, scenario, integrity, human, agent],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": ["is-quiet"] * 5,
            "count": "20 successes, 100%",
            "phrase": "100% success",
            "quiet": "All 5 evaluators are satisfied.",
            "findings": [],
            "headline": None,
            "ring_complete": True,
        },
        {
            "id": "B1",
            "kicker": "B1. A verdict-tier evaluator reports a problem",
            "run_title": "Walk the hallway",
            "passed": 19,
            "total": 20,
            "compact": True,
            "group": "card-b0",
            "outputs": [
                health_ok,
                _scenario(findings=[{"text": "A required step fell short."}]),
                integrity,
                human,
                agent,
            ],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": ["is-quiet", "is-speaking", "is-quiet", "is-quiet", "is-quiet"],
            "count": "19 successes, 95%",
            "phrase": "95% success",
            "quiet": None,
            "findings": ["Scenario A required step fell short."],
            "headline": None,
            "ring_complete": False,
        },
        {
            "id": "B2",
            "kicker": "B2. A health-finding evaluator reports two problems",
            "run_title": "Walk the hallway",
            "passed": 20,
            "total": 20,
            "compact": True,
            "group": "card-b1",
            "outputs": [
                scenario,
                _example(
                    "Robot health",
                    "Rob health",
                    tier="health_finding",
                    details_copy=(
                        "The camera node crashed at 12.4 s (trial 7). "
                        "A joint temperature rise at 9.2 s (trial 3) had no written limit."
                    ),
                    findings=[
                        {
                            "text": "Camera node crashed while walking down the hallway.",
                            "severity": "Needs attention",
                            "time": "12.4 s",
                            "trial": 7,
                        },
                        {
                            "text": (
                                "A joint temperature rose above the usual range, "
                                "with no written limit to check against."
                            ),
                            "severity": "Worth a look",
                            "time": "9.2 s",
                            "trial": 3,
                        },
                    ],
                ),
                integrity,
                human,
                agent,
            ],
            "mark_order": [
                "Scenario",
                "Robot health",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": ["is-quiet", "is-speaking", "is-quiet", "is-quiet", "is-quiet"],
            "count": "20 successes, 100%",
            "phrase": "100% success",
            "quiet": None,
            "findings": [
                "Robot health Camera node crashed while walking down the hallway.",
                "Robot health A joint temperature rose above the usual range, "
                "with no written limit to check against.",
            ],
            "headline": None,
            "ring_complete": True,
        },
        {
            "id": "B3",
            "kicker": "B3. A test-system evaluator reports a problem",
            "run_title": "Walk the hallway",
            "passed": 19,
            "total": 19,
            "compact": True,
            "group": "card-b2",
            "outputs": [
                health_ok,
                scenario,
                _integrity(
                    findings=[{"text": "One trial was not counted after a simulator crash."}]
                ),
                human,
                agent,
            ],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": ["is-quiet", "is-quiet", "is-speaking", "is-quiet", "is-quiet"],
            "count": "19 successes, 100%",
            "phrase": "100% success",
            "quiet": None,
            "findings": ["Run Integrity One trial was not counted after a simulator crash."],
            "headline": None,
            "ring_complete": True,
        },
        {
            "id": "B4",
            "kicker": "B4. Two reviewers report different issues",
            "run_title": "Walk the hallway",
            "passed": 20,
            "total": 20,
            "compact": True,
            "group": "card-b3",
            "outputs": [
                health_ok,
                scenario,
                integrity,
                _human(
                    findings=[
                        {
                            "text": "The robot hesitated at the doorway.",
                            "reported_by": "Reviewer 1",
                        },
                        {
                            "text": "The approach to the exit looked uneven.",
                            "reported_by": "Reviewer 2",
                        },
                    ]
                ),
                agent,
            ],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": ["is-quiet", "is-quiet", "is-quiet", "is-speaking", "is-quiet"],
            "count": "20 successes, 100%",
            "phrase": "100% success",
            "quiet": None,
            "findings": [
                "Human review Reviewer 1: The robot hesitated at the doorway.",
                "Human review Reviewer 2: The approach to the exit looked uneven.",
            ],
            "headline": None,
            "ring_complete": True,
        },
        {
            "id": "B5",
            "kicker": "B5. An observation-tier evaluator reports a problem",
            "run_title": "Walk the hallway",
            "passed": 20,
            "total": 20,
            "compact": True,
            "group": "card-b4",
            "outputs": [
                health_ok,
                scenario,
                integrity,
                human,
                _agent(
                    grade=72,
                    findings=[
                        {
                            "text": (
                                "72% — The hallway crossing looked uneven, "
                                "with a late correction near the exit."
                            )
                        }
                    ],
                ),
            ],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": [
                "is-quiet",
                "is-quiet",
                "is-quiet",
                "is-quiet",
                "is-speaking is-graded",
            ],
            "count": "20 successes, 100%",
            "phrase": "100% success",
            "quiet": None,
            "findings": [
                "Agent review 72% — The hallway crossing looked uneven, "
                "with a late correction near the exit."
            ],
            "headline": None,
            "ring_complete": True,
            "agent_grade_ring": True,
        },
        {
            "id": "C",
            "kicker": "C. Several evaluators report a problem",
            "run_title": "Walk the hallway",
            "passed": 4,
            "total": 20,
            "compact": False,
            "group": "card-c",
            "outputs": [
                _example(
                    "Robot health",
                    "Rob health",
                    details_copy=(
                        "Joint temperatures exceeded the written limit on 12 trials. "
                        "The camera node also crashed at 12.4 s (trial 7)."
                    ),
                    findings=[
                        {
                            "text": ("Joint temperatures exceeded the written limit on 12 trials."),
                            "severity": "Needs attention",
                            "tier": "verdict",
                        },
                        {
                            "text": "Camera node crashed while walking down the hallway.",
                            "severity": "Needs attention",
                            "time": "12.4 s",
                            "trial": 7,
                            "tier": "health_finding",
                        },
                    ],
                ),
                _scenario(findings=[{"text": "4 successes, 20%."}]),
                _integrity(
                    findings=[{"text": "One trial was not counted after a simulator crash."}]
                ),
                _human(
                    findings=[
                        {
                            "text": "The robot hesitated at the doorway.",
                            "reported_by": "Reviewer 1",
                        },
                        {
                            "text": "The approach to the exit looked uneven.",
                            "reported_by": "Reviewer 2",
                        },
                    ]
                ),
                _agent(
                    grade=25,
                    findings=[
                        {
                            "text": (
                                "25% — Most trials fell short, and internal faults "
                                "were visible in the recording."
                            )
                        }
                    ],
                ),
            ],
            "mark_order": [
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            ],
            "mark_states": [
                "is-speaking",
                "is-speaking",
                "is-speaking",
                "is-speaking",
                "is-speaking is-graded",
            ],
            "count": "4 successes, 20%",
            "phrase": "20% success",
            "quiet": None,
            "findings": [
                "Robot health Joint temperatures exceeded the written limit on 12 trials.",
                "Scenario 4 successes, 20%.",
                "Robot health Camera node crashed while walking down the hallway.",
                "Run Integrity One trial was not counted after a simulator crash.",
                "Human review Reviewer 1: The robot hesitated at the doorway.",
                "Human review Reviewer 2: The approach to the exit looked uneven.",
                "Agent review 25% — Most trials fell short, and internal faults "
                "were visible in the recording.",
            ],
            "headline": "5 evaluators reported 7 problems",
            "ring_complete": False,
            "agent_grade_ring": True,
        },
    ]


def _committed_cards():
    text = FIXTURES.read_text(encoding="utf-8")
    parts = re.split(r"(?=<article class='summary-card)", text)
    cards = [part[: part.find("</article>") + 10] for part in parts if part.startswith("<article")]
    assert [re.search(r"state-kicker'>([^<]+)", card).group(1) for card in cards] == [
        state["kicker"] for state in example_states()
    ]
    return cards


def _render(state):
    return render_example_card(
        kicker=state["kicker"],
        run_title=state["run_title"],
        passed=state["passed"],
        total=state["total"],
        outputs=state["outputs"],
        compact=state["compact"],
        group=state["group"],
    )


def _marks(card):
    titles = re.findall(r"eval-name-full'>([^<]+)", card)
    classes = re.findall(r"summary class='(eval-mark[^']*)'", card)
    return titles, classes


def _ring(card):
    start = card.index("<svg class='success-ring'")
    return card[start : card.index("</svg>", start)]


def test_fixtures_page_has_exactly_the_seven_labelled_states():
    cards = _committed_cards()
    assert len(cards) == 7
    kickers = [re.search(r"state-kicker'>([^<]+)", card).group(1) for card in cards]
    assert kickers == [state["kicker"] for state in example_states()]
    for card in cards:
        assert "Example data" in card
        for title in re.findall(r"eval-name-full'>([^<]+)", card):
            assert not title.lower().endswith("evaluator")
            assert title in {
                "Robot health",
                "Scenario",
                "Run Integrity",
                "Human review",
                "Agent review",
            }


def test_each_example_state_regenerates_the_committed_card():
    for state, committed in zip(example_states(), _committed_cards(), strict=True):
        assert _render(state) == committed, state["id"]


def test_each_example_state_structure_labels_order_and_empty_handling():
    for state in example_states():
        card = _render(state)
        assert f"state-kicker'>{state['kicker']}" in card, state["id"]
        assert f"run-title'>{state['run_title']}" in card
        assert f"pct'>{state['phrase']}" in card
        assert f"count'>{state['count']}" in card
        titles, classes = _marks(card)
        assert titles == state["mark_order"], state["id"]
        assert [klass.removeprefix("eval-mark ").strip() for klass in classes] == state[
            "mark_states"
        ], state["id"]
        # Every mark, including a quiet one, still has a details panel.
        assert card.count("<details class='eval-disclosure'") == 5
        assert card.count("<div class='eval-panel'>") == 5
        assert "open" not in card.split("<details", 1)[1][:80]
        if state["quiet"]:
            assert f"callout-ok'>{state['quiet']}" in card
            assert "evaluators reported" not in card
        else:
            assert "callout-ok'" not in card
        if state["headline"]:
            assert f"callout-headline'>{state['headline']}" in card
        else:
            assert "callout-headline'" not in card
        texts = [
            re.sub(r"<[^>]+>", "", block)
            for block in re.findall(r"class='finding-text'>(.*?)</p>", card)
        ]
        assert texts == state["findings"], state["id"]
        ring = _ring(card)
        if state["ring_complete"]:
            assert "visibility='visible'" in ring, state["id"]
            assert "100%" in ring
        else:
            assert "visibility='hidden'" in ring, state["id"]
            assert state["phrase"].split("%")[0] + "%" in ring
        if state.get("agent_grade_ring"):
            assert "mini-ring" in card
            assert "is-graded" in card
        visible = re.sub(r"<[^>]+>", " ", card)
        assert not re.search(r"\b\d+ of \d+\b", visible), state["id"]
        assert "evaluator" not in " ".join(titles).lower()


def test_non_verdict_findings_do_not_change_the_ring_on_the_example_states():
    quiet = next(state for state in example_states() if state["id"] == "A")
    noisy = next(state for state in example_states() if state["id"] == "B2")
    # Both are 20/20; a health finding must not change the stored rate.
    # A is a full-size card and B2 is compact, so the badge size differs.
    assert "100%" in _ring(_render(quiet))
    assert "100%" in _ring(_render(noisy))
    assert "visibility='visible'" in _ring(_render(quiet))
    assert "visibility='visible'" in _ring(_render(noisy))
    assert "20 successes, 100%" in _render(quiet)
    assert "20 successes, 100%" in _render(noisy)
    # B1's stored 19/20 rate is 95%, even though only Scenario speaks.
    b1 = next(state for state in example_states() if state["id"] == "B1")
    assert "95%" in _ring(_render(b1))
    assert "19 successes, 95%" in _render(b1)
