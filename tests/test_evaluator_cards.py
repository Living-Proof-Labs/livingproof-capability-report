"""Evaluator cards (#58): titles as stored, fixed 180px tabs, hover, selected, tabs semantics.

The target is Art's mock (design/evaluator-card-states at edb6834: desktop.png,
mobile.png, states.png). The checks a script can make are here: markup roles and
ids, titles, the closed-on-load default, and the CSS rules for width, hover and
selected. The last test drives a real browser when one is available and checks
the same behaviour as rendered; it is skipped when Playwright or a Chromium
binary is missing (set LIVINGPROOF_BROWSER to a Chromium executable to use one).
"""

import copy
import json
import os
import re
from html.parser import HTMLParser

import pytest

from livingproof_capability_report import html_theme
from livingproof_capability_report.evaluators import (
    FALLBACK_TITLE,
    render_marks,
    summary_front,
    views_from,
)
from test_integrity_summary import FAILED, SCENARIO, SUCCESS, _report, _success_map

GROUP = "run-evaluators"


class _Tree(HTMLParser):
    """Just enough structure to read tags, attributes and the text of a fragment."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parent": self.stack[-1] if self.stack else None}
        node["text"] = ""
        self.tags.append(node)
        if tag not in {"br", "img", "input", "meta", "path", "circle", "rect", "g", "stop"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data


def _tree(fragment):
    parser = _Tree()
    parser.feed(fragment)
    return parser.tags


def _find(nodes, tag, **attrs):
    return [
        node
        for node in nodes
        if node["tag"] == tag and all(node["attrs"].get(k) == v for k, v in attrs.items())
    ]


def _classes(node):
    return (node["attrs"].get("class") or "").split()


def _two_evaluators(*, grade="PASS", k=1, n=1, integrity=None):
    report = _report(integrity=integrity or _success_map(), grade=grade)
    for summary in report["summaries"]:
        summary["k"], summary["n"] = k, n
    return report


def _front(report):
    return summary_front(report, "<p class='stored'>stored run</p>")


def _tabs(front):
    nodes = _tree(front)
    return nodes, _find(nodes, "summary"), _find(nodes, "div", role="tabpanel")


# --- titles --------------------------------------------------------------------


def test_the_title_is_used_exactly_for_the_label_the_panel_heading_and_the_finding_leader():
    scenario = copy.deepcopy(SCENARIO)
    scenario["descriptor"]["title"] = "Scenario"
    scenario["descriptor"]["findings"] = [{"text": "The robot left the route.", "tier": "verdict"}]
    views = views_from([scenario, copy.deepcopy(SUCCESS)])
    markup = render_marks(views, group=GROUP)
    nodes = _tree(markup)
    names = [node["text"] for node in _find(nodes, "span") if "eval-name-full" in _classes(node)]
    assert names == ["Scenario", "Run Integrity"]
    headings = [node["text"] for node in _find(nodes, "h4")]
    assert headings == ["Scenario", "Run Integrity"]
    leaders = [node["text"] for node in _find(nodes, "strong")]
    assert leaders == ["Scenario"]
    assert "evaluator" not in "".join(names + headings + leaders).lower()


@pytest.mark.parametrize("title", ["Scenario", "Scenario evaluator", "Robot health", "Check"])
def test_no_evaluator_suffix_is_ever_added_to_a_stored_title(title):
    scenario = copy.deepcopy(SCENARIO)
    scenario["descriptor"]["title"] = title
    scenario["descriptor"].pop("short_title", None)
    markup = render_marks(views_from([scenario]), group=GROUP)
    nodes = _tree(markup)
    label = [n["text"] for n in _find(nodes, "span") if "eval-name-full" in _classes(n)]
    assert label == [title]
    assert [n["text"] for n in _find(nodes, "h4")] == [title]


def test_display_name_is_the_title_when_the_descriptor_has_none_and_evaluator_is_the_last_resort():
    named = copy.deepcopy(SCENARIO)
    named["descriptor"].pop("title")
    named["evaluator"]["display_name"] = "Scenario"
    bare = copy.deepcopy(SCENARIO)
    bare["descriptor"].pop("title")
    bare["evaluator"].pop("display_name")
    assert FALLBACK_TITLE == "Evaluator"
    for document, expected in ((named, "Scenario"), (bare, "Evaluator")):
        markup = render_marks(views_from([document]), group=GROUP)
        nodes = _tree(markup)
        label = [n["text"] for n in _find(nodes, "span") if "eval-name-full" in _classes(n)]
        assert label == [expected]
        assert [n["text"] for n in _find(nodes, "h4")] == [expected]


def test_a_short_title_is_rendered_as_stored_beside_the_title_never_in_place_of_it():
    scenario = copy.deepcopy(SCENARIO)
    scenario["descriptor"]["title"] = "Scenario"
    scenario["descriptor"]["short_title"] = "Scen."
    nodes = _tree(render_marks(views_from([scenario]), group=GROUP))
    full = [n["text"] for n in _find(nodes, "span") if "eval-name-full" in _classes(n)]
    short = [n["text"] for n in _find(nodes, "span") if "eval-name-short" in _classes(n)]
    assert (full, short) == (["Scenario"], ["Scen."])
    # A short title equal to the title adds nothing.
    scenario["descriptor"]["short_title"] = "Scenario"
    nodes = _tree(render_marks(views_from([scenario]), group=GROUP))
    assert not [n for n in _find(nodes, "span") if "eval-name-short" in _classes(n)]


# --- closed on load ------------------------------------------------------------


@pytest.mark.parametrize(
    "report",
    [
        _two_evaluators(),
        _two_evaluators(grade="FAIL", k=0, n=1),
        _two_evaluators(grade="FAIL", k=0, n=1, integrity={"livingproof-run-integrity": FAILED}),
    ],
    ids=["passing", "failing-run", "failing-run-and-integrity"],
)
def test_every_panel_is_closed_and_nothing_is_selected_on_load(report):
    front = _front(report)
    nodes, tabs, panels = _tabs(front)
    assert len(tabs) == 2 == len(panels)
    details = _find(nodes, "details")
    assert details and all("open" not in node["attrs"] for node in details)
    assert not re.search(r"<details[^>]*\sopen\b", front)
    assert [tab["attrs"]["aria-selected"] for tab in tabs] == ["false", "false"]


def test_a_failing_run_marks_the_host_as_speaking_but_still_loads_closed():
    front = _front(_two_evaluators(grade="FAIL", k=0, n=1))
    nodes, tabs, _panels = _tabs(front)
    speaking = [tab for tab in tabs if "is-speaking" in _classes(tab)]
    assert len(speaking) == 1
    assert all("open" not in node["attrs"] for node in _find(nodes, "details"))
    assert [tab["attrs"]["aria-selected"] for tab in tabs] == ["false", "false"]


# --- tabs pattern --------------------------------------------------------------


def test_the_row_is_a_tablist_each_mark_a_tab_and_each_panel_a_tabpanel_labelled_by_its_tab():
    front = _front(_two_evaluators())
    nodes, tabs, panels = _tabs(front)
    (row,) = _find(nodes, "div", role="tablist")
    assert "eval-row" in _classes(row) and row["attrs"]["aria-label"] == "Evaluators"
    for tab in tabs:
        assert tab["attrs"]["role"] == "tab"
        assert tab["parent"]["tag"] == "details"
        assert tab["parent"]["parent"] is row
        assert tab["parent"]["attrs"]["role"] == "none"
    ids = [tab["attrs"]["id"] for tab in tabs]
    assert len(set(ids)) == len(ids)
    for tab, panel in zip(tabs, panels, strict=True):
        assert tab["attrs"]["aria-controls"] == panel["attrs"]["id"]
        assert panel["attrs"]["aria-labelledby"] == tab["attrs"]["id"]
        assert panel["attrs"]["role"] == "tabpanel"
    # A tab holds only its summary. Its panel sits outside the (scrolling) row.
    assert all(len(_find(nodes, "div", id=panel["attrs"]["id"])) == 1 for panel in panels)
    assert all(panel["parent"]["attrs"]["class"] == "eval-tabpanels" for panel in panels)
    assert all(row is not panel["parent"]["parent"] for panel in panels)


def test_the_tabs_are_one_exclusive_group_and_every_id_is_unique_on_the_page():
    front = _front(_two_evaluators())
    nodes, tabs, panels = _tabs(front)
    names = {n["attrs"]["name"] for n in _find(nodes, "details")}
    assert names == {GROUP}
    ids = [n["attrs"]["id"] for n in nodes if "id" in n["attrs"]]
    assert len(ids) == len(set(ids))
    assert {t["attrs"]["id"] for t in tabs} == {f"{GROUP}-tab-1", f"{GROUP}-tab-2"}


def test_the_stored_run_sits_in_the_host_panel_and_the_panel_heading_is_the_title():
    front = _front(_two_evaluators())
    nodes, _tabs_, panels = _tabs(front)
    hosts = [p for p in panels if "stored run" in p["text"]]
    assert len(hosts) == 1
    assert hosts[0]["text"].startswith("Scenario")


def _script(front):
    start = front.index("<script data-eval-tabs>") + len("<script data-eval-tabs>")
    return front[start : front.index("</script>", start)]


# Anything that could reach outside the page or load more code. Matched on the
# script text. The allow-list below also fails on any identifier not in it, so a
# renamed or assembled call (``self.fetch``, ``a["fet"+"ch"]``) cannot slip in.
_NETWORK_AND_LOADING = (
    "fetch",
    "XMLHttpRequest",
    "import",
    "WebSocket",
    "WebTransport",
    "EventSource",
    "sendBeacon",
    "Worker",
    "serviceWorker",
    "Image",
    "Audio",
    "Request",
    "src",
    "href",
    "http",
    "//",
    "navigator",
    "location",
    "window",
    "top",
    "parent.",
    "frames",
    "postMessage",
    "cookie",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "Function",
    "setTimeout",
    "setInterval",
    "document.write",
    "innerHTML",
    "outerHTML",
    "insertAdjacent",
    "createElement",
    "appendChild",
    "open(",
)


def test_the_script_is_self_contained_and_makes_no_network_calls_or_loads_anything():
    front = _front(_two_evaluators())
    assert front.count("<script") == 1 == front.count("<script data-eval-tabs>")
    assert "<script src" not in front and "<script type" not in front
    script = _script(front)
    for banned in _NETWORK_AND_LOADING:
        assert banned not in script, banned
    assert not re.search(r"(?<![\w.-])eval\s*\(", script)
    # Allow-list: every global or member the script touches is one of these.
    allowed = {
        "function", "var", "return", "if", "undefined", "Array", "from", "find", "forEach",
        "indexOf", "focus", "preventDefault", "addEventListener", "querySelector",
        "querySelectorAll", "setAttribute", "tabIndex", "parentNode", "open", "target", "key",
        "document", "activeElement", "currentScript", "ArrowRight", "ArrowLeft", "Home", "End",
        "length", "aria", "selected", "true", "false", "scope", "eval", "row", "disclosure",
        "summary", "toggle", "focusin", "keydown", "data", "tabs", "s", "w", "t", "f", "a", "o",
        "x", "e", "i", "n",
    }  # fmt: skip
    literals = set(re.findall(r"'([^']*)'", script))
    assert literals == {
        ":scope > .eval-row",
        ":scope > .eval-disclosure > summary",
        "aria-selected",
        "true",
        "false",
        "toggle",
        "focusin",
        "keydown",
    }, literals
    assert '"' not in script and "`" not in script
    quoted = re.sub(r"'[^']*'", "''", script)
    words = set(re.findall(r"[A-Za-z_$][\w$]*", quoted))
    assert words <= allowed, sorted(words - allowed)
    assert len(script) < 1400


def test_the_script_only_reads_and_writes_inside_its_own_container():
    script = _script(_front(_two_evaluators()))
    assert "document.currentScript" in script and "s.parentNode" in script
    # Selectors are scoped to the row; the only document-level read is the focused element.
    assert script.count("document.") == 2
    assert "document.activeElement" in script
    assert re.findall(r"querySelector(?:All)?\('([^']*)'", script) == [
        ":scope > .eval-row",
        ":scope > .eval-disclosure > summary",
    ]


def test_the_markup_carries_no_roving_tabindex_so_with_scripts_off_every_tab_is_a_tab_stop():
    nodes, tabs, _panels = _tabs(_front(_two_evaluators()))
    assert all("tabindex" not in tab["attrs"] for tab in tabs)
    assert all("onclick" not in n["attrs"] and "onkeydown" not in n["attrs"] for n in nodes)


def test_the_script_handles_arrows_home_and_end_and_leaves_activation_to_the_native_summary():
    script = _script(_front(_two_evaluators()))
    for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert key in script
    assert "preventDefault" in script and "focus()" in script
    # Moving focus never opens a panel: no code path writes the details' open state.
    assert ".open=" not in script and ".open =" not in script and "click" not in script
    assert "tabIndex" in script and "aria-selected" in script
    # Without it the details element still opens, closes and styles the open tab.
    assert "[open] > summary.eval-mark" in html_theme.stylesheet()


# --- more marks than there are panel rules -------------------------------------


def test_a_mark_past_the_generated_panel_rules_keeps_its_panel_inside_its_own_details():
    limit = html_theme.MAX_PANEL_TABS
    documents = []
    for index in range(limit + 2):
        document = copy.deepcopy(SCENARIO)
        document["evaluator"]["id"] = f"evaluator-{index}"
        document["descriptor"]["title"] = f"Check {index:02d}"
        documents.append(document)
    markup = render_marks(views_from(documents), group=GROUP)
    nodes = _tree(markup)
    panels = _find(nodes, "div", role="tabpanel")
    assert len(panels) == limit + 2
    outside = [p for p in panels if p["parent"]["attrs"].get("class") == "eval-tabpanels"]
    inside = [p for p in panels if p["parent"]["tag"] == "details"]
    assert (len(outside), len(inside)) == (limit, 2)
    inline_classes = [_classes(d) for d in _find(nodes, "details") if "eval-inline" in _classes(d)]
    assert len(inline_classes) == 2
    # That the :has() rules stop at MAX_PANEL_TABS is pinned in
    # test_outside_panels_are_shown_only_by_has_rules_and_overflow_marks_use_open_details.


def test_removing_the_tabs_script_leaves_every_panel_body_in_the_markup():
    """Without the script, panel copy is still in the HTML and is not hidden or inert."""
    front = _front(_two_evaluators())
    stripped = re.sub(r"<script data-eval-tabs>.*?</script>", "", front, count=1, flags=re.S)
    assert "<script" not in stripped
    nodes, _, panels = _tabs(stripped)
    assert len(panels) == 2
    assert all("hidden" not in node["attrs"] and "inert" not in node["attrs"] for node in panels)
    assert [node["text"] for node in _find(nodes, "h4")] == ["Scenario", "Run Integrity"]
    assert "Scenario" in panels[0]["text"] and "Run Integrity" in panels[1]["text"]


def test_outside_panels_are_shown_only_by_has_rules_and_overflow_marks_use_open_details():
    """First 24 panels rely on :has(); a mark past that is shown by open details."""
    css = html_theme.stylesheet()
    assert ".eval-disclosure[open] > .eval-tabpanel { display: block; }" in css
    rules = [block.strip() for block in css.split("}") if "eval-tabpanel" in block]
    shown = [rule for rule in rules if "display: block" in rule]
    overflow = [rule for rule in shown if ".eval-disclosure[open] > .eval-tabpanel" in rule]
    has_rules = [rule for rule in shown if ":has(" in rule]
    assert len(overflow) == 1
    assert len(has_rules) == html_theme.MAX_PANEL_TABS
    assert len(shown) == 1 + html_theme.MAX_PANEL_TABS


# --- CSS: width, hover, selected, focus, narrow ----------------------------------


def _parse(text):
    """[(at_rule_or_None, selector, declarations)] for the theme CSS, one @media level deep."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    found = []

    def declarations(body):
        values = {}
        for item in body.split(";"):
            if ":" in item:
                key, value = item.split(":", 1)
                values[key.strip()] = " ".join(value.split())
        return values

    def walk(chunk, at):
        position = 0
        while True:
            start = chunk.find("{", position)
            if start < 0:
                return
            head = " ".join(chunk[position:start].split())
            depth, end = 1, start + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(chunk[end], 0)
                end += 1
            body = chunk[start + 1 : end - 1]
            if head.startswith("@media"):
                walk(body, head)
            elif not head.startswith("@"):
                found.append((at, head, declarations(body)))
            position = end

    walk(text, None)
    return found


