"""Caller-authorized executable assets, kept separate from evaluator result data."""

from dataclasses import dataclass
import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlencode


# The one viewer frame a native panel holds: FRAME_START, the escaped src, FRAME_END. The
# site command's --validated-viewer-run matches exactly this markup and nothing looser.
FRAME_START = (
    '<iframe title="Recorded replay" sandbox="allow-scripts allow-same-origin" loading="lazy" src="'
)
FRAME_END = (
    '" style="display:block;width:100%;height:660px;border:1px solid #bcc;max-width:100%">'
    "</iframe><noscript>Replay needs JavaScript; Recorded data remains available.</noscript>"
)


@dataclass(frozen=True)
class TrustedViewer:
    evaluator_id: str
    evaluator_version: str
    evaluator_publisher: str
    viewer_href: str
    viewer_sha256: str
    recording_format: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.evaluator_id):
            raise ValueError("Trusted viewer requires a stable evaluator id")
        for value in (self.evaluator_version, self.evaluator_publisher, self.recording_format):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError("Trusted viewer identity and format must be bounded strings")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.html", self.viewer_href):
            raise ValueError("Trusted viewer href must be a local HTML asset path")
        if not re.fullmatch(r"[a-f0-9]{64}", self.viewer_sha256):
            raise ValueError("Trusted viewer requires exact asset SHA-256")


def _read(root, relative, limit):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("Trusted viewer inputs must be local paths")
    root = Path(root)
    current = root
    if root.is_symlink():
        raise ValueError("Asset root cannot be a symlink")
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Trusted viewer inputs cannot contain symlinks")
    if not current.is_file() or current.stat().st_size > limit:
        raise ValueError("Missing or oversized trusted viewer input")
    with current.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Trusted viewer input exceeds size limit")
    return raw


def _index(value):
    return type(value) is int and value > 0


def viewer_panels(items, report, asset_root):
    """Validate local bytes and report identity before producing any HTML."""
    from .evaluators import advisory_documents

    if items is None:
        return {}
    if not isinstance(items, (list, tuple)) or len(items) > 16:
        raise ValueError("trusted_viewers must be a list or tuple of at most 16 typed inputs")
    if items and asset_root is None:
        raise ValueError("Trusted viewers require an explicit local asset_root")
    panels = {}
    seen = set()
    documents = advisory_documents(report)
    for item in items:
        if not isinstance(item, TrustedViewer):
            raise ValueError("Use TrustedViewer for caller inputs, never evaluator HTML")
        item.__post_init__()
        if item.evaluator_id in seen:
            raise ValueError("Duplicate trusted viewer evaluator")
        seen.add(item.evaluator_id)
        matches = [d for d in documents if d["evaluator"]["id"] == item.evaluator_id]
        if not matches:
            continue
        if len(matches) != 1:
            raise ValueError("Trusted viewer requires one unambiguous advisory result")
        document = matches[0]
        identity = document["evaluator"]
        if (
            identity.get("version") != item.evaluator_version
            or identity.get("publisher") != item.evaluator_publisher
            or identity.get("kind") != "advisory"
        ):
            raise ValueError("Trusted viewer evaluator identity mismatch")
        advisory = document["advisory"]
        trials = advisory.get("trials", [])
        if len(trials) != 1 or not _index(trials[0].get("index")):
            raise ValueError("Trusted viewer requires one positive integer trial index")
        trial = trials[0]
        results = [
            r
            for r in report["source_bundle"]["results"]
            if trial["observation_sha256"] in {e["sha256"] for e in r.get("evidence", [])}
        ]
        if len(results) != 1:
            raise ValueError("Trusted viewer requires one observation-bound result")
        result = results[0]
        selected = dict(
            run_id=result["provenance"]["run_id"],
            configuration=result["system"]["id"].rsplit("/", 1)[-1],
            index=trial["index"],
            observation_sha256=trial["observation_sha256"],
        )
        details = advisory["details_file"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.json", details["uri"]):
            raise ValueError("Recording must be a local JSON basename")
        raw = _read(asset_root, details["uri"], 16 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != details["sha256"]:
            raise ValueError("Recording digest differs from report")
        data = json.loads(raw)
        recorded = data.get("trials") if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or data.get("format") != item.recording_format
            or not isinstance(recorded, list)
            or len(recorded) != 1
            or not isinstance(recorded[0], dict)
            or recorded[0].get("format") != item.recording_format
            or not isinstance(recorded[0].get("trial"), dict)
            or not _index(recorded[0]["trial"].get("index"))
            or recorded[0]["trial"] != selected
        ):
            raise ValueError("Recording format or exact selected trial identity mismatch")
        viewer = _read(asset_root, item.viewer_href, 1024 * 1024)
        if hashlib.sha256(viewer).hexdigest() != item.viewer_sha256:
            raise ValueError("Trusted viewer asset digest mismatch")
        adjacent = str(PurePosixPath(item.viewer_href).parent / "data/recording.json")
        if _read(asset_root, adjacent, 16 * 1024 * 1024) != raw:
            raise ValueError("Viewer data copy differs from report recording")
        fragment = urlencode(
            dict(
                file="data/recording.json",
                sha256=details["sha256"],
                run=selected["run_id"],
                configuration=selected["configuration"],
                trial=selected["index"],
            )
        )
        src = escape(item.viewer_href + "#" + fragment, quote=True)
        panels[item.evaluator_id] = FRAME_START + src + FRAME_END
    return panels
