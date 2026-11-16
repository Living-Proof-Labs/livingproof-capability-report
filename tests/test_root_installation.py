# SPDX-License-Identifier: Apache-2.0
"""Exercise the supported shared environment against a checksum-pinned root release.

Run with LIVINGPROOF_NETWORK=1; CI runs this explicitly on both architectures.
The release baseline must be reviewed when root's dependency contract changes.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROOT_WHEEL = "livingproof-1.4.18-py3-none-any.whl"
ROOT_URL = (
    "https://github.com/Living-Proof-Labs/livingproof/releases/download/v1.4.18/"
    + ROOT_WHEEL
)
ROOT_SHA256 = "68901c1f9e2778a8070e17e1cd31f2455428c394ade0c393019ef5483e4c351f"


@pytest.mark.skipif(os.environ.get("LIVINGPROOF_NETWORK") != "1", reason="network opt-in")
def test_root_and_reporter_share_environment(tmp_path):
    uv = shutil.which("uv")
    assert uv, "uv is required for the installation regression test"

    def run(*args, cwd=tmp_path):
        result = subprocess.run(
            list(map(str, args)), cwd=cwd, capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    content = urlopen(ROOT_URL, timeout=60).read()
    assert hashlib.sha256(content).hexdigest() == ROOT_SHA256
    root_wheel = tmp_path / ROOT_WHEEL
    root_wheel.write_bytes(content)
    wheels = tmp_path / "wheels"
    run(uv, "build", "--wheel", "--out-dir", wheels, cwd=ROOT)
    reporter_wheel, = wheels.glob("livingproof_capability_report-*.whl")
    environment = tmp_path / "environment"
    run(uv, "venv", "--python", sys.executable, "--no-python-downloads", environment)
    python = environment / "bin" / "python"
    common = (
        "https://github.com/Living-Proof-Labs/livingproof-common/releases/download/"
        "v1.0.0/livingproof_common-1.0.0-py3-none-any.whl"
        "#sha256=8b7795748b54eeb89610f3716245f45db48ac0474465a5abbf974e7075c1476c"
    )
    # A single resolver transaction catches conflicting exact requirements.
    run(uv, "pip", "install", "--python", python, root_wheel, reporter_wheel, common)
    run(uv, "pip", "check", "--python", python)
    manifest = ROOT / "examples" / "bundle" / "manifest.json"
    reports = []
    for command in (
        [environment / "bin" / "livingproof-capability-report"],
        [environment / "bin" / "livingproof", "capability", "report"],
    ):
        run(*command, "validate", manifest)
        output = run(*command, "render", manifest, "--format", "json")
        reports.append(json.loads(output))
    assert reports[0] == reports[1]
    assert reports[0], "installed reporter must produce a report"
