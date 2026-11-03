"""Walk-hallway rendering: the markdown report from stored decisions and run assessments.

Each result is one seeded trial. Its status, failures and the run's k of N, interval and
grade are the capability verifier's (bundle 1.1.0); nothing here grades. Failed checks
carry structured fields {check, observed, limit, unit, t, seed, wall}.
"""

PASS, FAIL, INSUFFICIENT, INCOMPATIBLE = "PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "INCOMPATIBLE"
EVALUATORS = {
    "hallway-exit-reached": "1.0.0",
    "hallway-lateral-limit": "1.0.0",
    "hallway-wall-contact": "1.0.0",
    "hallway-fall": "1.0.0",
}


MARKER = "<!-- livingproof-verification -->"
GRADE = {
    PASS: "✅ PASS",
    FAIL: "❌ FAIL",
    INSUFFICIENT: "⚠️ INSUFFICIENT EVIDENCE",
    INCOMPATIBLE: "⚠️ INCOMPATIBLE",
}
ORDER = list(EVALUATORS)


def _label(value, where):
    """Display label for a stored grade or status; a malformed one is a clear error."""
    if not isinstance(value, str) or value not in GRADE:
        raise ValueError(f"Report {where} is {value!r}; expected one of {', '.join(GRADE)}")
    return GRADE[value]


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
    return f"{_robot(run['system'])} cannot be graded on {run['spec']['capability']}: {_label(run['grade'], 'summary grade')}."


def markdown(report, links=None):
    """PR-comment summary in Art's layout (review of 2026-11-01); update one comment in place."""
    runs = report.get("summaries", [])
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    lines = [MARKER]
    if runs:
        from . import sections

        plans = {canonical_plan(results[s["result_ids"][0]]) for s in runs}
        for plan in sorted(plans):
            lines.append(f"## {plan}")
        # #39 header: verdict, expected (spec text) and actual (verifier) above the table.
        lines += ["", *[_verdict(s) for s in runs]]
        mission = (report["source_bundle"].get("description") or {}).get("mission") or {}
        if isinstance(mission, dict) and mission.get("description"):
            lines += ["", f"**Expected:** {mission['description']}"]
        if any(sections.stored_run(report, s).get("failure_summary") for s in runs):
            lines += [""] + [
                f"**Actual · {_robot(s['system'])}:** {sections.actual(report, s)}" for s in runs
            ]
        lines += [
            "",
            "| Robot · configuration | Grade | Passed | 95% interval | Needs |",
            "|---|---|---|---|---|",
        ]
        for s in runs:
            lines.append(
                f"| {_robot(s['system'])} {s['system']['version']} | **{_label(s['grade'], 'summary grade')}** | "
                f"{s['k']}/{s['n']} | {_interval(s['wilson95'])} | {s['required_passes']} |"
            )
        for s in runs:
            why = sections.why_lines(report, s)
            if why is None:  # bundles before capability-verifier v1.12.0
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
        from . import links as evidence_links

        for s in runs:
            found = evidence_links.lines(report, s)
            if found:
                head = f"**Evidence links · {_robot(s['system'])}**" if len(runs) > 1 else None
                lines += ["", *([head] if head else []), *found]
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
    from . import sections

    if any(sections.visual_walls(report, s) for s in runs):
        footer.append(sections.WALLS_SHORT)
    footer += ["stored decisions, no regrading", "simulation evidence, not hardware validation"]
    lines += ["", "<sub>" + " · ".join(footer) + "</sub>"]
    notes = sorted({s["prototype"] for s in runs if s.get("prototype")})
    if notes:
        lines += ["", "<sub>" + " ".join(notes) + "</sub>"]  # own paragraph, one line
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
