"""Generic evaluator summary card.

The report does not name evaluators, keep an icon catalog, or branch on
``descriptor.kind``. A mark is whatever result is present. Text is escaped.
An icon is inlined only after the SVG subset check; otherwise the letter disc
is report chrome.

Detail kept behind a mark comes from the feature spec (``description``), the
run assessment, and the descriptor. The card itself shows the stored success
ring and only the finding rows an evaluator supplied.
"""

from datetime import datetime, timezone
import html
import json
import re
from pathlib import Path

from . import html_theme
from .steps import (
    compared_block,
    describe_success,
    repeat_statement,
    stored_finding_text,
    success_count,
)
from .svg_icon import acceptable_icon

FALLBACK_TITLE = "Evaluator"
TIER_ORDER = (
    "verdict",
    "health_finding",
    "test_system_status",
    "review",
    "observation",
)
TIER_LABEL = {
    "verdict": "Verdict",
    "health_finding": "Health finding",
    "test_system_status": "Test-system status",
    "review": "Review",
    "observation": "Observation",
}
GRADED_STATUSES = frozenset({"COMPLETED", "ERROR"})
NOT_GRADED = {
    "INCONCLUSIVE": "Not graded: no integrity check applied to this run.",
}
NOT_GRADED_UNKNOWN = "Not graded: this report version doesn't recognise this status yet."
ADVISORY_NOT_GRADED = "Advisory observations only; does not change the grade."
RESULT_FORMAT = re.compile(r"^livingproof-evaluator-result/1\.\d+\.\d+$")
NO_DESCRIPTOR = "No evaluator descriptor was stored."
_CHECK = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' aria-hidden='true' "
    "focusable='false'><path d='M3.2 8.2 6.1 11.1 12.8 4.4' fill='none' stroke='currentColor' "
    "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/></svg>"
)


_CROSS = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' aria-hidden='true' "
    "focusable='false'><path d='M4 4 12 12M12 4 4 12' fill='none' stroke='currentColor' "
    "stroke-width='2.2' stroke-linecap='round'/></svg>"
)


def esc(value):
    return html.escape(str(value), quote=True)


