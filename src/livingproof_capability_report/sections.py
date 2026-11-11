"""Hallway HTML sections (#39 header, #40 context card, failure section and trial grid).

Everything shown is a stored value: the bundle's top-level ``description`` (specs v1.9.0
text), each result's ``provenance.limits`` and per-trial ``decision`` (``primary_failure``,
``secondary_failures``), and the assessment run's ``failure_summary`` and ``worst``
(capability-verifier v1.12.0). Nothing is counted, ranked, derived or re-graded here: a
field that an older bundle lacks is left out with a short note saying which producer adds
it, rather than being recomputed.
"""

import html
import re

from . import hallway

PASS, FAIL = hallway.PASS, hallway.FAIL

# Which stored limit backs each check (display only; values come from provenance.limits).
LIMIT_FOR = {
    "hallway-exit-reached": ("time_limit", "exit_segment"),
    "hallway-lateral-limit": ("lateral_limit",),
    "hallway-fall": ("fall_height",),
    "hallway-wall-contact": (),
}
CHECK_NAME = {
    "hallway-exit-reached": "Exit reached",
    "hallway-lateral-limit": "Lateral drift",
    "hallway-wall-contact": "Wall contact",
    "hallway-fall": "Base height (fall)",
}
WORST = {"max": "highest", "min": "lowest"}
WALLS_NOTE = (
    "The hallway walls in the MuJoCo simulation are visual only: they do not collide, so "
    "a robot that drifts can pass into and through them. Touching or entering a wall is a "
    "failed check. From livingproof-sim-mujoco v1.8.3, a trial ends "
    "<code>left_hallway</code> as soon as any robot part reaches past a wall's outer face, "
    "and that trial does not reach the exit."
)
WALLS_SHORT = (
    "MuJoCo hallway walls are visual only (no collision); from sim-mujoco v1.8.3 a trial "
    "ends left_hallway past a wall's outer face"
)


def visual_walls(report, summary):
    """True when the run's stored provenance names the MuJoCo simulator on hallway-open."""
    if _dict(summary.get("environment")).get("id") != "hallway-open":
        return False
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    return any(
        _dict(
            _dict(_dict(results.get(r, {}).get("provenance")).get("simulator")).get("simulator")
        ).get("id")
        == "mujoco"
        for r in summary.get("result_ids", [])
    )


def esc(value):
    return html.escape(str(value), quote=True)


def num(value):
    """A stored number as written, unrounded (27.0 reads 27)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def stored_run(report, summary):
    """The bundle's assessment run behind a report summary (same result_ids), or {}."""
    runs = _dict(report["source_bundle"].get("assessment")).get("runs")
    for run in _list(runs):
        if isinstance(run, dict) and run.get("result_ids") == summary.get("result_ids"):
            return run
    return {}


def run_limits(report, summary):
    """The run's provenance.limits when every trial stores the same ones, else None."""
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    found = [
        _dict(results[r].get("provenance")).get("limits")
        for r in summary.get("result_ids", [])
        if r in results
    ]
    if not found or not isinstance(found[0], dict) or any(x != found[0] for x in found):
        return None
    return found[0]


def any_limits(report, summary):
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    return any(
        isinstance(_dict(results.get(r, {}).get("provenance")).get("limits"), dict)
        for r in summary.get("result_ids", [])
    )


