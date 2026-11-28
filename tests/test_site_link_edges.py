# SPDX-License-Identifier: Apache-2.0
"""Edge cases for the CI run, video and recording links on published run pages (va#55 b).

Ported from verification-reports-action tests/test_run_page_link_edges.py (va PR 84) for
the moved renderer (va#75). The published-links check (require_reports) and the collect
job's link resolution (evaluators_run) stay in the action with their tests.

These pin guards that the main tests leave unpinned: each one was found by mutation, a change
that removes the guard and leaves the suite green.
"""

import json
import os
from pathlib import Path

import pytest

from livingproof_capability_report.site import assemble as site

REPO = "https://github.com/Living-Proof-Labs/verification-reports-action"
RUN = f"{REPO}/actions/runs/46115314157"


# --------------------------------------------------------------- the URL filter, in anchors


@pytest.mark.parametrize(
    "suffix",
    [
        "/",
        "/job/7",
        "/attempts/2",
        "/artifacts/9",
        "?pr=1",
        "#summary",
        "x",
        ".zip",
        ";a=1",
        ":80",
        "&amp;x=1",
        "%2Fattempts%2F2",
        "%2fartifacts%2f2",
    ],
)
def test_an_anchor_that_is_more_than_the_run_address_is_unwrapped(suffix: str):
    kept = f"<a href='{RUN}'>CI run</a>"
    assert site.strip_actions_text(kept) == kept
    cleaned = site.strip_actions_text(f"<a href='{RUN}{suffix}'>CI run</a>")
    assert cleaned == "CI run"
    assert not site.html_is_dirty(cleaned)


@pytest.mark.parametrize("suffix", ["/job/7", "/attempts/2", "/artifacts/9", "?pr=1", "#summary"])
def test_a_run_address_with_a_suffix_is_not_a_public_evidence_url(suffix: str):
    assert not site._is_actions_url(RUN)
    assert site._is_actions_url(RUN + suffix)


def test_a_fragment_on_the_run_address_is_refused_on_a_public_page(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    page = reports / "index.html"
    page.write_text(f"<a href='{RUN}'>CI run</a>", encoding="utf-8")
    assert site.public_page_problems(reports) == []
    page.write_text(f"<a href='{RUN}#summary'>CI run</a>", encoding="utf-8")
    assert site.public_page_problems(reports) == ["index.html links to /actions/"]


# ------------------------------------------------ evidence the site did not publish: text


@pytest.fixture
def published(tmp_path: Path) -> Path:
    folder = tmp_path / "run"
    (folder / "evidence/video").mkdir(parents=True)
    (folder / "evidence/video/kept.mp4").write_bytes(b"mp4")
    (folder / "report.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"secret")
    try:
        os.symlink(outside, folder / "evidence/video/linked.mp4")
    except OSError:  # pragma: no cover - platforms without symlinks
        pytest.skip("symlinks are not available")
    return folder


def _anchor(target: str) -> str:
    return f"<a href='{target}'>label</a>"


def test_a_published_file_keeps_its_link_and_player(published: Path):
    # A percent-encoded name is the file the browser asks for, so it is still a published file.
    for name in ("kept.mp4", "ke%70t.mp4"):
        page = _anchor(f"evidence/video/{name}")
        page += f"<video controls src='evidence/video/{name}'></video>"
        assert site.unlink_unpublished_evidence(page, published) == page


@pytest.mark.parametrize(
    "target",
    [
        "evidence/video/missing.mp4",
        "evidence/video/linked.mp4",
        "evidence/../report.json",
        "evidence/video/../../report.json",
        "evidence/video/%2e%2e/%2e%2e/report.json",
        "evidence/video/%2E%2E/%2E%2E/report.json",
        "evidence/video/./kept.mp4",
        "evidence/video\\kept.mp4",
        "evidence/video/ke%70t.mp4%00",
    ],
)
def test_evidence_that_is_not_a_file_in_the_run_folder_is_plain_text(published: Path, target: str):
    anchor = site.unlink_unpublished_evidence(_anchor(target), published)
    assert anchor == "label", target
    video = site.unlink_unpublished_evidence(f"<video controls src='{target}'></video>", published)
    assert target not in video, target
    assert "<video" not in video, target


# ------------------------------------------------ L2: only this repository's run URLs


OTHER = "https://github.com/other-org/other-repo/actions/runs/46115314157"
THIS_REPO = "Living-Proof-Labs/verification-reports-action"


def test_a_run_url_from_another_repository_is_not_kept_as_a_link():
    kept = f"<a href='{RUN}'>CI run</a>"
    assert site.strip_actions_text(kept, repository=THIS_REPO) == kept
    cleaned = site.strip_actions_text(f"<a href='{OTHER}'>CI run</a>", repository=THIS_REPO)
    assert cleaned == "CI run"
    assert OTHER not in cleaned
    assert not site.html_is_dirty(cleaned, repository=THIS_REPO)


def test_a_run_url_from_another_repository_is_flagged_on_a_public_page(tmp_path: Path):
    reports = tmp_path / "reports"
    folder = reports / "unitree-g1/stock-mujoco-hallway/runs/1"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps({"run": {"id": "1", "url": RUN, "created": "2026-11-28T05:19:19Z"}}),
        encoding="utf-8",
    )
    page = reports / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"<a href='{RUN}'>CI run</a>", encoding="utf-8")
    assert site.public_page_problems(reports) == []
    page.write_text(f"<a href='{OTHER}'>CI run</a>", encoding="utf-8")
    assert site.public_page_problems(reports) == ["index.html links to /actions/"]