def _visible(value):
    """Plain text that has a visible character. An ampersand is kept."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text if text else ""


def _grade(value):
    if type(value) is int and 0 <= value <= 100:
        return value
    return None


def _trial(value):
    if type(value) is int and 0 <= value <= 999999:
        return value
    text = _visible(value) if isinstance(value, str) else ""
    return text or None


_LATE_THRESHOLD_SECONDS = 600


def _parse_iso_utc(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _utc_iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _utc_time_text(dt):
    return f"{dt.day} {dt.strftime('%b %Y, %H:%M')} UTC"


def _time_html(value):
    dt = _parse_iso_utc(value)
    if dt is None:
        return ""
    canonical = _utc_iso(dt)
    utc_text = _utc_time_text(dt)
    return f"<time datetime='{esc(canonical)}' title='{esc(utc_text)}'>{esc(utc_text)}</time>"


def _late_note(graded_dt, run_dt):
    if graded_dt is None or run_dt is None:
        return ""
    delta = (graded_dt - run_dt).total_seconds()
    if delta <= _LATE_THRESHOLD_SECONDS:
        return ""
    if delta < 3600:
        return f"Graded {int(delta // 60)} min after the run"
    if delta < 86400:
        return f"Graded {max(1, round(delta / 3600))} h after the run"
    return f"Graded {max(1, round(delta / 86400))} d after the run"


def _run_completed_at(report, summary):
    bundle = report.get("source_bundle")
    results = bundle.get("results") if isinstance(bundle, dict) else None
    by_id = {
        r["id"]: r for r in (results or []) if isinstance(r, dict) and isinstance(r.get("id"), str)
    }
    result_ids = summary.get("result_ids") or list(by_id.keys())
    trial_times = []
    for rid in result_ids:
        res = by_id.get(rid)
        if not isinstance(res, dict):
            continue
        ts = res.get("timestamps")
        if isinstance(ts, dict):
            dt = _parse_iso_utc(ts.get("completed_at"))
            if dt is not None:
                trial_times.append(dt)
    if trial_times:
        return max(trial_times)
    summary_ts = summary.get("timestamps")
    if isinstance(summary_ts, dict):
        dt = _parse_iso_utc(summary_ts.get("completed_at"))
        if dt is not None:
            return dt
    return None


def is_result(document):
    return (
        isinstance(document, dict)
        and isinstance(document.get("format"), str)
        and RESULT_FORMAT.fullmatch(document["format"]) is not None
    )


def tier_rank(tier):
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return len(TIER_ORDER)


def tier_label(tier):
    if not tier:
        return ""
    return TIER_LABEL.get(tier, tier)


def grouping_headline(n, m):
    """Report chrome. Shown on the card only when n is 3 or more."""
    evaluators = "evaluator" if n == 1 else "evaluators"
    problems = "problem" if m == 1 else "problems"
    return f"{n} {evaluators} reported {m} {problems}"


def all_quiet_line(n):
    if n == 1:
        return "1 evaluator is satisfied."
    return f"All {n} evaluators are satisfied."


def fallback_letter(short_title, title):
    for source in (short_title, title):
        text = _visible(source)
        if text:
            return text[0].upper()
    return "E"


def _findings(items):
    rows = []
    if not isinstance(items, list):
        return rows
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        rows.append(
            {
                "text": text.strip(),
                "severity": _visible(item.get("severity")),
                "time": _visible(item.get("time")),
                "trial": _trial(item.get("trial")),
                "tier": _visible(item.get("tier")),
                "reported_by": _visible(item.get("reported_by")),
                "index": index,
            }
        )
    return rows


def _view(
    *,
    title,
    short_title,
    icon,
    accessible_name,
    purpose,
    version,
    source,
    tier,
    details,
    grade,
    findings,
    missing_descriptor,
    identity,
    completed_at="",
):
    title = title or FALLBACK_TITLE
    short = short_title if short_title and short_title != title else ""
    clean = acceptable_icon(icon)
    return {
        "title": title,
        "short_title": short,
        "icon": clean,
        "accessible_name": accessible_name or short or title,
        "purpose": purpose,
        "version": version,
        "source": source,
        "tier": tier,
        "details": details,
        "grade": grade,
        "findings": findings,
        "missing_descriptor": missing_descriptor,
        "identity": identity or title,
        "completed_at": completed_at,
        "late_note": "",
        "body_html": "",
        "force_speaking": False,
        "letter": fallback_letter(short, title),
    }


def _percentage(value):
    if type(value) is int and 0 <= value <= 100:
        return value
    if type(value) is float and 0 <= value <= 100:
        return value
    return None


def not_graded_note(status):
    """Card copy for a run status that was not graded, else ''.

    INCONCLUSIVE (result format 1.2.0) means no check applied. A 1.x minor may
    add run statuses, and one this report does not know is not graded either.
    """
    if not status or status in GRADED_STATUSES:
        return ""
    return NOT_GRADED.get(status, NOT_GRADED_UNKNOWN)


def _apply_integrity(view, document):
    """Surface stored run-level integrity status, percentage and scope when present."""
    integrity = document.get("integrity")
    if not isinstance(integrity, dict):
        return
    run = integrity.get("run") if isinstance(integrity.get("run"), dict) else {}
    status = _visible(run.get("test_system_status"))
    if status:
        view["status"] = status
        view["not_graded"] = not_graded_note(status)
        view["integrity_error"] = status == "ERROR"
    percentage = _percentage(run.get("percentage"))
    if percentage is not None:
        view["percentage"] = percentage
    scope = _visible(run.get("scope")) or _visible(integrity.get("scope"))
    if scope:
        view["scope"] = scope


def _document_completed_at(document):
    ts = document.get("timestamps")
    if not isinstance(ts, dict):
        return ""
    dt = _parse_iso_utc(ts.get("completed_at"))
    return _utc_iso(dt) if dt is not None else ""


def resolve_one(document):
    """One mark from a result envelope or a bare descriptor (example data)."""
    if is_result(document):
        evaluator = document.get("evaluator") if isinstance(document.get("evaluator"), dict) else {}
        descriptor = (
            document.get("descriptor") if isinstance(document.get("descriptor"), dict) else None
        )
        fields = descriptor or {}
        display = _visible(evaluator.get("display_name"))
        title = _visible(fields.get("title")) or display or FALLBACK_TITLE
        if descriptor is not None and "icon" in descriptor:
            icon = descriptor.get("icon")
        else:
            icon = evaluator.get("icon")
        version = _visible(fields.get("version")) or _visible(evaluator.get("version"))
        findings = _findings(fields.get("findings")) if descriptor else []
        grade = _grade(fields.get("grade")) if descriptor else None
        details = _visible(fields.get("details_copy"))
        if not details and not findings:
            details = _visible(fields.get("success_copy"))
        identity = evaluator.get("id") if isinstance(evaluator.get("id"), str) else title
        view = _view(
            title=title,
            short_title=_visible(fields.get("short_title")),
            icon=icon,
            accessible_name=_visible(fields.get("icon_accessible_name")),
            purpose=_visible(fields.get("purpose")),
            version=version,
            source=_visible(fields.get("source")),
            tier=_visible(fields.get("tier")),
            details=details,
            grade=grade,
            findings=findings,
            missing_descriptor=descriptor is None,
            identity=identity,
            completed_at=_document_completed_at(document),
        )
        _apply_integrity(view, document)
        return view
    title = _visible(document.get("title")) or FALLBACK_TITLE
    findings = _findings(document.get("findings"))
    details = _visible(document.get("details_copy"))
    if not details and not findings:
        details = _visible(document.get("success_copy"))
    return _view(
        title=title,
        short_title=_visible(document.get("short_title")),
        icon=document.get("icon"),
        accessible_name=_visible(document.get("icon_accessible_name")),
        purpose=_visible(document.get("purpose")),
        version=_visible(document.get("version")),
        source=_visible(document.get("source")),
        tier=_visible(document.get("tier")),
        details=details,
        grade=_grade(document.get("grade")),
        findings=findings,
        missing_descriptor=False,
        identity=title,
        completed_at=_document_completed_at(document),
    )


def _merge_group(documents):
    views = [resolve_one(document) for document in documents]
    first = dict(views[0])
    # Prefer a descriptor-bearing member for display fields.
    chosen = next((view for view in views if not view["missing_descriptor"]), first)
    findings = []
    for view in views:
        findings.extend(view["findings"])
    for index, finding in enumerate(findings):
        finding["index"] = index
    grades = [view["grade"] for view in views if view["grade"] is not None]
    grade = grades[0] if grades and all(item == grades[0] for item in grades) else None
    completed_dts = [
        dt for dt in (_parse_iso_utc(view["completed_at"]) for view in views) if dt is not None
    ]
    completed_at = _utc_iso(max(completed_dts)) if completed_dts else ""
    chosen = dict(chosen)
    chosen["findings"] = findings
    chosen["grade"] = grade
    chosen["missing_descriptor"] = all(view["missing_descriptor"] for view in views)
    chosen["identity"] = first["identity"]
    chosen["completed_at"] = completed_at
    if not chosen["details"]:
        chosen["details"] = next((view["details"] for view in views if view["details"]), "")
    return chosen


def views_from(items):
    """Group result envelopes that share an evaluator id. Bare descriptors stay separate."""
    grouped = []
    pending = []

    def flush():
        if not pending:
            return
        buckets = []
        index = {}
        for document in pending:
            view = resolve_one(document)
            key = view["identity"]
            if key not in index:
                index[key] = len(buckets)
                buckets.append([])
            buckets[index[key]].append(document)
        for bucket in buckets:
            grouped.append(_merge_group(bucket))
        pending.clear()

    for item in items:
        if is_result(item):
            pending.append(item)
        else:
            flush()
            grouped.append(resolve_one(item))
    flush()
    return grouped


def order_marks(views):
    decorated = sorted(
        enumerate(views),
        key=lambda pair: (tier_rank(pair[1]["tier"]), pair[1]["title"].casefold(), pair[0]),
    )
    return [view for _, view in decorated]


def order_findings(views):
    rows = []
    for view in views:
        for finding in view["findings"]:
            tier = finding["tier"] or view["tier"]
            rows.append((view, finding, tier))
    rows.sort(
        key=lambda row: (
            tier_rank(row[2]),
            row[0]["title"].casefold(),
            row[1]["index"],
        )
    )
    return rows


def _embedded(result):
    docs = []
    if not isinstance(result, dict):
        return docs
    value = result.get("evaluator_results")
    if isinstance(value, list):
        docs.extend(value)
    provenance = result.get("provenance")
    if isinstance(provenance, dict):
        extra = provenance.get("evaluator_results")
        if isinstance(extra, list):
            docs.extend(extra)
        one = provenance.get("evaluator_result")
        if isinstance(one, dict):
            docs.append(one)
    original = result.get("original_result")
    if is_result(original):
        docs.append(original)
    return [doc for doc in docs if is_result(doc)]


def _integrity_documents(report, summary):
    """Run-level integrity results keyed by ``evaluator.id``, bound to this run only."""
    run_id = summary.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return []
    bundle = report.get("source_bundle")
    assessment = bundle.get("assessment") if isinstance(bundle, dict) else None
    stored = assessment.get("integrity_results") if isinstance(assessment, dict) else None
    if not isinstance(stored, dict):
        return []
    docs = []
    for item in stored.values():
        candidates = item if isinstance(item, list) else [item]
        for document in candidates:
            if not is_result(document):
                continue
            integrity = document.get("integrity")
            run = integrity.get("run") if isinstance(integrity, dict) else None
            if isinstance(run, dict) and run.get("id") == run_id:
                docs.append(document)
    return docs


def documents_for_summary(report, summary, evidence_results=None):
    by_id = {
        result["id"]: result
        for result in report["source_bundle"]["results"]
        if isinstance(result, dict) and "id" in result
    }
    docs = []
    for result_id in summary.get("result_ids") or []:
        result = by_id.get(result_id)
        if not result:
            continue
        docs.extend(_embedded(result))
        if evidence_results:
            docs.extend(item for item in evidence_results.get(result_id) or [] if is_result(item))
    extra = summary.get("evaluator_results")
    if isinstance(extra, list):
        docs.extend(item for item in extra if is_result(item))
    docs.extend(_integrity_documents(report, summary))
    return docs


def _read_evidence_json(root, item):
    from .core import safe_relative

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
    return data if isinstance(data, dict) else None


def load_evidence_results(bundle, root):
    """Evaluator result documents stored as evidence files. Observations are ignored."""
    found = {}
    if not isinstance(bundle, dict) or root is None:
        return found
    root = Path(root).resolve()
    for result in bundle.get("results") or []:
        if not isinstance(result, dict) or "id" not in result:
            continue
        docs = []
        for item in result.get("evidence") or []:
            data = _read_evidence_json(root, item)
            if is_result(data):
                docs.append(data)
        if docs:
            found[result["id"]] = docs
    return found


def _run_failed(summary):
    grade = summary.get("grade")
    if isinstance(grade, str) and grade and grade != "PASS":
        return True
    k, n = summary.get("k"), summary.get("n")
    return type(k) is int and type(n) is int and n > 0 and k < n


def _fallback_view():
    view = resolve_one({})
    view["missing_descriptor"] = True
    view["tier"] = ""
    view["identity"] = FALLBACK_TITLE
    return view


def assessment_failure_line(summary):
    """One plain callout from the assessment when it failed and no finding was stored.

    Successes and the percentage only. No fraction, and no reason the assessment
    did not record. A compared run that failed calls out the stored finding text.
    A pass, including identical repeats that agree, is not called out.
    """
    if not _run_failed(summary):
        return ""
    block = compared_block(summary)
    if block is not None:
        grade = summary.get("grade") if isinstance(summary.get("grade"), str) else ""
        detail = stored_finding_text(block)
        if grade and grade != "PASS" and detail:
            return f"Overall {grade}. {detail}"
        if detail:
            return detail
        if grade and grade != "PASS":
            return f"Overall {grade}."
        return ""
    counted = success_count(summary.get("k"), summary.get("n"))
    grade = summary.get("grade") if isinstance(summary.get("grade"), str) else ""
    if counted and grade and grade != "PASS":
        return f"{counted}; overall {grade}."
    if counted:
        return f"{counted}."
    if grade and grade != "PASS":
        return f"Overall {grade}."
    return ""


def _run_time_html(run_dt):
    if run_dt is None:
        return "<p class='run-time is-missing'>Time not recorded</p>"
    canonical = _utc_iso(run_dt)
    utc_text = _utc_time_text(run_dt)
    return (
        "<p class='run-time'>Ran "
        f"<time datetime='{esc(canonical)}' title='{esc(utc_text)}'>{esc(utc_text)}</time></p>"
    )


def _compared_hero(report, summary, run_dt=None):
    """The one outcome and the stored statement. No success ring and no rate."""
    description = report["source_bundle"].get("description")
    mission = description.get("mission") if isinstance(description, dict) else None
    headline = _visible(mission.get("title")) if isinstance(mission, dict) else ""
    if not headline:
        headline = _visible(summary.get("capability"))
    statement = repeat_statement(summary)
    grade = summary.get("grade") if isinstance(summary.get("grade"), str) else ""
    title = f"<h2 class='run-title'>{esc(headline)}</h2>" if headline else ""
    statement_html = f"<p class='pct'>{esc(statement)}</p>" if statement else ""
    time_html = _run_time_html(run_dt)
    status = f"<p class='stored-status'>Stored overall status: {esc(grade)}</p>" if grade else ""
    return f"<div class='summary-hero'><div>{title}{statement_html}{time_html}{status}</div></div>"


def _hero(report, summary, run_dt=None):
    if compared_block(summary) is not None:
        return _compared_hero(report, summary, run_dt)
    description = report["source_bundle"].get("description")
    mission = description.get("mission") if isinstance(description, dict) else None
    headline = _visible(mission.get("title")) if isinstance(mission, dict) else ""
    if not headline:
        headline = _visible(summary.get("capability"))
    shown = describe_success(summary.get("k"), summary.get("n"))
    if shown is None:
        phrase, face, complete, fill = "Success rate not stored", "", False, 0
        count = ""
    else:
        phrase = shown["phrase"]
        face, complete, fill = shown["face"], shown["complete"], shown["fill"]
        counted = success_count(summary.get("k"), summary.get("n"))
        count = f"<p class='count'>{esc(counted)}</p>" if counted else ""
    time_html = _run_time_html(run_dt)
    grade = summary.get("grade") if isinstance(summary.get("grade"), str) else ""
    status = f"<p class='stored-status'>Stored overall status: {esc(grade)}</p>" if grade else ""
    badge = html_theme.success_badge(face, phrase, esc, complete=complete, fill=fill, size=128)
    title = f"<h2 class='run-title'>{esc(headline)}</h2>" if headline else ""
    return (
        "<div class='summary-hero'>"
        f"<div class='badge'>{badge}</div><div>"
        f"{title}<p class='pct'>{esc(phrase)}</p>{count}{time_html}{status}</div></div>"
    )


def _icon_html(view):
    if view["icon"]:
        return f"<span class='mark-svg'>{view['icon']}</span>"
    return f"<span class='eval-fallback' aria-hidden='true'>{esc(view['letter'])}</span>"


def _anchor_id(identity, seen):
    """A stable, unique, URL-safe id for an evaluator's tab: ``evaluator-<evaluator id>``."""
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", str(identity)) or "evaluator"
    base = candidate = f"evaluator-{slug}"
    number = 1
    while candidate in seen:
        number += 1
        candidate = f"{base}-{number}"
    seen.add(candidate)
    return candidate