def _rules(at=None):
    return [(s, d) for a, s, d in _parse(html_theme.stylesheet()) if a == at]


def _rule(selector, at=None):
    """The declarations of every rule for exactly this selector, merged in source order."""
    merged = {}
    for found, declarations in _rules(at):
        if found == selector:
            merged.update(declarations)
    assert merged, selector
    return merged


def test_each_mark_is_11_25rem_wide_left_aligned_and_the_row_does_not_stretch_it():
    row = _rule(".eval-row")
    assert row["--eval-card-width"] == "11.25rem"
    assert row["display"] == "flex" and row["flex-wrap"] == "wrap"
    assert row["justify-content"] == "flex-start" and row["align-items"] == "stretch"
    assert "grid-template-columns" not in row
    disclosure = _rule(".eval-disclosure")
    assert disclosure["width"] == "var(--eval-card-width)"
    assert disclosure["flex"] == "0 0 var(--eval-card-width)"
    css = html_theme.stylesheet()
    assert "repeat(var(--eval-count" not in css
    assert "minmax(0, 1fr)" not in _rule(".eval-row").get("grid-template-columns", "")


def test_on_a_narrow_screen_the_marks_keep_their_width_and_the_row_scrolls_sideways():
    row = _rule(".eval-row", "@media (max-width: 640px)")
    assert row["flex-wrap"] == "nowrap" and row["overflow-x"] == "auto"
    narrow = _rule(".eval-row .eval-disclosure", "@media (max-width: 640px)")
    assert narrow["flex-shrink"] == "0" and "width" not in narrow and "flex-basis" not in narrow


