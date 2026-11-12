"""Sanitised inline SVG for an evaluator icon.

This mirrors the subset in livingproof-evaluator result 1.1.0
(docs/evaluator-descriptor.md on revision 60054b266f2ed6ed4473b249bb715f42e3b8262d).
The report does not import that package. An ampersand is rejected here because an
SVG entity is not in the subset. Descriptor text is a different field and may
contain an ampersand; the report escapes that text and does not run it through
this check.
"""

import re
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
CHILD_ELEMENTS = {"path", "circle", "rect", "line", "polyline", "polygon", "g"}
ALLOWED_PAINT = {"currentColor", "none", "transparent"}
ICON_MAX_BYTES = 8192
_EXTERNAL_VALUE = re.compile(r"(?i)(?:url\s*\(|javascript:|data:|https?:|file:|blob:)")


def _local(name):
    if name.startswith("{"):
        return name.split("}", 1)[1]
    return name


def _namespace(name):
    if name.startswith("{") and "}" in name:
        return name[1:].split("}", 1)[0]
    return None


def svg_subset_errors(icon):
    """Why an icon is outside the subset. An empty list means it may be inlined."""
    if not isinstance(icon, str):
        return ["must be a string"]
    size = len(icon.encode("utf-8"))
    if size > ICON_MAX_BYTES:
        return [f"is {size} UTF-8 bytes, and the cap is {ICON_MAX_BYTES}"]
    if not icon.strip():
        return ["is empty"]
    lowered = icon.lower()
    if "<?" in icon:
        return ["contains a processing instruction"]
    if "<![cdata[" in lowered:
        return ["contains CDATA"]
    if "<!--" in icon:
        return ["contains a comment"]
    if "<!" in icon:
        return ["contains a declaration"]
    if "&" in icon:
        return ["contains an entity reference"]
    try:
        root = fromstring(icon)
    except DefusedXmlException as exc:
        return [f"was rejected while parsing ({exc.__class__.__name__})"]
    except ParseError as exc:
        return [f"is not well-formed XML ({exc})"]
    errors = []
    _walk_svg(root, errors, root=True)
    return errors


def _walk_svg(element, errors, *, root):
    name = _local(element.tag)
    namespace = _namespace(element.tag)
    if namespace not in (None, SVG_NAMESPACE):
        errors.append(f"{name} is not in the SVG namespace")
    if root:
        if name != "svg":
            errors.append(f"root is {name!r}, and the root must be svg")
        if not any(_local(key) == "viewBox" for key in element.attrib):
            errors.append("is missing viewBox")
    elif name not in CHILD_ELEMENTS:
        errors.append(
            f"has an element {name!r}, and the allowed elements are "
            "path, circle, rect, line, polyline, polygon, and g"
        )
    errors.extend(_attribute_errors(name, element.attrib))
    if element.text and element.text.strip():
        errors.append(f"{name} has text content")
    if element.tail and element.tail.strip():
        errors.append(f"{name} has trailing text")
    for child in list(element):
        _walk_svg(child, errors, root=False)


def _attribute_errors(element_name, attrib):
    errors = []
    for raw_name, value in attrib.items():
        name = _local(raw_name)
        lowered = name.lower()
        if lowered == "xmlns" or raw_name.startswith("{http://www.w3.org/2000/xmlns/}"):
            continue
        if lowered.startswith("on"):
            errors.append(f"{element_name} has an event attribute {name}")
            continue
        if lowered in {"href", "src", "srcset"}:
            errors.append(f"{element_name} has an external reference {name}")
            continue
        if lowered == "style":
            errors.append(f"{element_name} has a style attribute")
            continue
        if _EXTERNAL_VALUE.search(value):
            errors.append(f"{element_name} {name} contains an external reference")
            continue
        if lowered in {"fill", "stroke"} and value not in ALLOWED_PAINT:
            errors.append(
                f"{element_name} {lowered} is {value!r}, and it must be "
                "currentColor, none, or transparent"
            )
    return errors


def acceptable_icon(icon):
    """The original SVG string when it passes the subset, otherwise None."""
    if svg_subset_errors(icon):
        return None
    return icon.strip()