def _mark(view, group, column, anchor=None, *, show_time=True):
    """One tab (a details element holding only its summary) and its panel.

    The tab is the summary. The panel carries the descriptor detail and, for the
    mark that hosts it, the stored run. The mark label is ``view['title']`` as
    stored (or the "Evaluator" fallback); nothing is appended to it.
    """
    speaking = bool(view["findings"]) or view.get("force_speaking")
    state = "is-speaking" if speaking else "is-quiet"
    grade = view["grade"]
    show_ring = speaking and grade is not None and grade < 100
    if show_ring:
        face_text = f"{grade}%"
        ring = html_theme.success_badge(
            face_text,
            f"{view['title']}: {grade}% grade",
            esc,
            complete=False,
            fill=grade,
            size=52,
        )
        face = f"<span class='mini-ring'>{ring}</span>"
        klass = f"eval-mark {state} is-graded"
    else:
        # A not-graded run is neither a pass nor a failure: the neutral face has no check pip.
        ungraded = bool(view.get("not_graded")) and not speaking
        # An ERROR integrity status is a failing mark, never the passing tick (#106).
        errored = bool(view.get("integrity_error")) and not speaking
        # An advisory card is never a pass: quiet views otherwise receive _CHECK.
        if view.get("advisory"):
            pip = ""
        elif errored:
            pip = f"<span class='pip pip-fail' aria-hidden='true'>{_CROSS}</span>"
        elif speaking or ungraded:
            pip = ""
        else:
            pip = f"<span class='pip' aria-hidden='true'>{_CHECK}</span>"
        face = f"{_icon_html(view)}{pip}"
        klass = f"eval-mark {state}{' is-error' if errored else ''}"
    accessible = view["accessible_name"]
    if view.get("not_graded") and not speaking:
        accessible = f"{view['title']}, not graded"
    elif view.get("integrity_error") and not speaking:
        accessible = f"{view['title']}: error"
    names = f"<span class='eval-name eval-name-full'>{esc(view['title'])}</span>"
    if view.get("advisory"):
        names += "<span class='eval-cue'>Advisory</span>"
    if view["short_title"]:
        names += f"<span class='eval-name eval-name-short'>{esc(view['short_title'])}</span>"
    tab_id = f"{group}-tab-{column}"
    panel_id = f"{group}-panel-{column}"
    panel = (
        f"<div class='eval-tabpanel' role='tabpanel' id='{esc(panel_id)}' "
        f"aria-labelledby='{esc(tab_id)}'>{_panel(view, show_time=show_time)}"
        f"<div class='stored-run'>{view.get('body_html') or ''}</div></div>"
    )
    inline = column > html_theme.MAX_PANEL_TABS
    anchor_attr = f" id='{esc(anchor)}'" if anchor else ""
    tab = (
        f"<details class='eval-disclosure{' eval-inline' if inline else ''}'{anchor_attr} "
        f"name='{esc(group)}' role='none'>"
        f"<summary class='{klass}' role='tab' id='{esc(tab_id)}' "
        f"aria-controls='{esc(panel_id)}' aria-selected='false'>"
        f"<span class='eval-face' role='img' aria-label='{esc(accessible)}'>{face}</span>"
        f"{names}</summary>"
    )
    if inline:
        # No generated rule picks this panel; it opens inside its own details.
        return f"{tab}{panel}</details>", ""
    return f"{tab}</details>", panel


