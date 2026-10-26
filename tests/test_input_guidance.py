"""Newcomer guidance must not weaken manifest validation or guess nearby files."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report
from livingproof_capability_report.core import decode, validate_bundle

EXAMPLES = Path(__file__).parents[1] / "examples/bundle"


@pytest.mark.parametrize("command", ["validate", "grade"])
def test_observation_hint_keeps_failure_and_does_not_write(tmp_path, command):
    observation = tmp_path / "unrelated-name.json"
    original = (EXAMPLES / "evidence/pass.json").read_bytes()
    observation.write_bytes(original)
    output = tmp_path / "report.json"
    args = [command, str(observation)]
    if command == "grade":
        args += ["-o", str(output)]
    result = CliRunner().invoke(report, args)
    assert result.exit_code == 1
    assert "Invalid bundle" in result.output
    assert "looks like a pause observation" in result.output
    assert "validate examples/bundle/manifest.json" in result.output
    assert "Do not add schema_version" in result.output
    assert not output.exists()
    assert observation.read_bytes() == original


@pytest.mark.parametrize("value", [{}, {"requested": "paused"}, [],
    {"schema_version": "1.0.0"}, {"results": []}])
def test_arbitrary_invalid_inputs_keep_schema_diagnostic(value):
    with pytest.raises(ValueError, match="Invalid bundle") as error:
        validate_bundle(value)
    assert "observation" not in str(error.value)


@pytest.mark.parametrize("marker", ["schema_version", "producer", "results"])
def test_malformed_manifest_with_observation_fields_is_not_reclassified(marker):
    value = decode((EXAMPLES / "evidence/pass.json").read_text())
    value[marker] = None
    with pytest.raises(ValueError, match="Invalid bundle") as error:
        validate_bundle(value)
    assert "looks like" not in str(error.value)


def test_quickstart_manifest_grade_render_flow(tmp_path):
    runner = CliRunner()
    saved = tmp_path / "report.json"
    assert runner.invoke(report, ["validate", str(EXAMPLES / "manifest.json")]).exit_code == 0
    assert runner.invoke(report, ["grade", str(EXAMPLES / "manifest.json"),
                                 "-o", str(saved)]).exit_code == 0
    assert json.loads(saved.read_text())["decisions"]
    rendered = runner.invoke(report, ["render", str(saved)])
    assert rendered.exit_code == 0
    assert "Living Proof Labs capability report" in rendered.output
    assert "PASS" in rendered.output
    assert "not an individual evidence/observation file" in runner.invoke(
        report, ["validate", "--help"]).output
