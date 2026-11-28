# SPDX-License-Identifier: Apache-2.0
"""Vera's Lows on verification-reports-action PR 84 (a27a1a0) that live in the moved renderer.

L1 an unquoted href with an encoded /actions/ survived as a link, L3 dead code, L4 a bad
run.url was reported under the Actions-links label. L2 (the player match is a substring) is in
the action's published-links gate, `tools/require_reports.py`, which stays in the action.
"""

import json
from pathlib import Path

import pytest
from test_site import _make_run_folder

from livingproof_capability_report.site import assemble as site

OWNER = "Living-Proof-Labs/verification-reports-action"
RUN = f"https://github.com/{OWNER}/actions/runs/46115314157"

UNQUOTED_ENCODED = [
    "https://github.com/evil/repo/%61ctions/runs/1",
    "https://github.com/evil/repo/&#97;ctions/runs/1",
    "https://github.com/evil/repo/&#x61;ctions/runs/1",
    "https://github.com/evil/repo/act%69ons/runs/1",
    "https://github.com/evil/repo/%2561ctions/runs/1",
    "https://github.com/evil/repo%2Factions%2Fruns%2F1",
    "https://github.com/evil/repo/%41CTIONS/runs/1",
]


@pytest.mark.parametrize("href", UNQUOTED_ENCODED)
def test_an_unquoted_href_with_an_encoded_actions_is_unwrapped(href: str):
    raw = f"<p><a href={href}>run</a></p>"
    assert site.mentions_actions(raw, repository=OWNER)
    cleaned = site.strip_actions_text(raw, repository=OWNER)
    assert cleaned == "<p>run</p>"
    assert not site.mentions_actions(cleaned, repository=OWNER)


@pytest.mark.parametrize("href", UNQUOTED_ENCODED)
def test_the_reporter_page_scrub_unwraps_an_unquoted_encoded_actions_href(href: str):
    record = {"run": {"url": RUN}, "evidence": []}
    raw = f"<p><a class=x href={href} title=t>run log</a></p>"
    cleaned = site.scrub_reporter_html(
        raw, record, trial=False, expired=False, days=7, repository=OWNER
    )
    assert "<a " not in cleaned
    assert cleaned == "<p>run log</p>"


def test_an_unquoted_href_to_this_repository_run_page_is_kept_and_other_unquoted_links_too():
    kept = f"<a href={RUN}>CI run</a> <a href=evidence/a.json>a</a> <a href=https://example.org/x>x</a>"
    assert site.strip_actions_text(kept, repository=OWNER) == kept
    assert not site.mentions_actions(kept, repository=OWNER)


def test_an_unquoted_anchor_does_not_swallow_the_next_link():
    text = (
        "<a href=https://github.com/evil/repo/%61ctions/runs/1>one</a>"
        "<a href='evidence/keep.json'>keep</a>"
    )
    assert site.strip_actions_text(text, repository=OWNER) == (
        "one<a href='evidence/keep.json'>keep</a>"
    )


def test_caller_repository_no_longer_exists():
    assert not hasattr(site, "caller_repository")


def _runs_dir(tmp_path: Path, caller: str) -> Path:
    _make_run_folder(tmp_path / "in", "hallway", run_id="100", caller=caller)
    return tmp_path / "in"


def test_a_foreign_run_url_is_reported_under_its_own_label(tmp_path: Path):
    runs = _runs_dir(tmp_path, "other-org/other-repo")
    with pytest.raises(site.SiteError) as error:
        site.build(tmp_path / "reports", runs, repository=OWNER)
    message = str(error.value)
    assert "run.url" in message and "runs/100/run.json" in message
    assert OWNER in message
    assert "--exclude-run," in message
    assert "Actions links or artifact wording" not in message


def test_a_missing_run_url_is_reported_under_the_same_label(tmp_path: Path):
    runs = _runs_dir(tmp_path, OWNER)
    run_json = next(runs.glob("*/run.json"))
    record = json.loads(run_json.read_text(encoding="utf-8"))
    del record["run"]["url"]
    run_json.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(site.SiteError) as error:
        site.build(tmp_path / "reports", runs, repository=OWNER)
    assert "run.url is missing" in str(error.value)
    assert "Actions links or artifact wording" not in str(error.value)


def test_an_actions_link_is_still_reported_as_an_actions_link(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "index.html").write_text("<p>https://github.com/o/r/actions/x</p>", encoding="utf-8")
    assert site.public_page_problems(reports, repository=OWNER) == ["index.html links to /actions/"]
    assert site.run_url_problems(reports, repository=OWNER) == []


def test_public_page_problems_still_includes_the_run_url_problems(tmp_path: Path):
    runs = _runs_dir(tmp_path, "other-org/other-repo")
    site_dir = tmp_path / "published"
    folder = site_dir / "g1/unitree-g1/stock/runs/100"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        (next(runs.glob("*/run.json"))).read_text(encoding="utf-8"), encoding="utf-8"
    )
    problems = site.public_page_problems(site_dir, repository=OWNER)
    assert problems == site.run_url_problems(site_dir, repository=OWNER)
    assert len(problems) == 1 and "run.url is not this repository's run" in problems[0]
