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


def test_historical_saved_release_keeps_draft_guard_and_skips_mutation(tmp_path):
    workflow = _load("verify-saved-release.yml")
    publish = workflow["jobs"]["publish-assets"]
    assert publish["if"] == (
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    steps = publish["steps"]
    draft_step = steps[0]
    assert draft_step["id"] == "draft"
    mutating = [
        step
        for step in steps[1:]
        if "gh release upload" in step.get("run", "") or "gh release edit" in step.get("run", "")
    ]
    assert len(mutating) == 2
    assert all(step.get("if") == "steps.draft.outputs.is_draft == 'true'" for step in steps[1:])
    assert "grep -x true" in steps[1]["run"]

    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "release" ] && [ "$2" = "view" ]; then\n'
        '  printf "%s\\n" "$FAKE_IS_DRAFT"\n'
        "  exit 0\n"
        "fi\n"
        "echo unexpected gh invocation: $* >&2\n"
        "exit 1\n"
    )
    gh.chmod(0o755)

    for value in ("false", "true"):
        out = tmp_path / f"output-{value}.txt"
        summary = tmp_path / f"summary-{value}.txt"
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "FAKE_IS_DRAFT": value,
            "RELEASE_TAG": "v1.2.0",
            "GITHUB_REPOSITORY": "Living-Proof-Labs/livingproof-capability-report",
            "GITHUB_OUTPUT": str(out),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        result = subprocess.run(
            ["bash", "-e", "-c", draft_step["run"]],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert out.read_text().strip() == f"is_draft={value}"
        if value == "false":
            assert "already published, nothing to do" in result.stdout
            assert "skipped asset upload and release mutation" in summary.read_text()


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
