"""Policy and revision behavior through public API and installed CLI entry point."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess

import pytest

from livingproof_capability_report import grade, load_bundle, render
from livingproof_capability_report.core import digest
from livingproof_capability_report.policy import POLICY_V2


@pytest.fixture
def loaded():
    source = Path(__file__).parents[1] / "examples/bundle/manifest.json"
    loaded = load_bundle(source)
    loaded["bundle"]["results"] = [loaded["bundle"]["results"][0]]
    return loaded


def contribution(loaded, identifier="review-1", status="PASS"):
    result = loaded["bundle"]["results"][0]
    return {"schema_version": "1.0.0", "assessments": [{
        "result_id": result["id"], "result_sha256": digest(result), "assessment": {
            "id": identifier, "evaluator": "human-review", "kind": "human",
            "version": "1.0.0", "status": status, "mandatory": False,
            "rationale": "Reviewed observation; self-declared identity",
            "evidence_ids": [result["evidence"][0]["id"]],
            "provenance": {"reviewer": "Fixture reviewer", "recorded_at": "2026-10-26"}}}]}


def test_human_revision_retains_history_and_dissent(loaded):
    before = copy.deepcopy(loaded)
    first = grade(loaded, POLICY_V2)
    second = grade(loaded, POLICY_V2, contribution(loaded, status="FAIL"), first)
    third = grade(loaded, POLICY_V2, contribution(loaded, "review-2"), second)
    assert loaded == before
    assert first["decisions"][0]["status"] == "PASS"
    assert second["decisions"][0]["status"] == third["decisions"][0]["status"] == "FAIL"
    assert third["grade_revision"] == 3
    assert third["previous_report"] == second
    assert second["previous_report_sha256"] == digest(first)
    assert third["decisions"][0]["dissent"] is True
    assert len(third["human_contributions"]["assessments"]) == 2
    assert json.loads(render(third)) == third
    for format in ("table", "html", "csv"):
        assert "review-1" in render(third, format)
        assert "Reviewed observation" in render(third, format)
    rows = list(csv.DictReader(io.StringIO(render(third, "csv"))))
    assert rows[0]["grade_revision"] == "3"


def test_v1_unchanged_and_legacy_revision(loaded):
    first = grade(loaded)
    assert "grade_revision" not in first
    assert "assessment_details" not in first["decisions"][0]
    assert grade(loaded, POLICY_V2, contribution(loaded), first)["grade_revision"] == 2
    assert grade(loaded, human=contribution(loaded))["decisions"][0]["status"] == "INCOMPATIBLE"


@pytest.mark.parametrize("mutation, expected", [
    ("mandatory-fail", "FAIL"), ("missing-human", "INSUFFICIENT_EVIDENCE"),
    ("incompatible", "INCOMPATIBLE"), ("missing-evidence", "INSUFFICIENT_EVIDENCE"),
    ("no-mandatory", "INSUFFICIENT_EVIDENCE"), ("no-refs", "INSUFFICIENT_EVIDENCE"),
    ("insufficient", "INSUFFICIENT_EVIDENCE"),
])
def test_policy_reasons(loaded, mutation, expected):
    result = loaded["bundle"]["results"][0]
    if mutation == "mandatory-fail":
        result["assessments"][0]["status"] = "FAIL"
        loaded["evidence_state"] = {}
    elif mutation == "missing-human":
        result["assessments"] = [a for a in result["assessments"] if a["kind"] != "human"]
    elif mutation == "incompatible":
        result["spec"]["commit"] = "f" * 40
        result["assessments"][0]["status"] = "FAIL"
    elif mutation == "missing-evidence":
        loaded["evidence_state"] = {}
    elif mutation == "no-mandatory":
        result["assessments"][0]["mandatory"] = False
    elif mutation == "no-refs":
        result["assessments"][0]["evidence_ids"] = []
    else:
        result["assessments"][0]["status"] = "INSUFFICIENT_EVIDENCE"
    decision = grade(loaded, POLICY_V2)["decisions"][0]
    assert decision["status"] == expected
    assert decision["reason"]
    assert decision["coordinate"]["spec"] == result["spec"]
    if mutation in {"mandatory-fail", "incompatible"}:
        assert decision["mandatory_failures"] == [result["assessments"][0]["id"]]


def test_evidence_grouping_and_fixture_marker(loaded):
    decision = grade(loaded, POLICY_V2)["decisions"][0]
    assert len(decision["evidence_groups"]) == 1
    assert len(decision["evidence_groups"][0]["assessment_ids"]) == 3
    mock = next(a for a in decision["assessment_details"] if a["kind"] == "mock-agent")
    assert mock["fixture"] is True


@pytest.mark.parametrize("mutation", ["digest", "reference", "identity", "collision"])
def test_invalid_contributions(loaded, mutation):
    human = contribution(loaded)
    item = human["assessments"][0]
    if mutation == "digest":
        item["result_sha256"] = "0" * 64
    elif mutation == "reference":
        item["assessment"]["evidence_ids"] = ["unknown"]
    elif mutation == "identity":
        item["assessment"]["provenance"]["reviewer"] = " "
    else:
        item["assessment"]["id"] = loaded["bundle"]["results"][0]["assessments"][0]["id"]
    with pytest.raises(ValueError):
        grade(loaded, POLICY_V2, human)


def test_revision_rejects_replay_changed_evidence_and_history(loaded):
    human = contribution(loaded)
    first = grade(loaded, POLICY_V2, human)
    with pytest.raises(ValueError, match="Duplicate"):
        grade(loaded, POLICY_V2, human, first)
    changed = copy.deepcopy(loaded)
    changed["evidence_state"] = {}
    with pytest.raises(ValueError, match="original"):
        grade(changed, POLICY_V2, previous=first)
    second = grade(loaded, POLICY_V2, previous=first)
    second["previous_report"]["decisions"][0]["status"] = "FAIL"
    with pytest.raises(ValueError, match="history"):
        render(second)


def test_installed_cli_preserves_reports_before_nonzero_exit(tmp_path):
    source = Path(__file__).parents[1] / "examples/bundle/manifest.json"
    output = tmp_path / "failed.json"
    command = ["livingproof-capability-report", "grade", str(source), "--policy", POLICY_V2,
               "--require-pass", "-o", str(output)]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 1
    assert "Report retained" in run.stderr
    saved = json.loads(output.read_text())
    assert any(d["status"] == "FAIL" for d in saved["decisions"])
    artifact = Path(__file__).parents[1] / "artifacts/assessment-failing-case.json"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(render(saved))
    for format in ("table", "html", "csv"):
        artifact.with_suffix("." + format).write_text(render(saved, format))
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode == 1
    assert json.loads(output.read_text()) == saved


@pytest.mark.parametrize("policy", ["all-required-v1@1.0.0", POLICY_V2])
def test_execution_incompatibility_precedes_capability_grading(loaded, policy):
    result = loaded["bundle"]["results"][0]
    result["assessments"] = []
    result["original_result"]["status"] = "INCOMPATIBLE"
    assert grade(loaded, policy)["decisions"][0]["status"] == "INSUFFICIENT_EVIDENCE"
    result["provenance"]["compatibility"] = {
        "status": "INCOMPATIBLE", "scope": "execution",
        "reason": "Released executor supports pause revision 1.0.0 only"}
    decision = grade(loaded, policy)["decisions"][0]
    assert decision["status"] == "INCOMPATIBLE"
    assert decision["reason"] == result["provenance"]["compatibility"]["reason"]


@pytest.mark.parametrize("policy", ["all-required-v1@1.0.0", POLICY_V2])
@pytest.mark.parametrize("declaration", [None, "INCOMPATIBLE", {},
    {"status": "INCOMPATIBLE", "scope": "execution", "reason": " "}])
def test_malformed_compatibility_rejected(loaded, declaration, policy):
    loaded["bundle"]["results"][0]["provenance"]["compatibility"] = declaration
    with pytest.raises(ValueError, match="compatibility"):
        grade(loaded, policy)


def test_installed_cli_human_revision(tmp_path):
    source = Path(__file__).parents[1] / "examples/bundle/manifest.json"
    first, second, human = [tmp_path / name for name in ("first.json", "second.json", "human.json")]
    prefix = ["livingproof-capability-report"]
    subprocess.run(prefix + ["grade", str(source), "--policy", POLICY_V2, "-o", str(first)],
                   check=True, capture_output=True)
    identifier = load_bundle(source)["bundle"]["results"][0]["id"]
    subprocess.run(prefix + ["human-template", str(source), "--result", identifier,
                   "--assessment-id", "additional-human", "--reviewer", "Fixture reviewer",
                   "--recorded-at", "2026-10-26", "-o", str(human)], check=True, capture_output=True)
    content = json.loads(human.read_text())
    content["assessments"][0]["assessment"].update(status="FAIL", rationale="Dissent retained")
    human.write_text(json.dumps(content))
    original_bytes = first.read_bytes()
    subprocess.run(prefix + ["grade", str(source), "--policy", POLICY_V2, "--previous", str(first),
                   "--human", str(human), "-o", str(second)], check=True, capture_output=True)
    revision = json.loads(second.read_text())
    assert revision["grade_revision"] == 2
    assert revision["decisions"][0]["status"] == "FAIL"
    assert first.read_bytes() == original_bytes


@pytest.mark.parametrize("status, expected_exit", [
    ("PASS", 0), ("INSUFFICIENT_EVIDENCE", 1), ("INCOMPATIBLE", 1),
])
def test_require_pass_exit_by_outcome(loaded, tmp_path, status, expected_exit):
    import shutil
    source = Path(__file__).parents[1] / "examples/bundle"
    shutil.copytree(source, tmp_path / "bundle")
    result = loaded["bundle"]["results"][0]
    if status == "INCOMPATIBLE":
        result["provenance"]["compatibility"] = {
            "status": status, "scope": "execution", "reason": "Fixture execution mismatch"}
        result["assessments"] = []
    elif status == "INSUFFICIENT_EVIDENCE":
        result["assessments"] = []
    manifest = tmp_path / "bundle/manifest.json"
    manifest.write_text(json.dumps(loaded["bundle"]))
    output = tmp_path / "outcome.json"
    run = subprocess.run([
        "livingproof-capability-report", "grade", str(manifest), "--policy", POLICY_V2,
        "--require-pass", "-o", str(output)], capture_output=True, text=True)
    assert run.returncode == expected_exit
    saved = json.loads(output.read_text())
    assert saved["decisions"][0]["status"] == status
    assert ("Report retained" in run.stderr) == (expected_exit == 1)


def test_parsed_output_status_and_evidence_agree(loaded):
    from html.parser import HTMLParser

    class ReportHTML(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tag = None
            self.cells = []
            self.lossless = ""

        def handle_starttag(self, tag, attrs):
            if tag in {"td", "pre"}:
                self.tag = tag

        def handle_endtag(self, tag):
            if tag == self.tag:
                self.tag = None

        def handle_data(self, data):
            if self.tag == "td":
                self.cells.append(data)
            elif self.tag == "pre":
                self.lossless += data

    saved = grade(loaded, POLICY_V2, contribution(loaded, status="FAIL"))
    decision = json.loads(render(saved))["decisions"][0]
    csv_row = next(csv.DictReader(io.StringIO(render(saved, "csv"))))
    parser = ReportHTML()
    parser.feed(render(saved, "html"))
    terminal = render(saved, "table")
    terminal_decision = next(json.loads(line) for line in terminal.splitlines()
                             if line.startswith('{"assessment_details"'))
    assert csv_row["status"] == parser.cells[4] == terminal_decision["status"] == decision["status"]
    assert json.loads(parser.lossless)["decisions"][0] == decision
    assert terminal_decision == decision
    assert json.loads(csv_row["evidence_groups"]) == decision["evidence_groups"]
    assert json.loads(csv_row["assessments"]) == decision["assessment_details"]


def test_revision_integrity_labels_do_not_prove_unchanged_mismatched_bytes(tmp_path):
    import shutil
    source = Path(__file__).parents[1] / "examples/bundle"
    shutil.copytree(source, tmp_path / "bundle")
    manifest = tmp_path / "bundle/manifest.json"
    bundle = json.loads(manifest.read_text())
    bundle["results"] = [bundle["results"][0]]
    manifest.write_text(json.dumps(bundle))
    evidence = manifest.parent / bundle["results"][0]["evidence"][0]["path"]
    evidence.write_text("first changed content")
    first = grade(load_bundle(manifest), POLICY_V2)
    evidence.write_text("different changed content")
    second = grade(load_bundle(manifest), POLICY_V2, previous=first)
    assert second["previous_report"] == first
    assert second["source_bundle"] == first["source_bundle"] == bundle
    assert second["evidence_state"] == first["evidence_state"]
    assert second["decisions"][0]["status"] == "INSUFFICIENT_EVIDENCE"
    assert first["decisions"][0]["evidence_groups"][0]["integrity"] == "digest_mismatch"
    assert second["decisions"][0]["evidence_groups"][0]["integrity"] == "digest_mismatch"
