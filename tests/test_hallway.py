"""Walk-hallway grading: contract, four evaluators, assessor kinds, structured failures."""
import copy
import hashlib
import json

import pytest

from livingproof_capability_report import hallway
from livingproof_capability_report.core import digest, grade, load_bundle, render

COMMIT = "b4ba31eb2c7eaca2721d68d5d375260e2a114449"
PLAN = {"trials": 20, "seeds": list(range(1, 21)), "command_speed": 0.5, "required_passes": 18}
FAILING = {4: "lateral", 5: "wall", 7: "both", 9: "lateral", 12: "wall", 14: "fall", 15: "exit", 18: "lateral"}


def det(eid, evaluator, status="PASS", failures=None):
    details = {"failures": failures} if failures else {}
    return {"id": f"{eid}/{evaluator}", "evaluator": evaluator, "kind": "deterministic",
            "version": "1.0.0", "status": status, "rationale": f"{evaluator} {status}",
            "mandatory": True, "evidence_ids": [eid],
            "provenance": {"assessor": {"type": "deterministic", "id": evaluator, "version": "1.0.0"},
                           "details": details}}


def trial(seed, kind=None):
    eid = f"stock-seed-{seed:02d}"
    assessments = {e: det(eid, e) for e in hallway.EVALUATORS}
    def fail(evaluator, **f):
        assessments[evaluator] = det(eid, evaluator, "FAIL",
                                     [{"check": evaluator, "seed": seed, **f}])
    if kind in ("lateral", "both"):
        fail("hallway-lateral-limit", observed=0.62, limit=0.49, unit="m", t=10.26)
    if kind in ("wall", "both"):
        fail("hallway-wall-contact", observed=0.03, limit=0.0, unit="m", t=4.5, wall="wall-left")
    if kind == "fall":
        fail("hallway-fall", observed=0.41, limit=0.5, unit="m", t=6.2)
    if kind == "exit":
        fail("hallway-exit-reached", observed=None, limit=27.0, unit="s", t=27.0)
    return eid, list(assessments.values())


def bundle(tmp_path, seeds=PLAN["seeds"], commit=COMMIT):
    (tmp_path / "evidence").mkdir(exist_ok=True)
    results = []
    for seed in seeds:
        eid, assessments = trial(seed, FAILING.get(seed))
        path = tmp_path / "evidence" / f"{eid}.json"
        path.write_text(json.dumps({"seed": seed}))
        results.append({
            "id": eid,
            "spec": {"repository": hallway.SPECS, "tag": "v1.6.0", "commit": commit,
                     "capability": "walk-hallway", "revision": "0.1.0"},
            "system": {"id": "unitree-g1/stock", "version": "1.1.0"},
            "environment": {"id": "hallway-open", "version": "0.1.0"},
            "evidence": [{"id": eid, "path": f"evidence/{eid}.json",
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
            "assessments": assessments,
            "provenance": {"run_id": "run-1", "plan": PLAN},
            "original_result": {"seed": seed},
        })
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0.0", "producer": {
        "id": "capability-verifier", "version": "1.3.2", "commit": "0" * 40}, "results": results}))
    return manifest


def test_hallway_trials_get_real_verdicts_and_structured_failures(tmp_path):
    report = grade(load_bundle(bundle(tmp_path)))
    status = {d["result_id"]: d for d in report["decisions"]}
    assert status["stock-seed-01"]["status"] == "PASS"
    assert status["stock-seed-07"]["status"] == "FAIL"
    assert {f["check"] for f in status["stock-seed-07"]["failures"]} == {
        "hallway-lateral-limit", "hallway-wall-contact"}
    assert status["stock-seed-05"]["failures"] == [{"check": "hallway-wall-contact", "seed": 5,
        "observed": 0.03, "limit": 0.0, "unit": "m", "t": 4.5, "wall": "wall-left"}]
    assert not any(d["status"] == "INCOMPATIBLE" for d in report["decisions"])
    (run,) = report["summaries"]
    assert (run["k"], run["n"], run["grade"], run["wilson95"]) == (12, 20, "FAIL", [0.3866, 0.7812])
    assert len(run["failures"]) == 9


