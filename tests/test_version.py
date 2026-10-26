"""Test consumer wiring and artifacts; version policy is tested in livingproof-common."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from click.testing import CliRunner
from livingproof_common.versioning import PROVENANCE, display, read_provenance as read
from livingproof_capability_report.version import current_version
from livingproof_capability_report.cli import report as command


def read_provenance(path):
    return read(path, "livingproof-capability-report")


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-C", str(root), *args],
                                   text=True, env=env).strip()


@pytest.mark.parametrize("change", ["clean", "tracked", "untracked", "deleted-config"])
def test_adapter_uses_consumer_checkout(tmp_path, monkeypatch, change):
    root = tmp_path / "consumer"
    package = root / "src/livingproof_capability_report"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (root / "pyproject.toml").write_text("# fixture")
    git(root, "init", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")
    git(root, "tag", "v8.2.0")
    if change == "tracked":
        (package / "__init__.py").write_text("# changed")
    elif change == "untracked":
        (root / "new").write_text("new")
    elif change == "deleted-config":
        (root / "pyproject.toml").unlink()
    monkeypatch.chdir(tmp_path)
    identity, _, source = current_version(package)
    assert source == "checkout"
    assert identity == "8.2.0" if change == "clean" else identity.endswith(".dirty")
    assert identity.startswith("8.2.0")  # Never common's 1.0.0.


def test_version_callback_uses_this_consumer(monkeypatch):
    monkeypatch.setattr("livingproof_capability_report.version.current_version",
                        lambda: ("8.2.0-dev.1+branch.local.gabcdef123456.dirty",
                                 "8.2.1.dev1", "checkout"))
    result = CliRunner().invoke(command, ["--version"])
    assert result.exit_code == 0
    assert "livingproof-capability-report, version 8.2.0-dev.1" in result.output
    assert "Package: 8.2.1.dev1; identity source: checkout" in result.output


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



