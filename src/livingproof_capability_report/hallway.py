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
# Matched by repository, commit and revision. Specs v1.6.0 is 34681d2, the #24 merge
# commit. Its tree is identical to b4ba31e, the pre-merge candidate that prototype
# bundles were produced from, so both are accepted.
CONTRACTS = {
    (SPECS, "34681d20bf13ba0a836e03ac09869c7fb13665f1", "0.1.0"),  # v1.6.0
    (SPECS, "b4ba31eb2c7eaca2721d68d5d375260e2a114449", "0.1.0"),  # pre-merge candidate
}
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
        ok = (
            isinstance(f, dict)
            and FAILURE_KEYS <= set(f) <= FAILURE_KEYS | {"wall"}
            and f["check"] == assessment["evaluator"]
            and (f["observed"] is None or _number(f["observed"]))
            and _number(f["limit"])
            and isinstance(f["unit"], str)
            and f["unit"]
            and (f["t"] is None or _number(f["t"]))
            and (f["seed"] is None or type(f["seed"]) is int)
            and ("wall" not in f or isinstance(f["wall"], str))
        )
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
    if (
        sorted(deterministic) != sorted(EVALUATORS)
        or not all(a["mandatory"] for a in assessments if a["kind"] == "deterministic")
        or any(a["status"] != PASS or not a["evidence_ids"] for a in assessments)
    ):
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
        key = (
            r["spec"]["commit"],
            r["system"]["id"],
            r["system"]["version"],
            r["environment"]["id"],
            r["environment"]["version"],
            r["provenance"].get("run_id"),
        )
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
        out.append(
            {
                "capability": CAPABILITY,
                "spec": dict(results[0]["spec"]),
                "system": dict(results[0]["system"]),
                "environment": dict(results[0]["environment"]),
                "run_id": key[-1],
                "k": k,
                "n": len(results) if n is None else n,
                "required_passes": need,
                "wilson95": wilson(k, len(results)),
                "grade": grade,
                "result_ids": [r["id"] for r in results],
                "failures": [f for r in results for f in by_id[r["id"]].get("failures", [])],
                "prototype": results[0]["provenance"].get("prototype"),
            }
        )
    return out


MARKER = "<!-- livingproof-verification -->"
GRADE = {
    PASS: "✅ PASS",
    FAIL: "❌ FAIL",
    INSUFFICIENT: "⚠️ INSUFFICIENT EVIDENCE",
    INCOMPATIBLE: "⚠️ INCOMPATIBLE",
}
ORDER = list(EVALUATORS)
WHAT = {
    "hallway-exit-reached": "exit not reached in time",
    "hallway-lateral-limit": "lateral limit exceeded",
    "hallway-wall-contact": "touched a wall",
    "hallway-fall": "fell",
}


def _fmt(value, other=None, decimals=2):
    """Fixed decimals; one more digit at a time only when value and other would read equal."""
    if value is None:
        return "—"
    for d in range(decimals, 7):
        if other is None or f"{value:.{d}f}" != f"{other:.{d}f}":
            return f"{value:.{d}f}"
    return f"{value:.6g}"


def _wall(name):
    side = (name or "").removeprefix("wall-")
    return f"{side} wall" if side else "a wall"


def _robot(system):
    robot, _, conf = system["id"].partition("/")
    return f"{robot} · {conf}" if conf else robot


def _worse(a, b):
    """The worse of two failures of one check."""
    if a["check"] == "hallway-fall":
        return a if a["observed"] < b["observed"] else b
    if a["observed"] is None or b["observed"] is None:
        return a if a["observed"] is None else b
    return a if a["observed"] > b["observed"] else b


def _describe(f):
    s = f" (seed {f['seed']})" if f["seed"] is not None else ""
    if f["check"] == "hallway-wall-contact":
        return f"touched {_wall(f.get('wall'))} at {_fmt(f['t'])} s{s}"
    if f["observed"] is None:
        return f"not reached by {_fmt(f['limit'])} s{s}"
    op = "<" if f["check"] == "hallway-fall" else ">"
    obs, lim = _fmt(f["observed"], f["limit"]), _fmt(f["limit"], f["observed"])
    at = f" at {_fmt(f['t'])} s" if f["unit"] != "s" else ""
    return f"{obs} {op} {lim} {f['unit']}{at}{s}"


def why_failed(run, limit=3):
    """Each failing seed counted once, under its first failure (earliest t, then check order)."""
    first = {}
    for f in run["failures"]:
        key = (f["t"] if f["t"] is not None else float("inf"), ORDER.index(f["check"]))
        if f["seed"] not in first or key < first[f["seed"]][0]:
            first[f["seed"]] = (key, f)
    groups = {}
    for _, f in first.values():
        groups.setdefault(f["check"], []).append(f)
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), ORDER.index(kv[0])))
    lines = []
    for check, items in ranked[:limit]:
        worst = items[0]
        for f in items[1:]:
            worst = _worse(worst, f)
        lines.append(f"- {len(items)}× {WHAT[check]} — worst: {_describe(worst)}")
    rest = sum(len(items) for _, items in ranked[limit:])
    if rest:
        lines.append(f"- {rest}× other first failures; see the per-seed details")
    return lines


def _interval(w):
    return f"{round(w[0] * 100)}–{round(w[1] * 100)}%"


def _verdict(run):
    subject = f"{_robot(run['system'])} {'passes' if run['grade'] == PASS else 'does not pass'}"
    if run["grade"] in (PASS, FAIL):
        return (
            f"{subject} {run['spec']['capability']}: {run['k']} of {run['n']} trials passed, "
            f"{run['required_passes']} needed."
        )
    return f"{_robot(run['system'])} cannot be graded on {run['spec']['capability']}: {GRADE[run['grade']]}."


