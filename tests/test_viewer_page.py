"""Exact native panel composition and read-only restore admission."""

import pytest

from livingproof_capability_report import render
from livingproof_capability_report.viewer_page import compose_viewer_page, validate_viewer_page
from test_trusted_viewer import case  # noqa: F401


def test_preserves_existing_shell_and_read_only_restore(case):  # noqa: F811
    root, report, pin = case
    page = render(report, "html")
    page = page.replace(
        "</body>",
        '<nav id="existing-nav">History</nav><p id="pins">Pinned inputs</p><p id="provenance">Source</p></body>',
    )

    def shell(value):
        if value != page:
            raise ValueError("shell changed")
        return value

    output = compose_viewer_page(
        page, report, trusted_viewers=[pin], asset_root=root, validate_shell=shell
    )
    assert output.count("<iframe ") == 1
    assert 'id="existing-nav"' in output and 'id="pins"' in output and 'id="provenance"' in output
    assert (
        validate_viewer_page(
            output, report, trusted_viewers=[pin], asset_root=root, validate_shell=shell
        )
        is None
    )
    assert (
        validate_viewer_page(
            output, report, trusted_viewers=[pin], asset_root=root, validate_shell=shell
        )
        is None
    )
    assert (
        compose_viewer_page(page, report, trusted_viewers=[], asset_root=root, validate_shell=shell)
        == page
    )


@pytest.mark.parametrize(
    "fault", ["extra-frame", "changed-frame", "changed-shell", "duplicate-panel", "tamper-data"]
)
def test_restored_alterations_refused(case, fault):  # noqa: F811
    root, report, pin = case
    page = render(report, "html")

    def shell(value):
        if value != page:
            raise ValueError("shell changed")
        return value

    output = compose_viewer_page(
        page, report, trusted_viewers=[pin], asset_root=root, validate_shell=shell
    )
    if fault == "extra-frame":
        output += '<iframe src="evil"></iframe>'
    if fault == "changed-frame":
        output = output.replace('loading="lazy"', 'loading="eager"')
    if fault == "changed-shell":
        output += "<p>changed</p>"
    if fault == "duplicate-panel":
        output += output
    if fault == "tamper-data":
        (root / "recording.json").write_bytes(b"changed")
    with pytest.raises(ValueError):
        validate_viewer_page(
            output, report, trusted_viewers=[pin], asset_root=root, validate_shell=shell
        )


def test_missing_or_edited_native_panel_is_not_a_slot(case):  # noqa: F811
    root, report, pin = case
    page = render(report, "html").replace("Recorded data</a>", "Changed link</a>")
    with pytest.raises(ValueError, match="native evaluator panel"):
        compose_viewer_page(
            page, report, trusted_viewers=[pin], asset_root=root, validate_shell=lambda p: p
        )
