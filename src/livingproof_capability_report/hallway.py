"""Walk-hallway grading: the contract, its four evaluators and k-of-N summaries.

Each result is one seeded trial. It passes under all-required-v1 only when each of
the four deterministic hallway evaluators is present once, mandatory and PASS with
verified evidence. Human and agent assessments are accepted and graded by the same
rule: any FAIL fails the trial. Deterministic is the only kind produced today.
Failed checks carry structured fields {check, observed, limit, unit, t, seed, wall}.
"""
import math

PASS, FAIL, INSUFFICIENT, INCOMPATIBLE = "PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "INCOMPATIBLE"
CAPABILITY = "walk-hallway"
SPECS = "https://github.com/Living-Proof-Labs/robot-capability-specs"
# Matched by repository, commit and revision. b4ba31e is the candidate for specs v1.6.0;
# add the release commit here if v1.6.0 is cut from a different commit.
CONTRACTS = {(SPECS, "b4ba31eb2c7eaca2721d68d5d375260e2a114449", "0.1.0")}
EVALUATORS = {
    "hallway-exit-reached": "1.0.0",
    "hallway-lateral-limit": "1.0.0",
    "hallway-wall-contact": "1.0.0",
    "hallway-fall": "1.0.0",
}
ASSESSOR_KINDS = {"deterministic", "human", "agent"}
FAILURE_KEYS = {"check", "observed", "limit", "unit", "t", "seed"}


def is_hallway(result):
    return result["spec"]["capability"] == CAPABILITY


def contract_supported(result):
    spec = result["spec"]
    return (spec["repository"], spec["commit"], spec["revision"]) in CONTRACTS


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def failures(assessment):
    """Validated structured failures of one assessment (empty when none are given)."""
    details = assessment["provenance"].get("details", {})
    items = details.get("failures", []) if isinstance(details, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"Invalid structured failures in {assessment['id']}")
    for f in items:
        ok = (isinstance(f, dict) and FAILURE_KEYS <= set(f) <= FAILURE_KEYS | {"wall"}
              and f["check"] == assessment["evaluator"]
              and (f["observed"] is None or _number(f["observed"])) and _number(f["limit"])
              and isinstance(f["unit"], str) and f["unit"]
              and (f["t"] is None or _number(f["t"]))
              and (f["seed"] is None or type(f["seed"]) is int)
              and ("wall" not in f or isinstance(f["wall"], str)))
        if not ok:
            raise ValueError(f"Invalid structured failure in {assessment['id']}")
    if items and assessment["status"] != FAIL:
        raise ValueError(f"Structured failures on a non-failing assessment {assessment['id']}")
    return [dict(f) for f in items]


def assessor_type(assessment):
    declared = assessment["provenance"].get("assessor", {})
    kind = declared.get("type", assessment["kind"]) if isinstance(declared, dict) else None
    if kind != assessment["kind"]:
        raise ValueError(f"Assessor type does not match kind in {assessment['id']}")
    return kind


def members_supported(assessments):
    for a in assessments:
        if a["kind"] not in ASSESSOR_KINDS:
            return False
        if a["kind"] == "deterministic" and EVALUATORS.get(a["evaluator"]) != a["version"]:
            return False
        if a["kind"] != "deterministic" and a["evaluator"] in EVALUATORS:
            return False  # a person or agent cannot stand in for a deterministic evaluator
    return True


def decide(assessments, complete):
    """all-required-v1 for one trial; returns (status, reason, failures, assessor types)."""
    found = [f for a in assessments for f in failures(a)]
    types = sorted({assessor_type(a) for a in assessments})
    failed = [a for a in assessments if a["status"] == FAIL]
    if failed:
        why = "; ".join(a["rationale"] for a in failed)
        return FAIL, f"Failed: {why}", found, types
    deterministic = [a["evaluator"] for a in assessments if a["kind"] == "deterministic"]
    if not complete:
        return INSUFFICIENT, "Evidence missing or digest mismatch", found, types
    if (sorted(deterministic) != sorted(EVALUATORS)
            or not all(a["mandatory"] for a in assessments if a["kind"] == "deterministic")
            or any(a["status"] != PASS or not a["evidence_ids"] for a in assessments)):
        return INSUFFICIENT, "Missing, duplicate or insufficient required assessment", found, types
    return PASS, "All four hallway evaluators and every retained assessment pass", found, types


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def summaries(bundle, decisions):
    """k of N per run (spec, system, environment, run id), from stored per-trial decisions."""
    by_id = {d["result_id"]: d for d in decisions}
    groups = {}
    for r in bundle["results"]:
        if not is_hallway(r):
            continue
        key = (r["spec"]["commit"], r["system"]["id"], r["system"]["version"],
               r["environment"]["id"], r["environment"]["version"], r["provenance"].get("run_id"))
        groups.setdefault(key, []).append(r)
    out = []
    for key, results in groups.items():
        statuses = [by_id[r["id"]]["status"] for r in results]
        plan = results[0]["provenance"].get("plan") or {}
        n, need = plan.get("trials"), plan.get("required_passes")
        k = statuses.count(PASS)
        if INCOMPATIBLE in statuses:
            grade = INCOMPATIBLE
        elif not (type(n) is int and type(need) is int) or len(results) != n:
            grade = INSUFFICIENT
        elif k >= need:
            grade = PASS
        elif k + statuses.count(INSUFFICIENT) >= need:
            grade = INSUFFICIENT
        else:
            grade = FAIL
        out.append({
            "capability": CAPABILITY, "spec": dict(results[0]["spec"]),
            "system": dict(results[0]["system"]), "environment": dict(results[0]["environment"]),
            "run_id": key[-1], "k": k, "n": len(results) if n is None else n,
            "required_passes": need, "wilson95": wilson(k, len(results)), "grade": grade,
            "result_ids": [r["id"] for r in results],
            "failures": [f for r in results for f in by_id[r["id"]].get("failures", [])],
            "prototype": results[0]["provenance"].get("prototype"),
        })
    return out


