import copy
import hashlib
import json

import pytest
from click.testing import CliRunner

from livingproof_capability_report import aggregate, grade, load_bundle, render
from livingproof_capability_report.cli import report
from livingproof_capability_report.core import CONTRACTS, MEMBERS, decode, digest, validate_bundle


@pytest.fixture
def bundle(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"elapsed_ms":120}')
    result = {
        "id": "pause-120", "spec": {"repository": CONTRACTS[0][0],
        "tag": "v1.1.1", "commit": CONTRACTS[0][2], "capability": "pause", "revision": "1.0.0"},
        "system": {"id": "fixtures", "version": "1.0.0"},
        "environment": {"id": "deterministic-fixture", "version": "1.0.0"},
        "evidence": [{"id": "observation", "path": "evidence.json",
                      "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}],
        "assessments": [{"id": name, "evaluator": name, "kind": kind, "version": "1.0.0",
                         "status": "PASS", "rationale": "<script>alert(1)</script>",
                         "mandatory": name == "pause-rules", "evidence_ids": ["observation"],
                         "provenance": {"label": "MOCK; no model" if kind == "mock-agent"
                                        else "recorded fixture"}}
                        for name, kind in MEMBERS.items()],
        "provenance": {"simulator": None}, "original_result": {"status": "PASS"}}
    value = {"schema_version": "1.0.0", "producer": {"id": "test", "version": "1.0.0",
             "commit": "b" * 40}, "results": [result]}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))
    return manifest


def test_lossless_and_nonmutating(bundle):
    loaded = load_bundle(bundle)
    before = copy.deepcopy(loaded)
    result = grade(loaded)
    assert result["decisions"][0]["status"] == "PASS"
    assert decode(render(result)) == result
    assert loaded == before
    assert "&lt;script&gt;" in render(result, "html")
    assert "<script>" not in render(result, "html")
    assert "INCOMPATIBLE" == grade(loaded, "future@2")["decisions"][0]["status"]


@pytest.mark.parametrize("mutation,expected", [
    ("fail", "FAIL"), ("missing", "INSUFFICIENT_EVIDENCE"),
    ("duplicate", "INSUFFICIENT_EVIDENCE"), ("version", "INCOMPATIBLE"),
    ("kind", "INCOMPATIBLE"), ("no_refs", "INSUFFICIENT_EVIDENCE"),
])
def test_policy(bundle, mutation, expected):
    loaded = load_bundle(bundle)
    assessments = loaded["bundle"]["results"][0]["assessments"]
    if mutation == "fail":
        assessments[0]["status"] = "FAIL"
        loaded["evidence_state"] = {}  # Known mandatory failure still wins.
    elif mutation == "missing":
        assessments.pop()
    elif mutation == "duplicate":
        duplicate = copy.deepcopy(assessments[-1])
        duplicate["id"] = "another"
        assessments.append(duplicate)
    elif mutation == "version":
        assessments[0]["version"] = "9.0.0"
    elif mutation == "kind":
        assessments[0]["kind"] = "human"
    else:
        assessments[0]["evidence_ids"] = []
    assert grade(loaded)["decisions"][0]["status"] == expected


def test_missing_and_tampered_evidence(bundle):
    evidence = bundle.parent / "evidence.json"
    evidence.write_text("changed")
    assert grade(load_bundle(bundle))["decisions"][0]["status"] == "INSUFFICIENT_EVIDENCE"
    evidence.unlink()
    assert grade(load_bundle(bundle))["decisions"][0]["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "https://example.org", "a\\b",
                                   "a/../b", "a//b", "./evidence.json"])
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


def test_human_addition_keeps_original(bundle):
    loaded = load_bundle(bundle)
    original = loaded["bundle"]["results"][0]
    human = original["assessments"].pop()
    contributions = {"schema_version": "1.0.0", "assessments": [{"result_id": original["id"],
                     "result_sha256": digest(original), "assessment": human}]}
    result = grade(loaded, human=contributions)
    assert result["decisions"][0]["status"] == "PASS"
    assert len(result["source_bundle"]["results"][0]["assessments"]) == 2
    assert result["human_contributions"] == contributions
    contributions["assessments"][0]["result_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        grade(loaded, human=contributions)


def test_grouping_and_render_never_regrade(bundle, monkeypatch):
    loaded = load_bundle(bundle)
    result = loaded["bundle"]["results"][0]
    other = copy.deepcopy(result)
    other["id"] = "strict"
    other["spec"]["revision"] = "2.0.0"
    assert len(aggregate([result, other])) == 2
    other["spec"] = result["spec"]
    other["environment"]["version"] = "2.0.0"
    assert len(aggregate([result, other])) == 2
    saved = grade(loaded)
    saved["policy"] = "retired-policy@0.1.0"
    monkeypatch.setattr("livingproof_capability_report.core.grade", lambda *a: pytest.fail())
    assert "PASS" in render(saved, "html")


def test_cli_and_no_overwrite(bundle):
    runner = CliRunner()
    output = bundle.parent / "report.json"
    assert runner.invoke(report, ["validate", str(bundle)]).exit_code == 0
    assert runner.invoke(report, ["grade", str(bundle), "-o", str(output)]).exit_code == 0
    assert runner.invoke(report, ["grade", str(bundle), "-o", str(bundle)]).exit_code != 0
    assert runner.invoke(report, ["render", str(output), "--format", "html", "-o",
                                 str(bundle.parent / "report.html")]).exit_code == 0


def test_reject_bad_json_and_csv_formula(bundle):
    for value in ['{"a":1,"a":2}', '{"a": NaN}']:
        with pytest.raises(ValueError):
            decode(value)
    saved = grade(load_bundle(bundle))
    saved["decisions"][0]["reason"] = " =1+1"
    assert "' =1+1" in render(saved, "csv")
