"""Each evaluator tab has a stable, unique anchor that opens it when navigated to (#109).

The tab ids `run-evaluators-tab-N` depend on the reporter's private order (tier, then title), so
an outside page cannot know N: Run Integrity is tab 2 whenever a Scenario result is present. Each
tab's `<details class="eval-disclosure">` now also carries `id="evaluator-<evaluator id>"`.
(The `<summary>` keeps `run-evaluators-tab-N`: it is the tab's id, and an element has one id.)
"""

import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from livingproof_capability_report.evaluators import summary_front
from test_evaluator_cards import _chromium, _page

FIXTURES = Path(__file__).parent / "fixtures/integrity"
INTEGRITY = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
SCENARIO = json.loads((FIXTURES / "scenario.json").read_text(encoding="utf-8"))
PAIRS = {"livingproof-run-integrity": "Run Integrity", "livingproof-scenario": "Scenario"}


def _front(*, scenario: bool, integrity: dict | None = None) -> str:
    document = copy.deepcopy(integrity or INTEGRITY)
    run_id = document["integrity"]["run"]["id"]
    results = [{"id": "stock-seed-01"}]
    if scenario:
        results[0]["evaluator_results"] = [copy.deepcopy(SCENARIO)]
    report = {
        "source_bundle": {
            "results": results,
            "assessment": {"integrity_results": {"livingproof-run-integrity": document}},
        },
        "summaries": [
            {"run_id": run_id, "result_ids": ["stock-seed-01"], "grade": "PASS", "k": 1, "n": 1}
        ],
    }
    return summary_front(report, "<p class='stored-status'>Stored overall status: PASS</p>")


class Tabs(HTMLParser):
    """Every element id on the page, and the label of the tab each `evaluator-*` id sits on."""

    def __init__(self, text: str):
        super().__init__()
        self.ids: list[str] = []
        self.labels: dict[str, str] = {}
        self._anchor: str | None = None
        self._in_label = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "details" and str(attrs.get("id", "")).startswith("evaluator-"):
            self._anchor = attrs["id"]
            assert "eval-disclosure" in attrs["class"]
        cls = attrs.get("class") or ""
        if tag == "span" and self._anchor and "eval-name-full" in cls.split():
            self._in_label = True

    def handle_data(self, data):
        if self._in_label and self._anchor:
            self.labels[self._anchor] = data
            self._in_label = False

    def handle_endtag(self, tag):
        if tag == "details":
            self._anchor = None


@pytest.mark.parametrize("scenario", [False, True], ids=["no scenario", "with scenario"])
def test_each_evaluator_has_a_unique_anchor_on_its_own_tab(scenario: bool):
    tabs = Tabs(_front(scenario=scenario))
    expected = {"livingproof-run-integrity": "Run Integrity"}
    if scenario:
        expected["livingproof-scenario"] = "Scenario"
    assert {k: v for k, v in tabs.labels.items()} == {
        f"evaluator-{k}": v for k, v in expected.items()
    }
    assert len(tabs.ids) == len(set(tabs.ids)), "ids must be unique on the page"
    for evaluator_id in expected:
        assert tabs.ids.count(f"evaluator-{evaluator_id}") == 1


def test_the_anchor_is_stable_whatever_the_tab_order():
    alone = Tabs(_front(scenario=False))
    both = Tabs(_front(scenario=True))
    anchor = "evaluator-livingproof-run-integrity"
    assert anchor in alone.labels and anchor in both.labels
    # Tab 1 without a Scenario result, tab 2 with one; the anchor did not move.
    assert re.search(r"id='run-evaluators-tab-1'", _front(scenario=False))
    html = _front(scenario=True)
    assert html.index("id='evaluator-livingproof-scenario'") < html.index(f"id='{anchor}'")
    assert both.ids.index("run-evaluators-tab-2") == both.ids.index(anchor) + 1


def test_the_existing_tab_and_panel_ids_are_kept():
    tabs = Tabs(_front(scenario=True))
    for name in ("run-evaluators-tab-1", "run-evaluators-tab-2", "run-evaluators-panel-1"):
        assert name in tabs.ids


def test_an_evaluator_id_is_made_safe_and_stays_unique():
    document = copy.deepcopy(INTEGRITY)
    document["evaluator"]["id"] = "Acme Co/Run #1"
    twin = copy.deepcopy(SCENARIO)
    twin["evaluator"]["id"] = "acme-co-run--1"
    run_id = document["integrity"]["run"]["id"]
    report = {
        "source_bundle": {
            "results": [{"id": "r", "evaluator_results": [twin]}],
            "assessment": {"integrity_results": {"x": document}},
        },
        "summaries": [{"run_id": run_id, "result_ids": ["r"], "grade": "PASS", "k": 1, "n": 1}],
    }
    ids = Tabs(summary_front(report, "")).ids
    anchors = [i for i in ids if i.startswith("evaluator-")]
    assert len(anchors) == 2 and len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"evaluator-[A-Za-z0-9._-]+", a) for a in anchors)


