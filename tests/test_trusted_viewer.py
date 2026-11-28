"""Caller-only inline viewer rendering; evaluator payloads remain data."""

import copy
from dataclasses import asdict, replace
import hashlib
import json

import pytest
from click.testing import CliRunner
from livingproof_capability_report import TrustedViewer, render
from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.trusted_viewer import viewer_panels
from test_advisory import load_advisory, with_advisory
from test_sections import bundle


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def case(tmp_path):
    data = bundle("g1")
    all_hashes = [e["sha256"] for r in data["results"] for e in r["evidence"]]
    result, evidence = next(
        (r, e) for r in data["results"] for e in r["evidence"] if all_hashes.count(e["sha256"]) == 1
    )
    selected = dict(
        run_id=result["provenance"]["run_id"],
        configuration=result["system"]["id"].rsplit("/", 1)[-1],
        index=1,
        observation_sha256=evidence["sha256"],
    )
    recording = {
        "format": "example-recording/1",
        "trials": [{"format": "example-recording/1", "trial": selected}],
    }
    raw = json.dumps(recording).encode()
    doc = load_advisory("battery-thermal")
    doc["advisory"]["trials"] = [dict(index=1, observation_sha256=evidence["sha256"])]
    doc["advisory"]["details_file"] = dict(uri="recording.json", sha256=sha(raw))
    stored = with_advisory(data, {"battery-thermal": doc})
    asset = b"<!doctype html><p>Trusted generic fixture viewer</p>"
    (tmp_path / "viewer/data").mkdir(parents=True)
    (tmp_path / "viewer/viewer.html").write_bytes(asset)
    (tmp_path / "recording.json").write_bytes(raw)
    (tmp_path / "viewer/data/recording.json").write_bytes(raw)
    pin = TrustedViewer(
        "battery-thermal",
        "0.1.0",
        "Living Proof Labs",
        "viewer/viewer.html",
        sha(asset),
        "example-recording/1",
    )
    return tmp_path, stored, pin


def test_optional_native_card_no_grade_or_portable_changes(case):
    root, stored, pin = case
    original = copy.deepcopy(stored)
    baseline = render(stored, "html")
    assert render(stored, "html", trusted_viewers=[], asset_root=root) == baseline
    page = render(stored, "html", trusted_viewers=[pin], asset_root=root)
    assert page.count("<iframe ") == 1
    assert "Recorded data</a>" in page and "<noscript>" in page
    assert page.index("<iframe ") > page.index("id='evaluator-battery-thermal'")
    assert 'sandbox="allow-scripts allow-same-origin"' in page
    assert stored == original
    assert render(stored) == render(original)
    assert (
        render(
            stored, "html", trusted_viewers=[replace(pin, evaluator_id="absent")], asset_root=root
        )
        == baseline
    )


@pytest.mark.parametrize(
    "fault",
    ["viewer", "data", "copy", "format", "empty", "duplicate", "run", "index", "observation"],
)
def test_invalid_bytes_or_trial_refuse_before_html(case, fault):
    root, stored, pin = case
    if fault in ("viewer", "data", "copy"):
        target = {
            "viewer": "viewer/viewer.html",
            "data": "recording.json",
            "copy": "viewer/data/recording.json",
        }[fault]
        (root / target).write_bytes(b"tampered")
    else:
        data = json.loads((root / "recording.json").read_bytes())
        if fault == "format":
            data["format"] = "other"
        if fault == "empty":
            data["trials"] = []
        if fault == "duplicate":
            data["trials"] *= 2
        if fault == "run":
            data["trials"][0]["trial"]["run_id"] = "other"
        if fault == "index":
            data["trials"][0]["trial"]["index"] = True
        if fault == "observation":
            data["trials"][0]["trial"]["observation_sha256"] = "0" * 64
        raw = json.dumps(data).encode()
        (root / "recording.json").write_bytes(raw)
        (root / "viewer/data/recording.json").write_bytes(raw)
        stored["source_bundle"]["assessment"]["advisory_results"]["battery-thermal"]["advisory"][
            "details_file"
        ]["sha256"] = sha(raw)
    with pytest.raises(ValueError):
        viewer_panels([pin], stored, root)


@pytest.mark.parametrize(
    "href", ["https://example.com/x.html", "../x.html", "x.html#bad", "x.html?bad", "/x.html"]
)
def test_executable_paths_are_caller_local(case, href):
    _, _, pin = case
    with pytest.raises(ValueError):
        replace(pin, viewer_href=href)


def test_actual_cli_keeps_raw_fallback_and_refuses_without_output(case):
    root, stored, pin = case
    report_file = root / "report.json"
    report_file.write_text(json.dumps(stored))
    pins = root / "pins.json"
    pins.write_text(json.dumps([asdict(pin)]))
    args = [
        "render",
        str(report_file),
        "--format",
        "html",
        "--trusted-viewers",
        str(pins),
        "--asset-root",
        str(root),
    ]
    runner = CliRunner()
    out = root / "page.html"
    result = runner.invoke(cli, args + ["-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "<iframe " in out.read_text() and "Recorded data</a>" in out.read_text()
    (root / "recording.json").write_text("bad")
    refused = root / "refused.html"
    result = runner.invoke(cli, args + ["-o", str(refused)])
    assert result.exit_code != 0
    assert not refused.exists()


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1"])
@pytest.mark.parametrize("side", ["report", "recording"])
def test_trial_indices_require_positive_integer(case, value, side):
    root, stored, pin = case
    doc = stored["source_bundle"]["assessment"]["advisory_results"]["battery-thermal"]
    if side == "report":
        doc["advisory"]["trials"][0]["index"] = value
    else:
        data = json.loads((root / "recording.json").read_bytes())
        data["trials"][0]["trial"]["index"] = value
        raw = json.dumps(data).encode()
        (root / "recording.json").write_bytes(raw)
        (root / "viewer/data/recording.json").write_bytes(raw)
        doc["advisory"]["details_file"]["sha256"] = sha(raw)
    with pytest.raises(ValueError):
        viewer_panels([pin], stored, root)


def test_missing_or_symlink_asset_refused(case):
    root, stored, pin = case
    path = root / "viewer/viewer.html"
    raw = path.read_bytes()
    path.unlink()
    with pytest.raises(ValueError):
        viewer_panels([pin], stored, root)
    (root / "other.html").write_bytes(raw)
    path.symlink_to(root / "other.html")
    with pytest.raises(ValueError):
        viewer_panels([pin], stored, root)
