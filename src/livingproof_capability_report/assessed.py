"""Bundle 1.1.0: render the capability verifier's decisions and run assessments as stored.

Nothing here grades. Per-result statuses come from each result's ``decision`` and per-run
k of N, interval and grade from the bundle's ``assessment`` (livingproof-run-assessment/0.1,
robot-capability-specs). The report keeps the report 1.0.0 document layout that reporter
1.x wrote, so ``render`` and ``comment`` print the same bytes; ``wilson95`` is kept.

A missing or malformed field is an error naming the field and the result. The one check
made against the evidence is integrity: a stored PASS whose evidence is missing or changed
is refused rather than shown.
"""

import copy

from . import core
from . import links as elinks

BUNDLE_VERSION = "1.1.0"
FORMAT = "livingproof-run-assessment/0.1"
STATUSES = {core.PASS, core.FAIL, core.INSUFFICIENT, core.INCOMPATIBLE}
SUMMARY_KEYS = (
    "capability",
    "spec",
    "system",
    "environment",
    "run_id",
    "k",
    "n",
    "required_passes",
    "wilson95",
    "grade",
    "result_ids",
    "failures",
    "prototype",
)
RUN_KEYS = tuple(k for k in SUMMARY_KEYS if k != "wilson95") + ("interval",)


def is_assessed(bundle):
    return isinstance(bundle, dict) and bundle.get("schema_version") == BUNDLE_VERSION


def _need(container, key, where, kind=None):
    if not isinstance(container, dict) or key not in container:
        raise ValueError(f"Bundle 1.1.0: {where} is missing required field '{key}'")
    value = container[key]
    if kind is not None and not isinstance(value, kind):
        raise ValueError(f"Bundle 1.1.0: {where} field '{key}' must be {kind.__name__}")
    return value


def _decision(result):
    where = f"result '{result['id']}'"
    stored = _need(result, "decision", where, dict)
    where = f"result '{result['id']}' decision"
    status = _need(stored, "status", where, str)
    if status not in STATUSES:
        raise ValueError(f"Bundle 1.1.0: {where} field 'status' is not a known status: {status!r}")
    decision = {"result_id": result["id"], "status": status}
    decision["reason"] = _need(stored, "reason", where, str)
    _need(stored, "policy", where, dict)
    if status != core.INCOMPATIBLE:  # reporter 1.x lists failures only for graded trials
        decision["failures"] = copy.deepcopy(_need(stored, "failures", where, list))
        decision["assessor_types"] = list(_need(stored, "assessor_types", where, list))
    return decision


def _summary(run, index):
    where = f"assessment run {index}"
    for key in RUN_KEYS:
        _need(run, key, where)
    interval = _need(run, "interval", where, dict)
    for key in ("method", "level", "lower", "upper"):
        _need(interval, key, f"{where} interval")
    if interval["method"] != "wilson" or interval["level"] != 0.95:
        raise ValueError(f"Bundle 1.1.0: {where} interval must be the Wilson 95% interval")
    out = {k: copy.deepcopy(run[k]) for k in RUN_KEYS if k != "interval"}
    out["wilson95"] = [interval["lower"], interval["upper"]]
    return {k: out[k] for k in SUMMARY_KEYS}


def report_from_bundle(loaded, evidence_links=None):
    """The report for a bundle 1.1.0, from its stored decisions; computes no grade."""
    bundle = core.validate_bundle(loaded["bundle"])
    if not is_assessed(bundle):
        raise ValueError(f"Expected bundle {BUNDLE_VERSION}, got {bundle.get('schema_version')!r}")
    assessment = _need(bundle, "assessment", "bundle", dict)
    for key in ("format", "policy", "aggregation", "decisions", "runs"):
        _need(assessment, key, "bundle assessment")
    if assessment["format"] != FORMAT:
        raise ValueError(
            f"Bundle 1.1.0: assessment format {assessment['format']!r} is not {FORMAT}"
        )
    policy = assessment["policy"]
    for key in ("id", "version"):
        _need(policy, key, "bundle assessment policy", str)
    decisions = [_decision(r) for r in bundle["results"]]
    stored = {d.get("result_id"): d for d in assessment["decisions"] if isinstance(d, dict)}
    for result, decision in zip(bundle["results"], decisions):
        listed = stored.get(result["id"])
        if listed is None:
            raise ValueError(
                f"Bundle 1.1.0: assessment decisions are missing result '{result['id']}'"
            )
        if listed.get("status") != decision["status"] or listed.get("reason") != decision["reason"]:
            raise ValueError(
                f"Bundle 1.1.0: result '{result['id']}' decision differs from the assessment"
            )
        if result["decision"]["policy"] != policy:
            raise ValueError(f"Bundle 1.1.0: result '{result['id']}' decision names another policy")
        if decision["status"] == core.PASS and any(
            state != "verified" for state in loaded["evidence_state"].get(result["id"], {}).values()
        ):
            raise ValueError(
                f"Bundle 1.1.0: result '{result['id']}' is stored as PASS but its evidence "
                "is missing or changed"
            )
    report = {
        "report_version": "1.0.0",
        "policy": f"{policy['id']}@{policy['version']}",
        "source_bundle": bundle,
        "source_bundle_sha256": core.digest(bundle),
        "human_contributions": {"schema_version": "1.0.0", "assessments": []},
        "evidence_state": copy.deepcopy(loaded["evidence_state"]),
        "groups": core.aggregate(bundle["results"]),
        "decisions": decisions,
    }
    runs = [_summary(run, i) for i, run in enumerate(assessment["runs"])]
    known = {r["id"] for r in bundle["results"]}
    for i, run in enumerate(runs):
        unknown = [rid for rid in run["result_ids"] if rid not in known]
        if unknown:
            raise ValueError(
                f"Bundle 1.1.0: assessment run {i} names unknown result '{unknown[0]}'"
            )
    if runs:
        report["summaries"] = runs
    if evidence_links:
        report["evidence_links"] = elinks.merge(evidence_links)
    return report
