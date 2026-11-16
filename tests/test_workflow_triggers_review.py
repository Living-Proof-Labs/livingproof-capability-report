"""Workflow triggers after making the historical v1.2.0 publisher dispatch-only.

Vera review of #71: the registry-mutating publisher must never run from a pull
request or a main push, its push-gated publish jobs and no-overwrite guard stay,
and the regular verify / release path keeps its pull_request and main triggers.
"""

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


def test_no_other_workflow_is_dispatch_only():
    dispatch_only = sorted(
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if set(_triggers(yaml.safe_load(path.read_text()))) == {"workflow_dispatch"}
    )
    assert dispatch_only == ["recover-registry.yml"]
