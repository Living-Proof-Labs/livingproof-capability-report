# SPDX-License-Identifier: Apache-2.0
"""Guards on the #84 run.url, encoded-actions and video-player logic that mutation left unpinned.

Ported from Vera's patch 0004 (tests/test_pr84_guard_gaps_round2.py, va PR 84, a27a1a0); its
gate, player and video-cell tests and the site_fixture CLI test stay in the action.
"""

import json
from pathlib import Path

import pytest

from livingproof_capability_report.site import assemble as site

OWNER = "Living-Proof-Labs/verification-reports-action"
RUN_ID = "46115314157"
RUN = f"https://github.com/{OWNER}/actions/runs/{RUN_ID}"
VIDEO = "evidence/video/trial-01-fail.mp4"
MCAP = "evidence/mcap/mcap/trial-01.mcap"


def _run_folder(reports: Path, run_id: str, url, created: str = "2026-11-28T05:19:19Z") -> Path:
    folder = reports / f"g1/unitree-g1/stock-mujoco-hallway/runs/{run_id}"
    folder.mkdir(parents=True)
    run = {"id": run_id, "created": created}
    if url is not None:
        run["url"] = url
    (folder / "run.json").write_text(json.dumps({"run": run}), encoding="utf-8")
    return folder


# --- encoded /actions/ in an href: every layer is decoded ---------------------------

ENCODED = [
    "https://github.com/evil/repo/%2561ctions/runs/1",
    "https://github.com/evil/repo/&amp;#97;ctions/runs/1",
    "https://github.com/evil/repo/&amp;#x61;ctions/runs/1",
    "https://github.com/evil/repo/%26%2397;ctions/runs/1",
    "https://github.com/evil/repo/%2526%252397;ctions/runs/1",
    "https://github.com/evil/repo%2Factions%2Fruns%2F1",
    "https://github.com/evil/repo%252Factions%252Fruns%252F1",
    "https://github.com/evil/repo/%41CTIONS/runs/1",
]


@pytest.mark.parametrize("href", ENCODED)
def test_a_multiply_encoded_actions_href_is_unwrapped_and_flagged(href: str):
    raw = f"<a href='{href}'>run</a>"
    assert site.mentions_actions(raw, repository=OWNER)
    assert site.strip_actions_text(raw, repository=OWNER) == "run"


@pytest.mark.parametrize("href", ENCODED)
def test_the_reporter_page_scrub_unwraps_an_encoded_actions_href(href: str):
    raw = f"<p><a href='{href}'>run</a></p>"
    cleaned = site.scrub_reporter_html(
        raw, {"evidence": []}, trial=False, expired=False, days=90, repository=OWNER
    )
    assert "<a " not in cleaned
    assert "evil/repo" not in cleaned
    assert not site.mentions_actions(cleaned, repository=OWNER)


@pytest.mark.parametrize(
    "href",
    [
        "https://github.com/evil/repo/ACTIONS/runs/1",
        "https://github.com/evil/repo/Actions/runs/1/job/2",
    ],
)
def test_an_upper_case_actions_href_is_not_a_kept_link(href: str):
    raw = f"<a href='{href}'>run</a>"
    assert site.mentions_actions(raw, repository=OWNER)
    assert site.strip_actions_text(raw, repository=OWNER) == "run"


def test_an_upper_case_anchor_tag_with_an_encoded_actions_href_is_unwrapped():
    raw = "<A HREF='https://github.com/evil/repo/%61ctions/runs/1'>run</A>"
    assert site.mentions_actions(raw, repository=OWNER)
    assert site.strip_actions_text(raw, repository=OWNER) == "run"


@pytest.mark.parametrize(
    "text",
    [
        "HTTPS://GITHUB.COM/evil/repo/actions/runs/1",
        "https://GitHub.com/evil/repo/actions/runs/1",
        "https://github.com/evil/repo/ACTIONS/runs/1",
    ],
)
def test_a_case_variant_of_the_host_scheme_or_actions_in_plain_text_is_stripped(text: str):
    cleaned = site.strip_actions_text(f"<p>see {text} now</p>", repository=OWNER)
    assert cleaned == "<p>see  now</p>"


# --- run.json: older runs and traversal order ----------------------------------------


def test_an_unreadable_run_json_does_not_hide_a_later_run_json_without_a_run_url(
    tmp_path: Path,
):
    reports = tmp_path / "reports"
    first = _run_folder(reports, "1", RUN)
    (first / "run.json").write_text("{not json", encoding="utf-8")
    _run_folder(reports, "2", None)
    problems = site.public_page_problems(reports, repository=OWNER)
    assert any("runs/2/run.json run.url is missing" in item for item in problems), problems