def test_hover_changes_the_background_and_border_and_keeps_the_pointer_cursor():
    hover = _rule(".eval-disclosure > summary.eval-mark:hover")
    assert hover["background"] == "color-mix(in srgb, var(--bg-muted) 85%, var(--surface))"
    assert hover["border-color"] == "var(--border-strong)"
    assert _rule(".eval-disclosure > summary.eval-mark")["cursor"] == "pointer"


def test_keyboard_focus_shows_the_focus_ring():
    ring = _rule(".eval-disclosure > summary.eval-mark:focus-visible")
    assert ring["outline"] == "3px solid var(--focus)"
    assert "summary:focus-visible" in html_theme.stylesheet()


def test_selected_chrome_belongs_to_the_open_mark_only_and_is_separate_from_speaking():
    selected = _rule(".eval-disclosure[open] > summary.eval-mark")
    assert selected["background"] == "color-mix(in srgb, var(--link) 9%, var(--surface))"
    assert selected["border-color"] == "color-mix(in srgb, var(--link) 70%, var(--border))"
    connector = _rule(".eval-disclosure[open] > summary.eval-mark::after")
    assert connector["content"] == '""' and connector["position"] == "absolute"
    assert "rotate(45deg)" in connector["transform"]
    # Speaking tint applies to closed marks only, so an open mark never mixes the two.
    speaking = _rule(".eval-disclosure:not([open]) > summary.eval-mark.is-speaking")
    assert speaking["background"] == "color-mix(in srgb, var(--speak) 10%, var(--surface))"
    assert speaking["border-color"] == "color-mix(in srgb, var(--speak) 45%, var(--border))"
    for selector, declarations in _rules():
        if selector.endswith(".eval-mark.is-speaking") and ":not([open])" not in selector:
            assert "background" not in declarations and "border-color" not in declarations
    # Nothing but an open mark's rules use the selected link tint.
    tinted = [s for s, d in _rules() if "var(--link) 9%" in str(d) and "::after" not in s]
    assert tinted == [".eval-disclosure[open] > summary.eval-mark"]


