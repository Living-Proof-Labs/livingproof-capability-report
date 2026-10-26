"""Opt-in policy; assessment conclusions are supplied, never model-generated."""
from collections import defaultdict

POLICY_V2 = "all-required-v2@1.0.0"


def explain(result, assessments, states):
    """Group evidence within one run; preserve every assessment and its dissent."""
    groups = defaultdict(list)
    for assessment in assessments:
        for reference in assessment["evidence_ids"]:
            groups[reference].append(assessment["id"])
    return {
        "coordinate": {key: result[key] for key in ("spec", "system", "environment")},
        "assessment_details": [dict(a, fixture=a["kind"] == "mock-agent") for a in assessments],
        "evidence_groups": [{"evidence_id": e["id"], "sha256": e["sha256"],
                             "integrity": states.get(e["id"], "missing"),
                             "assessment_ids": groups[e["id"]]} for e in result["evidence"]],
        "mandatory_failures": [a["id"] for a in assessments
                               if a["mandatory"] and a["status"] == "FAIL"],
        "dissent": len({a["status"] for a in assessments}) > 1,
    }


def decide(assessments, complete):
    """All required roles pass; no voting or replacement of retained conclusions."""
    if any(a["status"] == "FAIL" for a in assessments):
        return "FAIL", "A retained assessment failed; failures are never averaged away"
    if not complete:
        return "INSUFFICIENT_EVIDENCE", "Evidence missing or digest mismatch"
    required = {"deterministic", "mock-agent", "human"}
    if (not required <= {a["kind"] for a in assessments}
            or any(a["status"] != "PASS" or not a["evidence_ids"] for a in assessments)
            or not any(a["kind"] == "deterministic" and a["mandatory"] for a in assessments)):
        return "INSUFFICIENT_EVIDENCE", "Required role, conclusion, reference or mandatory rule missing"
    return "PASS", "All required roles pass with verified evidence; all assessments retained"
