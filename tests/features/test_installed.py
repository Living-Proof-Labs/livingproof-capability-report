"""Bounded observable reporter contracts; also the manual's scenario source."""

import hashlib
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cli(tmp_path):
    target = ROOT / "artifacts/docs/packages"
    assert target.is_dir(), "Run task docs:prepare first"
    env = {**os.environ, "PYTHONPATH": str(target)}

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "livingproof_capability_report", *map(str, args)],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
        )

    return run


def test_validate_portable_bundle(cli):
    """Given the released producer example bundle
    When the installed reporter validates its manifest
    Then validation succeeds without changing the original evidence.
    """
    files = list((ROOT / "examples/bundle").rglob("*.json"))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    result = cli("validate", ROOT / "examples/bundle/manifest.json")
    assert result.returncode == 0, result.stderr
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_refuse_bundle_without_decisions(cli, tmp_path):
    """Given a bundle 1.0.0, which carries no verifier decisions
    When the installed reporter is asked to render it
    Then it exits 1 with a pointer to capability-verifier and writes nothing.
    """
    data = json.loads((ROOT / "examples/bundle/manifest.json").read_text())
    data["schema_version"] = "1.0.0"
    data.pop("assessment")
    for result in data["results"]:
        result.pop("decision")
    bundle = tmp_path / "bundle"
    shutil.copytree(ROOT / "examples/bundle/evidence", bundle / "evidence")
    (bundle / "manifest.json").write_text(json.dumps(data))
    output = tmp_path / "report.json"
    result = cli("render", bundle / "manifest.json", "--format", "json", "-o", output)
    assert result.returncode == 1
    assert "this reporter does not grade" in result.stderr
    assert "capability-verifier" in result.stderr
    assert not output.exists()


def test_render_stored_decisions(cli, tmp_path):
    """Given a report saved from the verifier's bundle 1.1.0
    When the installed reporter renders its default terminal table
    Then stored decisions remain visible and the saved report is unchanged.
    """
    output = tmp_path / "report.json"
    manifest = ROOT / "examples/bundle/manifest.json"
    assert cli("render", manifest, "--format", "json", "-o", output).returncode == 0
    original = output.read_bytes()
    result = cli("render", output)
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout and "FAIL" in result.stdout
    assert output.read_bytes() == original


def test_reject_malformed_manifest(cli, tmp_path):
    """Given a manifest containing invalid JSON
    When the installed reporter validates it
    Then it exits unsuccessfully and provides an error instead of a report.
    """
    source = tmp_path / "invalid.json"
    source.write_text("{bad json")
    result = cli("validate", source)
    assert result.returncode != 0
    assert "Error" in result.stderr