def test_the_panel_has_a_3px_link_top_edge_and_a_link_coloured_heading():
    panel = _rule(".eval-panel")
    assert panel["border-top"] == "3px solid var(--link)"
    assert _rule(".eval-panel h4")["color"] == "var(--link)"


def test_closed_panels_are_hidden_until_their_tab_is_open():
    # The :has() reveal rules themselves are pinned in
    # test_outside_panels_are_shown_only_by_has_rules_and_overflow_marks_use_open_details.
    assert _rule(".eval-tabpanel")["display"] == "none"
    assert (
        ".evaluators:has(> .eval-row > .eval-disclosure:nth-child(1)[open]) "
        "> .eval-tabpanels > .eval-tabpanel:nth-child(1) { display: block; }"
    ) in html_theme.stylesheet()


def test_the_mark_label_is_not_restyled_by_the_generic_summary_rule():
    mark = _rule(".eval-mark")
    assert mark["text-transform"] == "none" and mark["letter-spacing"] == "normal"


# --- rendered in a browser -------------------------------------------------------


# CI sets this so a missing Playwright or Chromium fails the browser tests
# instead of skipping them; elsewhere they skip.
REQUIRE_BROWSER = os.environ.get("LIVINGPROOF_REQUIRE_BROWSER") == "1"


