"""Walk-hallway grading: contract, four evaluators, assessor kinds, structured failures."""

import copy
import hashlib
import json

import pytest

from livingproof_capability_report import hallway
from livingproof_capability_report.core import digest, grade, load_bundle, render

COMMIT = "b4ba31eb2c7eaca2721d68d5d375260e2a114449"
PLAN = {"trials": 20, "seeds": list(range(1, 21)), "command_speed": 0.5, "required_passes": 18}
FAILING = {
    4: "lateral",
    5: "wall",
    7: "both",
    9: "lateral",
    12: "wall",
    14: "fall",
    15: "exit",
    18: "lateral",
}


def det(eid, evaluator, status="PASS", failures=None):
    details = {"failures": failures} if failures else {}
    return {
        "id": f"{eid}/{evaluator}",
        "evaluator": evaluator,
        "kind": "deterministic",
        "version": "1.0.0",
        "status": status,
        "rationale": f"{evaluator} {status}",
        "mandatory": True,
        "evidence_ids": [eid],
        "provenance": {
            "assessor": {"type": "deterministic", "id": evaluator, "version": "1.0.0"},
            "details": details,
        },
    }


def trial(seed, kind=None):
    eid = f"stock-seed-{seed:02d}"
    assessments = {e: det(eid, e) for e in hallway.EVALUATORS}

    def fail(evaluator, **f):
        assessments[evaluator] = det(
            eid, evaluator, "FAIL", [{"check": evaluator, "seed": seed, **f}]
        )

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
        results.append(
            {
                "id": eid,
                "spec": {
                    "repository": hallway.SPECS,
                    "tag": "v1.6.0",
                    "commit": commit,
                    "capability": "walk-hallway",
                    "revision": "0.1.0",
                },
                "system": {"id": "unitree-g1/stock", "version": "1.1.0"},
                "environment": {"id": "hallway-open", "version": "0.1.0"},
                "evidence": [
                    {
                        "id": eid,
                        "path": f"evidence/{eid}.json",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                ],
                "assessments": assessments,
                "provenance": {"run_id": "run-1", "plan": PLAN},
                "original_result": {"seed": seed},
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "producer": {"id": "capability-verifier", "version": "1.3.2", "commit": "0" * 40},
                "results": results,
            }
        )
    )
    return manifest


def test_hallway_trials_get_real_verdicts_and_structured_failures(tmp_path):
    report = grade(load_bundle(bundle(tmp_path)))
    status = {d["result_id"]: d for d in report["decisions"]}
    assert status["stock-seed-01"]["status"] == "PASS"
    assert status["stock-seed-07"]["status"] == "FAIL"
    assert {f["check"] for f in status["stock-seed-07"]["failures"]} == {
        "hallway-lateral-limit",
        "hallway-wall-contact",
    }
    assert status["stock-seed-05"]["failures"] == [
        {
            "check": "hallway-wall-contact",
            "seed": 5,
            "observed": 0.03,
            "limit": 0.0,
            "unit": "m",
            "t": 4.5,
            "wall": "wall-left",
        }
    ]
    assert not any(d["status"] == "INCOMPATIBLE" for d in report["decisions"])
    (run,) = report["summaries"]
    assert (run["k"], run["n"], run["grade"], run["wilson95"]) == (12, 20, "FAIL", [0.3866, 0.7812])
    assert len(run["failures"]) == 9


def test_k_of_n_pass_and_missing_trials(tmp_path):
    report = grade(load_bundle(bundle(tmp_path, seeds=[1, 2, 3])))
    assert report["summaries"][0]["grade"] == "INSUFFICIENT_EVIDENCE"  # 3 of 20 planned trials


def test_missing_trials_use_the_planned_n(tmp_path):
    """Same rule as capability-verifier hallway.aggregate: N and Wilson use the plan."""
    s = grade(load_bundle(bundle(tmp_path, seeds=[1, 2, 3])))["summaries"][0]
    assert (s["k"], s["n"]) == (3, 20)
    assert s["wilson95"] == hallway.wilson(3, 20)
    assert s["wilson95"] != hallway.wilson(3, 3)


