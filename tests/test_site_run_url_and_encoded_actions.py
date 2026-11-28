# SPDX-License-Identifier: Apache-2.0
"""L1-L4 follow-ups on #84: fail closed on run.url, case variants, encoded actions, video player.

Ported from verification-reports-action tests/test_pr84_lows.py (va PR 84, a27a1a0); its gate tests
stay in the action.
"""

import json
from pathlib import Path

import pytest

from livingproof_capability_report.site import assemble as site

OWNER = "Living-Proof-Labs/verification-reports-action"
OTHER = "other-org/other-repo"
RUN = f"https://github.com/{OWNER}/actions/runs/46115314157"
OTHER_RUN = f"https://github.com/{OTHER}/actions/runs/7"


def _record(url) -> dict:
    run = {"id": "46115314157", "created": "2026-11-28T05:19:19Z"}
    if url is not None:
        run["url"] = url
    return {"run": run}


def test_a_foreign_run_url_does_not_rebind_this_repository(tmp_path: Path):
    # The caller is this repository. A run.json that names another repository must
    # not become the allowed repo (its link is not kept; this run's link is not dropped).
    folder = tmp_path / "reports/g1/unitree-g1/stock/runs/1"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps(_record(OTHER_RUN)), encoding="utf-8")
    page = f"<a href='{RUN}'>CI run</a> <a href='{OTHER_RUN}'>other</a>"
    (folder / "index.html").write_text(page, encoding="utf-8")
    problems = site.public_page_problems(tmp_path / "reports", repository=OWNER)
    assert any("run.url" in item for item in problems)
    cleaned = site.strip_actions_text(page, repository=OWNER)
    assert f"<a href='{RUN}'>" in cleaned
    assert f"<a href='{OTHER_RUN}'>" not in cleaned


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/living-proof-labs/verification-reports-action/actions/runs/46115314157",
        "https://github.com/Living-Proof-Labs/VERIFICATION-REPORTS-ACTION/actions/runs/46115314157",
        "https://github.com/LIVING-PROOF-LABS/verification-reports-action/actions/runs/46115314157",
    ],
)
def test_a_case_variant_of_this_repository_in_plain_text_is_stripped_not_a_build_error(
    tmp_path: Path, url: str
):
    text = f"<p>See {url}.</p>"
    cleaned = site.strip_actions_text(text, repository=OWNER)
    assert url not in cleaned
    assert not site.mentions_actions(cleaned, repository=OWNER)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "index.html").write_text(cleaned, encoding="utf-8")
    assert site.public_page_problems(reports, repository=OWNER) == []


@pytest.mark.parametrize(
    "href",
    [
        "https://github.com/evil/repo/&#97;ctions/runs/1/job/2",
        "https://github.com/evil/repo/%61ctions/runs/1",
        "https://github.com/evil/repo/&#x61;ctions/runs/1",
        "https://github.com/evil/repo/act%69ons/runs/1",
    ],
)
def test_an_encoded_actions_href_is_not_kept_as_a_link(href: str):
    cleaned = site.strip_actions_text(f"<a href='{href}'>run</a>", repository=OWNER)
    assert cleaned == "run"
    assert "<a " not in cleaned
    raw = f"<a href='{href}'>run</a>"
    assert site.mentions_actions(raw, repository=OWNER)
