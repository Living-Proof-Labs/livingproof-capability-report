"""Scenario-step success view for the HTML report.

Each ring is the share of trials whose stored assessment for that step is PASS.
The run ring is the stored k of n. Nothing here grades. The stored Wilson interval,
when the run carries one, is a muted line under the run rate, not a ring or a headline.
A run whose assessment says the repeats were compared is one outcome plus the stored
reproducibility statement. It is not a sample, so it has no success rate, no step
ring and no interval. Trial numbers are the stored seed. Duration comes from
observation ``duration_s`` when that file is readable beside the manifest.
"""

import html
import json
from pathlib import Path

from . import hallway
from . import html_theme
from .core import safe_relative

# How a known check's stored details are read. The visible name comes from the
# feature spec's success_criteria text, not from this table.
_KIND = {
    "hallway-lateral-limit": "lateral",
    "hallway-wall-contact": "wall",
    "hallway-exit-reached": "exit",
    "hallway-fall": "fall",
}
_LIMIT_KEY = {"lateral": "lateral_limit", "exit": "time_limit", "fall": "fall_height"}
_DEFAULT_UNIT = {"lateral": "m", "exit": "s", "fall": "m"}
_TIME_KIND = {
    "lateral": ("Largest offset", "First exceeded"),
    "wall": ("Closest clearance", "First contact"),
    "exit": ("Exit time", "First missed"),
    "fall": ("Lowest height", "First fell"),
}
# Wall clearance the verifier records when the robot never enters the search band.
_CAPPED_CLEARANCE_M = 0.25
_CAPPED_TIME_S = 0.0

CHECK = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' aria-hidden='true' "
    "focusable='false'><path d='M3.2 8.2 6.1 11.1 12.8 4.4' fill='none' stroke='currentColor' "
    "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/></svg>"
)


def criterion_names(description):
    """Step labels from the feature spec. Missing criteria are omitted, not invented."""
    mission = description.get("mission") if isinstance(description, dict) else None
    names = {}
    if not isinstance(mission, dict):
        return names
    for item in mission.get("success_criteria") or []:
        if not isinstance(item, dict):
            continue
        ident, text = item.get("evaluator"), item.get("text")
        if isinstance(ident, str) and ident and isinstance(text, str) and text.strip():
            names[ident] = text.strip()
    return names


def esc(value):
    return html.escape(str(value), quote=True)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fmt_m(value):
    """Metres as stored, without binary junk; keep a decimal so 0 reads 0.0."""
    if value is None:
        return "—"
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def fmt_s(value):
    if value is None:
        return "—"
    return f"{float(value):.2f} s"


def fmt_num(value):
    if not _number(value):
        return "—" if value is None else str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def contact_word(count):
    if not _number(count):
        return "—"
    count = int(count)
    return "1 contact" if count == 1 else f"{count} contacts"


def durations_by_result(bundle, root):
    """``duration_s`` from each result's evidence JSON, when the file is present.

    Missing, unreadable or non-observation files are skipped. Symlinks are not followed.
    """
    found = {}
    if not isinstance(bundle, dict) or root is None:
        return found
    root = Path(root).resolve()
    for result in bundle.get("results") or []:
        if not isinstance(result, dict) or "id" not in result:
            continue
        for item in result.get("evidence") or []:
            duration = _duration(root, item)
            if duration is not None:
                found[result["id"]] = duration
                break
    return found


def _duration(root, item):
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        return None
    try:
        relative = safe_relative(item["path"])
    except ValueError:
        return None
    file = root.joinpath(*relative.parts)
    if any(path.is_symlink() for path in [file, *file.parents] if path != root.parent):
        return None
    if not file.is_file():
        return None
    try:
        if not file.resolve().is_relative_to(root):
            return None
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    duration = data.get("duration_s") if isinstance(data, dict) else None
    return duration if _number(duration) else None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _results_for(report, summary):
    by_id = {
        result["id"]: result
        for result in report["source_bundle"]["results"]
        if isinstance(result, dict) and "id" in result
    }
    return [by_id[rid] for rid in summary.get("result_ids") or [] if rid in by_id]


