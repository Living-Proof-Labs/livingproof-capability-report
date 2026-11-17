"""PR comment subcommand: marker, update-in-place, pagination, offline dry run."""

import json

from click.testing import CliRunner

from livingproof_capability_report import comment
from livingproof_capability_report.cli import report


def test_body_joins_reports_under_marker():
    assert comment.body(["a\n", " b "]) == f"{comment.MARKER}\n\na\n\nb\n"


def test_publish_creates_then_updates_and_follows_pages():
    calls = []
    pages = {
        "repos/o/r/issues/3/comments?per_page=100": (
            [{"id": 1, "body": "hi"}],
            '<https://api.github.com/next>; rel="next"',
        ),
        "https://api.github.com/next": ([{"id": 9, "body": f"x {comment.MARKER}"}], ""),
    }

    def call(method, path, payload=None):
        calls.append((method, path, payload))
        return pages[path] if method == "GET" else ({}, "")

    assert comment.publish("o/r", 3, "T", call) == ("PATCH", "repos/o/r/issues/comments/9")
    assert calls[-1] == ("PATCH", "repos/o/r/issues/comments/9", {"body": "T"})
    empty = lambda m, p, payload=None: ([], "")  # noqa: E731
    assert comment.publish("o/r", 3, "T", empty, dry_run=True)[0] == "POST"


def test_cli_dry_run_offline(tmp_path):
    md = tmp_path / "report.md"
    md.write_text("<!-- livingproof-verification -->\n## x\n")
    listed = tmp_path / "comments.json"
    listed.write_text(json.dumps([{"id": 5, "body": comment.MARKER}]))
    result = CliRunner().invoke(
        report,
        ["comment", "--repo", "o/r", "--pr", "2", "--dry-run", "--comments", str(listed), str(md)],
    )
    assert result.exit_code == 0, result.output
    assert result.output.startswith("would PATCH repos/o/r/issues/comments/5")
    assert comment.MARKER in result.output and "## x" in result.output


def test_cli_without_token_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    md = tmp_path / "report.md"
    md.write_text("x\n")
    result = CliRunner().invoke(report, ["comment", "--repo", "o/r", "--pr", "2", str(md)])
    assert result.exit_code != 0 and "GITHUB_TOKEN" in result.output
