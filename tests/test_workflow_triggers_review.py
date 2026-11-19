"""Workflow triggers after making the historical v1.2.0 recovery workflows dispatch-only.

Vera review of #71: the registry-mutating publisher must never run from a pull
request or a main push, its push-gated publish jobs and no-overwrite guard stay,
and the regular verify / release path keeps its pull_request and main triggers.
Issue #102 extends the same dispatch-only guard and a non-mutating already-published
short-circuit to the sibling saved-release recovery workflow.
"""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare `on:` key as boolean True.
    triggers = workflow.get(True, workflow.get("on"))
    return triggers if isinstance(triggers, dict) else {name: None for name in triggers}


def test_historical_publisher_runs_only_on_manual_dispatch():
    triggers = _triggers(_load("recover-registry.yml"))
    assert set(triggers) == {"workflow_dispatch"}


def test_historical_publisher_keeps_no_overwrite_guard_and_push_gate():
    workflow = _load("recover-registry.yml")
    text = (WORKFLOWS / "recover-registry.yml").read_text()
    assert text.count("tools/require_absent_image.py") >= 2
    steps = workflow["jobs"]["saved-image"]["steps"]
    publish = [step for step in steps if "docker push" in step.get("run", "")]
    assert publish and all(step.get("if") == "github.event_name == 'push'" for step in publish)
    assert workflow["jobs"]["manifest"].get("if") == "github.event_name == 'push'"


def test_historical_saved_release_runs_only_on_manual_dispatch():
    triggers = _triggers(_load("verify-saved-release.yml"))
    assert set(triggers) == {"workflow_dispatch"}