def _seed(result):
    return _dict(result.get("original_result")).get("seed")


def _assessments(result):
    found = {}
    for item in result.get("assessments") or []:
        if isinstance(item, dict) and item.get("evaluator"):
            found[item["evaluator"]] = item
    return found


def _unit(kind, limits, details):
    key = _LIMIT_KEY.get(kind)
    entry = _dict(limits).get(key) if key else None
    if isinstance(entry, dict) and isinstance(entry.get("unit"), str) and entry["unit"]:
        return entry["unit"]
    if kind == "wall":
        for failure in details.get("failures") or []:
            unit = failure.get("unit") if isinstance(failure, dict) else None
            if isinstance(unit, str) and unit:
                return unit
        return "m"
    return _DEFAULT_UNIT.get(kind, "")


def _capped(kind, status, margin, time):
    return (
        kind == "wall"
        and status == "PASS"
        and _number(margin)
        and _number(time)
        and abs(float(margin) - _CAPPED_CLEARANCE_M) < 1e-9
        and abs(float(time) - _CAPPED_TIME_S) < 1e-9
    )


def _measure(kind, value, unit):
    if value is None:
        return "—"
    if kind == "exit" or unit == "s":
        return fmt_s(value)
    if unit:
        return f"{fmt_m(value)} {esc(unit)}"
    return fmt_m(value)


def _observed(step, details, status, limits):
    kind = step["kind"]
    observed = details.get("observed")
    limit = details.get("threshold")
    margin = details.get("margin")
    if kind == "wall":
        return _wall_observed(details, status, limits, observed, limit, margin)
    unit = _unit(kind, limits, details)
    if observed is None and limit is None:
        return "—"
    return f"{_measure(kind, observed, unit)} (limit {_measure(kind, limit, unit)})"


def _deepest_time(details, depth):
    """Time of the deepest recorded contact, only when that contact stores one."""
    best = None
    moment = None
    for failure in details.get("failures") or []:
        if not isinstance(failure, dict) or not _number(failure.get("observed")):
            continue
        observed = abs(float(failure["observed"]))
        if best is None or observed > best:
            best = observed
            moment = failure.get("t") if _number(failure.get("t")) else None
    if best is None or abs(best - depth) > 1e-4:
        return None
    return moment


def _wall_observed(details, status, limits, observed, limit, margin):
    if observed is None:
        body = "—"
    else:
        body = esc(contact_word(observed))
        if status != "PASS" and limit is not None:
            body += f" (limit {esc(fmt_num(limit))})"
    unit = esc(_unit("wall", limits, details))
    if _capped("wall", status, margin, details.get("time")):
        body += (
            "<span class='margin-note'>Capped at "
            f"{esc(fmt_m(margin))} m, not a real measurement</span>"
        )
    elif status == "PASS" and _number(margin) and float(margin) >= 0:
        body += f"<span class='margin-note'>Closest clearance {esc(fmt_m(margin))} {unit}</span>"
    elif status != "PASS" and _number(margin):
        # The stored margin is the deepest penetration, not the first contact.
        depth = abs(float(margin))
        text = f"Deepest penetration {esc(fmt_m(depth))} {unit}"
        moment = _deepest_time(details, depth)
        if moment is not None:
            text += f" at {esc(fmt_s(moment))}"
        body += f"<span class='margin-note'>{text}</span>"
    return body


def _time(step, details, status):
    moment = details.get("time")
    if not _number(moment):
        return "—"
    if _capped(step["kind"], status, details.get("margin"), moment):
        kind = "Capped, not a real measurement"
    else:
        passed, failed = _TIME_KIND.get(step["kind"], ("Extreme value", "First not met"))
        kind = passed if status == "PASS" else failed
    return f"{esc(fmt_s(moment))}<span class='time-kind'>{esc(kind)}</span>"


