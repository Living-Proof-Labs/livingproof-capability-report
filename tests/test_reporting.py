import copy
import hashlib
import json

import pytest
from click.testing import CliRunner

from livingproof_capability_report import aggregate, load_bundle, render
from livingproof_capability_report.cli import report
from livingproof_capability_report.core import decode, validate_bundle
from test_hallway import example, stored

PAUSE = (
    "https://github.com/Living-Proof-Labs/robot-capability-specs",
    "e8ff8b45d76c6c0c0c3f7a0c2f62e1c0d1f2a3b4",
)
MEMBERS = {"pause-rules": "deterministic", "pause-review": "mock-agent"}


@pytest.fixture
def bundle(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"elapsed_ms":120}')
    result = {
        "id": "pause-120",
        "spec": {
            "repository": PAUSE[0],
            "tag": "v1.1.1",
            "commit": PAUSE[1],
            "capability": "pause",
            "revision": "1.0.0",
        },
        "system": {"id": "fixtures", "version": "1.0.0"},
        "environment": {"id": "deterministic-fixture", "version": "1.0.0"},
        "evidence": [
            {
                "id": "observation",
                "path": "evidence.json",
                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
        ],
        "assessments": [
            {
                "id": name,
                "evaluator": name,
                "kind": kind,
                "version": "1.0.0",
                "status": "PASS",
                "rationale": "<script>alert(1)</script>",
                "mandatory": name == "pause-rules",
                "evidence_ids": ["observation"],
                "provenance": {
                    "label": "MOCK; no model" if kind == "mock-agent" else "recorded fixture"
                },
            }
            for name, kind in MEMBERS.items()
        ],
        "provenance": {"simulator": None},
        "original_result": {"status": "PASS"},
    }
    value = {
        "schema_version": "1.0.0",
        "producer": {"id": "test", "version": "1.0.0", "commit": "b" * 40},
        "results": [result],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))
    return manifest


def test_lossless_nonmutating_and_escaped(tmp_path):
    loaded = load_bundle(example(tmp_path))
    before = copy.deepcopy(loaded)
    result = stored(example(tmp_path / "again"))
    result["decisions"][0]["reason"] = "<script>alert(1)</script>"
    assert decode(render(result)) == result
    assert loaded == before
    assert "&lt;script&gt;" in render(result, "html")
    assert "<script>" not in render(result, "html")


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        "https://example.org",
        "a\\b",
        "a/../b",
        "a//b",
        "./evidence.json",
    ],
)
def test_unsafe_paths(bundle, path):
    value = decode(bundle.read_text())
    value["results"][0]["evidence"][0]["path"] = path
    with pytest.raises(ValueError):
        validate_bundle(value)


def test_symlinks(bundle):
    path = bundle.parent / "evidence.json"
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="Symlink"):
        load_bundle(bundle)


def test_grouping_and_render_never_regrade(bundle, tmp_path):
    loaded = load_bundle(bundle)
    result = loaded["bundle"]["results"][0]
    other = copy.deepcopy(result)
    other["id"] = "strict"
    other["spec"]["revision"] = "2.0.0"
    assert len(aggregate([result, other])) == 2
    other["spec"] = result["spec"]
    other["environment"]["version"] = "2.0.0"
    assert len(aggregate([result, other])) == 2
    saved = stored(example(tmp_path))
    saved["policy"] = "retired-policy@0.1.0"
    assert "PASS" in render(saved, "html")


def test_cli_and_no_overwrite(bundle, tmp_path):
    runner = CliRunner()
    assert runner.invoke(report, ["validate", str(bundle)]).exit_code == 0
    manifest = example(tmp_path)
    output = manifest.parent / "report.json"
    assert (
        runner.invoke(
            report, ["render", str(manifest), "--format", "json", "-o", str(output)]
        ).exit_code
        == 0
    )
    assert runner.invoke(report, ["render", str(manifest), "-o", str(manifest)]).exit_code != 0
    assert (
        runner.invoke(
            report,
            ["render", str(output), "--format", "html", "-o", str(manifest.parent / "report.html")],
        ).exit_code
        == 0
    )


def test_reject_bad_json_and_csv_formula(tmp_path):
    for value in ['{"a":1,"a":2}', '{"a": NaN}']:
        with pytest.raises(ValueError):
            decode(value)
    saved = stored(example(tmp_path))
    saved["decisions"][0]["reason"] = " =1+1"
    assert "' =1+1" in render(saved, "csv")