def _panel(view, *, show_time=True):
    bits = [f"<h4>{esc(view['title'])}</h4>"]
    if view["version"]:
        bits.append(f"<p class='meta'>{esc(view['version'])}</p>")
    if view.get("status"):
        bits.append(f"<p class='meta'>Status: {esc(view['status'])}</p>")
    percentage = view.get("percentage")
    if percentage is not None:
        shown = (
            str(int(percentage))
            if type(percentage) is float and percentage.is_integer()
            else str(percentage)
        )
        bits.append(f"<p class='meta'>{esc(shown)}%</p>")
    if view.get("not_graded"):
        # Neutral: the muted .meta style the status line uses, not a failing chip.
        bits.append(f"<p class='meta not-graded'>{esc(view['not_graded'])}</p>")
    if view.get("scope"):
        bits.append(f"<p class='meta'>Scope: {esc(view['scope'])}</p>")
    if view["purpose"]:
        bits.append(f"<p class='purpose'>{esc(view['purpose'])}</p>")
    if view.get("summary"):
        bits.append(f"<p class='more'>{esc(view['summary'])}</p>")
    if view["source"]:
        bits.append(f"<p class='meta'>{esc(view['source'])}</p>")
    label = tier_label(view["tier"])
    if label:
        bits.append(f"<p class='meta'>Tier: {esc(label)}</p>")
    if show_time and not view.get("advisory"):
        time_html = _time_html(view.get("completed_at"))
        if time_html:
            bits.append(f"<p class='meta'>Graded {time_html}</p>")
            if view.get("late_note"):
                bits.append(f"<p class='meta late-note'>{esc(view['late_note'])}</p>")
        else:
            bits.append("<p class='meta is-missing'>Time not recorded</p>")
    if view["details"]:
        bits.append(f"<p class='more'>{esc(view['details'])}</p>")
    if view.get("details_href"):
        bits.append(f"<p class='more'><a href='{esc(view['details_href'])}'>Recorded data</a></p>")
    if view.get("trusted_viewer_html"):
        bits.append(view["trusted_viewer_html"])
    if view["missing_descriptor"]:
        bits.append(f"<p class='descriptor-note'>{esc(NO_DESCRIPTOR)}</p>")
    return f"<div class='eval-panel'>{''.join(bits)}</div>"


