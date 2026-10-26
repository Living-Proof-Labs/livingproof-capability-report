"""Record a successful clean-install probe from inside its tested runtime."""
import importlib.metadata
import json
import os
import platform
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from livingproof_capability_report.version import current_version, read_provenance, PROVENANCE
import livingproof_capability_report

identity, package_version, identity_source = current_version()
if identity_source != "recorded-build":
    raise SystemExit("Installed package must retain recorded build provenance without a checkout")
provenance = read_provenance(Path(livingproof_capability_report.__file__).parent / PROVENANCE)
if provenance is None or provenance["identity"]["commit"] is None:
    raise SystemExit("Installed package lost its build commit identity")

version_output = subprocess.check_output(
    [sys.executable, "-m", "livingproof_capability_report", "--version"], text=True)
if f"version {identity}\n" not in version_output or "identity source: recorded-build" not in version_output:
    raise SystemExit("Installed CLI version disagrees with retained provenance")

path, method = sys.argv[1:]
host = os.environ["COMPATIBILITY_HOST_MACHINE"]
if platform.machine() != host:
    raise SystemExit("Expected matching native host/container architecture")
release = platform.freedesktop_os_release()
data = {
    "display_version": identity, "identity_source": identity_source,
    "version_output": version_output,
    "build_provenance": provenance,
    "os": release.get("PRETTY_NAME"), "os_version": release.get("VERSION_ID"),
    "os_details": release,
    "debian_version": (Path("/etc/debian_version").read_text().strip()
                       if Path("/etc/debian_version").exists() else None),
    "architecture": platform.machine(), "python": platform.python_version(),
    "python_details": sys.version, "install_method": method,
    "execution": "native", "host_machine": host,
    "runner_label": os.environ.get("COMPATIBILITY_RUNNER", "local"),
    "outcome": "PASS", "recorded_at": datetime.now(timezone.utc).isoformat(),
    "evidence": os.environ.get("COMPATIBILITY_EVIDENCE", "local execution"),
    "versions": {name: importlib.metadata.version(name)
                 for name in ("livingproof-capability-report", "click", "jsonschema")},
}
Path(path).write_text(json.dumps(data, indent=2) + "\n")