def markdown(report, links=None):
    """PR-comment summary in Art's layout (review of 2026-11-01); update one comment in place."""
    runs = report.get("summaries", [])
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    lines = [MARKER]
    if runs:
        plans = {canonical_plan(results[s["result_ids"][0]]) for s in runs}
        for plan in sorted(plans):
            lines.append(f"## {plan}")
        lines += [
            "",
            "| Robot · configuration | Grade | Passed | 95% interval | Needs |",
            "|---|---|---|---|---|",
        ]
        for s in runs:
            lines.append(
                f"| {_robot(s['system'])} {s['system']['version']} | **{GRADE[s['grade']]}** | "
                f"{s['k']}/{s['n']} | {_interval(s['wilson95'])} | {s['required_passes']} |"
            )
        lines.append("")
        lines += [_verdict(s) for s in runs]
        for s in runs:
            why = why_failed(s)
            if why:
                lines += ["", f"**Why runs failed · {_robot(s['system'])}**", *why]
        for s in runs:
            assets = [(r, results[r]["provenance"].get("assets")) for r in s["result_ids"]]
            assets = [(r, a) for r, a in assets if isinstance(a, dict) and a.get("thumbnail")]
            if assets:
                status = {d["result_id"]: d["status"] for d in report["decisions"]}
                fails = [x for x in assets if status[x[0]] == FAIL]
                passes = [x for x in assets if status[x[0]] == PASS]
                cells = [
                    f"[![{label} {r}]({a['thumbnail']})]({a.get('clip', a['thumbnail'])})"
                    for label, pick in (("worst fail", fails), ("pass", passes))
                    if pick
                    for r, a in pick[:1]
                ]
                lines += ["", f"{_robot(s['system'])}: " + " ".join(cells)]
        if links:
            row = [
                f"[{label}]({links[key]})"
                for key, label in (
                    ("report", "Full report"),
                    ("clips", "All clips"),
                    ("lock_diff", "Lock diff"),
                )
                if links.get(key)
            ]
            if row:
                lines += ["", " · ".join(row)]
        for s in runs:
            lines += [
                "",
                f"<details><summary>Per-seed failures · {_robot(s['system'])}</summary>",
                "",
            ]
            if not s["failures"]:
                lines.append("No failed checks.")
            by_check = {}
            for f in s["failures"]:
                by_check.setdefault(f["check"], []).append(f)
            for check in [c for c in ORDER if c in by_check]:
                items = sorted(
                    by_check[check], key=lambda f: (f["seed"] is None, f["seed"] or 0, f["t"] or 0)
                )
                lines += [f"**{check}**", ""]
                if check == "hallway-wall-contact":
                    lines += ["| Seed | Contact |", "|---|---|"]
                    lines += [
                        f"| {f['seed']} | touched {_wall(f.get('wall'))} at {_fmt(f['t'])} s |"
                        for f in items
                    ]
                else:
                    unit = items[0]["unit"]
                    lines += [
                        f"| Seed | Observed ({unit}) | Limit ({unit}) | t (s) |",
                        "|---|---|---|---|",
                    ]
                    lines += [
                        f"| {f['seed']} | {_fmt(f['observed'], f['limit'])} | "
                        f"{_fmt(f['limit'], f['observed'])} | {_fmt(f['t'])} |"
                        for f in items
                    ]
                lines.append("")
            lines.append("</details>")
    others = [
        d for d in report["decisions"] if not any(d["result_id"] in s["result_ids"] for s in runs)
    ]
    if others:
        lines += ["", "| Result | Grade | Reason |", "|---|---|---|"]
        lines += [
            f"| `{d['result_id']}` | **{GRADE[d['status']]}** | {d['reason'].replace('|', '/')} |"
            for d in others
        ]
    catalogs = sorted({f"{s['spec']['tag']} @ {s['spec']['commit'][:7]}" for s in runs}) or sorted(
        {f"{r['spec']['tag']} @ {r['spec']['commit'][:7]}" for r in results.values()}
    )
    footer = [f"Policy {report['policy']}", "catalog " + ", ".join(catalogs)]
    footer += [f"run {s['run_id']}" for s in runs if s.get("run_id")]
    footer += ["stored decisions, no regrading", "simulation evidence, not hardware validation"]
    lines += ["", "<sub>" + " · ".join(footer) + "</sub>"]
    notes = sorted({s["prototype"] for s in runs if s.get("prototype")})
    if notes:
        lines.append("<sub>" + " ".join(notes) + "</sub>")
    return "\n".join(lines) + "\n"


def canonical_plan(result):
    """Header: scenario, N, command speed, pass bar and the lock it came from."""
    prov = result["provenance"]
    plan = prov.get("plan") or {}
    spec = result["spec"]
    parts = [f"{spec['capability']}@{spec['revision']}", f"N={plan.get('trials', '?')}"]
    if "command_speed" in plan:
        parts.append(f"{_fmt(plan['command_speed'])} m/s")
    if "required_passes" in plan:
        parts.append(f"pass bar {plan['required_passes']}/{plan.get('trials', '?')}")
    lock = prov.get("lock")
    if isinstance(lock, dict) and isinstance(lock.get("sha256"), str):
        parts.append(f"`{lock.get('path', 'verification.lock.json')} @ {lock['sha256'][:7]}`")
    return " · ".join(parts)
