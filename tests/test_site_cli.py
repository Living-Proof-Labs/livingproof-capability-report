# SPDX-License-Identifier: Apache-2.0
"""The `site` command: the reports section verification-reports-action now calls (va#75)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest
import site_fixture
from click.testing import CliRunner

from livingproof_capability_report.cli import report

ROOT = Path(__file__).resolve().parents[1]


CALLER = "Living-Proof-Labs/livingproof-unitree-g1"


def _site(*args: str, env: dict | None = None):
    return CliRunner().invoke(report, ["site", *args], env=env, catch_exceptions=False)


def test_the_site_command_writes_the_golden_site_byte_for_byte(tmp_path: Path):
    reports = tmp_path / "reports"
    site_fixture.write(tmp_path / "in1", run_id="100", created="2026-11-20T06:00:00Z")
    site_fixture.write(
        tmp_path / "in2",
        run_id="200",
        created="2026-11-29T06:00:00Z",
        commit="b" * 40,
        tag="v2.3.33",
    )
    first = _site(str(reports), "--runs", str(tmp_path / "in1"), "--repository", CALLER)
    assert first.exit_code == 0, first.output
    second = _site(
        str(reports),
        "--runs",
        str(tmp_path / "in2"),
        "--evidence-retention-days",
        "7",
        "--repository",
        CALLER,
    )
    assert second.exit_code == 0, second.output
    assert "Added unitree-g1/stock-mujoco-hallway/runs/200" in second.output
    assert second.output.rstrip().endswith("(3 scenarios, 6 runs).")
    expected = (ROOT / "tests/fixtures/site-golden/SHA256SUMS").read_text(encoding="utf-8")
    assert site_fixture.digests(reports) == expected


def test_the_site_command_refuses_a_tampered_run_and_says_why(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    report_json = next((tmp_path / "in").glob("*/report.json"))
    report_json.write_text(report_json.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = _site(
        str(tmp_path / "reports"), "--runs", str(tmp_path / "in"), "--repository", CALLER
    )
    assert result.exit_code == 1
    assert "does not match SHA256SUMS" in result.output
    assert not (tmp_path / "reports/index.html").exists()


def test_the_site_command_fails_when_the_built_tree_has_a_broken_link(tmp_path: Path, monkeypatch):
    from livingproof_capability_report import site

    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    monkeypatch.setattr(
        site, "check_reports_tree", lambda reports, repository=None: ["index.html: broken link x/"]
    )
    result = _site(
        str(tmp_path / "reports"), "--runs", str(tmp_path / "in"), "--repository", CALLER
    )
    assert result.exit_code == 1
    assert "Generated reports/ check failed: index.html: broken link x/" in result.output


def test_the_site_command_drops_an_excluded_restored_run(tmp_path: Path):
    reports = tmp_path / "reports"
    site_fixture.write(tmp_path / "in1", run_id="100", created="2026-11-20T06:00:00Z")
    site_fixture.write(tmp_path / "in2", run_id="200", created="2026-11-21T06:00:00Z")
    assert (
        _site(str(reports), "--runs", str(tmp_path / "in1"), "--repository", CALLER).exit_code == 0
    )
    result = _site(
        str(reports),
        "--runs",
        str(tmp_path / "in2"),
        "--exclude-run",
        "100",
        "--repository",
        CALLER,
    )
    assert result.exit_code == 0, result.output
    assert not list(reports.glob("*/*/runs/100"))
    assert json.loads((reports / "site.json").read_text(encoding="utf-8"))["runs"] == 3


def test_the_site_command_refuses_an_unsafe_exclude_entry(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    result = _site(
        str(tmp_path / "reports"),
        "--runs",
        str(tmp_path / "in"),
        "--exclude-run",
        "../1",
        "--repository",
        CALLER,
    )
    assert result.exit_code == 1
    assert not (tmp_path / "reports").exists()


def test_the_site_command_is_listed_in_the_reporter_help():
    result = CliRunner().invoke(report, ["--help"])
    assert result.exit_code == 0
    assert "site" in result.output.split("Commands:")[1]


def test_the_site_styles_and_script_ship_inside_the_package():
    assets = resources.files("livingproof_capability_report.site") / "assets"
    assert (assets / "styles.css").read_text(encoding="utf-8").startswith("/* SPDX")
    assert (assets / "open.js").read_text(encoding="utf-8").startswith("// SPDX")


def test_the_site_command_defaults_the_caller_to_github_repository(tmp_path: Path):
    # The caller repository decides which CI run pages a published page may link, so the
    # command refuses to build without one and never infers it from a run.json.
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    runs = ("--runs", str(tmp_path / "in"))
    missing = _site(str(tmp_path / "none"), *runs, env={"GITHUB_REPOSITORY": ""})
    assert missing.exit_code == 2
    assert "--repository" in missing.output and "GITHUB_REPOSITORY" in missing.output
    assert not (tmp_path / "none").exists()
    foreign = _site(str(tmp_path / "bad"), *runs, env={"GITHUB_REPOSITORY": "other-org/other-repo"})
    assert foreign.exit_code == 1
    assert "run.url is not this repository's run" in foreign.output
    good = _site(str(tmp_path / "good"), *runs, env={"GITHUB_REPOSITORY": CALLER})
    assert good.exit_code == 0, good.output


def test_the_site_command_names_the_run_json_whose_run_url_is_wrong(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    result = _site(
        str(tmp_path / "reports"),
        "--runs",
        str(tmp_path / "in"),
        "--repository",
        "other-org/other-repo",
    )
    assert result.exit_code == 1
    assert "run.json run.url is not this repository's run" in result.output
    assert "Actions links or artifact wording" not in result.output


@pytest.mark.parametrize(
    "repository",
    [
        "Living-Proof-Labs",
        "Living-Proof-Labs/",
        "/verification-reports-action",
        "Living-Proof-Labs/verification-reports-action/extra",
        "Living-Proof-Labs/verification reports",
        "Living-Proof-Labs/verification-reports-action\n",
        "Living_Proof_Labs/verification-reports-action",
        "-Living-Proof-Labs/verification-reports-action",
        "Living-Proof-Labs/..",
        "Living-Proof-Labs/.",
        "Living-Proof-Labs/repo+x",
        "Living-Proof-Labs/(repo)",
        "https://github.com/Living-Proof-Labs/verification-reports-action",
        "Living-Proof-Labs/verification-reports-action/actions",
    ],
)
def test_the_site_command_refuses_a_repository_that_is_not_owner_slash_name(
    tmp_path: Path, repository: str
):
    # Vera's I2 on 143: an owner-only value would accept https://github.com/OWNER/actions/runs/N.
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    flag = _site(str(reports), "--runs", str(tmp_path / "in"), "--repository", repository)
    assert flag.exit_code == 2, flag.output
    assert "OWNER/NAME" in flag.output
    env = _site(str(reports), "--runs", str(tmp_path / "in"), env={"GITHUB_REPOSITORY": repository})
    assert env.exit_code == 2, env.output
    assert not reports.exists()


@pytest.mark.parametrize(
    "repository",
    ["Living-Proof-Labs/verification-reports-action", "a/b", "o1/repo.name_x-y", "O/.github"],
)
def test_the_site_command_accepts_an_owner_slash_name_repository(tmp_path: Path, repository: str):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    result = _site(
        str(tmp_path / "reports"), "--runs", str(tmp_path / "in"), "--repository", repository
    )
    # The shape is accepted; the fixture's run.url names CALLER, so only CALLER builds.
    assert "OWNER/NAME shape" not in result.output