def _verdict(status):
    if status == "PASS":
        return f"<span class='step-result step-result-success'>{CHECK} Success</span>"
    if status == "INSUFFICIENT_EVIDENCE":
        return "<span class='step-result step-result-neutral'>Insufficient evidence</span>"
    if status == "FAIL":
        return "<span class='step-result step-result-quiet'>Not met</span>"
    return f"<span class='step-result step-result-neutral'>{esc(status or '—')}</span>"


def _trial_rows(step, trials, durations):
    rows = []
    ordered = sorted(
        trials, key=lambda item: (_seed(item[0]) is None, _seed(item[0]) or 0, item[0].get("id", ""))
    )
    for result, assessments in ordered:
        seed = _seed(result)
        label = "—" if seed is None else esc(seed)
        duration = durations.get(result.get("id"))
        duration_cell = esc(fmt_s(duration)) if _number(duration) else "—"
        assessment = assessments.get(step["id"])
        if not assessment:
            rows.append(_empty_row(label, duration_cell))
            continue
        details = _dict(_dict(assessment.get("provenance")).get("details"))
        status = assessment.get("status")
        limits = _dict(_dict(result.get("provenance")).get("limits"))
        klass = " class='is-success'" if status == "PASS" else ""
        rows.append(
            f"<tr{klass}>"
            f"<td data-label='Trial'>{label}</td>"
            f"<td data-label='Result'>{_verdict(status)}</td>"
            "<td class='obs' data-label='Observed vs limit'>"
            f"<span class='cell-value'>{_observed(step, details, status, limits)}</span></td>"
            f"<td data-label='Time'><span class='cell-value'>{_time(step, details, status)}</span></td>"
            f"<td data-label='Duration'><span class='cell-value'>{duration_cell}</span></td>"
            "</tr>"
        )
    return "".join(rows)


def _empty_row(label, duration_cell):
    return (
        "<tr>"
        f"<td data-label='Trial'>{label}</td>"
        "<td data-label='Result'><span class='step-result step-result-neutral'>Not assessed</span></td>"
        "<td class='obs' data-label='Observed vs limit'><span class='cell-value'>—</span></td>"
        "<td data-label='Time'><span class='cell-value'>—</span></td>"
        f"<td data-label='Duration'><span class='cell-value'>{duration_cell}</span></td>"
        "</tr>"
    )


def describe_success(passed, total):
    """Words and ring fill for a success count.

    The check and the complete-success sentence require every trial to have passed.
    A rounded 100 with one miss is ">99%"; a rounded 0 with one success is "<1%".
    """
    if not _number(passed) or not _number(total) or int(total) <= 0:
        return None
    passed, total = int(passed), int(total)
    exact = 100 * passed / total
    rounded = int(round(exact))
    complete = passed == total
    if complete:
        face = "100%"
    elif passed > 0 and rounded == 0:
        face = "<1%"
    elif passed < total and rounded == 100:
        face = ">99%"
    else:
        face = f"{rounded}%"
    return {"face": face, "phrase": f"{face} success", "complete": complete, "fill": exact}


def _counted(count, total, singular):
    """'{count} successes, 60%'. Never a k-of-n fraction."""
    shown = describe_success(count, total)
    if shown is None:
        return None
    number = int(count)
    plural = {"success": "successes", "failure": "failures"}.get(singular, f"{singular}s")
    word = singular if number == 1 else plural
    return f"{number} {word}, {shown['face']}"


def success_count(passed, total):
    return _counted(passed, total, "success")


def compared_block(summary):
    """The stored reproducibility object when this run compared its repeats.

    Anything else, including a missing key, is a k-of-n run and keeps that
    rendering. No count or bound is filled in here.
    """
    if not isinstance(summary, dict):
        return None
    block = summary.get("reproducibility")
    if isinstance(block, dict) and block.get("compared") is True:
        return block
    return None