@pytest.mark.parametrize("scenario", [False, True], ids=["no scenario", "with scenario"])
def test_in_a_browser_the_fragment_opens_its_own_tab(scenario: bool, tmp_path):
    path = _page(_front(scenario=scenario), tmp_path)
    manager, browser = _chromium()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        for evaluator_id, title in PAIRS.items():
            if evaluator_id == "livingproof-scenario" and not scenario:
                continue
            # First load with the fragment in the URL.
            page.goto(f"{path.as_uri()}#evaluator-{evaluator_id}")
            page.wait_for_function("() => document.querySelectorAll('.eval-tabpanel').length > 0")
            page.wait_for_function(
                "t => document.querySelector('summary[aria-selected=true] .eval-name-full')"
                "?.textContent === t",
                arg=title,
                timeout=3000,
            )
            assert page.locator(".eval-tabpanel:visible h4").all_inner_texts() == [title]
            assert (
                page.evaluate("document.activeElement.querySelector('.eval-name-full').textContent")
                == title
            )
        # Navigating to another evaluator's anchor on the same page switches tabs.
        if scenario:
            page.evaluate("location.hash = '#evaluator-livingproof-scenario'")
            page.wait_for_function(
                "() => document.querySelector('summary[aria-selected=true] .eval-name-full')"
                "?.textContent === 'Scenario'",
                timeout=3000,
            )
            page.evaluate("location.hash = '#evaluator-livingproof-run-integrity'")
            page.wait_for_function(
                "() => document.querySelector('summary[aria-selected=true] .eval-name-full')"
                "?.textContent === 'Run Integrity'",
                timeout=3000,
            )
            assert page.locator(".eval-tabpanel:visible").count() == 1
    finally:
        browser.close()
        manager.stop()


def test_the_readme_documents_the_anchor():
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    assert "### Deep-linking to an evaluator" in readme
    assert "evaluator-<evaluator id>" in readme and "#evaluator-livingproof-run-integrity" in readme


# --- Art's refinements: scroll into view, and a CSS-only landed highlight ------------


def _tall(path: Path) -> Path:
    """The card below 2000px of filler, so landing on a tab has to scroll."""
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("<main class='wrap'>", "<main class='wrap'><div style='height:2000px'></div>")
    )
    return path


def _in_view(page, selector: str) -> bool:
    return page.evaluate(
        "s => { const r = document.querySelector(s).getBoundingClientRect();"
        " return r.top >= 0 && r.bottom <= innerHeight; }",
        selector,
    )


def test_the_landed_tab_gets_a_scroll_margin_and_a_css_only_highlight():
    from livingproof_capability_report import html_theme

    css = html_theme.stylesheet()
    assert re.search(r"\.eval-disclosure\[id\][^{]*\{[^}]*scroll-margin-top:", css)
    assert "@keyframes eval-landed" in css
    rule = re.search(r"\.eval-disclosure\[data-landed\][^{]*\{([^}]*)\}", css).group(1)
    assert "outline: 2px solid var(--focus)" in rule and "animation: eval-landed 1.5s" in rule
    reduced = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S).group(
        1
    )
    assert "data-landed" in reduced and "animation: none" in reduced


@pytest.mark.parametrize("scenario", [False, True], ids=["no scenario", "with scenario"])
def test_in_a_browser_landing_scrolls_into_view_and_marks_the_tab(scenario: bool, tmp_path):
    path = _tall(_page(_front(scenario=scenario), tmp_path))
    manager, browser = _chromium()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 700})
        page.goto(f"{path.as_uri()}#evaluator-livingproof-run-integrity")
        page.wait_for_function("() => document.querySelector('[data-landed]')", timeout=3000)
        landed = page.locator("details[data-landed]")
        assert landed.count() == 1
        assert landed.get_attribute("id") == "evaluator-livingproof-run-integrity"
        assert page.evaluate("scrollY") > 0
        assert _in_view(page, "details[data-landed] > summary")
        panel = page.evaluate(
            "() => { const p = [...document.querySelectorAll('.eval-tabpanel')]"
            ".find(e => e.offsetParent); const r = p.getBoundingClientRect();"
            " return r.top >= 0 && r.bottom <= innerHeight; }"
        )
        assert panel, "the opened panel should be in view"
        assert page.locator(".eval-tabpanel:visible h4").all_inner_texts() == ["Run Integrity"]
        # Landing on another evaluator moves the mark: one at a time.
        if scenario:
            page.evaluate("location.hash = '#evaluator-livingproof-scenario'")
            page.wait_for_function(
                "() => document.querySelector('details[data-landed]')?.id"
                " === 'evaluator-livingproof-scenario'",
                timeout=3000,
            )
            assert page.locator("details[data-landed]").count() == 1
        # The highlight is a 2px accent outline that fades by CSS animation, no timers.
        style = page.evaluate(
            "() => { const s = document.querySelector('details[data-landed] > summary');"
            " const c = getComputedStyle(s);"
            " return {w: c.outlineWidth, a: c.animationName, d: c.animationDuration,"
            " fv: s.matches(':focus-visible')}; }"
        )
        if style["fv"]:
            assert style["w"] == "3px"  # the keyboard focus ring wins, so it never fades away
        else:
            assert (style["w"], style["a"], style["d"]) == ("2px", "eval-landed", "1.5s")
        # Reduced motion: the same outline, static.
        calm = browser.new_page(viewport={"width": 1280, "height": 700}, reduced_motion="reduce")
        calm.goto(f"{path.as_uri()}#evaluator-livingproof-run-integrity")
        calm.wait_for_function("() => document.querySelector('[data-landed]')", timeout=3000)
        rest = calm.evaluate(
            "() => { const s = document.querySelector('details[data-landed] > summary');"
            " const c = getComputedStyle(s);"
            " return {w: c.outlineWidth, a: c.animationName, fv: s.matches(':focus-visible')}; }"
        )
        assert rest["a"] == "none"
        assert rest["w"] == ("3px" if rest["fv"] else "2px")
    finally:
        browser.close()
        manager.stop()