@pytest.mark.parametrize(
    'status,artifact_available,guard,expected',
    [
        ('false', False, 'false', 'success'),
        ('true', True, 'true', 'success'),
        ('true', False, 'true', 'failure'),
        ('api-error', False, 'true', 'failure'),
        ('null', False, 'true', 'failure'),
        ('', False, 'true', 'failure'),
        ('true', True, 'false', 'failure'),
        ('true', True, 'api-error', 'failure'),
        ('true', True, 'after-download', 'failure'),
        ('true', True, 'after-notes', 'failure'),
    ],
)
def test_saved_release_recovery_paths(tmp_path, status, artifact_available, guard, expected):
    """Execute real shell steps with local gh/curl stubs and model job dependencies.

    The historical download action is replaced by an availability fixture. No
    artifacts, containers or releases are accessed. Exact graph assertions keep
    this small model tied to the workflow's GitHub success()/needs semantics.
    """
    jobs = _load('verify-saved-release.yml')['jobs']
    preflight, verify, publish = (jobs[name] for name in
                                ('preflight', 'verify-saved', 'publish-assets'))
    assert 'needs' not in preflight
    assert preflight['if'] == (
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert preflight['outputs'] == {'is_draft': '${{ steps.draft.outputs.is_draft }}'}
    assert verify['needs'] == 'preflight'
    assert publish['needs'] == ['preflight', 'verify-saved']
    for job in (verify, publish):
        assert job['if'] == "needs.preflight.outputs.is_draft == 'true'"
        assert not job.get('continue-on-error', False)
    assert verify['steps'][0]['uses'].startswith('actions/download-artifact@')
    assert len(preflight['steps']) == 1
    assert preflight['steps'][0]['id'] == 'draft'
    for step in publish['steps']:
        assert 'if' not in step
        lines = step['run'].splitlines()
        for i, line in enumerate(lines):
            if 'gh release upload' in line or 'gh release edit' in line:
                assert 'isDraft --jq .isDraft | grep -x true' in lines[i - 1]

    gh = tmp_path / 'gh'
    gh.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$2" == view && "$*" == *isDraft* ]]; then
  value="$STATUS"
  if [[ -f "$SEEN" ]]; then value="$GUARD"; fi
  if [[ "$value" == after-download || "$value" == after-notes ]]; then
    value=true
    [[ -f "$SEEN-$GUARD" ]] && value=false
  fi
  touch "$SEEN"
  [[ "$value" == api-error ]] && exit 1
  printf '%s\\n' "$value"
elif [[ "$2" == download ]]; then
  touch "$SEEN-after-download"
  mkdir assets
  printf data > assets/a
  printf data > assets/b
  (cd assets && sha256sum a > SHA256SUMS-amd64 && sha256sum b > SHA256SUMS-arm64)
elif [[ "$2" == view ]]; then
  touch "$SEEN-after-notes"
  echo notes
elif [[ "$2" != upload && "$2" != edit ]]; then
  echo "Unexpected gh invocation" >&2
  exit 1
fi
''')
    gh.chmod(0o755)
    curl = tmp_path / 'curl'
    curl.write_text('#!/bin/sh\ncp "$FIXTURE/$4" "$4"\n')
    curl.chmod(0o755)
    fixture = tmp_path / 'fixture'
    fixture.mkdir()
    for name in ('livingproof-capability-report_1.2.0_all.deb',
                 'compatibility-amd64.json', 'compatibility-arm64.json'):
        (fixture / name).write_text('')
    sums = subprocess.check_output(
        ['sha256sum', *sorted(path.name for path in fixture.iterdir())], cwd=fixture, text=True
    )
    (fixture / 'SHA256SUMS').write_text(sums)
    out, calls = tmp_path / 'output', tmp_path / 'calls'
    summary = tmp_path / 'summary'
    env = {
        **os.environ, 'PATH': f'{tmp_path}:{os.environ["PATH"]}',
        'STATUS': status, 'GUARD': guard, 'SEEN': str(tmp_path / 'seen'),
        'CALLS': str(calls), 'FIXTURE': str(fixture),
        'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': str(summary),
        'RELEASE_TAG': 'v1.2.0', 'GITHUB_REPOSITORY': 'fixture/repo',
    }

    def run(step):
        return subprocess.run(
            ['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', step['run']],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
        )

    result = run(preflight['steps'][0])
    outcome = 'success' if result.returncode == 0 else 'failure'
    artifact_attempted = False
    publish_attempted = False
    if outcome == 'success' and out.read_text().strip() == 'is_draft=true':
        artifact_attempted = True
        if not artifact_available:
            outcome = 'failure'
        else:
            publish_attempted = True
            for step in publish['steps']:
                result = run(step)
                if result.returncode:
                    outcome = 'failure'
                    break
    assert outcome == expected, result.stderr
    mutations = [line for line in calls.read_text().splitlines()
                 if line.startswith(('release upload', 'release edit'))]
    if status == 'true' and artifact_available and guard == 'true':
        assert publish_attempted and len(mutations) == 2
    elif guard == 'after-notes':
        assert len(mutations) == 1 and mutations[0].startswith('release upload')
    else:
        assert not mutations
    if status != 'true':
        assert not artifact_attempted and not publish_attempted
    if status == 'false':
        assert 'already published, nothing to do' in result.stdout
        assert 'skipped asset upload and release mutation' in summary.read_text()
    if status in ('api-error', 'null', ''):
        assert not out.exists()


def test_regular_ci_and_release_keep_pull_request_and_main_push():
    for name in ("verify.yml", "development.yml", "documentation.yml"):
        triggers = _triggers(_load(name))
        assert "pull_request" in triggers, name
        assert triggers.get("push", {}).get("branches") == ["main"], name
    jobs = _load("verify.yml")["jobs"]
    assert (
        "collaboration-guidelines/.github/workflows/semantic-release.yml@"
        in jobs["release"]["uses"]
    )
    for job in ("publish", "manifest", "verify-registry", "publish-release"):
        assert job in jobs


def test_only_historical_v120_workflows_are_dispatch_only():
    dispatch_only = sorted(
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if set(_triggers(yaml.safe_load(path.read_text()))) == {"workflow_dispatch"}
    )
    assert dispatch_only == ["recover-registry.yml", "verify-saved-release.yml"]