def repeat_statement(summary):
    """``reproducibility.statement`` when it is stored text, else None."""
    block = compared_block(summary)
    if block is None:
        return None
    statement = block.get("statement")
    if isinstance(statement, str) and statement.strip():
        return statement.strip()
    return None


def stored_finding_text(block):
    """The finding's stored text. A missing finding adds nothing."""
    if not isinstance(block, dict):
        return ""
    finding = block.get("finding")
    if isinstance(finding, str) and finding.strip():
        return finding.strip()
    if isinstance(finding, dict):
        detail = finding.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return ""


def failure_count(failed, total):
    return _counted(failed, total, "failure")


def required_percentage(required, total):
    """Acceptance as a percentage of the stored trial count."""
    shown = describe_success(required, total)
    if shown is None:
        return None
    return f"{shown['face']} required"


def success_summary(passed, total, grade=None, required=None):
    """'12 successes, 60%; overall FAIL. 90% required.'

    The percentage words come from ``success_count`` and ``required_percentage``.
    A trial total of zero, or a count that is not a number, adds no percentage.
    """
    counted = success_count(passed, total)
    needed = required_percentage(required, total)
    if counted and grade:
        observed = f"{counted}; overall {grade}"
    elif counted:
        observed = counted
    elif grade:
        observed = f"overall {grade}"
    else:
        observed = None
    parts = [part for part in (observed, needed) if part]
    if not parts:
        return ""
    return ". ".join(parts) + "."


def _catalog(trials, names):
    """Assessed steps. Spec criteria order is the tie-break; the label is the spec text."""
    present = []
    for _, assessments in trials:
        for evaluator in assessments:
            if evaluator not in present:
                present.append(evaluator)
    ordered = [ident for ident in names if ident in present]
    ordered += sorted(ident for ident in present if ident not in ordered)
    return [
        {"id": ident, "name": names.get(ident, ident), "kind": _KIND.get(ident, "other")}
        for ident in ordered
    ]


def _ranked(catalog, trials):
    total = len(trials)
    ranked = []
    for index, step in enumerate(catalog):
        passed = sum(
            1
            for _, assessments in trials
            if assessments.get(step["id"], {}).get("status") == "PASS"
        )
        version = next(
            (
                assessments[step["id"]].get("version")
                for _, assessments in trials
                if step["id"] in assessments and assessments[step["id"]].get("version")
            ),
            None,
        )
        ranked.append({**step, "passed": passed, "total": total, "version": version, "order": index})
    ranked.sort(key=lambda step: (step["passed"], step["order"], step["id"]))
    return ranked


def _places(ranked):
    places = []
    raw = 0
    previous = None
    for index, step in enumerate(ranked, start=1):
        if step["passed"] != previous:
            raw = index
        places.append(raw)
        previous = step["passed"]
    shared = {place for place in places if places.count(place) > 1}
    return places, shared


def _confidence(summary):
    """Stored run interval, in plain words. Not a ring and not a headline."""
    interval = summary.get("wilson95")
    if not isinstance(interval, list) or len(interval) != 2:
        return ""
    if not _number(interval[0]) or not _number(interval[1]):
        return ""
    return (
        "<p class='confidence'>95% confidence range for the success rate: "
        f"{esc(hallway._interval(interval))}</p>"
    )


def _acceptance(results, summary):
    """Plan acceptance only when it matches this assessment's n and required_passes.

    A plan copied from another run (for example 18 of 20 on a 3-trial assessment)
    is omitted rather than shown.
    """
    plans = []
    for result in results:
        plan = _dict(_dict(result.get("provenance")).get("plan"))
        if "required_passes" not in plan:
            return ""
        plans.append(plan)
    if not plans:
        return ""
    first = plans[0]
    if any(plan.get("required_passes") != first.get("required_passes") for plan in plans[1:]):
        return ""
    trials = first.get("trials")
    count = trials.get("count") if isinstance(trials, dict) else trials
    if count != summary.get("n"):
        return ""
    if summary.get("required_passes") is not None and first.get("required_passes") != summary.get(
        "required_passes"
    ):
        return ""
    acceptance = required_percentage(first.get("required_passes"), count)
    if not acceptance:
        return ""
    return (
        "<p class='plan-note'><strong>Acceptance recorded on this run's plan.</strong> "
        f"<span class='nowrap'>{esc(acceptance)}</span>.</p>"
    )


