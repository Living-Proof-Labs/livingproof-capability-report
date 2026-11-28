# SPDX-License-Identifier: Apache-2.0
"""Guards on this-repository run links that mutation left unpinned (follow-up to #79 and #84).

Each test here fails when the guard it names is removed, and the suite was green without it.

Ported from verification-reports-action tests/test_run_link_guard_gaps.py (va PR 84, a27a1a0); its
gate tests stay in the action.
"""

import json
from pathlib import Path

import pytest

from livingproof_capability_report.site import assemble as site


OWNER_REPO = "Living-Proof-Labs/verification-reports-action"
OTHER_REPO = "Other-Org/other-repo"
RUN = f"https://github.com/{OWNER_REPO}/actions/runs/46115314157"
OTHER_RUN = f"https://github.com/{OTHER_REPO}/actions/runs/7"


def _run(reports: Path, name: str, repo: str, run_id: str, page: str) -> Path:
    folder = reports / name / "runs" / run_id
    folder.mkdir(parents=True)
    record = {
        "run": {
            "id": run_id,
            "url": f"https://github.com/{repo}/actions/runs/{run_id}",
            "created": "2026-11-28T05:19:19Z",
        }
    }
    (folder / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (folder / "index.html").write_text(page, encoding="utf-8")
    return folder


def test_a_url_in_evidence_links_to_another_repository_is_dropped():
    report = {
        "evidence_links": {
            "run": RUN,
            "links": [
                {"label": "mine", "kind": "note", "url": RUN},
                {"label": "theirs", "kind": "note", "url": OTHER_RUN},
            ],
        }
    }
    assert site.strip_actions_links(report, repository=OWNER_REPO)
    links = report["evidence_links"]["links"]
    assert links[0]["url"] == RUN
    assert "url" not in links[1]
    assert report["evidence_links"]["run"] == RUN


def test_a_run_page_may_not_link_another_repository_that_is_elsewhere_on_the_site(
    tmp_path: Path,
):
    # Two repositories publish to one site. A run page is held to its own repository,
    # not to every repository on the site.
    reports = tmp_path / "reports"
    _run(reports, "a", OWNER_REPO, "1", f"<a href='{RUN}'>CI run</a>")
    _run(
        reports,
        "b",
        OTHER_REPO,
        "7",
        f"<a href='https://github.com/{OTHER_REPO}/actions/runs/7'>x</a>",
    )
    # A site is bound to the caller, not to whatever run.url says. The other
    # repository's run.json and its own run link are refused.
    problems = site.public_page_problems(reports, repository=OWNER_REPO)
    assert any("b/runs/7/run.json run.url" in item for item in problems)
    page = reports / "a/runs/1/index.html"
    page.write_text(f"<a href='{OTHER_RUN}'>other</a>", encoding="utf-8")
    problems = site.public_page_problems(reports, repository=OWNER_REPO)
    assert "a/runs/1/index.html links to /actions/" in problems


@pytest.mark.parametrize(
    "href",
    [
        f"https://github.com/{OWNER_REPO.lower()}/actions/runs/46115314157",
        f"https://github.com/{OWNER_REPO.upper()}/actions/runs/46115314157",
        "https://github.com/Living-Proof-Labs/Verification-Reports-Action/actions/runs/1",
    ],
)
def test_the_owner_and_repository_are_matched_exactly_not_by_case(href: str):
    # Fails closed: a different spelling of this repository is not kept as a link.
    cleaned = site.strip_actions_text(f"<a href='{href}'>run</a>", repository=OWNER_REPO)
    assert cleaned == "run"
