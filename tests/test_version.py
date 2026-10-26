"""Real Git repositories and artifact provenance, independent of caller checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report
from livingproof_capability_report.version import (
    PROVENANCE, branch_slug, build_provenance, current_version, display, read_provenance,
    source_identity, unknown,
)


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-C", str(root), *args], text=True, env=env).strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-b", "main")
    (root / "pyproject.toml").write_text('[project]\nname="livingproof-capability-report"\n')
    package = root / "src/livingproof_capability_report"
    package.mkdir(parents=True)
    (package / "sample.py").write_text("# fixture\n")
    (root / ".gitignore").write_text("src/livingproof_capability_report/_build_provenance.json\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")
    git(root, "tag", "v1.4.0")
    return root


def ahead(root):
    git(root, "checkout", "-b", "fix/visible-example")
    (root / "src/livingproof_capability_report/sample.py").write_text("# changed\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "ahead")


def test_clean_release_and_branch_ahead(repository):
    identity = source_identity(repository)
    assert identity["state"] == "clean"
    assert display(identity) == "1.4.0"
    ahead(repository)
    identity = source_identity(repository)
    assert identity["distance"] == 1
    assert identity["branch"] == "local"  # No publication of private local names.
    git(repository, "remote", "add", "origin",
        "https://github.com/Living-Proof-Labs/livingproof-capability-report.git")
    git(repository, "update-ref", "refs/remotes/origin/fix/visible-example", "HEAD")
    identity = source_identity(repository)
    assert identity["branch"] == branch_slug("fix/visible-example")
    assert display(identity).startswith("1.4.0-dev.1+branch.fix-visible-example-")
    assert display(identity).endswith(".clean")
    assert ".g" + git(repository, "rev-parse", "HEAD")[:12] in display(identity)


@pytest.mark.parametrize("change", ["tracked", "staged", "untracked"])
def test_live_dirty_state_without_reinstall(repository, change):
    package = repository / "src/livingproof_capability_report"
    assert current_version(package)[0] == "1.4.0"
    if change == "untracked":
        (repository / "new-file").write_text("new")
    else:
        (package / "sample.py").write_text("# dirty\n")
        if change == "staged":
            git(repository, "add", ".")
    version, _, source = current_version(package)
    assert version.startswith("1.4.0-dev.0+") and version.endswith(".dirty")
    assert source == "checkout"


def test_detached_and_private_origin_do_not_expose_branch(repository):
    ahead(repository)
    git(repository, "remote", "add", "origin", "https://example.invalid/private.git")
    git(repository, "update-ref", "refs/remotes/origin/fix/visible-example", "HEAD")
    assert source_identity(repository)["branch"] == "local"
    git(repository, "checkout", "--detach")
    assert source_identity(repository)["branch"] == "detached"
    assert "+branch.detached." in display(source_identity(repository))


def test_empty_and_untagged_states(tmp_path):
    git(tmp_path, "init", "-b", "private-name")
    identity = source_identity(tmp_path)
    assert identity["history"] == "empty"
    assert "dev.empty" in display(identity)
    (tmp_path / "file").write_text("new")
    assert source_identity(tmp_path)["state"] == "dirty"
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "first")
    identity = source_identity(tmp_path)
    assert identity["history"] == "untagged" and identity["distance"] == 1
    assert display(identity).startswith("0.0.0-dev.untagged.1+")


def test_shallow_history_is_explicit(repository, tmp_path):
    ahead(repository)
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "--depth=1", repository.as_uri(), str(shallow))
    identity = source_identity(shallow)
    assert identity["history"] == "shallow"
    assert display(identity).endswith(".clean.shallow")
    assert "dev.unknown" in display(identity)


def test_no_git_and_caller_repository_are_not_guessed(repository, tmp_path, monkeypatch):
    package = tmp_path / "installed/livingproof_capability_report"
    package.mkdir(parents=True)
    monkeypatch.chdir(repository)
    assert current_version(package)[0] == "0.0.0-dev.unknown+nogit.unknown"
    assert source_identity(tmp_path) is None
    nested = repository / "nested"
    nested.mkdir()
    assert source_identity(nested) is None


def test_installed_provenance_survives_no_git(repository, tmp_path, monkeypatch):
    ahead(repository)
    package = tmp_path / "installed/livingproof_capability_report"
    package.mkdir(parents=True)
    saved = build_provenance(repository, "1.4.1.dev1")
    (package / PROVENANCE).write_text(json.dumps(saved))
    monkeypatch.setenv("PATH", "")
    version, _, origin = current_version(package)
    assert version == display(saved["identity"])
    assert origin == "recorded-build"
    assert source_identity(repository) is None
    assert current_version(repository / "src/livingproof_capability_report")[2] == (
        "checkout-unavailable")


def test_source_archive_preserves_snapshot_and_build_is_deterministic(repository, tmp_path):
    first = build_provenance(repository, "1.4.0")
    assert first == build_provenance(repository, "1.4.0")
    package = repository / "src/livingproof_capability_report"
    (package / PROVENANCE).write_text(json.dumps(first))
    assert source_identity(repository)["state"] == "clean"
    archive = tmp_path / "archive"
    shutil.copytree(repository, archive, ignore=shutil.ignore_patterns(".git"))
    assert build_provenance(archive, "1.4.0") == first
    (package / "sample.py").write_text("# dirty")
    dirty = build_provenance(repository, "1.4.0")
    assert dirty == build_provenance(repository, "1.4.0")
    assert dirty["identity"]["state"] == "dirty"
    assert "timestamp" not in json.dumps(dirty)


def test_git_environment_cannot_redirect_identity(repository, tmp_path, monkeypatch):
    git(tmp_path, "init")
    monkeypatch.setenv("GIT_DIR", str(tmp_path / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    assert display(source_identity(repository)) == "1.4.0"


def test_slug_is_bounded_and_collision_resistant():
    first = branch_slug("A/" + "x" * 100 + "-1")
    second = branch_slug("A/" + "x" * 100 + "-2")
    assert len(first) <= 33 and first != second


def test_invalid_saved_provenance_is_explicitly_unknown(tmp_path):
    path = tmp_path / PROVENANCE
    path.write_text('{"format_version": 1}')
    assert read_provenance(path) is None
    assert display(unknown()) == "0.0.0-dev.unknown+nogit.unknown"


def test_version_option_reports_display_and_package(monkeypatch):
    monkeypatch.setattr("livingproof_capability_report.version.current_version",
                        lambda: ("1.4.0-dev.1+branch.local.gabcdef123456.dirty",
                                 "1.4.1.dev1", "checkout"))
    result = CliRunner().invoke(report, ["--version"])
    assert result.exit_code == 0
    assert "gabcdef123456.dirty" in result.output
    assert "Package: 1.4.1.dev1; identity source: checkout" in result.output


def test_built_wheel_and_source_archive_retain_provenance(tmp_path):
    import sys
    import tarfile
    import zipfile

    root = tmp_path / "project"
    shutil.copytree(Path(__file__).parents[1], root,
                    ignore=shutil.ignore_patterns(".git", ".venv", "dist", "artifacts",
                                                 "__pycache__", ".pytest_cache", ".ruff_cache",
                                                 PROVENANCE))
    git(root, "init", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-m", "release fixture")
    git(root, "tag", "v1.4.0")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SETUPTOOLS_SCM_")}
    subprocess.run(["uv", "build", "--offline", "--out-dir", "dist"], cwd=root,
                   env=env, check=True, capture_output=True)
    wheel = next((root / "dist").glob("*.whl"))
    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installed)
    saved = read_provenance(installed / "livingproof_capability_report" / PROVENANCE)
    assert saved["identity"]["state"] == "clean"
    assert saved["identity"]["commit"] == git(root, "rev-parse", "HEAD")
    assert display(saved["identity"]) == "1.4.0"
    # Import the actual wheel files outside a checkout, with no Git on PATH.
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); "
             "from livingproof_capability_report.version import current_version; "
             "import json; print(json.dumps(current_version()))")
    output = subprocess.check_output([sys.executable, "-c", probe, str(installed)],
                                     cwd=tmp_path, env={**env, "PATH": ""}, text=True)
    assert json.loads(output) == ["1.4.0", "1.4.0", "recorded-build"]
    with tarfile.open(next((root / "dist").glob("*.tar.gz"))) as archive:
        archive.extractall(tmp_path / "sdist", filter="data")
    source = next((tmp_path / "sdist").iterdir())
    subprocess.run(["uv", "build", "--offline", "--wheel", "--out-dir", "dist"],
                   cwd=source, env=env, check=True, capture_output=True)
    with zipfile.ZipFile(next((source / "dist").glob("*.whl"))) as archive:
        rebuilt = json.loads(archive.read("livingproof_capability_report/" + PROVENANCE))
    assert rebuilt == saved

    (root / "README.md").write_text("Dirty build fixture\n")
    snapshots = []
    for number in range(2):
        output_dir = tmp_path / f"dirty-{number}"
        subprocess.run(["uv", "build", "--offline", "--wheel", "--out-dir", str(output_dir)],
                       cwd=root, env=env, check=True, capture_output=True)
        with zipfile.ZipFile(next(output_dir.glob("*.whl"))) as archive:
            snapshots.append(json.loads(archive.read("livingproof_capability_report/" + PROVENANCE)))
    assert snapshots[0] == snapshots[1]
    assert snapshots[0]["package_version"] == "1.4.1.dev0"
    assert display(snapshots[0]["identity"]).endswith(".dirty")



@pytest.mark.parametrize("change", ["invalid", "deleted"])
def test_edited_pyproject_still_reports_live_dirty_identity(repository, change):
    if change == "invalid":
        (repository / "pyproject.toml").write_text("[broken configuration")
    else:
        (repository / "pyproject.toml").unlink()
    identity, _, origin = current_version(repository / "src/livingproof_capability_report")
    assert origin == "checkout"
    assert identity.endswith(".dirty")



@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("competing_tag", ["v1.1.0-rc.1", "v1.1.0+build.1", "v01.1.0"])
def test_nonrelease_tags_cannot_hide_older_valid_release(repository, annotated, competing_tag):
    git(repository, "tag", "-d", "v1.4.0")
    git(repository, "tag", "v1.0.0")
    ahead(repository)
    if annotated:
        git(repository, "tag", "-a", competing_tag, "-m", "nonrelease fixture")
    else:
        git(repository, "tag", competing_tag)
    identity = source_identity(repository)
    assert identity["history"] == "tagged"
    assert identity["base_version"] == "1.0.0"
    assert identity["distance"] == 1
    assert display(identity).startswith("1.0.0-dev.1+")
    git(repository, "tag", "v1.1.0")
    assert display(source_identity(repository)) == "1.1.0"


def test_only_prerelease_tags_remain_explicitly_untagged(repository):
    git(repository, "tag", "-d", "v1.4.0")
    git(repository, "tag", "v1.1.0-rc.1")
    identity = source_identity(repository)
    assert identity["history"] == "untagged"
    assert identity["base_version"] is None
    assert display(identity).startswith("0.0.0-dev.untagged.1+")
