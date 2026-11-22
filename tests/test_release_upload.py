# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_every_release_upload_replaces_assets_so_a_rerun_still_publishes():
    uploads = [
        (path.name, line.strip().removeprefix("run:").strip())
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for line in path.read_text().splitlines()
        if "gh release upload" in line
    ]
    assert [name for name, _line in uploads] == ["verify-saved-release.yml", "verify.yml"]
    assert all("--clobber" in line for _name, line in uploads)
    assert all("image-" not in line for _name, line in uploads)
    assert uploads[1][1] == (
        'gh release upload "$RELEASE_TAG" public/* --repo "$GITHUB_REPOSITORY" --clobber'
    )


def test_only_test_report_publishing_may_continue_on_error():
    """A Checks API failure may skip the report. It must not skip the test result."""
    reporters = []
    retried = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for job in workflow["jobs"].values():
            for step in job.get("steps") or []:
                uses = step.get("uses") or ""
                if uses.startswith("dorny/test-reporter@"):
                    reporters.append((path.name, step.get("name")))
                    assert step.get("continue-on-error") is True
                    assert "!cancelled()" in str(step.get("if"))
                elif path.name == "documentation-deploy.yml" and step.get("id") in {
                    "pages-id-first",
                    "pages-name-first",
                }:
                    assert uses.startswith("actions/download-artifact@")
                    assert step.get("continue-on-error") is True
                    retried.append(step["id"])
                else:
                    assert not step.get("continue-on-error"), (path.name, step)
    assert reporters == [
        ("development.yml", "Individual container tests in run summary"),
        ("documentation-build.yml", "Individual installed scenarios and manual checks"),
        ("verify.yml", "Individual tests in run summary"),
    ]
    assert retried == ["pages-id-first", "pages-name-first"]
    deploy = yaml.safe_load((WORKFLOWS / "documentation-deploy.yml").read_text())["jobs"]["deploy"]
    steps = deploy["steps"]
    assert any(step.get("id") == "pages-id-retry" for step in steps)
    assert any(step.get("id") == "pages-name-retry" for step in steps)
    assert "matching ID and name readback" in steps[-3]["name"]