def words(f):
    """One stored failure in words; observed and limit as stored, two decimals."""
    fmt = hallway._fmt
    t = f" at {fmt(f['t'])} s" if f.get("t") is not None else ""
    check = f.get("check")
    if check == "hallway-wall-contact":
        depth = f" ({fmt(f['observed'], decimals=3)} m in)" if f.get("observed") else ""
        side = (f.get("wall") or "").removeprefix("wall-")
        return f"touched {'the ' + side + ' wall' if side else 'a wall'}{t}{depth}"
    if check == "hallway-exit-reached":
        via = f.get("via")
        if isinstance(via, str) and via.startswith("wall-"):
            return f"left the hallway through the {via.removeprefix('wall-')} wall{t}"
        if via == "exit-outside-segment":
            return f"crossed the exit line outside the exit segment{t}"
        if f.get("observed") is None:
            return f"did not reach the exit within {fmt(f.get('limit'))} s"
        return f"reached the exit at {fmt(f['observed'], f.get('limit'))} s > {fmt(f.get('limit'), f['observed'])} s"
    obs, lim = f.get("observed"), f.get("limit")
    if obs is None:
        return f"{check} not measured"
    if check == "hallway-lateral-limit":
        return f"drifted {fmt(obs, lim)} m > {num(lim)} m from the centreline{t}"
    if check == "hallway-fall":
        return f"base dropped to {fmt(obs, lim)} m < {num(lim)} m{t}"
    return f"{check}: {fmt(obs, lim)} {f.get('unit', '')} vs {fmt(lim, obs)}{t}"


def _seed(result, decision):
    seed = _dict(result.get("original_result")).get("seed")
    if seed is None:
        for f in _list(decision.get("failures")):
            if isinstance(f, dict) and f.get("seed") is not None:
                return f["seed"]
    return seed


def _fill(template, values):
    """Fill {name} placeholders from ``values`` only; others stay as written."""
    return re.sub(
        r"\{(\w+)\}",
        lambda m: values[m.group(1)] if m.group(1) in values else m.group(0),
        template,
    )


def _limit_line(name, limit):
    if not isinstance(limit, dict):
        return None
    inputs = _dict(limit.get("inputs"))
    shown = ", ".join(
        f"{k} {num(v)}" for k, v in inputs.items() if not k.endswith("_source") and v != {}
    )
    if "value" in limit:
        head = f"{num(limit['value'])} {limit.get('unit', '')}".strip()
    elif "met" in limit:
        head = "met" if limit["met"] is True else "NOT met"
    else:
        return None
    formula = f" = {limit['formula']}" if limit.get("formula") else ""
    return f"{name}: {head}{formula}" + (f" ({shown})" if shown else "")


def header(report, summary, description):
    """#39 verdict header: robot/config/mission in words, grade, k of N, bar, interval,
    the expected sentence (spec) and the actual summary (verifier)."""
    grade = summary["grade"]
    mission = _dict(_dict(description).get("mission"))
    world = _dict(_dict(description).get("world"))
    robot = hallway._robot(summary["system"])
    what = mission.get("title") or _dict(summary.get("spec")).get("capability") or "capability"
    where = world.get("title") or _dict(summary.get("environment")).get("id")
    title = f"{robot} {summary['system'].get('version', '')}".strip() + f" — {what}"
    if where:
        title += f" in the {where}" if world.get("title") else f" on {where}"
    interval = summary.get("wilson95")
    facts = [
        f"{summary['k']} of {summary['n']} trials passed; overall {grade}",
        f"{summary['required_passes']} of {summary['n']} required",
    ]
    if isinstance(interval, list) and len(interval) == 2:
        facts.append(
            f"95% interval {hallway._interval(interval)} (Wilson, stored, rounded to whole percent)"
        )
    out = [
        f"<section class='verdict' data-grade='{esc(grade)}'>",
        f"<p class='robot'>{esc(title)}</p>",
        f"<p class='grade'><strong>{esc(grade)}</strong></p>",
        "<ul class='facts'>" + "".join(f"<li>{esc(x)}</li>" for x in facts) + "</ul>",
    ]
    if mission.get("description"):
        out.append(f"<p><strong>Expected:</strong> {esc(mission['description'])}</p>")
    else:
        out.append(
            "<p class='muted'>Expected: no scenario description stored in this bundle "
            "(capability-verifier v1.12.0 with specs v1.9.0 adds it).</p>"
        )
    out.append(f"<p><strong>Actual:</strong> {esc(actual(report, summary))}</p>")
    out.append("</section>")
    return "".join(out)