def _callout_icon(view):
    return f"<span class='callout-icon' aria-hidden='true'>{_icon_html(view)}</span>"


def _finding_text(finding):
    text = esc(finding["text"])
    if finding["reported_by"]:
        return f"{esc(finding['reported_by'])}: {text}"
    return text


def _finding_meta(finding):
    parts = []
    if finding["severity"]:
        parts.append(finding["severity"])
    if finding["time"]:
        parts.append(finding["time"])
    if finding["trial"] is not None:
        parts.append(f"trial {finding['trial']}")
    if not parts:
        return ""
    return f"<p class='finding-meta'>{esc(' · '.join(parts))}</p>"


def _callouts(views, *, quiet):
    rows = order_findings(views)
    if not rows:
        if quiet and not any(
            view.get("not_graded") or view.get("integrity_error") for view in views
        ):
            return f"<p class='callout-ok'>{esc(all_quiet_line(len(views)))}</p>"
        return ""
    speakers = [view for view in views if view["findings"]]
    n = len(speakers)
    m = len(rows)
    bits = []
    if n >= 3:
        bits.append(f"<p class='callout-headline'>{esc(grouping_headline(n, m))}</p>")
    bits.append("<ul class='callouts'>")
    for view, finding, _tier in rows:
        bits.append(
            "<li>"
            f"{_callout_icon(view)}<div class='callout-body'>"
            f"<p class='finding-text'><strong>{esc(view['title'])}</strong> "
            f"{_finding_text(finding)}</p>{_finding_meta(finding)}</div></li>"
        )
    bits.append("</ul>")
    return "".join(bits)


# Progressive enhancement for the tabs, self-contained: it reads and writes
# attributes of its own .evaluators container and listens to events inside it.
# It makes no network request and loads nothing. The page works without it:
# opening, closing, the one-open-at-a-time rule and the selected look come from
# the details element and CSS. Without it only these stay as loaded:
#   - aria-selected (always "false"), and
#   - arrow/Home/End keys and the roving tabindex (every tab is a Tab stop), and
#   - opening a tab from its #evaluator-<id> fragment (without it the fragment only
#     scrolls to the tab). It listens to hashchange (and load) to do that.
# With it:
#   - aria-selected follows the open details element;
#   - Left/Right move focus between tabs (wrapping), Home/End to the first/last;
#   - tabindex roves: the tab last focused is the one Tab stop; until a tab has
#     been focused it is the open one, else the first. Only focusing a tab moves
#     the stop, never the asynchronous toggle event, so where Shift+Tab re-enters
#     the row does not depend on whether a toggle was delivered before or after
#     focus left it.
# The keys only move focus (manual activation). Enter/Space open or close the
# focused tab, as for a native summary, so panels never open as a side effect
# of moving, and the selected one can still be closed.
_TABS_SCRIPT = (
    "<script data-eval-tabs>(function(s){"
    "var w=s.parentNode.querySelector(':scope > .eval-row');"
    "function t(){return Array.from(w.querySelectorAll(':scope > .eval-disclosure > summary'))}"
    "var c;"
    "function f(){var a=t(),o=a.indexOf(c)<0?a.find(function(x){return x.parentNode.open})||a[0]:c;"
    "a.forEach(function(x){x.setAttribute('aria-selected',x.parentNode.open?'true':'false');"
    "x.tabIndex=x===o?0:-1})}"
    "w.addEventListener('toggle',f,true);"
    "w.addEventListener('focusin',function(e){if(t().indexOf(e.target)>=0)c=e.target;f()});"
    "w.addEventListener('keydown',function(e){var a=t(),i=a.indexOf(e.target),"
    "n={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:a.length-1}[e.key];"
    "if(i<0||n===undefined)return;e.preventDefault();a[(n+a.length)%a.length].focus()});"
    "function h(){var a=Array.from(w.querySelectorAll(':scope > .eval-disclosure')),"
    "d=a.find(function(x){return '#'+x.id===location.hash});"
    "a.forEach(function(x){x.toggleAttribute('data-landed',false)});if(!d)return;"
    "d.open=true;var m=d.querySelector('summary'),"
    "p=s.parentNode.querySelector('#'+m.getAttribute('aria-controls'));"
    "m.focus({preventScroll:true});if(p)p.scrollIntoView({block:'nearest'});"
    "m.scrollIntoView({block:'nearest'});d.toggleAttribute('data-landed',true)}"
    "addEventListener('hashchange',h);addEventListener('load',h);"
    "f();h()})(document.currentScript)</script>"
)


