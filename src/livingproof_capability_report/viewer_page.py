"""Compose exact Reporter panel fragments without taking ownership of a site's shell."""

from .core import render
from .evaluators import _panel, advisory_views
from .trusted_viewer import viewer_panels


def _fragments(report, trusted_viewers, asset_root):
    # Keep the ordinary report integrity/grade validation, including bundle digest.
    render(report, "json")
    panels = viewer_panels(trusted_viewers, report, asset_root)
    result = []
    for view in advisory_views(report):
        if view["identity"] in panels:
            original = _panel(view, show_time=False)
            decorated = _panel(
                dict(view, trusted_viewer_html=panels[view["identity"]]), show_time=False
            )
            result.append((original, decorated))
    return result


def _checked_shell(page, validate_shell):
    if not isinstance(page, str) or not callable(validate_shell):
        raise ValueError("A page and the caller's existing shell validator are required")
    # Validators may sanitize other inputs; here any change is a refusal. The
    # caller must use its trusted publication policy, never an evaluator callback.
    if validate_shell(page) != page:
        raise ValueError("Page differs from the validated shell")


def compose_viewer_page(page, report, *, trusted_viewers, asset_root, validate_shell):
    """Fill exact native advisory panels in a caller-validated existing page.

    No shell parsing, new navigation, file writes or execution. The caller supplies
    its existing trusted shell validator. Every byte outside the exact Reporter
    panel fragments is preserved. This is not an arbitrary-HTML sanitizer.
    """
    _checked_shell(page, validate_shell)
    fragments = _fragments(report, trusted_viewers, asset_root)
    for original, decorated in fragments:
        if page.count(original) != 1 or decorated in page:
            raise ValueError("Expected one unchanged native evaluator panel")
        before, _, after = page.partition(original)
        page = before + decorated + after
    return page


def validate_viewer_page(page, report, *, trusted_viewers, asset_root, validate_shell):
    """Read-only restore check; returns None and never rewrites published bytes.

    Revalidate current caller pins, raw data and trial binding, then check the
    exact native generated panels. Validate the remaining shell under the caller's
    unchanged publication policy. An extra/altered iframe is never exempted.
    The caller must first verify the complete incoming file manifest, and pin the
    compatible Reporter release used for these immutable page fragments.
    """
    fragments = _fragments(report, trusted_viewers, asset_root)
    for original, decorated in fragments:
        if page.count(decorated) != 1:
            raise ValueError("Published viewer differs from the native bound panel")
        before, _, after = page.partition(decorated)
        page = before + original + after
    _checked_shell(page, validate_shell)


def shell_after_removing_viewer(page, report, frame):
    """Return the page with the composed viewer panel replaced by the original panel.

    The frame has to be a whole element in the exact place `compose_viewer_page` puts it
    (inside the native advisory panel). The same bytes inside a start tag, an attribute
    value or a script do not form that panel and are refused. This does not read
    `trusted-viewer/`; the caller supplies the frame it already matched.
    """
    if not isinstance(page, str) or not isinstance(frame, str) or not frame:
        raise ValueError("A page and the composed viewer frame are required")
    found = None
    for view in advisory_views(report):
        original = _panel(view, show_time=False)
        decorated = _panel(dict(view, trusted_viewer_html=frame), show_time=False)
        count = page.count(decorated)
        if count == 0:
            continue
        if count != 1 or found is not None:
            raise ValueError("Expected one unchanged native evaluator panel")
        found = (original, decorated)
    if found is None:
        raise ValueError("Published viewer differs from the native bound panel")
    original, decorated = found
    before, _, after = page.partition(decorated)
    return before + original + after
