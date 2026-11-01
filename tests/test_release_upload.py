# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_every_release_upload_replaces_assets_so_a_rerun_still_publishes():
    uploads = [
        line
        for path in WORKFLOWS.glob("*.yml")
        for line in path.read_text().splitlines()
        if "gh release upload" in line
    ]
    assert len(uploads) >= 4 and all("--clobber" in line for line in uploads)