def render_marks(views, *, group="eval-marks", quiet=False, anchors=False, show_time=True):
    """The tabs and panels. With ``anchors``, each tab also gets ``id="evaluator-<id>"``."""
    ordered = order_marks(views)
    tabs, panels = [], []
    seen = set()
    for index, view in enumerate(ordered):
        anchor = _anchor_id(view["identity"], seen) if anchors else None
        tab, panel = _mark(view, group, index + 1, anchor, show_time=show_time)
        tabs.append(tab)
        panels.append(panel)
    return (
        (
            "<style>"
            + html_theme.PRESENTATION_STYLES
            + "</style><div class='evaluators has-presentations'>"
            if any(v.get("advisory") for v in ordered)
            else "<div class='evaluators'>"
        )
        + "<p class='evaluators-label'>Evaluators</p>"
        f"<div class='eval-row' role='tablist' aria-label='Evaluators' "
        f"style='--eval-count:{len(tabs) or 1}'>{''.join(tabs)}</div>"
        f"<div class='eval-tabpanels'>{''.join(panels)}</div>"
        f"{_TABS_SCRIPT}</div>"
        + _callouts([view for view in ordered if not view.get("advisory")], quiet=quiet)
    )


def render_example_card(
    *,
    kicker,
    run_title,
    passed,
    total,
    outputs,
    compact=False,
    count=None,
    group="example",
):
    """One example-data card. The ring is the supplied stored rate, not the findings."""
    shown = describe_success(passed, total)
    phrase = shown["phrase"] if shown else ""
    face = shown["face"] if shown else ""
    badge = html_theme.success_badge(
        face,
        f"{run_title}: {phrase}",
        esc,
        complete=bool(shown and shown["complete"]),
        fill=shown["fill"] if shown else 0,
        size=72 if compact else 104,
    )
    if count is None and shown:
        count = success_count(passed, total)
    views = []
    for item in outputs:
        view = resolve_one(item)
        view["body_html"] = item.get("body_html") or ""
        views.append(view)
    quiet = not any(view["findings"] or view.get("force_speaking") for view in views)
    klass = "summary-card is-compact" if compact else "summary-card"
    count_html = f"<p class='count'>{esc(count)}</p>" if count else ""
    return (
        f"<article class='{klass}'>"
        "<div class='card-head'>"
        f"<p class='state-kicker'>{esc(kicker)}</p>"
        "<p class='example-tag'>Example data</p></div>"
        "<div class='summary-hero'>"
        f"<div class='badge'>{badge}</div><div>"
        f"<h3 class='run-title'>{esc(run_title)}</h3>"
        f"<p class='pct'>{esc(phrase)}</p>{count_html}</div></div>"
        f"{render_marks(views, group=group, quiet=quiet, show_time=False)}</article>"
    )


def summary_front(report, stored_body, evidence_results=None, *, presentations=(), viewer_panels=None):
    """Visible ring and marks. ``stored_body`` sits inside one mark's details."""
    runs = [summary for summary in report.get("summaries") or [] if isinstance(summary, dict)]
    docs = []
    for summary in runs:
        docs.extend(documents_for_summary(report, summary, evidence_results))
    views = views_from(docs)
    identities = {view["identity"] for view in views}
    for contribution in presentations:
        if contribution.id in identities:
            raise ValueError("Optional presentation cannot replace an existing evaluator")
        identities.add(contribution.id)
        views.append(_presentation_view(contribution))
    for view in advisory_views(report, evidence_results):
        if view["identity"] in identities:
            raise ValueError("Optional presentation cannot replace an existing evaluator")
        identities.add(view["identity"])
        if viewer_panels and view["identity"] in viewer_panels:
            view["trusted_viewer_html"] = viewer_panels[view["identity"]]
        views.append(view)
    failed = any(_run_failed(summary) for summary in runs)
    if not views:
        if not runs and not stored_body:
            return ""
        views = [_fallback_view()]
    if stored_body and views:
        # The run record stays one expansion away. With one mark, that mark
        # holds it. With several, the first mark after tier-then-title order
        # holds it. descriptor.kind is not consulted.
        host = next((v for v in order_marks(views) if not v.get("advisory")), None)
        if host is None:
            host = _fallback_view()
            views.insert(0, host)
        host["body_html"] = stored_body
        if failed and not host["findings"]:
            host["force_speaking"] = True
    quiet = not failed and not any(view["findings"] or view.get("force_speaking") for view in views)
    run_times = [_run_completed_at(report, summary) for summary in runs]
    valid_run_times = [dt for dt in run_times if dt is not None]
    latest_run_dt = max(valid_run_times) if valid_run_times else None
    for view in views:
        view["late_note"] = _late_note(_parse_iso_utc(view.get("completed_at")), latest_run_dt)
    heroes = "".join(
        _hero(report, summary, run_dt) for summary, run_dt in zip(runs, run_times, strict=True)
    )
    failure = ""
    if not any(view["findings"] for view in views):
        lines = [assessment_failure_line(summary) for summary in runs]
        failure = "".join(
            f"<p class='assessment-failure'>{esc(line)}</p>" for line in lines if line
        )
    return (
        "<article class='summary-card'>"
        f"{heroes}{failure}{render_marks(views, group='run-evaluators', quiet=quiet, anchors=True)}</article>"
    )


