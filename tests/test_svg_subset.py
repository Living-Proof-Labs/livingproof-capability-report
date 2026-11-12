"""SVG subset, mirrored from livingproof-evaluator result 1.1.0."""

from xml.etree.ElementTree import ParseError

import pytest
from defusedxml.common import DefusedXmlException

from livingproof_capability_report.svg_icon import acceptable_icon, fromstring, svg_subset_errors


def _svg(body="", *, view_box=True):
    box = " viewBox='0 0 24 24'" if view_box else ""
    return f"<svg{box}>{body}</svg>"


def test_parser_is_defusedxml():
    import defusedxml.ElementTree as defused_tree

    assert fromstring is defused_tree.fromstring


def test_allowed_shapes_and_paints():
    icon = _svg(
        "<line x1='0' y1='0' x2='1' y2='1' stroke='currentColor'/>"
        "<polyline points='0,0 1,1' fill='none' stroke='currentColor'/>"
        "<polygon points='0,0 1,0 1,1' fill='transparent'/>"
        "<circle cx='1' cy='1' r='1' fill='none'/>"
        "<g><rect width='1' height='1' fill='currentColor'/></g>"
        "<path d='M0 0 L1 1' fill='none' stroke='currentColor'/>"
    )
    assert svg_subset_errors(icon) == []
    assert acceptable_icon(icon) == icon.strip()


def test_external_entity_is_not_resolved(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-MARKER")
    icon = (
        '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file://'
        + str(secret)
        + '">]><svg viewBox="0 0 24 24">&xxe;</svg>'
    )
    errors = svg_subset_errors(icon)
    assert errors
    assert "SECRET-MARKER" not in "\n".join(errors)
    with pytest.raises((DefusedXmlException, ParseError)):
        fromstring(icon)


def test_byte_cap_counts_utf8_bytes():
    icon = "<svg viewBox='0 0 24 24' id='" + ("é" * 4096) + "'></svg>"
    assert len(icon) <= 8192
    assert len(icon.encode("utf-8")) > 8192
    assert any("bytes" in error for error in svg_subset_errors(icon))


@pytest.mark.parametrize(
    ("name", "icon", "needle"),
    [
        ("script", _svg("<script>alert(1)</script>"), "script"),
        ("nested-script", _svg("<g><script>alert(1)</script></g>"), "script"),
        ("style", _svg("<style>svg{fill:red}</style>"), "style"),
        ("foreignObject", _svg("<foreignObject width='1' height='1'/>"), "foreignObject"),
        ("image", _svg("<image href='https://example.com/a.png'/>"), "image"),
        ("use", _svg("<use href='#mark'/>"), "use"),
        ("text", _svg("<text>hi</text>"), "element 'text'"),
        ("onload", _svg("<rect ONLOAD='alert(1)' width='1' height='1' fill='none'/>"), "ONLOAD"),
        ("onclick", _svg("<rect onclick='alert(1)' width='1' height='1' fill='none'/>"), "event attribute"),
        (
            "href",
            _svg("<rect href='https://example.com/x' width='1' height='1' fill='none'/>"),
            "href",
        ),
        (
            "xlink-href",
            (
                "<svg xmlns:xlink='http://www.w3.org/1999/xlink' viewBox='0 0 24 24'>"
                "<rect width='1' height='1' fill='none' xlink:href='#mark'/>"
                "</svg>"
            ),
            "href",
        ),
        ("entity", _svg("<rect width='1' height='&amp;' fill='none'/>"), "entity"),
        ("numeric-entity", _svg("<rect width='1' height='&#60;' fill='none'/>"), "entity"),
        ("oversize", "<svg viewBox='0 0 24 24'>" + (" " * 8200) + "</svg>", "bytes"),
        ("missing-viewBox", _svg("<rect width='1' height='1' fill='none'/>", view_box=False), "viewBox"),
        ("comment", _svg("<!-- x --><rect width='1' height='1' fill='none'/>"), "comment"),
        ("doctype", "<!DOCTYPE svg><svg viewBox='0 0 24 24'></svg>", "declaration"),
        ("not-svg", "<rect viewBox='0 0 24 24' width='1' height='1' fill='none'/>", "root"),
        ("black-fill", _svg("<rect width='1' height='1' fill='black'/>"), "black"),
        ("style-attribute", _svg("<rect style='fill:red' width='1' height='1' fill='none'/>"), "style attribute"),
    ],
)
def test_svg_subset_rejects(name, icon, needle):
    del name
    errors = svg_subset_errors(icon)
    assert errors
    assert any(needle in error for error in errors)
    assert acceptable_icon(icon) is None