def _simulator(result):
    simulator = _dict(_dict(_dict(result.get("provenance")).get("simulator")).get("simulator"))
    ident = simulator.get("id")
    if ident == "mujoco":
        return "MuJoCo"
    return ident if isinstance(ident, str) and ident else None


def _software(system):
    if not isinstance(system, dict):
        return None
    ident = system.get("id") or ""
    name = ident.partition("/")[2] or ident
    version = system.get("version")
    return " ".join(part for part in (name, version) if part) or None


def _constants(report, summary, result):
    system = summary.get("system") if isinstance(summary.get("system"), dict) else {}
    environment = summary.get("environment") if isinstance(summary.get("environment"), dict) else {}
    spec = summary.get("spec") if isinstance(summary.get("spec"), dict) else {}
    if environment.get("id") and environment.get("version"):
        world = f"{environment['id']}@{environment['version']}"
    else:
        world = environment.get("id")
    pairs = [
        ("Scenario", spec.get("capability") or summary.get("capability")),
        ("Robot software", _software(system)),
        ("World", world),
        ("Simulator", _simulator(result) if result else None),
        ("Policy", report.get("policy")),
    ]
    rows = "".join(
        f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>"
        for key, value in pairs
        if value not in (None, "")
    )
    if not rows:
        return ""
    return f"<div class='locked'><h3>This run's constants</h3><dl>{rows}</dl></div>"


def _bar(fill):
    return html_theme._ring_number(fill)


def _article(step, place, tied, close, trials, durations):
    shown = describe_success(step["passed"], step["total"])
    rate = shown["phrase"]
    badge = html_theme.success_badge(
        shown["face"], f"{step['name']}: {rate}", esc, complete=shown["complete"], fill=shown["fill"], size=88
    )
    place_label = f"={place}" if tied else str(place)
    place_class = "place tie" if tied else "place"
    version = f"v{step['version']}" if step.get("version") else ""
    eval_line = " · ".join(part for part in (step["id"], version) if part)
    chip = "<span class='chip chip-muted'>Close</span>" if close else ""
    complete = (
        "<span class='complete'>Stored as complete success for every trial.</span>"
        if shown["complete"]
        else ""
    )
    return (
        "<article class='step'><details>"
        "<summary class='step-summary'>"
        f"<span class='{place_class}'>{esc(place_label)}</span>"
        f"<span class='badge'>{badge}</span>"
        "<span class='rank-body'>"
        f"<h3 class='step-name'>{esc(step['name'])}"
        f"<span class='colon'>: </span><span class='rate'>{esc(rate)}</span></h3>"
        "<span class='step-meta'>"
        f"<span class='count'>{esc(success_count(step['passed'], step['total']))}</span>"
        f"{chip}"
        f"<span class='eval-line'>{esc(eval_line)}</span>"
        "<span class='disclose'><span class='chevron' aria-hidden='true'></span>"
        "<span class='disclose-closed'>Show trials</span>"
        "<span class='disclose-open'>Hide trials</span></span>"
        "</span>"
        f"<span class='success-bar' style='--p:{_bar(shown['fill'])}' aria-hidden='true'><i></i></span>"
        f"{complete}</span></summary>"
        "<div class='trial-panel'>"
        "<p class='trial-note'>Each trial for this step. Time is the first moment the step "
        "was not met, the exit time on success, or the time of the extreme value for a "
        "successful continuous check. Duration is the observation <code>duration_s</code>.</p>"
        "<div class='table-wrap'><table class='trial-table'><thead><tr>"
        "<th scope='col'>Trial</th><th scope='col'>Result</th>"
        "<th scope='col'>Observed vs limit</th><th scope='col'>Time</th>"
        "<th scope='col'>Duration</th></tr></thead><tbody>"
        f"{_trial_rows(step, trials, durations)}</tbody></table></div></div>"
        "</details></article>"
    )


