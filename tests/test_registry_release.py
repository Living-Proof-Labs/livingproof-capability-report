# SPDX-License-Identifier: Apache-2.0
"""Anonymous registry manifests become immutable release instructions."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/living-proof-labs/livingproof-capability-report"


def load():
    spec = importlib.util.spec_from_file_location(
        "registry_release", ROOT / "tools/registry_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


registry_release = load()


def manifest_body():
    body = json.dumps(
        {
            "manifests": [
                {"platform": {"os": "linux", "architecture": "arm64"}},
                {"platform": {"os": "linux", "architecture": "amd64"}},
            ]
        }
    ).encode()
    return body, "sha256:" + hashlib.sha256(body).hexdigest()


class Response:
    def __init__(self, payload, headers):
        self.payload = payload
        self.headers = headers

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(body, digest, seen):
    def urlopen(request, data=None, timeout=None):
        del data, timeout
        if isinstance(request, str):
            seen.append(request)
            parsed = urllib.parse.urlparse(request)
            query = urllib.parse.parse_qs(parsed.query)
            assert parsed.netloc == "ghcr.io"
            assert parsed.path == "/token"
            assert query["service"] == ["ghcr.io"]
            assert query["scope"] == [
                "repository:living-proof-labs/livingproof-capability-report:pull"
            ]
            return Response(b'{"token":"anonymous"}', {})
        seen.append(request.full_url)
        assert request.get_header("Authorization") == "Bearer anonymous"
        accept = request.get_header("Accept")
        assert "application/vnd.oci.image.index.v1+json" in accept
        assert "application/vnd.docker.distribution.manifest.list.v2+json" in accept
        assert request.full_url.endswith("/manifests/1.4.0")
        return Response(body, {"Docker-Content-Digest": digest})

    return urlopen


def test_resolve_accepts_an_anonymous_two_platform_manifest(monkeypatch):
    body, digest = manifest_body()
    seen = []
    monkeypatch.setattr(
        registry_release.urllib.request, "urlopen", fake_urlopen(body, digest, seen)
    )
    record = registry_release.resolve("1.4.0")
    assert seen[0].startswith("https://ghcr.io/token?")
    assert record == {
        "image": IMAGE,
        "version": "1.4.0",
        "manifest_digest": digest,
        "platforms": ["linux/amd64", "linux/arm64"],
        "manifests": json.loads(body)["manifests"],
    }


def test_resolve_rejects_a_digest_that_does_not_match_the_body(monkeypatch):
    body, _digest = manifest_body()
    monkeypatch.setattr(
        registry_release.urllib.request,
        "urlopen",
        fake_urlopen(body, "sha256:" + "ab" * 32, []),
    )
    with pytest.raises(ValueError, match="digest does not match"):
        registry_release.resolve("1.4.0")


def test_resolve_rejects_a_manifest_that_is_not_amd64_and_arm64(monkeypatch):
    body = json.dumps(
        {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}
    ).encode()
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(registry_release.urllib.request, "urlopen", fake_urlopen(body, digest, []))
    with pytest.raises(ValueError, match="Unexpected release platforms"):
        registry_release.resolve("1.4.0")


def test_notes_distinguish_the_manifest_digest_from_a_local_image_id():
    text = registry_release.notes(
        {
            "image": IMAGE,
            "version": "1.4.0",
            "manifest_digest": "sha256:" + "cd" * 32,
            "platforms": ["linux/amd64", "linux/arm64"],
        }
    )
    reference = f"{IMAGE}@sha256:{'cd' * 32}"
    assert "not a local image ID" in text
    assert f"docker pull {reference}" in text
    assert f"docker run --rm {reference} --version" in text
    assert "linux/amd64, linux/arm64" in text
    assert "docker save -o reporter-image.tar" in text
    assert "Routine releases do not attach" in text
    assert "image-amd64.tar" not in text


def test_notes_command_prints_the_same_instructions(tmp_path):
    record = {
        "image": IMAGE,
        "version": "1.4.0",
        "manifest_digest": "sha256:" + "ef" * 32,
        "platforms": ["linux/amd64", "linux/arm64"],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(record))
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/registry_release.py"), "notes", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == registry_release.notes(record) + "\n"
