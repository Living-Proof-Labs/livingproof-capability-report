"""Exercise clean wheel, Debian and image installs with no source checkout."""
import os
import subprocess
from pathlib import Path

network = ["--network", os.environ["PACKAGE_NETWORK"]] if "PACKAGE_NETWORK" in os.environ else []
trust = (["-v", f"{os.environ['PACKAGE_CA_BUNDLE']}:/tmp/package-ca.pem:ro",
          "-e", "PIP_CERT=/tmp/package-ca.pem"] if "PACKAGE_CA_BUNDLE" in os.environ else [])
root = Path(__file__).resolve().parents[1]
version = os.environ.get("VERSION", "0.0.0")
image = f"ghcr.io/living-proof-labs/livingproof-capability-report:{version}"
dist = root / "dist"
bundle = root / "examples/bundle"
# Normal Docker entrypoint receives only subcommands/options.
subprocess.run(["docker", "run", *network, *trust, "--rm", image, "--help"], check=True)
subprocess.run(["docker", "run", *network, *trust, "--rm", "-v", f"{bundle}:/input:ro", image,
                "validate", "/input/manifest.json"], check=True)
# Job containers may override ENTRYPOINT and invoke a shell; test separately.
exercise = """set -eu
livingproof-capability-report grade /input/manifest.json -o /tmp/report.json
livingproof-capability-report render /tmp/report.json --format html -o /tmp/report.html
livingproof-capability-report render /tmp/report.json --format csv -o /tmp/report.csv
python -c 'import json; r=json.load(open("/tmp/report.json")); s={d["result_id"]:d["status"] for d in r["decisions"]}; assert s["v1.1.1-slow"]=="PASS"; assert s["v1.2.0-slow"]=="FAIL"; assert s["v1.2.0-insufficient"]=="INSUFFICIENT_EVIDENCE"'
"""
subprocess.run(["docker", "run", *network, *trust, "--rm", "--entrypoint", "/bin/sh", "-v",
                f"{bundle}:/input:ro", image, "-c", exercise], check=True)
wheel = """set -eu
python -m venv /tmp/clean
/tmp/clean/bin/pip install --no-index --find-links=/packages/wheels livingproof-capability-report=="$1"
export PATH=/tmp/clean/bin:$PATH
cd /tmp
""" + exercise
subprocess.run(["docker", "run", *network, *trust, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                f"{bundle}:/input:ro", "python:3.12.12-slim-bookworm", "sh", "-c",
                wheel, "smoke", version], check=True)
source = """set -eu
python -m venv /tmp/from-source
/tmp/from-source/bin/pip install --find-links=/packages/wheels /packages/livingproof_capability_report-*.tar.gz
cd /tmp
/tmp/from-source/bin/livingproof-capability-report validate /input/manifest.json
"""
subprocess.run(["docker", "run", *network, *trust, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                f"{bundle}:/input:ro", "python:3.12.12-slim-bookworm", "sh", "-c", source],
               check=True)
debian = """set -eu
apt-get update -qq
apt-get install -y /packages/livingproof-capability-report_*_amd64.deb
cd /tmp
livingproof-capability-report validate /input/manifest.json
livingproof-capability-report grade /input/manifest.json -o /tmp/report.json
livingproof-capability-report render /tmp/report.json --format html -o /tmp/report.html
/usr/bin/python3 -c 'import importlib.util; assert importlib.util.find_spec("livingproof_capability_report") is None'
/opt/livingproof-capability-report/bin/python -c 'from livingproof_capability_report import grade; print(grade.__module__)'
"""
subprocess.run(["docker", "run", *network, *trust, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                f"{bundle}:/input:ro", "ubuntu:24.04", "sh", "-c", debian], check=True)