def _fmt(value, other=None):
    if value is None:
        return "—"
    for d in range(2, 7):
        if other is None or f"{value:.{d}f}" != f"{other:.{d}f}":
            return f"{value:.{d}f}"
    return f"{value:.6g}"


def markdown(report):
    """PR-comment summary, failures grouped by check. DRAFT layout pending Art's review."""
    lines = ["<!-- livingproof-capability-report markdown summary (draft layout for Art) -->",
             f"## Capability report · policy `{report['policy']}`", ""]
    runs = report.get("summaries", [])
    if runs:
        lines += ["| System | Environment | Passed | Wilson 95% | Needs | Verdict |",
                  "|---|---|---|---|---|---|"]
        for s in runs:
            lo, hi = s["wilson95"]
            lines.append(f"| `{s['system']['id']}` {s['system']['version']} | "
                         f"`{s['environment']['id']}` {s['environment']['version']} | "
                         f"{s['k']}/{s['n']} | {lo:.2f}–{hi:.2f} | {s['required_passes']} | "
                         f"**{s['grade']}** |")
        for s in runs:
            lines += ["", f"### `{s['system']['id']}`: {s['k']}/{s['n']}, **{s['grade']}**", ""]
            if s.get("prototype"):
                lines += [f"> {s['prototype']}", ""]
            by_check = {}
            for f in s["failures"]:
                by_check.setdefault(f["check"], []).append(f)
            if not by_check:
                lines.append("No failed checks.")
            for check, items in by_check.items():
                seeds = sorted({f["seed"] for f in items if f["seed"] is not None})
                unit = items[0]["unit"]
                count = f"{len(seeds)} seed{'s' if len(seeds) != 1 else ''}"
                if len(items) != len(seeds):
                    count += f", {len(items)} events"
                lines += ["", f"<details><summary><b>{check}</b>: {count}</summary>", ""]
                walls = any("wall" in f for f in items)
                head = "| Seed | " + ("Wall | " if walls else "") + f"Observed ({unit}) | Limit ({unit}) | t (s) |"
                lines += [head, "|" + "---|" * (5 if walls else 4)]
                for f in sorted(items, key=lambda f: (f["seed"] is None, f["seed"] or 0, f["t"] or 0)):
                    wall = f"{f.get('wall', '')} | " if walls else ""
                    lines.append(f"| {f['seed'] if f['seed'] is not None else '—'} | {wall}"
                                 f"{_fmt(f['observed'], f['limit'])} | {_fmt(f['limit'], f['observed'])} | "
                                 f"{_fmt(f['t'])} |")
                lines += ["", "</details>"]
            spec = s["spec"]
            lines += ["", f"<sub>Catalog {spec['tag']} `{spec['commit'][:7]}` · {spec['capability']} "
                      f"{spec['revision']} · run `{s['run_id']}`</sub>"]
    others = [d for d in report["decisions"]
              if not any(d["result_id"] in s["result_ids"] for s in runs)]
    if others:
        lines += ["", "| Result | Status | Reason |", "|---|---|---|"]
        lines += [f"| `{d['result_id']}` | **{d['status']}** | {d['reason'].replace('|', '/')} |"
                  for d in others]
    lines += ["", f"<sub>Report of bundle `{report['source_bundle_sha256'][:12]}`. Stored decisions, "
              "no regrading. Simulation evidence is not hardware validation.</sub>", ""]
    return "\n".join(lines)