def _collapsed(value):
    """One line of plain text. The field is already plain, so nothing is escaped."""
    return " ".join(str(value).split())


def _plain(value):
    """One line of Markdown-safe text: no line breaks, no table or emphasis markup."""
    text = _collapsed(value)
    for char in ("\\", "|", "*", "_", "`", "[", "]", "<", ">"):
        text = text.replace(char, "\\" + char)
    return text


def markdown_line(report, evidence_results=None):
    """``**Evaluators:** Title version · ...`` for the Markdown report and PR comment.

    Built from each contributing evaluator's descriptor (title, and version where
    known), in the same order as the HTML marks. An evaluator's problems (findings)
    are counted only when it reported some. None when no evaluator result is in the
    report, so a bundle without evaluator entries renders as before.
    """
    runs = [summary for summary in report.get("summaries") or [] if isinstance(summary, dict)]
    docs = []
    for summary in runs:
        docs.extend(documents_for_summary(report, summary, evidence_results))
    views = order_marks(views_from(docs))
    if not views:
        return None
    names = []
    for view in views:
        name = _plain(view["title"])
        if view["version"]:
            name += f" {_plain(view['version'])}"
        count = len(view["findings"])
        if count:
            name += f" ({count} {'problem' if count == 1 else 'problems'})"
        names.append(name)
    return "**Evaluators:** " + " · ".join(names)


