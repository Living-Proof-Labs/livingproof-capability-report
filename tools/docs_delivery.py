"""Check the reporter documentation's exact published wheel and sealed identity."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RELEASED = ROOT / "artifacts/docs-released-wheel"
STABLE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
PREVIEW = rf"({STABLE})-pr\.[1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def edition(version, package_version, tag):
    if not (version or package_version or tag):
        return "development"
    if (
        tag
        and re.fullmatch(STABLE, version)
        and tag == f"v{version}"
        and package_version == version
    ):
        return "release"
    candidate = re.fullmatch(PREVIEW, version)
    if (
        not tag
        and candidate
        and re.fullmatch(re.escape(candidate[1]) + r"\.dev[1-9][0-9]*", package_version)
    ):
        return "preview"
    raise ValueError("Expected matching stable release or planned preview documentation versions")


def release_assets(record, tag, version):
    if (
        edition(version, version, tag) != "release"
        or record.get("tag_name") != tag
        or record.get("draft") is not False
        or record.get("prerelease") is not False
        or record.get("immutable") is not True
        or not isinstance(record.get("published_at"), str)
        or not record["published_at"]
    ):
        raise ValueError("Expected the exact immutable published stable reporter release")
    name = f"livingproof_capability_report-{version}-py3-none-any.whl"
    uploaded = [asset for asset in record.get("assets", []) if asset["state"] == "uploaded"]
    digests = {}
    for required in (name, "SHA256SUMS"):
        matches = [asset.get("digest") for asset in uploaded if asset["name"] == required]
        if len(matches) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", matches[0] or ""):
            raise ValueError("Missing or ambiguous published wheel or checksum manifest digest")
        digests[required] = matches[0]
    return name, digests


def released_wheel(directory, tag, version, commit):
    name, assets = release_assets(
        json.loads((directory / "release.json").read_text()), tag, version
    )
    wheel = directory / name
    checksums = directory / "SHA256SUMS"
    actual = digest(wheel)
    if (
        assets[name] != f"sha256:{actual}"
        or assets["SHA256SUMS"] != f"sha256:{digest(checksums)}"
        or checksums.read_text().splitlines().count(f"{actual}  {name}") != 1
    ):
        raise ValueError("Published wheel bytes disagree with release and checksum manifest")
    member = "livingproof_capability_report/_build_provenance.json"
    with ZipFile(wheel) as archive:
        if archive.namelist().count(member) != 1:
            raise ValueError("Expected one provenance record in the released wheel")
        provenance = json.loads(archive.read(member))
    identity = provenance["identity"]
    if not (
        provenance["distribution"] == "livingproof-capability-report"
        and provenance["package_version"] == version
        and identity["commit"] == commit
        and identity["base_version"] == version
        and identity["distance"] == 0
        and identity["state"] == "clean"
        and identity["history"] == "tagged"
    ):
        raise ValueError("Released wheel does not record the exact clean stable tag")
    return wheel


def require_manifest(record):
    expected = {
        "source_commit": os.environ["PLAN_COMMIT"],
        "source_dirty": False,
        "edition": "release",
        "version": os.environ["MANUAL_VERSION"],
        "package_version": os.environ["MANUAL_PACKAGE_VERSION"],
        "release_tag": os.environ["MANUAL_RELEASE_TAG"],
        "run_id": os.environ["PLAN_RUN"],
        "run_attempt": os.environ["PLAN_ATTEMPT"],
    }
    if any(record.get(key) != value for key, value in expected.items()) or not re.fullmatch(
        r"[0-9a-f]{64}", record.get("wheel_sha256", "")
    ):
        raise ValueError("Manual is not the exact released wheel, source and same-run build")


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "released":
        release_assets(json.loads((RELEASED / "release.json").read_text()), *args)
    elif mode == "seal":
        require_manifest(json.loads(Path(args[0]).read_text()))
    else:
        raise SystemExit("Expected released or seal")
