"""Refuse to publish over any existing tag; fail closed on lookup errors."""
import json
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

repository = "living-proof-labs/livingproof-capability-report"
tag = sys.argv[1]
if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:amd64|arm64))?", tag):
    raise SystemExit("Expected a versioned reporting image tag")
with urlopen(f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repository}:pull") as response:
    token = json.load(response)["token"]
request = Request(f"https://ghcr.io/v2/{repository}/manifests/{tag}", headers={
    "Authorization": f"Bearer {token}",
    "Accept": ", ".join(["application/vnd.oci.image.index.v1+json",
                         "application/vnd.oci.image.manifest.v1+json",
                         "application/vnd.docker.distribution.manifest.list.v2+json",
                         "application/vnd.docker.distribution.manifest.v2+json"]),
})
try:
    with urlopen(request):
        raise SystemExit(f"Refusing to overwrite existing image tag: {tag}")
except HTTPError as error:
    if error.code != 404:
        raise
    body = json.load(error)
    if not any(e.get("code") == "MANIFEST_UNKNOWN" for e in body.get("errors", [])):
        raise SystemExit("Unexpected registry response; publication refused")
print(f"Confirmed absent image tag: {tag}")