def _unavailable(reason):
    if REQUIRE_BROWSER:
        pytest.fail(f"LIVINGPROOF_REQUIRE_BROWSER is set but {reason}", pytrace=False)
    pytest.skip(reason)


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        _unavailable(f"Playwright is not installed: {error}")
    manager = sync_playwright().start()
    path = os.environ.get("LIVINGPROOF_BROWSER") or None
    try:
        return manager, manager.chromium.launch(executable_path=path)
    except Exception as error:  # no browser binary on this machine
        manager.stop()
        _unavailable(f"no Chromium available: {error}")


def _selected(page, expected):
    """aria-selected follows the toggle event, which the browser fires a moment after a click."""
    page.wait_for_function(
        "want => JSON.stringify([...document.querySelectorAll('summary[role=tab]')]"
        ".map(e => e.getAttribute('aria-selected'))) === JSON.stringify(want)",
        arg=expected,
        timeout=3000,
    )


def _page(front, tmp_path):
    style = html_theme.stylesheet()
    path = tmp_path / "cards.html"
    path.write_text(
        f"<!doctype html><meta charset='utf-8'><style>{style}</style>"
        f"<main class='wrap'>{front}</main>",
        encoding="utf-8",
    )
    return path


def test_in_a_browser_marks_are_180px_open_one_at_a_time_and_aria_selected_follows(tmp_path):
    report = json.loads(json.dumps(_two_evaluators(grade="FAIL", k=0, n=1)))
    path = _page(_front(report), tmp_path)
    manager, browser = _chromium()
    try:
        wide = browser.new_page(viewport={"width": 1280, "height": 800})
        wide.goto(path.as_uri())
        tabs = wide.locator("summary[role=tab]")
        assert tabs.count() == 2
        widths = [tabs.nth(i).evaluate("e => e.getBoundingClientRect().width") for i in range(2)]
        assert widths == [180, 180]
        card = wide.locator(".evaluators").bounding_box()["width"]
        assert wide.locator(".eval-row").evaluate("e => e.scrollWidth") <= card + 1
        lefts = [tabs.nth(i).bounding_box()["x"] for i in range(2)]
        assert lefts[1] - lefts[0] == pytest.approx(180 + 7.2, abs=0.6)
        assert wide.locator(".eval-tabpanel:visible").count() == 0
        assert [tabs.nth(i).get_attribute("aria-selected") for i in range(2)] == ["false"] * 2

        tabs.nth(0).click()
        _selected(wide, ["true", "false"])
        assert wide.locator(".eval-tabpanel:visible").count() == 1
        assert wide.locator(".eval-tabpanel:visible").get_attribute("aria-labelledby") == (
            tabs.nth(0).get_attribute("id")
        )
        tabs.nth(1).click()
        _selected(wide, ["false", "true"])
        assert wide.locator(".eval-tabpanel:visible").count() == 1
        tabs.nth(1).click()
        _selected(wide, ["false", "false"])
        assert wide.locator(".eval-tabpanel:visible").count() == 0

        tabs.nth(1).hover()
        quiet = tabs.nth(1).evaluate("e => getComputedStyle(e).backgroundColor")
        wide.mouse.move(5, 5)
        rest = tabs.nth(1).evaluate("e => getComputedStyle(e).backgroundColor")
        assert quiet != rest

        narrow = browser.new_page(viewport={"width": 390, "height": 800})
        narrow.goto(path.as_uri())
        marks = narrow.locator("summary[role=tab]")
        assert [marks.nth(i).evaluate("e => e.getBoundingClientRect().width") for i in (0, 1)] == [
            180,
            180,
        ]
        row = narrow.locator(".eval-row")
        assert row.evaluate("e => e.scrollWidth > e.clientWidth")
        assert row.evaluate("e => getComputedStyle(e).overflowX") == "auto"
    finally:
        browser.close()
        manager.stop()


