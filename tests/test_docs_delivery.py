"""Exercise the released reporter wheel and no-checkout manual delivery gates."""

import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tarfile
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
HELPER = runpy.run_path(str(ROOT / "tools/docs_delivery.py"))
VERSION = "3.15.3"
COMMIT = "a" * 40
TAG = f"v{VERSION}"
WHEEL = f"livingproof_capability_report-{VERSION}-py3-none-any.whl"


def workflow(name):
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())


def test_only_published_wheel_delivery_depends_on_the_package_finalizer():
    jobs = workflow("verify")["jobs"]
    assert jobs["release"]["needs"] == "verify"
    assert jobs["publish-release"]["needs"] == ["release", "verify-registry"]
    build = jobs["build-released-manual"]
    assert build["needs"] == ["release", "publish-release"]
    assert "needs.publish-release.result == 'success'" in build["if"]
    assert "needs.release.outputs.commit == github.sha" in build["if"]
    assert build["with"]["package_version"] == "${{ needs.release.outputs.version }}"
    assert build["permissions"] == {"contents": "read"}
    replay = workflow("documentation")["jobs"]
    release_pin = jobs["release"]["uses"].rsplit("@", 1)[1]
    assert {job["uses"] for job in replay.values()} == {
        "Living-Proof-Labs/collaboration-guidelines/.github/workflows/"
        f"semantic-release-candidate.yml@{release_pin}",
        "./.github/workflows/documentation-build.yml",
        "./.github/workflows/documentation-deploy.yml",
    }
    assert "workflow_dispatch" in replay["deploy-manual"]["if"]
    assert "refs/heads/main" in replay["deploy-manual"]["if"]
    assert "needs.version.outputs.commit == github.sha" in replay["deploy-manual"]["if"]
    deploy = workflow("documentation-deploy")["jobs"]["deploy"]
    assert not any("actions/checkout" in step.get("uses", "") for step in deploy["steps"])
    assert not any("tools/" in step.get("run", "") for step in deploy["steps"])


@pytest.fixture
def released(tmp_path):
    wheel = tmp_path / WHEEL
    provenance = {
        "distribution": "livingproof-capability-report",
        "package_version": VERSION,
        "identity": {
            "commit": COMMIT,
            "base_version": VERSION,
            "distance": 0,
            "state": "clean",
            "history": "tagged",
        },
    }
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "livingproof_capability_report/_build_provenance.json", json.dumps(provenance)
        )
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(f"{HELPER['digest'](wheel)}  {wheel.name}\n")
    release = {
        "tag_name": TAG,
        "draft": False,
        "prerelease": False,
        "immutable": True,
        "published_at": "fixture",
        "assets": [
            {"name": p.name, "state": "uploaded", "digest": f"sha256:{HELPER['digest'](p)}"}
            for p in (wheel, checksums)
        ],
    }
    return tmp_path, release


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"tag_name": "v3.15.2"},
        {"draft": True},
        {"immutable": False},
        {"prerelease": True},
        {"published_at": None},
        {"assets": []},
    ],
)
def test_released_wheel_requires_an_exact_stable_immutable_release(released, changes):
    directory, release = released
    (directory / "release.json").write_text(json.dumps(release | changes))
    check = HELPER["released_wheel"]
    if changes:
        with pytest.raises(ValueError):
            check(directory, TAG, VERSION, COMMIT)
    else:
        assert check(directory, TAG, VERSION, COMMIT) == directory / WHEEL


@pytest.mark.parametrize("changed", [WHEEL, "SHA256SUMS", "commit"])
def test_released_wheel_rejects_changed_bytes_or_build_provenance(released, changed):
    directory, release = released
    (directory / "release.json").write_text(json.dumps(release))
    source = COMMIT
    if changed == "commit":
        source = "b" * 40
    else:
        with (directory / changed).open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises(ValueError):
        HELPER["released_wheel"](directory, TAG, VERSION, source)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"source_commit": "b" * 40},
        {"edition": "preview"},
        {"package_version": "3.15.2"},
        {"release_tag": "v3.15.2"},
        {"run_attempt": "7"},
        {"wheel_sha256": "bad"},
    ],
)
def test_privileged_job_reads_only_matching_archive_manifest(tmp_path, changes):
    target = tmp_path / "verified-reporter"
    target.mkdir()
    archive = target / "artifact.tar"
    record = {
        "source_commit": COMMIT,
        "source_dirty": False,
        "edition": "release",
        "version": VERSION,
        "package_version": VERSION,
        "release_tag": TAG,
        "run_id": "10",
        "run_attempt": "1",
        "wheel_sha256": "c" * 64,
    }
    with tarfile.open(archive, "w") as tar:
        data = json.dumps(record | changes).encode()
        info = tarfile.TarInfo("./build.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    guard = next(
        step
        for step in workflow("documentation-deploy")["jobs"]["deploy"]["steps"]
        if step.get("id") == "pages-package"
    )
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "DIGEST": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "VERSION": VERSION,
        "RELEASE_TAG": TAG,
        "SOURCE": COMMIT,
        "PLAN_RUN": "10",
        "PLAN_ATTEMPT": "1",
    }
    result = subprocess.run(["bash", "-c", guard["run"]], env=env, capture_output=True, check=False)
    assert (result.returncode == 0) is (not changes), result.stderr
    if not changes:
        assert archive.read_bytes() == (tmp_path / "artifact.tar").read_bytes()
