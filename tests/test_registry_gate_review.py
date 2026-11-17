"""Reviewer coverage: public release assets wait for an anonymous digest-pinned pull.

publish-release attaches assets only after every verify-registry leg passed. That
leg pulls the manifest digest recorded by the manifest job, with an empty Docker
config and no login, and fails unless the pulled image ID equals the CI-tested one.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
JOBS = yaml.safe_load((ROOT / ".github/workflows/verify.yml").read_text())["jobs"]
GATED = ("manifest", "verify-registry", "publish-release")
STATUS_FUNCTIONS = ("always()", "failure()", "cancelled()", "!cancelled()")


def _smoke() -> str:
    return next(
        step["run"]
        for step in JOBS["verify-registry"]["steps"]
        if "docker pull" in step.get("run", "")
    )


def test_publish_release_waits_for_registry_verification_after_the_manifest():
    assert "verify-registry" in JOBS["publish-release"]["needs"]
    assert "manifest" in JOBS["verify-registry"]["needs"]
    for name in GATED:
        condition = str(JOBS[name].get("if", ""))
        assert not any(function in condition for function in STATUS_FUNCTIONS), name


def test_no_gated_job_or_step_may_continue_on_error():
    for name in GATED:
        job = JOBS[name]
        assert "continue-on-error" not in job, name
        assert all("continue-on-error" not in step for step in job["steps"]), name


def test_the_pull_is_anonymous_and_pinned_to_the_recorded_manifest_digest():
    smoke = _smoke()
    lines = [line.strip() for line in smoke.splitlines()]
    assert lines[0] == 'export DOCKER_CONFIG="$(mktemp -d)"'
    assert "docker login" not in str(JOBS["verify-registry"])
    assert "GH_TOKEN" not in str(JOBS["verify-registry"])
    assert "secrets." not in str(JOBS["verify-registry"])
    assert any(
        line.startswith("digest=$(python3 -c")
        and '["manifest_digest"]' in line
        and "registry.json" in line
        for line in lines
    )
    assert 'reference="$image@$digest"' in lines
    pulls = [line for line in lines if line.startswith("docker pull")]
    assert pulls and all(line.endswith('"$reference"') for line in pulls)
    assert ':$VERSION"' not in "\n".join(line for line in lines if "docker" in line)


def test_a_pulled_image_id_that_differs_from_the_ci_tested_image_fails_the_leg():
    lines = [line.strip() for line in _smoke().splitlines()]
    expected = (
        'test "$(docker image inspect "$reference" --format \'{{.Id}}\')" = '
        '"$(cat native/image-id-${{ matrix.architecture }}.txt)"'
    )
    assert expected in lines
    assert "set +e" not in lines
    recorded = next(
        step["run"] for step in JOBS["publish"]["steps"] if "image-id-" in step.get("run", "")
    )
    assert "--format '{{.Id}}'" in recorded
    assert "dist/image-id-${{ matrix.architecture }}.txt" in recorded