_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_TAG = re.compile(r"^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _assessment_value(report, key):
    bundle = report.get("source_bundle") if isinstance(report, dict) else None
    assessment = bundle.get("assessment") if isinstance(bundle, dict) else None
    if not isinstance(assessment, dict) or key not in assessment:
        return None
    return assessment.get(key)


def _bounded_plain(name, text, limit):
    """The presentation plain-text check, applied to a field of the same limit."""
    from .presentation import EvaluatorPresentation

    slot = {80: "title", 64: "version", 400: "purpose", 2000: "details"}[limit]
    fields = {
        "id": "a",
        "title": "T",
        "version": "1",
        "purpose": "p",
        "details": "d",
        "source_bundle_sha256": "0" * 64,
    }
    fields[slot] = text
    try:
        EvaluatorPresentation(**fields)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Evaluator presentation {name} must be bounded plain text") from exc


def _provenance_line(record):
    """``Source <repo>@<ref> (<commit[:12]>)`` from the loader record, or a refusal."""
    if not isinstance(record, dict):
        raise ValueError("Advisory provenance must be a record with repo, ref and commit")
    repo, ref, commit = record.get("repo"), record.get("ref"), record.get("commit")
    if not isinstance(repo, str) or _REPO.fullmatch(repo) is None:
        raise ValueError("Advisory provenance repo must be owner/name")
    if not isinstance(ref, str) or (_TAG.fullmatch(ref) is None and _HEX40.fullmatch(ref) is None):
        raise ValueError("Advisory provenance ref must be a vX.Y.Z tag or a commit")
    if not isinstance(commit, str) or _HEX40.fullmatch(commit) is None:
        raise ValueError("Advisory provenance commit must be 40 lowercase hex")
    return f"Source {repo}@{ref} ({commit[:12]})"


def _provenance_by_id(report):
    """``source_bundle.assessment.advisory_provenance``, keyed by ``evaluator.id``."""
    stored = _assessment_value(report, "advisory_provenance")
    if stored is None:
        return {}
    if not isinstance(stored, dict):
        raise ValueError("advisory_provenance must be an object keyed by evaluator id")
    return {key: _provenance_line(record) for key, record in stored.items()}


def _not_run_title(ident, record):
    descriptor = record.get("descriptor") if isinstance(record.get("descriptor"), dict) else None
    title = descriptor.get("title") if isinstance(descriptor, dict) else None
    if isinstance(title, str) and title.strip():
        _bounded_plain("title", title, 80)
        return title
    return ident


def _not_run_view(ident, record):
    if not isinstance(record, dict):
        raise ValueError("advisory_not_run entry must be a record with outcome and reason")
    outcome = record.get("outcome")
    if outcome not in {"failure", "refused"}:
        raise ValueError("Advisory not-run outcome must be failure or refused")
    _bounded_plain("reason", record.get("reason"), 2000)
    _bounded_plain("id", ident, 80)
    from .presentation import EvaluatorPresentation

    try:
        EvaluatorPresentation(
            id=ident,
            title="T",
            version="1",
            purpose="p",
            details="d",
            source_bundle_sha256="0" * 64,
        )
    except ValueError as exc:
        raise ValueError("Advisory not-run id must be a stable lowercase slug") from exc
    title = _not_run_title(ident, record)
    line = f"{title}: NOT RUN ({outcome}): {record['reason']}"
    view = resolve_one({"title": title, "tier": "observation"})
    view.update(
        identity=ident,
        advisory=True,
        not_graded=ADVISORY_NOT_GRADED,
        summary=line,
        not_run_line=line,
    )
    return view


def _not_run_views(report, taken):
    """``source_bundle.assessment.advisory_not_run``, keyed by ``evaluator.id``."""
    stored = _assessment_value(report, "advisory_not_run")
    if stored is None:
        return []
    if not isinstance(stored, dict):
        raise ValueError("advisory_not_run must be an object keyed by evaluator id")
    views = []
    for ident, record in stored.items():
        view = _not_run_view(ident, record)
        if view["identity"] in taken:
            raise ValueError("Optional presentation cannot replace an existing evaluator")
        taken.add(view["identity"])
        views.append(view)
    return views


def advisory_documents(report):
    """Read ``source_bundle.assessment.advisory_results``.

    The object is keyed by ``evaluator.id``. Each value is one result or a list
    of results, the same shape ``_integrity_documents`` reads from
    ``integrity_results``. Absent means this bundle stored no advisory result.
    """
    bundle = report.get("source_bundle") if isinstance(report, dict) else None
    assessment = bundle.get("assessment") if isinstance(bundle, dict) else None
    stored = assessment.get("advisory_results") if isinstance(assessment, dict) else None
    if stored is None:
        return []
    if not isinstance(stored, dict):
        raise ValueError("advisory_results must be an object keyed by evaluator id")
    documents = []
    for key, item in stored.items():
        candidates = item if isinstance(item, list) else [item]
        for document in candidates:
            if not is_result(document):
                raise ValueError(f"advisory_results entry {key!r} must be an evaluator result")
            documents.append(document)
    return documents


def _advisory_contribution(document, source_bundle_sha256):
    """One presentation from a descriptor plus the advisory payload.

    Title, purpose and version come from the descriptor. Summary and details
    come from the payload. ``details_file.uri`` is the local details link.
    The same limits and plain-text check as ``EvaluatorPresentation`` apply.
    """
    evaluator = document.get("evaluator") if isinstance(document.get("evaluator"), dict) else {}
    descriptor = document.get("descriptor")
    descriptor = descriptor if isinstance(descriptor, dict) else None
    payload = document.get("advisory") if isinstance(document.get("advisory"), dict) else None
    if descriptor is None or payload is None:
        raise ValueError("Advisory result requires a descriptor and an advisory payload")
    from .presentation import EvaluatorPresentation

    href = None
    details_file = payload.get("details_file")
    if details_file is not None:
        if not isinstance(details_file, dict) or not isinstance(details_file.get("uri"), str):
            raise ValueError(
                "Evaluator presentation details_href must be a local JSON or text path"
            )
        href = details_file["uri"]
    fields = {
        "id": evaluator.get("id"),
        "title": descriptor.get("title"),
        "version": descriptor.get("version"),
        "purpose": descriptor.get("purpose"),
        "details": payload.get("details"),
        "source_bundle_sha256": source_bundle_sha256,
        "details_href": href,
    }
    contribution = EvaluatorPresentation(**fields)
    # Summary uses the purpose bound (400) and the same plain-text check.
    try:
        EvaluatorPresentation(**{**fields, "purpose": payload.get("summary")})
    except (TypeError, ValueError) as exc:
        raise ValueError("Evaluator presentation summary must be bounded plain text") from exc
    return contribution, payload.get("summary")


def _presentation_view(contribution, summary=""):
    """The existing advisory card. ``summary`` is the payload line, when present."""
    view = resolve_one(
        {
            "title": contribution.title,
            "version": contribution.version,
            "purpose": contribution.purpose,
            "details_copy": contribution.details,
            "tier": "observation",
        }
    )
    view.update(
        identity=contribution.id,
        advisory=True,
        not_graded=ADVISORY_NOT_GRADED,
        details_href=contribution.details_href,
    )
    if summary:
        view["summary"] = summary
    return view


def _apply_provenance(view, provenance):
    line = provenance.get(view["identity"])
    if line:
        view["source"] = line
    return view


def advisory_views(report, evidence_results=None):
    """One peer view per advisory result or not-run record. The caller builds no presentation."""
    documents = advisory_documents(report)
    provenance = _provenance_by_id(report)
    if not documents and not _assessment_value(report, "advisory_not_run"):
        return []
    if not any(isinstance(summary, dict) for summary in report.get("summaries") or []):
        raise ValueError("Advisory results require a run summary")
    embedded = []
    for summary in report.get("summaries") or []:
        if isinstance(summary, dict):
            embedded.extend(documents_for_summary(report, summary, evidence_results))
    taken = {view["identity"] for view in views_from(embedded)}
    digest = report.get("source_bundle_sha256")
    views = []
    for document in documents:
        contribution, summary = _advisory_contribution(document, digest)
        if contribution.id in taken:
            raise ValueError("Optional presentation cannot replace an existing evaluator")
        taken.add(contribution.id)
        views.append(_apply_provenance(_presentation_view(contribution, summary), provenance))
    for view in _not_run_views(report, taken):
        views.append(_apply_provenance(view, provenance))
    return views


def _advisory_line(view, *, plain):
    name = plain(view["title"])
    if view["version"]:
        name += f" {plain(view['version'])}"
    return f"{name} · {plain(view['summary'])}"


def _format_advisory_lines(views, *, plain, prefix):
    lines = []
    for view in views:
        if view.get("not_run_line"):
            lines.append(plain(view["not_run_line"]))
        else:
            lines.append(f"{prefix}{_advisory_line(view, plain=plain)}")
        if view.get("source"):
            lines.append(plain(view["source"]))
    return lines


def advisory_markdown_lines(report, evidence_results=None):
    """One Markdown line per advisory result, in mark order. Empty when none are stored."""
    views = order_marks(advisory_views(report, evidence_results))
    if not views:
        return []
    return _format_advisory_lines(views, plain=_plain, prefix="**Advisory:** ")


def advisory_text_lines(report, evidence_results=None):
    """One plain line per advisory result, in mark order. Empty when none are stored."""
    views = order_marks(advisory_views(report, evidence_results))
    if not views:
        return []
    return _format_advisory_lines(views, plain=_collapsed, prefix="Advisory: ")
