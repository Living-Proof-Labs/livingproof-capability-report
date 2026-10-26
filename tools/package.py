"""Build wheel, source archive, Debian package and saved installed-package image."""
import hashlib
import os
import platform
import tarfile
import re
import subprocess
from pathlib import Path

from fetch_common import fetch

architecture = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
version = os.environ.get("VERSION", "0.0.0")
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("VERSION must be a release version such as 1.0.0")
network = ["--network", os.environ["PACKAGE_NETWORK"]] if "PACKAGE_NETWORK" in os.environ else []
trust = (["-v", f"{os.environ['PACKAGE_CA_BUNDLE']}:/tmp/package-ca.pem:ro",
          "-e", "PIP_CERT=/tmp/package-ca.pem"] if "PACKAGE_CA_BUNDLE" in os.environ else [])
root = Path(__file__).resolve().parents[1]
dist = root / "dist"
if dist.exists() and list(dist.iterdir()):
    raise SystemExit("Use a fresh checkout or remove prior generated dist files before packaging")
dist.mkdir(exist_ok=True)
fetch(dist)
env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION": version}
subprocess.run(["uv", "build", "--out-dir", str(dist)], env=env, check=True)
subprocess.run(["uv", "export", "--locked", "--no-dev", "--no-emit-project",
                "--no-hashes", "--no-emit-package", "livingproof-common", "--output-file", str(dist / "requirements.txt")], check=True)
subprocess.run(["docker", "build", *network, "-f", "tools/Dockerfile.packages", "-t",
                "livingproof-report-packager", "."], check=True)
subprocess.run(["docker", "run", *network, *trust, "--rm", "-e", f"OUTPUT_UID={os.getuid()}",
                "-e", f"OUTPUT_GID={os.getgid()}", "-v", f"{dist}:/out",
                "-v", f"{dist}/requirements.txt:/requirements.txt:ro",
                "livingproof-report-packager", version], check=True)
image = f"ghcr.io/living-proof-labs/livingproof-capability-report:{version}-{architecture}"
subprocess.run(["docker", "build", *network, "--build-arg", f"VERSION={version}", "-t", image, "."],
               check=True)
subprocess.run(["docker", "save", "-o", str(dist / f"image-{architecture}.tar"), image], check=True)
checksums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(dist)}"
             for p in sorted(dist.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
(dist / "SHA256SUMS").write_text("\n".join(checksums) + "\n")

with tarfile.open(dist / f"wheelhouse-{architecture}.tar.gz", "w:gz") as archive:
    archive.add(dist / "wheels", arcname="wheels")
assets = [dist / f"image-{architecture}.tar", dist / f"wheelhouse-{architecture}.tar.gz"]
if architecture == "amd64":
    assets += [*dist.glob("*.whl"), *dist.glob("livingproof*.tar.gz"), *dist.glob("*.deb"),
               dist / "requirements.txt"]
with (dist / f"SHA256SUMS-{architecture}").open("w") as stream:
    for path in sorted(assets):
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        stream.write(f"{checksum}  {path.name}\n")