def _marks_page(count, tmp_path):
    documents = []
    for index in range(count):
        document = copy.deepcopy(SCENARIO)
        document["evaluator"]["id"] = f"evaluator-{index + 1}"
        document["descriptor"]["title"] = f"Check {index + 1}"
        document["descriptor"]["findings"] = []
        documents.append(document)
    markup = render_marks(views_from(documents), group=GROUP)
    return _page(markup, tmp_path)


def _visible_panels(page):
    return page.eval_on_selector_all(
        ".eval-tabpanel",
        "els => els.filter(e => e.getClientRects().length).map(e => e.getAttribute('id'))",
    )


@pytest.fixture
def chromium():
    manager, browser = _chromium()
    try:
        yield browser
    finally:
        browser.close()
        manager.stop()


def test_with_scripts_off_one_panel_opens_at_a_time_and_only_aria_selected_goes_stale(
    chromium, tmp_path
):
    path = _marks_page(3, tmp_path)
    context = chromium.new_context(
        java_script_enabled=False, viewport={"width": 1280, "height": 800}
    )
    page = context.new_page()
    page.goto(path.as_uri())
    tabs = page.locator("summary[role=tab]")
    assert tabs.count() == 3
    assert _visible_panels(page) == []
    tabs.nth(0).click()
    assert _visible_panels(page) == [f"{GROUP}-panel-1"]
    # The panel shows its own copy: the title heading and its descriptor text.
    assert page.locator(f"#{GROUP}-panel-1 h4").inner_text() == "Check 1"
    assert "Checks each step" in page.locator(f"#{GROUP}-panel-1").inner_text()
    tabs.nth(1).click()
    assert _visible_panels(page) == [f"{GROUP}-panel-2"]
    tabs.nth(1).click()
    assert _visible_panels(page) == []
    tabs.nth(2).click()
    assert _visible_panels(page) == [f"{GROUP}-panel-3"]
    # Only the ARIA state stays as loaded, and no tab is taken out of the Tab order.
    assert [tabs.nth(i).get_attribute("aria-selected") for i in range(3)] == ["false"] * 3
    assert [tabs.nth(i).get_attribute("tabindex") for i in range(3)] == [None] * 3
    context.close()


