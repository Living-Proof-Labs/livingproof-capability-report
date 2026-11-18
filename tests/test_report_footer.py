"""Reader navigation through the actual robot report renderer."""

from html.parser import HTMLParser

import pytest

from test_evaluator_cards import chromium  # noqa: F401
from test_publish import _page

GUIDE = "https://docs.livingprooflabs.com/reading-reports.html"


class FooterLinks(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.in_footer = False
        self.links = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == "footer":
            self.in_footer = True
        if tag == "a" and self.in_footer:
            self.links.append(dict(attrs)["href"])

    def handle_endtag(self, tag):
        if tag == "footer":
            self.in_footer = False


def test_robot_report_footer_links_to_published_reader_guide(tmp_path):
    page = _page(tmp_path, history={"href": "../", "label": "Run history"})
    assert FooterLinks(page).links == [GUIDE]
    assert "How to read this report</a>" in page
    assert "<a href='../'>Run history</a>" in page
    assert page.index("<footer") > page.index("Full lossless report")


@pytest.mark.parametrize("width", [1280, 390])
def test_reader_guide_is_visible_and_keyboard_accessible(chromium, tmp_path, width):  # noqa: F811
    path = tmp_path / "report.html"
    path.write_text(_page(tmp_path), encoding="utf-8")
    page = chromium.new_page(viewport={"width": width, "height": 800})
    try:
        page.goto(path.as_uri())
        footer = page.get_by_role("contentinfo")
        link = footer.get_by_role("link", name="How to read this report", exact=True)
        assert link.count() == 1
        assert link.get_attribute("href") == GUIDE
        link.scroll_into_view_if_needed()
        assert link.is_visible()
        # Shift+Tab from the final link, then Tab, exercises its native tab stop.
        link.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        assert link.evaluate("e => e === document.activeElement")
        box = link.bounding_box()
        assert 0 <= box["x"] and box["x"] + box["width"] <= width
        assert footer.evaluate("e => e.scrollWidth <= e.clientWidth")
    finally:
        page.close()