def why_lines(report, summary):
    """Markdown bullets from the stored failure_summary and worst values, or None."""
    run = stored_run(report, summary)
    fs = _dict(run.get("failure_summary"))
    if not fs:
        return None
    worst = {w.get("check"): w for w in _list(run.get("worst")) if isinstance(w, dict)}
    ids = summary.get("result_ids") or []
    one = hallway.repeat_name(report=report, result_ids=ids)
    many = hallway.repeat_name(report=report, result_ids=ids, plural=True)
    lines = []
    for b in _list(fs.get("by_primary")):
        if not isinstance(b, dict):
            continue
        w = worst.get(b.get("check"), {})
        tail = ""
        if w.get("observed") is not None:
            tail = f" — worst {num(w['observed'])} {w.get('unit', '')} ({one} {w.get('seed')})"
        seeds = ", ".join(str(x) for x in _list(b.get("seeds")))
        lines.append(
            f"- {b.get('count')}× {hallway.WHAT.get(b.get('check'), b.get('check'))} "
            f"(primary) — {many} {seeds}{tail}"
        )
    return lines


def actual(report, summary):
    fs = _dict(stored_run(report, summary).get("failure_summary"))
    if not fs:
        return hallway._verdict(summary)
    failed = fs.get("failed_trials")
    if not failed:
        return f"No trial failed: {summary['k']} of {summary['n']} trials passed."
    ids = summary.get("result_ids") or []
    parts = []
    for b in _list(fs.get("by_primary")):
        if not isinstance(b, dict):
            continue
        listed = _list(b.get("seeds"))
        name = hallway.repeat_name(report=report, result_ids=ids, plural=len(listed) != 1)
        parts.append(
            f"{hallway.WHAT.get(b['check'], b['check'])} in {b['count']} "
            f"({name} {', '.join(str(s) for s in listed)})"
        )
    text = f"{failed} of {summary['n']} trials failed"
    if parts:
        text += "; primary failure: " + "; ".join(parts)
    return text + "."


