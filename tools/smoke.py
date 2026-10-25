"""Exercise clean wheel, Debian and image installs with no source checkout."""
import os
import platform
import subprocess
from pathlib import Path

network = ["--network", os.environ["PACKAGE_NETWORK"]] if "PACKAGE_NETWORK" in os.environ else []
trust = (["-v", f"{os.environ['PACKAGE_CA_BUNDLE']}:/tmp/package-ca.pem:ro",
          "-e", "PIP_CERT=/tmp/package-ca.pem"] if "PACKAGE_CA_BUNDLE" in os.environ else [])
architecture = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
root = Path(__file__).resolve().parents[1]
version = os.environ.get("VERSION", "0.0.0")
image = f"ghcr.io/living-proof-labs/livingproof-capability-report:{version}-{architecture}"
dist = root / "dist"
bundle = root / "examples/bundle"
records = dist / "compatibility"
records.mkdir(exist_ok=True)
evidence = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            if "GITHUB_RUN_ID" in os.environ else "local execution")
probe = ["-v", f"{records}:/results", "-v", f"{root}/tools/record_compatibility.py:/probe.py:ro",
         "-e", f"COMPATIBILITY_HOST_MACHINE={platform.machine()}",
         "-e", f"COMPATIBILITY_RUNNER={os.environ.get('RUNNER_LABEL', 'local')}",
         "-e", f"COMPATIBILITY_EVIDENCE={evidence}"]
# Normal Docker entrypoint receives only subcommands/options.
subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", image, "--help"], check=True)
subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", "-v", f"{bundle}:/input:ro", image,
                "validate", "/input/manifest.json"], check=True)
# Job containers may override ENTRYPOINT and invoke a shell; test separately.
exercise = """set -eu
livingproof-capability-report grade /input/manifest.json -o /tmp/report.json
livingproof-capability-report render /tmp/report.json > /tmp/table.txt
grep -q "Separate contexts" /tmp/table.txt
livingproof-capability-report render /tmp/report.json --format html -o /tmp/report.html
livingproof-capability-report render /tmp/report.json --format csv -o /tmp/report.csv
python -c 'import json; r=json.load(open("/tmp/report.json")); s={d["result_id"]:d["status"] for d in r["decisions"]}; assert s["v1.1.1-slow"]=="PASS"; assert s["v1.2.0-slow"]=="FAIL"; assert s["v1.2.0-insufficient"]=="INSUFFICIENT_EVIDENCE"'
"""
subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", "--entrypoint", "/bin/sh", "-v",
                f"{bundle}:/input:ro", image, "-c", exercise + "python /probe.py /results/image.json installed-image\n"], check=True)
wheel = """set -eu
python -m venv /tmp/clean
/tmp/clean/bin/pip install --no-index --find-links=/packages/wheels livingproof-capability-report=="$1"
export PATH=/tmp/clean/bin:$PATH
cd /tmp
""" + exercise + "python /probe.py /results/wheel.json wheel\n"
subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                f"{bundle}:/input:ro", "python:3.12.12-slim-bookworm", "sh", "-c",
                wheel, "smoke", version], check=True)
source = """set -eu
python -m venv /tmp/from-source
/tmp/from-source/bin/pip install --find-links=/packages/wheels /packages/livingproof_capability_report-*.tar.gz
cd /tmp
/tmp/from-source/bin/livingproof-capability-report validate /input/manifest.json
/tmp/from-source/bin/python /probe.py /results/source.json source-distribution
"""
subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                f"{bundle}:/input:ro", "python:3.12.12-slim-bookworm", "sh", "-c", source],
               check=True)
debian = """set -eu
apt-get update -qq
apt-get install -y /packages/livingproof-capability-report_*_all.deb
cd /tmp
livingproof-capability-report validate /input/manifest.json
livingproof-capability-report grade /input/manifest.json -o /tmp/report.json
livingproof-capability-report render /tmp/report.json > /tmp/table.txt
grep -q "Separate contexts" /tmp/table.txt
livingproof-capability-report render /tmp/report.json --format html -o /tmp/report.html
/usr/bin/python3 -c 'from livingproof_capability_report import grade; print(grade.__module__)'
test ! -d /opt/livingproof-capability-report
/usr/bin/python3 -c 'import click, jsonschema; print(click.__file__, jsonschema.__file__)'
dpkg-query -W -f='${Architecture} ${Version}\\n' livingproof-capability-report python3 python3-click python3-jsonschema
livingproof-capability-report --version
python3 /probe.py /tmp/compatibility.json distribution-managed-deb
apt-get remove -y livingproof-capability-report
/usr/bin/python3 -c 'import importlib.util; assert importlib.util.find_spec("livingproof_capability_report") is None; import click, jsonschema'
cp /tmp/compatibility.json /results/"$1".json
"""
for distribution in ("ubuntu:24.04", "debian:12-slim", "debian:13-slim"):
    print(f"Clean native {architecture} installation on {distribution}", flush=True)
    subprocess.run(["docker", "run", *network, *trust, *probe, "--rm", "-v", f"{dist}:/packages:ro", "-v",
                    f"{bundle}:/input:ro", distribution, "sh", "-c", debian, "smoke",
                    distribution.replace(":", "-")], check=True)
