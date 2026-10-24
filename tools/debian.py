"""Build a pure-Python Architecture: all package; apt owns runtime dependencies."""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

version = sys.argv[1]
out = Path("/out")
wheel = next(out.glob("livingproof_capability_report-*-py3-none-any.whl"))
wheels = out / "wheels"
wheels.mkdir(exist_ok=True)
# These native wheels are ONLY for the architecture-specific container/offline wheelhouse.
subprocess.run(["python3", "-m", "pip", "download", "--only-binary=:all:",
                "--dest", str(wheels), "-r", "/requirements.txt", str(wheel)], check=True)
root = Path("/tmp/debian-stage")
packages = root / "usr/lib/python3/dist-packages"
with zipfile.ZipFile(wheel) as archive:
    for entry in archive.infolist():
        name = Path(entry.filename)
        if name.is_absolute() or ".." in name.parts:
            raise SystemExit("Unsafe wheel path")
        if not (name.parts[0] == "livingproof_capability_report"
                or name.parts[0].endswith(".dist-info")):
            raise SystemExit(f"Unexpected wheel content: {name}")
        data = archive.read(entry)
        if data.startswith(b"\x7fELF") or name.suffix in {".so", ".dll", ".dylib", ".pyc"}:
            raise SystemExit("Native or interpreter-specific content cannot enter Architecture: all")
        if not entry.is_dir():
            destination = packages / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
control = root / "DEBIAN"
control.mkdir()
(control / "control").write_text(f"""Package: livingproof-capability-report
Version: {version}
Section: python
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-click (>= 8.1), python3-jsonschema (>= 4.10)
Maintainer: Living Proof Labs <rivet@rollerbot.ai>
Description: Portable capability reports using distribution-managed Python dependencies
""")
for name, command in [("postinst", "py3compile -p livingproof-capability-report"),
                      ("prerm", "py3clean -p livingproof-capability-report")]:
    script = control / name
    script.write_text(f"#!/bin/sh\nset -e\n{command}\n")
    script.chmod(0o755)
bin_dir = root / "usr/bin"
bin_dir.mkdir(parents=True)
command = bin_dir / "livingproof-capability-report"
command.write_text('#!/bin/sh\nexec /usr/bin/python3 -m livingproof_capability_report "$@"\n')
command.chmod(0o755)
copyright = root / "usr/share/doc/livingproof-capability-report/copyright"
copyright.parent.mkdir(parents=True)
copyright.write_text(Path("/build/LICENSE").read_text())
subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(root),
                str(out / f"livingproof-capability-report_{version}_all.deb")], check=True)
for path in out.rglob("*"):
    os.chown(path, int(os.environ.get("OUTPUT_UID", "0")),
             int(os.environ.get("OUTPUT_GID", "0")))
