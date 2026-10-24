"""Build an Ubuntu 24.04 amd64 package with private dependencies, using dpkg-deb."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

version = sys.argv[1]
out = Path("/out")
wheel = next(out.glob("livingproof_capability_report-*.whl"))
wheels = out / "wheels"
wheels.mkdir(exist_ok=True)
subprocess.run(["python3", "-m", "pip", "download", "--only-binary=:all:",
                "--dest", str(wheels), "-r", "/requirements.txt", str(wheel)], check=True)
root = Path("/tmp/debian-stage")
venv = root / "opt/livingproof-capability-report"
subprocess.run(["python3", "-m", "venv", str(venv)], check=True)
subprocess.run([str(venv / "bin/pip"), "install", "--no-index", "--find-links", str(wheels),
                f"livingproof-capability-report=={version}"], check=True)
# The wrapper uses python -m, so staged pip/entrypoint shebangs are not shipped.
for file in (venv / "bin").iterdir():
    if not file.name.startswith("python"):
        file.unlink()
for pattern in ("pip*", "setuptools*", "_distutils_hack", "distutils-precedence.pth"):
    for path in (venv / "lib/python3.12/site-packages").glob(pattern):
        shutil.rmtree(path) if path.is_dir() else path.unlink()
control = root / "DEBIAN"
control.mkdir()
(control / "control").write_text(f"""Package: livingproof-capability-report
Version: {version}
Section: science
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.12), python3 (<< 3.13), python3-venv
Maintainer: Living Proof Labs <rivet@rollerbot.ai>
Description: Portable capability evidence reports in a private Python environment
""")
bin = root / "usr/bin"
bin.mkdir(parents=True)
command = bin / "livingproof-capability-report"
command.write_text('#!/bin/sh\nexec /opt/livingproof-capability-report/bin/python -m livingproof_capability_report "$@"\n')
command.chmod(0o755)
subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(root),
                str(out / f"livingproof-capability-report_{version}_amd64.deb")], check=True)
# Docker-created files remain usable by the calling contributor.
for path in out.rglob("*"):
    os.chown(path, int(os.environ.get("OUTPUT_UID", "0")),
             int(os.environ.get("OUTPUT_GID", "0")))
