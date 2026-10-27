"""Bounded observable reporter contracts; also the manual's scenario source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cli(tmp_path):
    target = ROOT / 'artifacts/docs/packages'
    assert target.is_dir(), 'Run task docs:prepare first'
    env = {**os.environ, 'PYTHONPATH': str(target)}

    def run(*args):
        return subprocess.run(
            [sys.executable, '-m', 'livingproof_capability_report', *map(str, args)],
            cwd=tmp_path, env=env, text=True, capture_output=True,
        )
    return run


def test_validate_portable_bundle(cli):
    """Given the released producer example bundle
    When the installed reporter validates its manifest
    Then validation succeeds without changing the original evidence.
    """
    files = list((ROOT / 'examples/bundle').rglob('*.json'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    result = cli('validate', ROOT / 'examples/bundle/manifest.json')
    assert result.returncode == 0, result.stderr
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_require_pass_retains_report(cli, tmp_path):
    """Given a bundle with passing, failing and insufficient coordinates
    When grade is run with --require-pass and an output path
    Then it exits 1 and retains the report with those distinct decisions.
    """
    output = tmp_path / 'report.json'
    result = cli('grade', ROOT / 'examples/bundle/manifest.json', '--require-pass', '-o', output)
    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_text())
    assert {d['status'] for d in report['decisions']} == {
        'PASS', 'FAIL', 'INSUFFICIENT_EVIDENCE'}
    assert len(report['decisions']) == 8
    assert report['source_bundle']['producer']['version'] == '1.1.0'


def test_render_stored_decisions(cli, tmp_path):
    """Given a saved graded report
    When the installed reporter renders its default terminal table
    Then stored decisions remain visible and the saved report is unchanged.
    """
    output = tmp_path / 'report.json'
    assert cli('grade', ROOT / 'examples/bundle/manifest.json', '-o', output).returncode == 0
    original = output.read_bytes()
    result = cli('render', output)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout and 'FAIL' in result.stdout
    assert output.read_bytes() == original


def test_reject_malformed_manifest(cli, tmp_path):
    """Given a manifest containing invalid JSON
    When the installed reporter validates it
    Then it exits unsuccessfully and provides an error instead of a valid grade.
    """
    source = tmp_path / 'invalid.json'
    source.write_text('{bad json')
    result = cli('validate', source)
    assert result.returncode != 0
    assert 'Error' in result.stderr
