"""Generic evaluator summary card.

The report does not name evaluators, keep an icon catalog, or branch on
``descriptor.kind``. A mark is whatever result is present. Text is escaped.
An icon is inlined only after the SVG subset check; otherwise the letter disc
is report chrome.

Detail kept behind a mark comes from the feature spec (``description``), the
run assessment, and the descriptor. The card itself shows the stored success
ring and only the finding rows an evaluator supplied.
"""

import html
import json
import re
from pathlib import Path

from . import html_theme
from .steps import describe_success, success_count
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
RESULT_FORMAT = re.compile(r"^livingproof-evaluator-result/1\.\d+\.\d+$")
NO_DESCRIPTOR = "No evaluator descriptor was stored."
_CHECK = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' aria-hidden='true' "
    "focusable='false'><path d='M3.2 8.2 6.1 11.1 12.8 4.4' fill='none' stroke='currentColor' "
    "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/></svg>"
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
        "body_html": "",
        "force_speaking": False,
        "letter": fallback_letter(short, title),
    }


def resolve_one(document):
    """One mark from a result envelope or a bare descriptor (example data)."""
    if is_result(document):
        evaluator = document.get("evaluator") if isinstance(document.get("evaluator"), dict) else {}
        descriptor = document.get("descriptor") if isinstance(document.get("descriptor"), dict) else None
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
        return _view(
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
        )
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
    chosen = dict(chosen)
    chosen["findings"] = findings
    chosen["grade"] = grade
    chosen["missing_descriptor"] = all(view["missing_descriptor"] for view in views)
    chosen["identity"] = first["identity"]
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
    did not record.
    """
    if not _run_failed(summary):
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


def _hero(report, summary):
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
    grade = summary.get("grade") if isinstance(summary.get("grade"), str) else ""
    status = (
        f"<p class='stored-status'>Stored overall status: {esc(grade)}</p>" if grade else ""
    )
    badge = html_theme.success_badge(
        face, phrase, esc, complete=complete, fill=fill, size=128
    )
    title = f"<h2 class='run-title'>{esc(headline)}</h2>" if headline else ""
    return (
        "<div class='summary-hero'>"
        f"<div class='badge'>{badge}</div><div>"
        f"{title}<p class='pct'>{esc(phrase)}</p>{count}{status}</div></div>"
    )


def _icon_html(view):
    if view["icon"]:
        return f"<span class='mark-svg'>{view['icon']}</span>"
    return f"<span class='eval-fallback' aria-hidden='true'>{esc(view['letter'])}</span>"


def _mark(view, group, column, count):
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
        pip = "" if speaking else f"<span class='pip' aria-hidden='true'>{_CHECK}</span>"
        face = f"{_icon_html(view)}{pip}"
        klass = f"eval-mark {state}"
    accessible = view["accessible_name"]
    names = f"<span class='eval-name eval-name-full'>{esc(view['title'])}</span>"
    if view["short_title"]:
        names += f"<span class='eval-name eval-name-short'>{esc(view['short_title'])}</span>"
    panel = _panel(view)
    body = view.get("body_html") or ""
    return (
        f"<details class='eval-disclosure' name='{esc(group)}' style='--col:{column}'>"
        f"<summary class='{klass}'>"
        f"<span class='eval-face' role='img' aria-label='{esc(accessible)}'>{face}</span>"
        f"{names}</summary>{panel}"
        f"<div class='stored-run' style='--eval-count:{count}'>{body}</div></details>"
    )


def _panel(view):
    bits = [f"<h4>{esc(view['title'])}</h4>"]
    if view["version"]:
        bits.append(f"<p class='meta'>{esc(view['version'])}</p>")
    if view["purpose"]:
        bits.append(f"<p class='purpose'>{esc(view['purpose'])}</p>")
    if view["source"]:
        bits.append(f"<p class='meta'>{esc(view['source'])}</p>")
    label = tier_label(view["tier"])
    if label:
        bits.append(f"<p class='meta'>Tier: {esc(label)}</p>")
    if view["details"]:
        bits.append(f"<p class='more'>{esc(view['details'])}</p>")
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
        if quiet:
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


def render_marks(views, *, group="eval-marks", quiet=False):
    ordered = order_marks(views)
    count = len(ordered) or 1
    marks = "".join(
        _mark(view, group, index + 1, count) for index, view in enumerate(ordered)
    )
    return (
        "<div class='evaluators'>"
        "<p class='evaluators-label'>Evaluators</p>"
        f"<div class='eval-row' style='--eval-count:{count}'>{marks}</div></div>"
        + _callouts(ordered, quiet=quiet)
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
        f"{render_marks(views, group=group, quiet=quiet)}</article>"
    )


def summary_front(report, stored_body, evidence_results=None):
    """Visible ring and marks. ``stored_body`` sits inside one mark's details."""
    runs = [summary for summary in report.get("summaries") or [] if isinstance(summary, dict)]
    docs = []
    for summary in runs:
        docs.extend(documents_for_summary(report, summary, evidence_results))
    views = views_from(docs)
    failed = any(_run_failed(summary) for summary in runs)
    if not views:
        if not runs and not stored_body:
            return ""
        views = [_fallback_view()]
    if stored_body and views:
        # The run record stays one expansion away. With one mark, that mark
        # holds it. With several, the first mark after tier-then-title order
        # holds it. descriptor.kind is not consulted.
        host = order_marks(views)[0]
        host["body_html"] = stored_body
        if failed and not host["findings"]:
            host["force_speaking"] = True
    quiet = not failed and not any(
        view["findings"] or view.get("force_speaking") for view in views
    )
    heroes = "".join(_hero(report, summary) for summary in runs)
    failure = ""
    if not any(view["findings"] for view in views):
        lines = [assessment_failure_line(summary) for summary in runs]
        failure = "".join(
            f"<p class='assessment-failure'>{esc(line)}</p>" for line in lines if line
        )
    return (
        "<article class='summary-card'>"
        f"{heroes}{failure}{render_marks(views, group='run-evaluators', quiet=quiet)}</article>"
    )
