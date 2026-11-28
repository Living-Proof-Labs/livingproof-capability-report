# SPDX-License-Identifier: Apache-2.0
"""The `site` command: the reports section verification-reports-action now calls (va#75)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import site_fixture
from click.testing import CliRunner

from livingproof_capability_report.cli import report

ROOT = Path(__file__).resolve().parents[1]


def _site(*args: str):
    return CliRunner().invoke(report, ["site", *args], catch_exceptions=False)


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
    first = _site(str(reports), "--runs", str(tmp_path / "in1"))
    assert first.exit_code == 0, first.output
    second = _site(str(reports), "--runs", str(tmp_path / "in2"), "--evidence-retention-days", "7")
    assert second.exit_code == 0, second.output
    assert "Added unitree-g1/stock-mujoco-hallway/runs/200" in second.output
    assert second.output.rstrip().endswith("(3 scenarios, 6 runs).")
    expected = (ROOT / "tests/fixtures/site-golden/SHA256SUMS").read_text(encoding="utf-8")
    assert site_fixture.digests(reports) == expected


def test_the_site_command_refuses_a_tampered_run_and_says_why(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    report_json = next((tmp_path / "in").glob("*/report.json"))
    report_json.write_text(report_json.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = _site(str(tmp_path / "reports"), "--runs", str(tmp_path / "in"))
    assert result.exit_code == 1
    assert "does not match SHA256SUMS" in result.output
    assert not (tmp_path / "reports/index.html").exists()


def test_the_site_command_fails_when_the_built_tree_has_a_broken_link(tmp_path: Path, monkeypatch):
    from livingproof_capability_report import site

    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    monkeypatch.setattr(site, "check_reports_tree", lambda reports: ["index.html: broken link x/"])
    result = _site(str(tmp_path / "reports"), "--runs", str(tmp_path / "in"))
    assert result.exit_code == 1
    assert "Generated reports/ check failed: index.html: broken link x/" in result.output


def test_the_site_command_drops_an_excluded_restored_run(tmp_path: Path):
    reports = tmp_path / "reports"
    site_fixture.write(tmp_path / "in1", run_id="100", created="2026-11-20T06:00:00Z")
    site_fixture.write(tmp_path / "in2", run_id="200", created="2026-11-21T06:00:00Z")
    assert _site(str(reports), "--runs", str(tmp_path / "in1")).exit_code == 0
    result = _site(str(reports), "--runs", str(tmp_path / "in2"), "--exclude-run", "100")
    assert result.exit_code == 0, result.output
    assert not list(reports.glob("*/*/runs/100"))
    assert json.loads((reports / "site.json").read_text(encoding="utf-8"))["runs"] == 3


def test_the_site_command_refuses_an_unsafe_exclude_entry(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    result = _site(
        str(tmp_path / "reports"), "--runs", str(tmp_path / "in"), "--exclude-run", "../1"
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
