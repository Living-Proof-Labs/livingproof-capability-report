"""Newcomer guidance must not weaken manifest validation or guess nearby files."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report
from livingproof_capability_report.core import decode, validate_bundle

EXAMPLES = Path(__file__).parents[1] / "examples/bundle"
# A pause observation as robots wrote them; the example bundle is a hallway run now.
OBSERVATION = json.dumps(
    {
        "requested": "paused",
        "observed": "paused",
        "elapsed_ms": 120,
        "motion_inhibited": True,
        "assessments": {"mock-ai": {"status": "PASS", "rationale": "Scripted example"}},
    },
    indent=2,
).encode()


@pytest.mark.parametrize("command", ["validate"])
def test_observation_hint_keeps_failure_and_does_not_write(tmp_path, command):
    observation = tmp_path / "unrelated-name.json"
    original = OBSERVATION
    observation.write_bytes(original)
    output = tmp_path / "report.json"
    args = [command, str(observation)]
    if command == "render":
        args += ["-o", str(output)]
    result = CliRunner().invoke(report, args)
    assert result.exit_code == 1
    assert "Invalid bundle" in result.output
    assert "looks like an individual pause observation" in result.output
    assert result.output.startswith("Error: Expected a bundle manifest")
    assert result.output.index("validate examples/bundle/manifest.json") < result.output.index(
        "Details: Invalid bundle"
    )
    assert "validate examples/bundle/manifest.json" in result.output
    assert "Do not add schema_version" in result.output
    assert not output.exists()
    assert observation.read_bytes() == original


@pytest.mark.parametrize(
    "value", [{}, {"requested": "paused"}, [], {"schema_version": "1.0.0"}, {"results": []}]
)
def test_arbitrary_invalid_inputs_keep_schema_diagnostic(value):
    with pytest.raises(ValueError, match="Invalid bundle") as error:
        validate_bundle(value)
    assert "observation" not in str(error.value)


@pytest.mark.parametrize("marker", ["schema_version", "producer", "results"])
def test_malformed_manifest_with_observation_fields_is_not_reclassified(marker):
    value = decode(OBSERVATION.decode())
    value[marker] = None
    with pytest.raises(ValueError, match="Invalid bundle") as error:
        validate_bundle(value)
    assert "looks like" not in str(error.value)


def test_quickstart_manifest_render_flow(tmp_path):
    runner = CliRunner()
    saved = tmp_path / "report.json"
    manifest = str(EXAMPLES / "manifest.json")
    assert runner.invoke(report, ["validate", manifest]).exit_code == 0
    args = ["render", manifest, "--format", "json", "-o", str(saved)]
    assert runner.invoke(report, args).exit_code == 0
    assert json.loads(saved.read_text())["decisions"]
    rendered = runner.invoke(report, ["render", manifest])
    assert rendered.exit_code == 0
    assert "Living Proof Labs capability report" in rendered.output
    assert "PASS" in rendered.output and "FAIL" in rendered.output
    assert runner.invoke(report, ["render", str(saved)]).output == rendered.output
    assert (
        "not an individual evidence/observation file"
        in runner.invoke(report, ["validate", "--help"]).output
    )


def test_real_user_command_leads_with_recovery(monkeypatch, tmp_path):
    (tmp_path / "pass.json").write_bytes(OBSERVATION)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(report, ["validate", "pass.json"])
    assert result.exit_code == 1
    assert result.output.startswith("Error: Expected a bundle manifest containing version")
    assert "evidence paths and assessment references" in result.output
    assert "livingproof-capability-report validate examples/bundle/manifest.json" in result.output
    assert result.output.index("Use the containing bundle") < result.output.index("schema_version")


@pytest.mark.parametrize("command", [[], ["validate"], ["render"]])
def test_help_teaches_runnable_workflow(command):
    result = CliRunner().invoke(report, [*command, "--help"])
    assert result.exit_code == 0
    commands = [
        "livingproof-capability-report render examples/bundle/manifest.json --format json"
        " -o report.json",
        "livingproof-capability-report render report.json",
    ]
    if command != ["render"]:
        commands.insert(0, "livingproof-capability-report validate examples/bundle/manifest.json")
    assert all(line in result.output for line in commands)
    assert [result.output.index(line) for line in commands] == sorted(
        result.output.index(line) for line in commands
    )
    assert "report grade" not in result.output and "--require-pass" not in result.output


def test_examples_in_help_run(monkeypatch, tmp_path):
    """Every command line the help prints works from the repository root, in a scratch dir."""
    import re
    import shlex
    import shutil

    shutil.copytree(EXAMPLES.parent, tmp_path / "examples")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    lines = set()
    for command in ([], ["validate"], ["render"]):
        text = runner.invoke(report, [*command, "--help"]).output
        lines |= set(re.findall(r"livingproof-capability-report (.+)", text))
    assert lines
    for line in sorted(lines):
        result = runner.invoke(report, shlex.split(line))
        assert result.exit_code == 0, (line, result.output)