@pytest.mark.parametrize("scripts", [True, False], ids=["scripts-on", "scripts-off"])
def test_the_25th_and_26th_marks_still_open_and_close_their_panels(chromium, tmp_path, scripts):
    limit = html_theme.MAX_PANEL_TABS
    path = _marks_page(limit + 2, tmp_path)
    context = chromium.new_context(
        java_script_enabled=scripts, viewport={"width": 1280, "height": 900}
    )
    page = context.new_page()
    page.goto(path.as_uri())
    tabs = page.locator("summary[role=tab]")
    assert tabs.count() == limit + 2
    last, after = limit, limit + 1  # zero-based: the 25th and 26th marks

    tabs.nth(last).click()
    assert _visible_panels(page) == [f"{GROUP}-panel-{limit + 1}"]
    # The panel opens full width under the row, not squeezed into its 180px tab.
    box = page.locator(f"#{GROUP}-panel-{limit + 1}").bounding_box()
    assert box["width"] > 600
    # The open tab keeps a normal tab height, not the height of the details with its panel.
    height = "e => e.getBoundingClientRect().height"
    open_height = tabs.nth(last).evaluate(height)
    closed_height = tabs.nth(after).evaluate(height)
    assert abs(open_height - closed_height) <= 2, (open_height, closed_height)
    assert open_height < 120
    assert tabs.nth(last).evaluate("e => e.getBoundingClientRect().width") == 180
    if scripts:
        page.wait_for_function(
            "() => document.querySelectorAll('summary[role=tab]')[24].getAttribute('aria-selected') === 'true'"
        )
    # The selected chrome (details[open] > summary) still applies to the 25th tab.
    border = "e => getComputedStyle(e).borderColor"
    assert tabs.nth(last).evaluate(border) != tabs.nth(after).evaluate(border)

    tabs.nth(after).click()  # exclusive: the 26th replaces the 25th
    assert _visible_panels(page) == [f"{GROUP}-panel-{limit + 2}"]
    assert abs(tabs.nth(after).evaluate(height) - closed_height) <= 2
    tabs.nth(5).click()  # a panel under the row replaces an inline one
    assert _visible_panels(page) == [f"{GROUP}-panel-6"]
    tabs.nth(last).click()
    assert _visible_panels(page) == [f"{GROUP}-panel-{limit + 1}"]
    tabs.nth(last).click()  # clicking the open one closes it
    assert _visible_panels(page) == []
    context.close()


