import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report import grade, load_bundle, render
from livingproof_capability_report.cli import report


@pytest.fixture
def saved(tmp_path):
    source = Path(__file__).parents[1] / "examples/bundle/manifest.json"
    value = grade(load_bundle(source))
    path = tmp_path / "report.json"
    path.write_text(render(value))
    return path, value


def test_default_stdout_and_legacy_file_default(saved, tmp_path):
    path, value = saved
    runner = CliRunner()
    result = runner.invoke(report, ["render", str(path)])
    assert result.exit_code == 0
    assert result.output == render(value, "table")
    assert "Result" in result.output and "INSUFFICIENT_EVIDENCE" in result.output
    assert "\x1b" not in result.output
    output = tmp_path / "legacy.html"
    assert runner.invoke(report, ["render", str(path), "-o", str(output)]).exit_code == 0
    assert output.read_text().startswith("<!doctype html>")
    assert runner.invoke(report, ["render", str(path), "-o", str(output)]).exit_code != 0
    assert runner.invoke(report, ["render", str(path), "-o", str(path)]).exit_code != 0
    assert json.loads(path.read_text()) == value


@pytest.mark.parametrize("format", ["table", "json", "html", "csv"])
def test_explicit_formats_stdout_and_file(saved, tmp_path, format):
    path, value = saved
    runner = CliRunner()
    result = runner.invoke(report, ["render", str(path), "--format", format])
    assert result.exit_code == 0
    # Click normalizes newlines on stdout; exported files retain the format's line endings.
    assert result.output == render(value, format).replace("\r\n", "\n")
    output = tmp_path / ("export." + format)
    assert runner.invoke(report, ["render", str(path), "--format", format,
                                 "-o", str(output)]).exit_code == 0
    assert output.read_bytes() == render(value, format).encode()


def test_help_invalid_options_and_terminal_controls(saved):
    path, value = saved
    runner = CliRunner()
    result = runner.invoke(report, ["render", "--help"])
    assert "Default: table on stdout" in result.output
    assert "[table|json|html|csv]" in result.output
    assert runner.invoke(report, ["render", str(path), "--format", "unknown"]).exit_code != 0
    value["decisions"][0]["reason"] = "\x1b[31mnot executed"
    value["groups"] = []  # Renderer derives contexts from the preserved source, not grades.
    text = render(value, "table")
    assert "\x1b" not in text
    assert "Separate contexts" in text
    assert "1.0.0" in text and "2.0.0" in text