def test_k_of_n_pass_and_missing_trials(tmp_path):
    report = grade(load_bundle(bundle(tmp_path, seeds=[1, 2, 3])))
    assert report["summaries"][0]["grade"] == "INSUFFICIENT_EVIDENCE"  # 3 of 20 planned trials


def test_human_and_agent_assessments_are_graded(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    result = loaded["bundle"]["results"][0]
    for kind, status in (("human", "PASS"), ("agent", "FAIL")):
        result["assessments"].append({
            "id": f"{result['id']}/{kind}-review", "evaluator": f"{kind}-review", "kind": kind,
            "version": "1.0.0", "status": status, "rationale": f"{kind} saw it", "mandatory": False,
            "evidence_ids": [result["id"]], "provenance": {"assessor": {"type": kind},
            "reviewer": f"test-{kind}", "recorded_at": "2026-11-01T08:00:00Z"}})
    d = grade(loaded)["decisions"][0]
    assert d["status"] == "FAIL" and d["assessor_types"] == ["agent", "deterministic", "human"]


def test_agent_cannot_stand_in_for_a_deterministic_evaluator(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    a = loaded["bundle"]["results"][0]["assessments"][0]
    a["kind"] = a["provenance"]["assessor"]["type"] = "agent"
    assert grade(loaded)["decisions"][0]["status"] == "INCOMPATIBLE"


def test_human_contribution_to_hallway_result(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    result = loaded["bundle"]["results"][0]
    human = {"schema_version": "1.0.0", "assessments": [{
        "result_id": result["id"], "result_sha256": digest(result),
        "assessment": {"id": "h1", "evaluator": "human-review", "kind": "human", "version": "1.0.0",
                       "status": "FAIL", "rationale": "stumble at 8.00 s (seed 1)", "mandatory": True,
                       "evidence_ids": [result["id"]],
                       "provenance": {"reviewer": "art", "recorded_at": "2026-11-01T08:00:00Z"}}}]}
    assert grade(loaded, human=human)["decisions"][0]["status"] == "FAIL"


def test_unknown_contract_or_version_is_incompatible(tmp_path):
    report = grade(load_bundle(bundle(tmp_path, seeds=[1], commit="f" * 40)))
    assert report["decisions"][0]["status"] == "INCOMPATIBLE"
    loaded = load_bundle(bundle(tmp_path))
    loaded["bundle"]["results"][0]["assessments"][0]["version"] = "9.0.0"
    assert grade(loaded)["decisions"][0]["status"] == "INCOMPATIBLE"


@pytest.mark.parametrize("change", [{"seed": "7"}, {"limit": None}, {"check": "hallway-fall"},
                                    {"extra": 1}, {"t": float("inf")}])
def test_malformed_structured_failure_is_rejected(tmp_path, change):
    loaded = load_bundle(bundle(tmp_path))
    a = next(a for a in loaded["bundle"]["results"][3]["assessments"] if a["status"] == "FAIL")
    a["provenance"]["details"]["failures"][0].update(change)
    with pytest.raises(ValueError):
        grade(copy.deepcopy(loaded))


def test_markdown_groups_failures_by_check(tmp_path):
    md = render(grade(load_bundle(bundle(tmp_path))), "markdown")
    assert "| `unitree-g1/stock` 1.1.0 | `hallway-open` 0.1.0 | 12/20 | 0.39–0.78 | 18 | **FAIL** |" in md
    assert "<b>hallway-lateral-limit</b>: 4 seeds" in md
    assert "| 7 | wall-left | 0.03 | 0.00 | 4.50 |" in md
    assert "| 15 | — | 27.00 | 27.00 |" in md
    assert "all-required-v1@1.0.0" in md and "draft layout for Art" in md


def test_pause_example_still_grades(tmp_path):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    report = grade(load_bundle(root / "examples/bundle/manifest.json"))
    assert "summaries" not in report
    assert {d["status"] for d in report["decisions"]} <= {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "INCOMPATIBLE"}
    assert "Result" in render(report, "markdown")
