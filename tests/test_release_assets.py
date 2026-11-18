"""Public releases retain packages while image transfers remain CI artifacts."""

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_assets", ROOT / "tools/release_assets.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def populate(root):
    names = [
        "livingproof_capability_report-1.2.0.whl",
        "livingproof_common-1.0.0.whl",
        "livingproof_capability_report-1.2.0.tar.gz",
        "livingproof-capability-report_1.2.0_all.deb",
        "python3-livingproof-common_1.0.0_all.deb",
        "requirements.txt",
    ]
    for arch in ("amd64", "arm64"):
        names += [
            f"wheelhouse-{arch}.tar.gz",
            f"compatibility-{arch}.json",
            f"compatibility-{arch}.md",
        ]
    for name in names + [
        "image-amd64.tar",
        "image-arm64.tar",
        "image-id-amd64.txt",
        "image-id-arm64.txt",
        "SHA256SUMS",
        "SHA256SUMS-amd64",
        "SHA256SUMS-arm64",
    ]:
        (root / name).write_text(name)
    return names


def test_public_assets_preserve_packages_and_checksums_without_images(tmp_path):
    names = populate(tmp_path)
    target = tmp_path / "public"
    module.stage(tmp_path, target)
    assert {p.name for p in target.iterdir()} == set(names) | {
        "SHA256SUMS",
        "SHA256SUMS-amd64",
        "SHA256SUMS-arm64",
    }
    assert (tmp_path / "image-amd64.tar").exists()
    assert (tmp_path / "image-arm64.tar").exists()
    assert "image-" not in (target / "SHA256SUMS").read_text()
    assert not list(target.glob("image-*"))
    for line in (target / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ")
        assert checksum == hashlib.sha256((target / name).read_bytes()).hexdigest()
    assert len((target / "SHA256SUMS").read_text().splitlines()) == len(names)


def test_missing_architecture_package_blocks_staging(tmp_path):
    populate(tmp_path)
    (tmp_path / "wheelhouse-arm64.tar.gz").unlink()
    with pytest.raises(ValueError, match="wheelhouse-arm64"):
        module.stage(tmp_path, tmp_path / "public")
    assert not (tmp_path / "public").exists()


def assert_workflow_gates_public_assets(text):
    jobs = yaml.safe_load(text)["jobs"]
    assert "verify-registry" in jobs
    for job, dependencies in {
        "release": {"verify"},
        "publish": {"release"},
        "manifest": {"release", "publish"},
        "verify-registry": {"release", "manifest"},
        "publish-release": {"release", "verify-registry"},
    }.items():
        needs = jobs[job]["needs"]
        assert dependencies <= set([needs] if isinstance(needs, str) else needs)
    assert "gh release upload" not in str(jobs["publish"])
    assert "gh release upload" not in str(jobs["manifest"])
    assert "tools/release_assets.py" in str(jobs["publish-release"])
    assert "tools/registry_release.py resolve" in str(jobs["manifest"])
    assert "tools/registry_release.py notes" in str(jobs["publish-release"])
    # Check the workflow identity and exact version pin, not Renovate's chosen patch.
    assert re.fullmatch(
        r"Living-Proof-Labs/collaboration-guidelines/\.github/workflows/"
        r"semantic-release\.yml@v[0-9]+\.[0-9]+\.[0-9]+",
        jobs["release"]["uses"],
    )
    assert jobs["release"]["with"]["draft-release"] is True
    for job in ("verify", "publish"):
        transfers = [s for s in jobs[job]["steps"] if s.get("with", {}).get("path") == "dist/"]
        assert transfers and all(s["with"]["retention-days"] == 14 for s in transfers)
    smoke = next(
        step["run"]
        for step in jobs["verify-registry"]["steps"]
        if "docker pull" in step.get("run", "")
    )
    assert 'DOCKER_CONFIG="$(mktemp -d)"' in smoke
    assert 'docker pull --platform "linux/${{ matrix.architecture }}" "$reference"' in smoke
    assert "image-id-${{ matrix.architecture }}.txt" in smoke
    assert "defusedxml" in smoke
    assert "debian:13-slim" in str(jobs["verify-registry"])
    uploads = [
        line.strip().removeprefix("run:").strip()
        for line in text.splitlines()
        if "gh release upload" in line
    ]
    assert uploads == [
        'gh release upload "$RELEASE_TAG" public/* --repo "$GITHUB_REPOSITORY" --clobber'
    ]


def test_workflow_gates_public_assets_on_registry_verification():
    assert_workflow_gates_public_assets((ROOT / ".github/workflows/verify.yml").read_text())


@pytest.mark.parametrize("version", ["v9.6.3", "v9.6.5", "v9.6.6"])
def test_workflow_gate_accepts_guidelines_patch_updates(version):
    text = (ROOT / ".github/workflows/verify.yml").read_text()
    text, count = re.subn(
        r"semantic-release\.yml@v[0-9.]+", f"semantic-release.yml@{version}", text
    )
    assert count == 1
    assert_workflow_gates_public_assets(text)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("  verify-registry:\n", "  unverified-registry:\n"),
        ("needs: verify\n", "needs: []\n"),
        ("needs: release\n", "needs: []\n"),
        ("needs: [release, publish]", "needs: [release]"),
        ("needs: [release, manifest]", "needs: [release]"),
        ("needs: [release, verify-registry]", "needs: [release]"),
        ("draft-release: true", "draft-release: false"),
        ("tools/registry_release.py resolve", "echo resolve"),
        ("docker pull --platform", "echo --platform"),
        ("semantic-release.yml@", "other-release.yml@"),
        ("Living-Proof-Labs/collaboration-guidelines/", "other-owner/collaboration-guidelines/"),
    ],
)
def test_workflow_gate_rejects_missing_safety_contract(before, after):
    text = (ROOT / ".github/workflows/verify.yml").read_text()
    assert text.count(before) == 1
    with pytest.raises((AssertionError, StopIteration)):
        assert_workflow_gates_public_assets(text.replace(before, after))


@pytest.mark.parametrize("ref", ["main", "v9", "v9.6", "v9.6.5-extra"])
def test_workflow_gate_rejects_non_exact_release_pin(ref):
    text = (ROOT / ".github/workflows/verify.yml").read_text()
    text, count = re.subn(r"semantic-release\.yml@v[0-9.]+", f"semantic-release.yml@{ref}", text)
    assert count == 1
    with pytest.raises(AssertionError):
        assert_workflow_gates_public_assets(text)


def test_readme_describes_verified_public_assets():
    readme = (ROOT / "README.md").read_text()
    assert "registry manifest digest" in readme
    assert "retained for 14 days" in readme
    assert "recover-registry.yml" in readme
    assert "Saved `image-amd64.tar`" not in readme
    assert "wheelhouses, saved images" not in readme


@pytest.mark.parametrize(
    "missing",
    [
        "livingproof_capability_report-1.2.0.whl",
        "livingproof_common-1.0.0.whl",
        "livingproof-capability-report_1.2.0_all.deb",
        "python3-livingproof-common_1.0.0_all.deb",
    ],
)
def test_missing_shared_package_blocks_staging(tmp_path, missing):
    populate(tmp_path)
    (tmp_path / missing).unlink()
    with pytest.raises(ValueError, match="Missing required release asset"):
        module.stage(tmp_path, tmp_path / "public")