def test_arrow_keys_move_focus_with_wrapping_home_and_end_and_never_open_a_panel(
    chromium, tmp_path
):
    path = _marks_page(3, tmp_path)
    page = chromium.new_page(viewport={"width": 1280, "height": 800})
    page.goto(path.as_uri())
    tabs = page.locator("summary[role=tab]")

    def state():
        found = page.evaluate(
            "() => [...document.querySelectorAll('summary[role=tab]')]"
            ".map(e => [e.tabIndex, e === document.activeElement])"
        )
        # Exactly one tab is in the Tab order at any moment (roving tabindex).
        assert sum(1 for index, _ in found if index == 0) == 1, found
        return found

    # Roving tabindex from load: the first tab is the one Tab stop.
    assert [t for t, _ in state()] == [0, -1, -1]
    tabs.nth(0).focus()
    page.keyboard.press("ArrowRight")
    assert state() == [[-1, False], [0, True], [-1, False]]
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")  # wraps to the first
    assert state() == [[0, True], [-1, False], [-1, False]]
    page.keyboard.press("ArrowLeft")  # wraps to the last
    assert state() == [[-1, False], [-1, False], [0, True]]
    page.keyboard.press("Home")
    assert state()[0] == [0, True]
    page.keyboard.press("End")
    assert state()[2] == [0, True]
    # Moving focus opened nothing and selected nothing.
    assert _visible_panels(page) == []
    assert [tabs.nth(i).get_attribute("aria-selected") for i in range(3)] == ["false"] * 3

    # Enter opens the focused tab, and again closes it, as for a native summary.
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelectorAll('summary[role=tab]')[2].getAttribute('aria-selected') === 'true'"
    )
    assert _visible_panels(page) == [f"{GROUP}-panel-3"]
    page.keyboard.press("ArrowLeft")  # moving away leaves it open and selected
    assert _visible_panels(page) == [f"{GROUP}-panel-3"]
    assert tabs.nth(2).get_attribute("aria-selected") == "true"
    page.keyboard.press("Enter")
    assert _visible_panels(page) == [f"{GROUP}-panel-2"]
    page.keyboard.press("Enter")
    assert _visible_panels(page) == []

    # With a tab focused, Tab leaves the row rather than visiting the other tabs.
    tabs.nth(1).focus()
    page.keyboard.press("Tab")
    assert not any(focused for _, focused in state())
    page.keyboard.press("Shift+Tab")
    assert state()[1] == [0, True]