_DIFFERING_FIELDS = ("index", "outcome", "trajectory_sha256", "sha256")


def _shared_status(step, trials):
    """The one status every assessed repeat stored for this step, or None."""
    statuses = []
    for _, assessments in trials:
        if step["id"] not in assessments:
            continue
        statuses.append(assessments[step["id"]].get("status"))
    if statuses and all(item == statuses[0] for item in statuses):
        return statuses[0]
    return None


def _differing_list(block):
    """Repeats the assessment listed under ``differing``. Only stored fields."""
    rows = block.get("differing")
    if not isinstance(rows, list):
        return ""
    items = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        keys = [key for key in _DIFFERING_FIELDS if key in rec]
        keys += sorted(key for key in rec if key not in _DIFFERING_FIELDS)
        bits = []
        for key in keys:
            value = rec[key]
            if isinstance(value, (dict, list)):
                continue
            bits.append(f"{key} {value}")
        if bits:
            items.append(
                "<li style='overflow-wrap:anywhere'>" + esc(", ".join(bits)) + "</li>"
            )
    if not items:
        return ""
    return (
        "<h3>Differing repeats</h3>"
        "<ul class='differing' style='overflow-wrap:anywhere;min-width:0'>"
        + "".join(items)
        + "</ul>"
    )


def _step_version(step, trials):
    return next(
        (
            assessments[step["id"]].get("version")
            for _, assessments in trials
            if step["id"] in assessments and assessments[step["id"]].get("version")
        ),
        None,
    )


def _compared_article(step, trials, durations):
    """One step of a compared run: the shared outcome, never a success rate."""
    status = _shared_status(step, trials)
    outcome = f"<span class='count'>{_verdict(status)}</span>" if status else ""
    version = _step_version(step, trials)
    version = f"v{version}" if version else ""
    eval_line = " · ".join(part for part in (step["id"], version) if part)
    return (
        "<article class='step is-outcome'><details>"
        "<summary class='step-summary is-outcome' style='grid-template-columns:minmax(0, 1fr)'>"
        "<span class='rank-body'>"
        f"<h3 class='step-name'>{esc(step['name'])}</h3>"
        "<span class='step-meta'>"
        f"{outcome}"
        f"<span class='eval-line'>{esc(eval_line)}</span>"
        "<span class='disclose'><span class='chevron' aria-hidden='true'></span>"
        "<span class='disclose-closed'>Show trials</span>"
        "<span class='disclose-open'>Hide trials</span></span>"
        "</span></span></summary>"
        "<div class='trial-panel' style='padding-left:0'>"
        "<p class='trial-note'>Each trial for this step. Time is the first moment the step "
        "was not met, the exit time on success, or the time of the extreme value for a "
        "successful continuous check. Duration is the observation <code>duration_s</code>.</p>"
        "<div class='table-wrap'><table class='trial-table'><thead><tr>"
        "<th scope='col'>Trial</th><th scope='col'>Result</th>"
        "<th scope='col'>Observed vs limit</th><th scope='col'>Time</th>"
        "<th scope='col'>Duration</th></tr></thead><tbody>"
        f"{_trial_rows(step, trials, durations)}</tbody></table></div></div>"
        "</details></article>"
    )