def test_human_and_agent_assessments_are_graded(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    result = loaded["bundle"]["results"][0]
    for kind, status in (("human", "PASS"), ("agent", "FAIL")):
        result["assessments"].append(
            {
                "id": f"{result['id']}/{kind}-review",
                "evaluator": f"{kind}-review",
                "kind": kind,
                "version": "1.0.0",
                "status": status,
                "rationale": f"{kind} saw it",
                "mandatory": False,
                "evidence_ids": [result["id"]],
                "provenance": {
                    "assessor": {"type": kind},
                    "reviewer": f"test-{kind}",
                    "recorded_at": "2026-11-01T08:00:00Z",
                },
            }
        )
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
    human = {
        "schema_version": "1.0.0",
        "assessments": [
            {
                "result_id": result["id"],
                "result_sha256": digest(result),
                "assessment": {
                    "id": "h1",
                    "evaluator": "human-review",
                    "kind": "human",
                    "version": "1.0.0",
                    "status": "FAIL",
                    "rationale": "stumble at 8.00 s (seed 1)",
                    "mandatory": True,
                    "evidence_ids": [result["id"]],
                    "provenance": {"reviewer": "art", "recorded_at": "2026-11-01T08:00:00Z"},
                },
            }
        ],
    }
    assert grade(loaded, human=human)["decisions"][0]["status"] == "FAIL"


def test_unknown_contract_or_version_is_incompatible(tmp_path):
    report = grade(load_bundle(bundle(tmp_path, seeds=[1], commit="f" * 40)))
    assert report["decisions"][0]["status"] == "INCOMPATIBLE"
    loaded = load_bundle(bundle(tmp_path))
    loaded["bundle"]["results"][0]["assessments"][0]["version"] = "9.0.0"
    assert grade(loaded)["decisions"][0]["status"] == "INCOMPATIBLE"


@pytest.mark.parametrize(
    "change",
    [{"seed": "7"}, {"limit": None}, {"check": "hallway-fall"}, {"extra": 1}, {"t": float("inf")}],
)
def test_malformed_structured_failure_is_rejected(tmp_path, change):
    loaded = load_bundle(bundle(tmp_path))
    a = next(a for a in loaded["bundle"]["results"][3]["assessments"] if a["status"] == "FAIL")
    a["provenance"]["details"]["failures"][0].update(change)
    with pytest.raises(ValueError):
        grade(copy.deepcopy(loaded))


def _provenance(manifest, **extra):
    data = json.loads(manifest.read_text())
    for r in data["results"]:
        r["provenance"].update(
            lock={"path": "verification.lock.json", "sha256": "abcdef1" + "0" * 57}, **extra
        )
    for r in data["results"]:
        r["provenance"]["plan"] = PLAN
    manifest.write_text(json.dumps(data))
    return manifest


def test_markdown_follows_arts_layout(tmp_path):
    md = render(grade(load_bundle(_provenance(bundle(tmp_path)))), "markdown")
    lines = md.splitlines()
    assert lines[0] == "<!-- livingproof-verification -->"  # 1: stable marker
    assert "draft" not in md.lower()
    assert lines[1] == (
        "## walk-hallway@0.1.0 · N=20 · 0.50 m/s · pass bar 18/20 · "
        "`verification.lock.json @ abcdef1`"
    )  # 2: header
    assert "| Robot · configuration | Grade | Passed | 95% interval | Needs |" in md  # 3
    assert "| unitree-g1 · stock 1.1.0 | **❌ FAIL** | 12/20 | 39–78% | 18 |" in md
    assert (
        "unitree-g1 · stock does not pass walk-hallway: 12 of 20 trials passed, 18 needed." in md
    )  # 4
    # 5: each failing seed once, under its first failure. Seed 7 touched the wall at 4.50 s
    # before crossing the lateral limit at 10.26 s, so it counts as a wall contact.
    assert "- 3× lateral limit exceeded — worst: 0.62 > 0.49 m at 10.26 s (seed 18)" in md
    assert "- 3× touched a wall — worst: touched left wall at 4.50 s (seed 12)" in md
    assert "- 1× exit not reached in time — worst: not reached by 27.00 s (seed 15)" in md
    assert "- 1× other first failures; see the per-seed details" in md  # the fall, beyond 3 bullets
    assert md.index("Why runs failed") < md.index("<details>")
    assert "| 7 | touched left wall at 4.50 s |" in md  # 6: wall contacts, no observed/limit
    assert "![" not in md  # 7: no stored assets, no thumbnails
    assert "Full report" not in md  # 8: no links given, no links row
    assert "<details><summary>Per-seed failures · unitree-g1 · stock</summary>" in md  # 9
    assert lines[-1].startswith(
        "<sub>Policy all-required-v1@1.0.0 · catalog v1.6.0 @ b4ba31e · run run-1 · "
    )
    assert lines[-1].endswith(
        "stored decisions, no regrading · simulation evidence, not hardware validation</sub>"
    )


def test_markdown_close_call_keeps_minimal_extra_digit():
    f = {
        "check": "hallway-lateral-limit",
        "observed": 0.492,
        "limit": 0.49,
        "unit": "m",
        "t": 9.2,
        "seed": 17,
    }
    assert hallway._describe(f) == "0.492 > 0.490 m at 9.20 s (seed 17)"
    assert hallway._describe(dict(f, observed=0.62)) == "0.62 > 0.49 m at 9.20 s (seed 17)"


def test_markdown_thumbnails_links_and_prototype_line(tmp_path):
    m = _provenance(
        bundle(tmp_path),
        prototype="PROTOTYPE: unreleased catalog",
        assets={"thumbnail": "t.png", "clip": "c.mp4"},
    )
    md = render(
        grade(load_bundle(m)),
        "markdown",
        {"report": "r.html", "clips": "clips/", "lock_diff": None},
    )
    assert "[![worst fail stock-seed-04](t.png)](c.mp4) [![pass stock-seed-01](t.png)](c.mp4)" in md
    assert "[Full report](r.html) · [All clips](clips/)" in md and "Lock diff" not in md
    assert md.splitlines()[-1] == "<sub>PROTOTYPE: unreleased catalog</sub>"


def test_pause_example_still_grades(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    report = grade(load_bundle(root / "examples/bundle/manifest.json"))
    assert "summaries" not in report
    assert {d["status"] for d in report["decisions"]} <= {
        "PASS",
        "FAIL",
        "INSUFFICIENT_EVIDENCE",
        "INCOMPATIBLE",
    }
    assert "Result" in render(report, "markdown")


def test_released_v160_commit_is_a_known_contract():
    assert (hallway.SPECS, "34681d20bf13ba0a836e03ac09869c7fb13665f1", "0.1.0") in hallway.CONTRACTS
    assert (hallway.SPECS, COMMIT, "0.1.0") in hallway.CONTRACTS


def test_specs_25_candidate_grades_like_v160(tmp_path):
    """Specs #25 rewords the feature only; a bundle at its commit grades the same."""
    candidate = "a378e92216fd9498984f290e677b9f4e7a33232c"
    assert (hallway.SPECS, candidate, "0.1.0") in hallway.CONTRACTS
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    old = grade(load_bundle(bundle(tmp_path / "old")))
    new = grade(load_bundle(bundle(tmp_path / "new", commit=candidate)))
    assert [d["status"] for d in new["decisions"]] == [d["status"] for d in old["decisions"]]
    assert "INCOMPATIBLE" not in {d["status"] for d in new["decisions"]}


def test_released_v161_commit_grades_like_v160(tmp_path):
    """v1.6.1 is the #25 merge commit (0bdf1db); a bundle at it grades the same."""
    released = "0bdf1db3f975b044692c0b8f1ec37737ad8b889f"
    assert (hallway.SPECS, released, "0.1.0") in hallway.CONTRACTS
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    old = grade(load_bundle(bundle(tmp_path / "old")))
    new = grade(load_bundle(bundle(tmp_path / "new", commit=released)))
    assert [d["status"] for d in new["decisions"]] == [d["status"] for d in old["decisions"]]
    assert "INCOMPATIBLE" not in {d["status"] for d in new["decisions"]}


RUN = "https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7"
ART = RUN + "/artifacts/"


def _links(**extra):
    return {
        "run": RUN,
        "links": [
            {"label": "evidence", "url": ART + "1", "kind": "artifact"},
            {"label": "MCAP, all trials", "url": ART + "2", "kind": "mcap"},
            {"label": "video", "url": ART + "3", "kind": "video", "seed": 1, "status": "PASS"},
            {"label": "MCAP", "url": ART + "4", "kind": "mcap", "seed": 1, "status": "PASS"},
            {"label": "video", "url": ART + "5", "kind": "video", "seed": 4, "status": "FAIL"},
            {"label": "video", "url": "", "kind": "video", "seed": 2, "status": "FAIL"},
        ],
        **extra,
    }


def test_evidence_links_stored_in_report_and_rendered(tmp_path):
    report = grade(load_bundle(bundle(tmp_path)), evidence_links=[_links()])
    stored = report["evidence_links"]
    assert stored["run"] == RUN
    assert len(stored["links"]) == 5  # the empty URL (skipped upload) is dropped
    assert report["source_bundle_sha256"] == digest(report["source_bundle"])  # no digest change
    md = render(report, "markdown")
    assert f"**Evidence:** [CI run]({RUN}) · [evidence]({ART}1) · [MCAP, all trials]({ART}2)" in md
    assert f"- ▶️ seed 4 (fail): [video]({ART}5)" in md
    assert f"- ▶️ seed 1 (pass): [video]({ART}3) · [MCAP]({ART}4)" in md
    assert md.index("seed 4 (fail)") < md.index("seed 1 (pass)") < md.index("<details>")
    page = render(report, "html")
    assert f"<a href='{ART}5'>seed 4 (FAIL): video</a>" in page
    assert json.loads(render(report, "json"))["evidence_links"] == stored


def test_evidence_links_absent_leaves_markdown_unchanged(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    md = render(grade(loaded), "markdown")
    assert "Evidence:" not in md and "evidence_links" not in grade(loaded)


def test_evidence_link_status_must_match_stored_decision(tmp_path):
    bad = _links()
    bad["links"][2] = dict(bad["links"][2], seed=4)  # seed 4 failed; a "pass" video is a lie
    report = grade(load_bundle(bundle(tmp_path)), evidence_links=[bad])
    with pytest.raises(ValueError, match="seed 4 says PASS, stored decision is FAIL"):
        render(report, "markdown")


@pytest.mark.parametrize(
    "entry",
    [
        {"label": "x", "url": "http://insecure", "kind": "artifact"},
        {"label": "x](javascript:1)", "url": ART + "1", "kind": "artifact"},
        {"label": "x", "url": ART + "1 extra", "kind": "artifact"},
        {"label": "x", "url": ART + "1", "kind": "zip"},
        {"label": "x", "url": ART + "1", "kind": "video", "seed": 1},
        {"label": "x", "url": ART + "1", "kind": "artifact", "note": "?"},
    ],
)
def test_evidence_links_rejected(tmp_path, entry):
    with pytest.raises(ValueError):
        grade(load_bundle(bundle(tmp_path)), evidence_links=[{"links": [entry]}])


def test_evidence_links_files_merge_and_must_agree_on_run(tmp_path):
    loaded = load_bundle(bundle(tmp_path))
    first = {"run": RUN, "links": [{"label": "a", "url": ART + "1", "kind": "artifact"}]}
    second = {"links": [{"label": "b", "url": ART + "2", "kind": "artifact"}]}
    merged = grade(loaded, evidence_links=[first, second])["evidence_links"]
    assert [e["label"] for e in merged["links"]] == ["a", "b"] and merged["run"] == RUN
    with pytest.raises(ValueError, match="different CI runs"):
        grade(loaded, evidence_links=[first, {"run": RUN + "0", "links": []}])