def context(report, summary, description):
    """#40 test context card: mission, criteria with limits, world, robot, derivation."""
    d = _dict(description)
    mission, world, rules = _dict(d.get("mission")), _dict(d.get("world")), _dict(d.get("limits"))
    limits = run_limits(report, summary)
    robot = hallway._robot(summary["system"])
    out = ["<section class='context'><h3>Test context</h3>"]
    if not d:
        out.append(
            "<p class='muted'>This bundle carries no scenario description "
            "(capability-verifier v1.12.0 with specs v1.9.0 adds the mission and world "
            "text).</p>"
        )
    items = []
    if mission:
        items.append(
            (
                "Mission",
                " — ".join(x for x in (mission.get("title"), mission.get("description")) if x),
            )
        )
    criteria = []
    for c in _list(mission.get("success_criteria")):
        if not isinstance(c, dict):
            continue
        lines = [
            _limit_line(k.replace("_", " "), _dict(limits).get(k))
            for k in LIMIT_FOR.get(c.get("evaluator"), ())
        ]
        lines = [x for x in lines if x]
        criteria.append(
            f"<li>{esc(c.get('text', c.get('evaluator', '')))}"
            + "".join(f"<br><span class='limit'>{esc(x)}</span>" for x in lines)
            + "</li>"
        )
    out.append("<dl>")
    out += [f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items if v]
    if criteria:
        out.append("<dt>Success criteria</dt><dd><ul>" + "".join(criteria) + "</ul></dd>")
    if mission.get("grading"):
        out.append(f"<dt>Grading</dt><dd>{esc(mission['grading'])}</dd>")
    if mission.get("time_limit_explained"):
        out.append(f"<dt>Time limit</dt><dd>{esc(mission['time_limit_explained'])}</dd>")
    if world:
        dims = ", ".join(
            f"{k.replace('_', ' ')} {num(v['value'])} {v.get('unit', '')}".strip()
            for k, v in _dict(world.get("dimensions")).items()
            if isinstance(v, dict) and "value" in v
        )
        text = " — ".join(x for x in (world.get("title"), world.get("description")) if x)
        out.append(
            f"<dt>World</dt><dd>{esc(text)}"
            + (f"<br><span class='limit'>{esc(dims)}</span>" if dims else "")
            + "</dd>"
        )
    system = summary["system"]
    out.append(
        f"<dt>Robot and configuration</dt><dd>{esc(robot)} {esc(system.get('version', ''))}</dd>"
    )
    if limits:
        lat = _dict(limits.get("lateral_limit"))
        inputs = _dict(lat.get("inputs"))
        sentence = _dict(rules.get("lateral_limit")).get("sentence")
        if sentence and "value" in lat:
            text = _fill(
                sentence,
                {
                    "robot": robot,
                    "value": num(lat["value"]),
                    **{k: num(v) for k, v in inputs.items() if k in ("clear_width", "robot_width")},
                },
            )
        else:
            text = _limit_line("Lateral limit", lat) or ""
        if inputs.get("robot_width_source"):
            text += f" Robot width from {inputs['robot_width_source']}."
        if text:
            out.append(f"<dt>Lateral limit</dt><dd>{esc(text)}</dd>")
        fits = _dict(limits.get("fits_width"))
        if fits.get("detail") or "met" in fits:
            out.append(
                f"<dt>Fits the hallway</dt><dd>{esc(fits.get('detail') or _limit_line('fits width', fits))}</dd>"
            )
        others = [
            _limit_line(k.replace("_", " "), v)
            for k, v in limits.items()
            if k not in ("lateral_limit", "fits_width") and not mission
        ]
        others = [x for x in others if x]
        if others:
            out.append("<dt>Stored limits</dt><dd>" + "<br>".join(esc(x) for x in others) + "</dd>")
    elif any_limits(report, summary):
        out.append(
            "<dt>Limits</dt><dd class='muted'>The trials in this run store different "
            "limits; see each result's provenance.limits in the full report.</dd>"
        )
    else:
        out.append(
            "<dt>Limits</dt><dd class='muted'>No resolved limits stored for this run "
            "(capability-verifier v1.12.0 adds provenance.limits).</dd>"
        )
    out.append("</dl>")
    if visual_walls(report, summary):
        out.append(f"<p class='note'><strong>Note:</strong> {WALLS_NOTE}</p>")
    out.append("</section>")
    return "".join(out)