def _compared_cards(report, summary, results, trials, catalog, durations):
    """One outcome and the stored statement. No rate, ring, bar or interval."""
    statement = repeat_statement(summary)
    grade = summary.get("grade") or ""
    statement_html = f"<p class='pct'>{esc(statement)}</p>" if statement else ""
    status = f"<p class='stored-status'>Stored overall status: {esc(grade)}</p>" if grade else ""
    pieces = [_compared_article(step, trials, durations) for step in catalog]
    return (
        "<div class='card scenario-steps'><h2>This run</h2><div class='split'><div style='min-width:0'>"
        "<div class='run-hero'><div>"
        f"{statement_html}{status}</div></div>"
        f"{_differing_list(compared_block(summary))}</div>"
        f"{_constants(report, summary, results[0])}</div></div>"
        "<div class='card scenario-steps'><h2>Steps</h2>"
        f"<div class='step-list'>{''.join(pieces)}</div>"
        "<p class='sources'>Observed values, limits, times and margins are the stored "
        "assessments. The step name is the feature spec's success criterion for that "
        "check. Duration is <code>duration_s</code> from the trial observation when that "
        "file is available to the report.</p></div>"
    )


def _run_cards(report, summary, durations):
    results = _results_for(report, summary)
    if not results:
        return ""
    trials = [(result, _assessments(result)) for result in results]
    catalog = _catalog(trials, criterion_names(report["source_bundle"].get("description")))
    if not catalog:
        return ""
    if compared_block(summary) is not None:
        return _compared_cards(report, summary, results, trials, catalog, durations)
    k, n = summary.get("k"), summary.get("n")
    shown = describe_success(k, n)
    if shown is None:
        rate, face, complete, fill = "Success rate not stored", "", False, 0
    else:
        rate, face, complete, fill = shown["phrase"], shown["face"], shown["complete"], shown["fill"]
    grade = summary.get("grade") or ""
    counted = success_count(k, n)
    count = f"<p class='count'>{esc(counted)}</p>" if counted else ""
    status = f"<p class='stored-status'>Stored overall status: {esc(grade)}</p>" if grade else ""
    badge = html_theme.success_badge(face, rate, esc, complete=complete, fill=fill, size=128)
    ranked = _ranked(catalog, trials)
    places, shared = _places(ranked)
    pieces = []
    for index, (previous, step, place) in enumerate(zip([None, *ranked[:-1]], ranked, places)):
        neighbors = [item for item in (ranked[index - 1] if index else None, ranked[index + 1] if index + 1 < len(ranked) else None) if item]
        close = any(abs(step["passed"] - other["passed"]) == 1 for other in neighbors)
        pieces.append(_article(step, place, place in shared, close, trials, durations))
        if previous is not None and abs(step["passed"] - previous["passed"]) == 1:
            pieces.append(
                "<p class='close-note'>"
                f"{esc(previous['name'])} and {esc(step['name'])} are one trial apart, "
                "so they are not distinguishable from each other.</p>"
            )
    return (
        "<div class='card scenario-steps'><h2>This run</h2><div class='split'><div>"
        "<div class='run-hero'>"
        f"<div class='badge'>{badge}</div><div>"
        f"<p class='pct'>{esc(rate)}</p>{count}{status}</div></div>"
        f"<div class='success-bar' style='--p:{_bar(fill)}' aria-hidden='true'><i></i></div>"
        f"{_confidence(summary)}{_acceptance(results, summary)}</div>"
        f"{_constants(report, summary, results[0])}</div></div>"
        "<div class='card scenario-steps'><h2>Steps, by success</h2>"
        f"<div class='step-list'>{''.join(pieces)}</div>"
        "<p class='sources'>Observed values, limits, times and margins are the stored "
        "assessments. The step name is the feature spec's success criterion for that "
        "check. Duration is <code>duration_s</code> from the trial observation when that "
        "file is available to the report.</p></div>"
    )


def scenario_steps(report, durations=None):
    """HTML for each stored run: a success ring, then one ring per scenario step."""
    durations = durations or {}
    blocks = [
        _run_cards(report, summary, durations)
        for summary in report.get("summaries") or []
        if isinstance(summary, dict)
    ]
    return "".join(block for block in blocks if block)