def test_a_dotdot_or_encoded_slash_owner_is_not_a_run_address():
    for host_path in ("../other/actions/runs/1", "o%2Fx/repo/actions/runs/1"):
        url = f"https://github.com/{host_path}"
        assert not site.RUN_ADDRESS.fullmatch(url)
        assert site._is_actions_url(url)


def test_another_repository_run_url_is_dropped_from_evidence_links():
    report = {"evidence_links": {"run": OTHER, "links": []}}
    assert site.strip_actions_links(report, repository=THIS_REPO) is True
    assert "run" not in report["evidence_links"]
    report = {"evidence_links": {"run": RUN, "links": []}}
    assert site.strip_actions_links(report, repository=THIS_REPO) is False
    assert report["evidence_links"]["run"] == RUN


# -------------------------------- L3: near-miss addresses are end-of-address misses


L3_SUFFIXES = (".zip", ";a=1", ":80", "&x=1", "%2Fattempts%2F2")


@pytest.mark.parametrize("suffix", L3_SUFFIXES)
def test_a_near_miss_run_address_in_plain_text_is_flagged(tmp_path: Path, suffix: str):
    reports = tmp_path / "reports"
    reports.mkdir()
    page = reports / "index.html"
    page.write_text(f"See {RUN} for the log.", encoding="utf-8")
    assert site.public_page_problems(reports) == []
    page.write_text(f"See {RUN}{suffix} for the log.", encoding="utf-8")
    assert site.public_page_problems(reports) == ["index.html links to /actions/"]
    assert site.html_is_dirty(f"See {RUN}{suffix}.")
    assert not site.html_is_dirty(f"See {RUN}.")


@pytest.mark.parametrize("suffix", L3_SUFFIXES)
def test_a_near_miss_run_address_is_removed_from_evidence_links(suffix: str):
    report = {
        "evidence_links": {
            "run": RUN + suffix,
            "links": [{"label": "note", "url": RUN + suffix, "kind": "note"}],
        }
    }
    assert site._is_actions_url(RUN + suffix)
    assert site.strip_actions_links(report) is True
    assert "run" not in report["evidence_links"]
    assert "url" not in report["evidence_links"]["links"][0]
