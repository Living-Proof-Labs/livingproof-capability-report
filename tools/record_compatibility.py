"""Record a successful clean-install probe from inside its tested runtime."""
import importlib.metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

path, method = sys.argv[1:]
host = os.environ["COMPATIBILITY_HOST_MACHINE"]
if platform.machine() != host:
    raise SystemExit("Expected matching native host/container architecture")
release = platform.freedesktop_os_release()
data = {
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
