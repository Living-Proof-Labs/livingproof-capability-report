"""Public rendering API: independent neutral contributions, never grading inputs."""

from dataclasses import asdict, replace
import copy

import pytest

from livingproof_capability_report import EvaluatorPresentation, render
from test_evaluator_cards import _chromium
from test_sections import bundle, report


def stored():
    return report(bundle("g1"))


def contribution(saved, **changes):
    fields = dict(
        id="health",
        title="Health",
        version="1.1.2",
        purpose="Recorded observations only; no robot verdict.",
        details="Simulator measurements are separate from absent robot health telemetry.",
        source_bundle_sha256=saved["source_bundle_sha256"],
        details_href="health.json",
    )
    fields.update(changes)
    return EvaluatorPresentation(**fields)


def test_public_api_is_optional_bound_neutral_and_does_not_mutate_documents():
    saved = stored()
    original = copy.deepcopy(saved)
    baseline = render(saved, "html")
    before_json = render(saved)
    assert render(saved, "html", evaluator_presentations=[]) == baseline
    first = contribution(saved)
    second = contribution(saved, id="recording-notes", title="Recording notes", details_href=None)
    for contributions in ([first], [second], [first, second]):
        page = render(saved, "html", evaluator_presentations=contributions)
        assert "has-presentations" in page
        assert "Advisory observations only; does not change the grade." in page
        for item in contributions:
            tab = page.split(f"id='evaluator-{item.id}'", 1)[1].split("</details>", 1)[0]
            assert "Advisory" in tab
            assert "class='pip'" not in tab
            assert "mini-ring" not in tab
        assert saved == original
        assert render(saved) == before_json
    assert "evaluator-health" not in render(saved, "html", evaluator_presentations=[second])
    assert EvaluatorPresentation.from_dict(asdict(first)) == first


@pytest.mark.parametrize(
    "changes",
    [
        {"format": "livingproof-evaluator-presentation/2"},
        {"state": "pass"},
        {"title": "<script>alert(1)</script>"},
        {"details": "bad\ntext"},
        {"title": ""},
        {"details": "a" * 2001},
        {"id": "../health"},
        {"source_bundle_sha256": "not-a-digest"},
        {"details_href": "../health.json"},
        {"details_href": "/health.json"},
        {"details_href": "https://example.com/health.json"},
        {"details_href": "health.html"},
        {"details_href": "health.json?x=1"},
        {"details_href": "%2e%2e/health.json"},
    ],
)
def test_invalid_presentation_is_refused(changes):
    with pytest.raises(ValueError):
        contribution(stored(), **changes)


def test_wire_fields_digest_duplicate_and_format_refusals():
    saved = stored()
    item = contribution(saved)
    for document in ({**asdict(item), "html": "arbitrary"}, {"id": "health"}):
        with pytest.raises(ValueError):
            EvaluatorPresentation.from_dict(document)
    for items in ([asdict(item)], [item, item], [replace(item, source_bundle_sha256="0" * 64)]):
        with pytest.raises(ValueError):
            render(saved, "html", evaluator_presentations=items)
    with pytest.raises(ValueError, match="only for HTML"):
        render(saved, "json", evaluator_presentations=[item])


def test_plain_entities_are_escaped_not_executed():
    saved = stored()
    item = contribution(saved, details="R&D and &lt;script&gt; stay text")
    page = render(saved, "html", evaluator_presentations=[item])
    assert "R&amp;D and &amp;lt;script&amp;gt; stay text" in page


@pytest.mark.parametrize("width", [390, 430, 1280])
@pytest.mark.parametrize("javascript", [True, False])
def test_browser_optional_peers_fit_keyboard_and_no_js(width, javascript):
    saved = stored()
    peers = [contribution(saved), contribution(saved, id="notes", title="Recording notes")]
    markup = render(saved, "html", evaluator_presentations=peers)
    manager, browser = _chromium()
    try:
        context = browser.new_context(
            viewport={"width": width, "height": 900}, java_script_enabled=javascript
        )
        page = context.new_page()
        page.set_content(markup)
        row = page.locator(".has-presentations > .eval-row")
        assert row.evaluate("e => e.scrollWidth <= e.clientWidth")
        for ident in ("health", "notes"):
            tab = page.locator(f"#evaluator-{ident} > summary")
            bounds = tab.bounding_box()
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
            tab.focus()
            tab.press("Enter")
            panel = page.locator("#" + tab.get_attribute("aria-controls"))
            assert panel.is_visible()
            assert "Advisory observations only" in panel.inner_text()
            assert tab.locator(".pip").count() == 0
            if javascript:
                page.wait_for_function(
                    "id => document.getElementById(id).getAttribute('aria-selected') === 'true'",
                    arg=tab.get_attribute("id"),
                )
                tab.press("Home")
                assert page.locator(".has-presentations summary").first.evaluate(
                    "e => e === document.activeElement"
                )
        context.close()
    finally:
        browser.close()
        manager.stop()


def test_existing_evaluator_identity_cannot_be_replaced():
    saved = stored()
    saved["summaries"][0]["evaluator_results"] = [
        {
            "format": "livingproof-evaluator-result/1.1.0",
            "evaluator": {"id": "health", "display_name": "Existing evaluator"},
            "descriptor": {"title": "Existing evaluator", "tier": "observation"},
        }
    ]
    with pytest.raises(ValueError, match="cannot replace"):
        render(saved, "html", evaluator_presentations=[contribution(saved)])
