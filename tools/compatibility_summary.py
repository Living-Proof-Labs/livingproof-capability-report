"""Generate compatibility JSON/Markdown and checksums from actual runtime records."""
import hashlib
import json
import platform
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "dist"
architecture = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
expected = ["image", "wheel", "source", "ubuntu-24.04", "debian-12-slim", "debian-13-slim"]
records = []
for name in expected:
    path = root / "compatibility" / (name + ".json")
    records.append(json.loads(path.read_text()) if path.exists()
                   else {"probe": name, "outcome": "NOT_COMPLETED"})
report = {"schema_version": "1.0.0", "host_architecture": architecture, "records": records}
root.mkdir(exist_ok=True)
json_path = root / f"compatibility-{architecture}.json"
json_path.write_text(json.dumps(report, indent=2) + "\n")
lines = [f"## Compatibility results: {architecture}", "",
         "Generated from clean-install probes. Missing probes are not passing results.", "",
         "| Actual OS/version | CPU | Python | Install method | Execution | Outcome | Evidence |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
for r in records:
    values = [r.get("os", r.get("probe", "unknown")), r.get("architecture", "unknown"),
              r.get("python", "unknown"), r.get("install_method", "unknown"),
              r.get("execution", "unknown"), r["outcome"], r.get("evidence", "not run")]
    lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ")
                                   for v in values) + " |")
markdown = "\n".join(lines) + "\n"
(root / f"compatibility-{architecture}.md").write_text(markdown)
print(markdown)
# Only list files that will be attached to the public release from this native job.
assets = [root / f"image-{architecture}.tar", root / f"wheelhouse-{architecture}.tar.gz",
          json_path, root / f"compatibility-{architecture}.md"]
if architecture == "amd64":
    assets += [*root.glob("*.whl"), *root.glob("livingproof*.tar.gz"), *root.glob("*.deb"),
               root / "requirements.txt"]
with (root / f"SHA256SUMS-{architecture}").open("w") as stream:
    for path in sorted(assets):
        if path.is_file():
            with path.open("rb") as source:
                checksum = hashlib.file_digest(source, "sha256").hexdigest()
            stream.write(f"{checksum}  {path.name}\n")