def failures(report, summary):
    """#40 failure section: stored primary-failure counts and worst values."""
    run = stored_run(report, summary)
    fs = _dict(run.get("failure_summary"))
    worst = _list(run.get("worst"))
    limits = _dict(run_limits(report, summary))
    ids = summary.get("result_ids") or []
    many = hallway.repeat_name(report=report, result_ids=ids, plural=True, capital=True)
    one = hallway.repeat_name(report=report, result_ids=ids, capital=True)
    out = ["<section class='failures'><h3>Why trials failed</h3>"]
    if fs:
        out.append(
            f"<p>{esc(fs.get('failed_trials'))} of {esc(summary['n'])} trials failed. "
            "Each failed trial is counted once, under the primary failure the verifier "
            "stored; its other failures are listed with it below.</p>"
        )
        rows = [
            f"<tr><td>{esc(hallway.WHAT.get(b.get('check'), b.get('check')))}</td>"
            f"<td>{esc(b.get('count'))}</td>"
            f"<td>{esc(', '.join(str(s) for s in _list(b.get('seeds'))))}</td></tr>"
            for b in _list(fs.get("by_primary"))
            if isinstance(b, dict)
        ]
        if rows:
            out.append(
                "<table class='primary'><thead><tr><th>Primary failure</th><th>Trials</th>"
                f"<th>{many}</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            )
    else:
        out.append(
            "<p class='muted'>No failure summary stored in this bundle "
            "(capability-verifier v1.12.0 adds failure_summary); each trial's stored "
            "reason is shown in the trial grid.</p>"
        )
    if worst:
        rows = []
        for w in worst:
            if not isinstance(w, dict):
                continue
            check = w.get("check")
            if w.get("observed") is None:
                value = "none observed"
                if check == "hallway-exit-reached" and w.get("missing") is not None:
                    value = f"no exit time in {w['missing']} of {summary['n']} trials"
            else:
                value = f"{num(w['observed'])} {w.get('unit', '')}".strip()
                if w.get("wall"):
                    value += f" ({hallway._wall(w['wall'])})"
                if check == "hallway-exit-reached" and w.get("missing"):
                    value += f"; no exit time in {w['missing']} of {summary['n']} trials"
            lim = [
                f"{num(limits[k]['value'])} {limits[k].get('unit', '')}".strip()
                for k in LIMIT_FOR.get(check, ())[:1]
                if isinstance(limits.get(k), dict) and "value" in limits[k]
            ]
            if check == "hallway-wall-contact":
                lim = ["any contact fails"]
            rows.append(
                f"<tr><td>{esc(CHECK_NAME.get(check, check))}</td>"
                f"<td>{esc(WORST.get(w.get('worst'), w.get('worst', '')))}</td><td>{esc(value)}</td>"
                f"<td>{esc('' if w.get('seed') is None else w['seed'])}</td>"
                f"<td>{esc('' if w.get('t') is None else hallway._fmt(w['t']) + ' s')}</td>"
                f"<td>{esc(', '.join(lim))}</td></tr>"
            )
        out.append(
            "<h4>Worst value per check (all trials, as stored)</h4>"
            "<table class='worst'><thead><tr><th>Check</th><th>Worst is</th><th>Value</th>"
            f"<th>{one}</th><th>Time</th><th>Limit</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    elif fs:
        out.append("<p class='muted'>No worst values stored for this run.</p>")
    out.append("</section>")
    return "".join(out)


def trials(report, summary):
    """#40 trial grid: one row per non-passing trial, passes as chips; no JSON column."""
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    decisions = {d["result_id"]: d for d in report["decisions"]}
    stored = _dict(report.get("evidence_links"))
    per_seed = {}
    for e in _list(stored.get("links")):
        if isinstance(e, dict) and "seed" in e:
            per_seed.setdefault(e["seed"], []).append(e)
    rows, chips = [], []
    for rid in summary.get("result_ids", []):
        result, decision = results.get(rid, {}), decisions.get(rid, {})
        bundle_decision = _dict(result.get("decision"))
        seed = _seed(result, decision)
        label = f"{hallway.repeat_name(result)} {seed}" if seed is not None else rid
        links = "".join(
            f" <a href='{esc(e['url'])}'>{esc(e['label'])}</a>" for e in per_seed.get(seed, [])
        )
        if decision.get("status") == PASS:
            chips.append(f"<li class='chip pass' title='{esc(rid)}'>{esc(label)}{links}</li>")
            continue
        primary = bundle_decision.get("primary_failure")
        if isinstance(primary, dict):
            main = words(primary)
            rest = [
                words(f)
                for f in _list(bundle_decision.get("secondary_failures"))
                if isinstance(f, dict)
            ]
            then = ("then " + "; then ".join(rest)) if rest else ""
        else:
            main = decision.get("reason", "")
            then = "no primary failure stored (capability-verifier v1.12.0 adds it)"
        rows.append(
            f"<tr><td title='{esc(rid)}'>{esc(label)}</td><td>{esc(decision.get('status', ''))}</td>"
            f"<td>{esc(main)}<br><span class='muted'>{esc(then)}</span></td>"
            f"<td>{links.strip()}</td></tr>"
        )
    out = [f"<section class='trials'><h3>Trials · {esc(hallway._robot(summary['system']))}</h3>"]
    if rows:
        out.append(
            "<table class='failed'><thead><tr><th>Trial</th><th>Status</th>"
            "<th>Primary failure, then the others</th><th>Evidence</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    if chips:
        out.append("<p>Passed:</p><ul class='chips'>" + "".join(chips) + "</ul>")
    out.append("</section>")
    return "".join(out)
