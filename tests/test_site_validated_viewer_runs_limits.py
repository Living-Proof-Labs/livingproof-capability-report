"""Rivet's decisions on #145 (comment 7238913493): tighter src, checksums, untouched assets.

The flag already leaves only one composed frame out of the restored-page check. These tests
pin the rest of that call: the frame `src` is exactly the path and query
`compose_viewer_page` writes (one filename, no extra keys), `write_published_checksums`
refuses a symlinked SHA256SUMS and does not leave a temporary file behind, and `site` does
not change, add or delete anything under a listed run's `trusted-viewer/` folder.
"""

from __future__ import annotations

import hashlib

import pytest

from test_site_validated_viewer_runs import RUN, _history, _next, _site
from test_site_validated_viewer_runs_gaps import _rewrite, _swap


# --- src is the exact path and query compose_viewer_page writes ----------------------------

SRC_FAULTS = {
    "other filename": _swap("trusted-viewer/viewer.html#", "trusted-viewer/other.html#"),
    "nested filename": _swap("trusted-viewer/viewer.html#", "trusted-viewer/data/recording.html#"),
    "extra key": _swap("&amp;trial=1", "&amp;trial=1&amp;x=1"),
    "extra key first": _swap("viewer.html#file=", "viewer.html#x=1&amp;file="),
    "missing trial": _swap("&amp;trial=1", ""),
    "missing file": _swap("file=data%2Frecording.json&amp;", ""),
    "reordered keys": _swap(
        "file=data%2Frecording.json&amp;sha256=",
        "sha256=ca2509979d7f2ddd851b4f3a32bc6f12fb151c95a2144064b4eeaa3d2ae9bed3&amp;file=data%2Frecording.json&amp;sha256=",
    ),
    "raw file path": _swap("file=data%2Frecording.json", "file=data/recording.json"),
    "uppercase sha256": _swap("sha256=ca250997", "sha256=CA250997"),
}


@pytest.mark.parametrize("fault", sorted(SRC_FAULTS))
def test_the_frame_src_must_be_the_exact_composed_path_and_query(tmp_path, fault):
    reports = _history(tmp_path)
    _rewrite(reports, SRC_FAULTS[fault])
    with pytest.raises(_site().SiteError):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])


# --- write_published_checksums: no write through a symlink, no leftover temp ---------------


def test_write_published_checksums_refuses_a_symlinked_SHA256SUMS_and_leaves_the_target(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "a.txt").write_text("a", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.write_text("keep me", encoding="utf-8")
    (folder / "SHA256SUMS").symlink_to(outside)
    with pytest.raises(_site().SiteError, match="symlink"):
        _site().write_published_checksums(folder)
    assert outside.read_text(encoding="utf-8") == "keep me"
    assert (folder / "SHA256SUMS").is_symlink()
    assert (folder / "SHA256SUMS").read_text(encoding="utf-8") == "keep me"


def test_write_published_checksums_replaces_the_file_and_leaves_no_temporary(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "SHA256SUMS").write_text("stale\n", encoding="utf-8")
    _site().write_published_checksums(folder)
    expected = f"{hashlib.sha256(b'a').hexdigest()}  a.txt\n"
    assert (folder / "SHA256SUMS").read_text(encoding="utf-8") == expected
    assert (folder / "SHA256SUMS").is_file() and not (folder / "SHA256SUMS").is_symlink()
    leftovers = [p.name for p in folder.iterdir() if p.name != "a.txt" and p.name != "SHA256SUMS"]
    assert leftovers == []


# --- site does not change, add or delete anything under trusted-viewer/ --------------------


def _viewer_state(reports):
    root = reports / RUN / "trusted-viewer"
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_site_does_not_change_add_or_delete_files_under_trusted_viewer(tmp_path):
    reports = _history(tmp_path)
    extra = reports / RUN / "trusted-viewer" / "extra.txt"
    extra.write_text("leave me", encoding="utf-8")
    _site().write_published_checksums(reports / RUN)
    before = _viewer_state(reports)
    assert "extra.txt" in before
    _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert _viewer_state(reports) == before
    # Evidence expiry rewrites the page; the folder is still left byte-for-byte.
    reports = _history(tmp_path / "exp")
    extra = reports / RUN / "trusted-viewer" / "extra.txt"
    extra.write_text("leave me", encoding="utf-8")
    _site().write_published_checksums(reports / RUN)
    before = _viewer_state(reports)
    _next(tmp_path / "exp", reports, validated_viewer_runs=[RUN], now="2027-01-01T00:00:00Z")
    assert _viewer_state(reports) == before
    assert extra.read_text(encoding="utf-8") == "leave me"
    # And the reports tree around it still checks out.
    assert (
        _site().check_reports_tree(
            reports, repository="Living-Proof-Labs/verification-reports-action"
        )
        == []
    )
