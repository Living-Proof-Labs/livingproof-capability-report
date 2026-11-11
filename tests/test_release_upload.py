# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_every_release_upload_replaces_assets_so_a_rerun_still_publishes():
    uploads = [
        line
        for path in WORKFLOWS.glob("*.yml")
        for line in path.read_text().splitlines()
        if "gh release upload" in line
    ]
    assert len(uploads) >= 4 and all("--clobber" in line for line in uploads)


def test_only_test_report_publishing_may_continue_on_error():
    """A Checks API failure may skip the report. It must not skip the test result."""
    reporters = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for job in workflow["jobs"].values():
            for step in job.get("steps") or []:
                uses = step.get("uses") or ""
                if uses.startswith("dorny/test-reporter@"):
                    reporters.append((path.name, step.get("name")))
                    assert step.get("continue-on-error") is True
                    assert "!cancelled()" in str(step.get("if"))
                else:
                    assert not step.get("continue-on-error"), (path.name, step)
    assert len(reporters) == 4
