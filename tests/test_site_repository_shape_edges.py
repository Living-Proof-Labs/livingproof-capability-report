# SPDX-License-Identifier: Apache-2.0
"""Edges of the OWNER/NAME check on `site --repository` that mutation left unpinned (PR 144).

Each case is run through the flag and through GITHUB_REPOSITORY. A refused value exits 2 and
writes nothing; an accepted value passes the shape check (it then fails later, because the
fixture's run.url names another repository, which is not what these tests are about).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import site_fixture
from click.testing import CliRunner

from livingproof_capability_report.cli import report

OWNER_39 = "a" + "b" * 38
NAME_100 = "r" * 100


def _site(*args: str, env: dict | None = None):
    return CliRunner().invoke(report, ["site", *args], env=env, catch_exceptions=False)


def _both(tmp_path: Path, repository: str):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    flag = _site(str(reports), "--runs", str(tmp_path / "in"), f"--repository={repository}")
    env = _site(str(reports), "--runs", str(tmp_path / "in"), env={"GITHUB_REPOSITORY": repository})
    return reports, flag, env


@pytest.mark.parametrize(
    "repository",
    [
        "a.b/repo",
        "a" * 40 + "/repo",
        "a" * 200 + "/repo",
        "owner/" + "r" * 101,
        "owner/" + "r" * 5000,
        "ｏwner/repo",
        "owner/ｒepo",
        "öwner/repo",
        "owner/répo",
        "оwner/repo",
        "owner/re\u0301po",
        "owner/re\u200bpo",
        "owner/repo\u2028",
        "own\u00a0er/repo",
        "owner/rep\x7fo",
        "owner/rép\u0663",
        "٣owner/repo",
        "owner\t/repo",
        "-/repo",
        "--help/repo",
        "own/er/repo",
        "owner/repo/",
        "owner\\repo",
        "owner/repo?x=1",
        "owner/repo#x",
        "owner/repo@v1",
    ],
)
def test_the_site_command_refuses_each_edge_of_the_repository_shape(tmp_path: Path, repository):
    reports, flag, env = _both(tmp_path, repository)
    assert flag.exit_code == 2, flag.output
    assert env.exit_code == 2, env.output
    assert "OWNER/NAME" in flag.output and "OWNER/NAME" in env.output
    assert not reports.exists()


@pytest.mark.parametrize(
    "repository",
    [
        OWNER_39 + "/repo",
        "o/" + NAME_100,
        "o/.github",
        "o/a.b_c-d",
        "O/R",
        "1/2",
        "o/-r",
        "o/...",
    ],
)
def test_the_site_command_accepts_the_edges_of_a_valid_repository_shape(tmp_path: Path, repository):
    _reports, flag, env = _both(tmp_path, repository)
    assert "OWNER/NAME" not in flag.output
    assert "OWNER/NAME" not in env.output
    assert flag.exit_code != 2 and env.exit_code != 2
