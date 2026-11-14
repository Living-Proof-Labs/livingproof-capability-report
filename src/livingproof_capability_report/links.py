"""Evidence links carried in report.json, outside the source bundle.

Links change no digest and no grade. Each ``--evidence-links`` file is a JSON object::

    {"run": "https://github.com/OWNER/REPO/actions/runs/1",
     "links": [
        {"label": "logs", "path": "evidence/logs.txt", "kind": "log"},
        {"label": "MCAP", "path": "evidence/seed-01.mcap", "kind": "mcap",
         "seed": 1, "status": "PASS"},
        {"label": "video", "path": "evidence/seed-01.mp4", "kind": "video",
         "seed": 1, "status": "PASS", "poster": "evidence/seed-01.jpg",
         "why": "Typical pass"},
        {"label": "coverage", "path": "evidence/coverage.txt", "kind": "note"},
        {"label": "video", "path": "evidence/seed-04.mp4", "kind": "video",
         "seed": 4, "status": "FAIL", "expired": true}]}

``path`` is a relative site path. The public page renders that string exactly.
``poster`` and ``why`` are shown only when the caller supplies them. ``expired``
true means the site has pruned the file: the page shows "Evidence kept for N days"
from the retention value passed to render, and does not point at the file. The
reporter has no retention default. An optional https ``url`` stays in report.json.
A GitHub Actions artifact address is not rendered on the public page.

Files are merged in order; a second ``run`` must match the first. A per-trial link
names the verifier's status for that seed, and rendering refuses a link whose status
disagrees with the stored decision. The rendered line says trial for an evidence
2.0.0 result and seed for the earlier model. The ``seed`` field itself is unchanged.
An entry with an empty URL, no path and no expired flag is dropped (a skipped upload).
"""

import copy
import html
import json
import re

from . import narrative

KINDS = ("artifact", "video", "mcap", "log", "note")
_URL = re.compile(r"^https://[^\s()<>\[\]|`]+$")
_LABEL = re.compile(r"^[^\[\]()|`<>\n]{1,80}$")
_WHY = re.compile(r"^[^\[\]()|`<>\n]{1,160}$")
_PATH = re.compile(r"^[A-Za-z0-9._~!$&'()*+,;=@%/-]{1,240}$")
_ARTIFACT_WORD = re.compile(r"artifact", re.I)
_ARTIFACT_URL = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/actions/runs/\d+/artifacts\b",
    re.I,
)
_KEPT = "Evidence kept for {retention} days"
_FIELDS = {"label", "url", "kind", "seed", "status", "path", "expired", "poster", "why"}


def is_artifact_reference(value):
    """True when text names a GitHub Actions artifact or uses that word."""
    return isinstance(value, str) and (
        _ARTIFACT_WORD.search(value) is not None or _ARTIFACT_URL.search(value) is not None
    )


def check_site_path(value, what):
    """A relative or site-root path. Returned unchanged so render can copy it."""
    if (
        not isinstance(value, str)
        or not _PATH.match(value)
        or "://" in value
        or value.startswith("//")
        or ":" in value
        or is_artifact_reference(value)
    ):
        raise ValueError(f"{what} must be a relative site path")
    return value


def check_retention(value):
    """The caller's retention in days, or None when the caller did not pass one."""
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise ValueError(
            "Evidence retention must be a positive number of days supplied by the caller; "
            "the reporter has no default"
        )
    return value


def kept_phrase(retention):
    """Success-framed wording. The number comes only from the caller."""
    days = check_retention(retention)
    if days is None:
        raise ValueError(
            "Expired evidence needs a retention value supplied by the caller; "
            "the reporter has no default"
        )
    return _KEPT.format(retention=days)


def ensure_retention(report, retention):
    """Refuse expired evidence when the caller did not pass a retention value."""
    retention = check_retention(retention)
    stored = report.get("evidence_links") if isinstance(report, dict) else None
    links = stored.get("links", []) if isinstance(stored, dict) else []
    expired = any(isinstance(entry, dict) and entry.get("expired") for entry in links)
    if expired and retention is None:
        raise ValueError(
            "Expired evidence needs a retention value supplied by the caller; "
            "the reporter has no default"
        )
    return retention


def check_history(history):
    """None when no slot was supplied. An address without a label is an error."""
    if history is None:
        return None
    if not isinstance(history, dict) or set(history) - {"href", "label"}:
        raise ValueError("Run history must be an object with href and label")
    href, label = history.get("href"), history.get("label")
    if not href or not label:
        raise ValueError("Run history needs both an address and a label supplied by the caller")
    if not isinstance(label, str) or not _LABEL.match(label) or is_artifact_reference(label):
        raise ValueError("Run history label must be 1-80 plain characters")
    if not isinstance(href, str) or is_artifact_reference(href):
        raise ValueError("Run history address must be a site path or https URL")
    if href.startswith("https://"):
        if not _URL.match(href):
            raise ValueError(f"Run history URL must be https without spaces: {href!r}")
    else:
        check_site_path(href, "Run history address")
    return {"href": href, "label": label}


def _check(entry):
    if not isinstance(entry, dict):
        raise ValueError("Evidence link must be an object")
    unknown = set(entry) - _FIELDS
    if unknown:
        raise ValueError(f"Unknown evidence link fields: {', '.join(sorted(unknown))}")
    if not isinstance(entry.get("label"), str) or not _LABEL.match(entry["label"]):
        raise ValueError("Evidence link label must be 1-80 plain characters")
    if entry.get("kind") not in KINDS:
        raise ValueError(f"Evidence link kind must be one of {', '.join(KINDS)}")
    expired = entry.get("expired", False)
    if "expired" in entry and type(expired) is not bool:
        raise ValueError("Evidence link expired must be true or false")
    path = entry.get("path")
    if path is not None:
        check_site_path(path, "Evidence link path")
    url = entry.get("url")
    if url:
        if not isinstance(url, str) or not _URL.match(url):
            raise ValueError(f"Evidence link URL must be https without spaces: {url!r}")
    elif not path and not expired:
        raise ValueError("Evidence link needs a url or a relative path")
    if "poster" in entry:
        if entry.get("kind") != "video":
            raise ValueError("Evidence link poster is only for a video")
        check_site_path(entry["poster"], "Evidence link poster")
    if "why" in entry and (
        not isinstance(entry["why"], str)
        or not _WHY.match(entry["why"])
        or is_artifact_reference(entry["why"])
    ):
        raise ValueError("Evidence link why must be 1-160 plain characters")
    if ("seed" in entry) != ("status" in entry):
        raise ValueError("A per-trial evidence link needs both seed and status")
    if "seed" in entry and (
        type(entry["seed"]) is not int or entry["status"] not in ("PASS", "FAIL")
    ):
        raise ValueError("Per-trial evidence link needs an integer seed and PASS or FAIL")
    return dict(entry)


def validate(stored):
    """Check a stored ``evidence_links`` object; return it unchanged."""
    if not isinstance(stored, dict) or set(stored) - {"run", "links"}:
        raise ValueError("evidence_links must be an object with run and links")
    run = stored.get("run")
    if run is not None and (not isinstance(run, str) or not _URL.match(run)):
        raise ValueError(f"Run URL must be https without spaces: {run!r}")
    if not isinstance(stored.get("links", []), list):
        raise ValueError("evidence_links.links must be a list")
    for entry in stored.get("links", []):
        _check(entry)
    return stored


def merge(documents):
    """Merge ``--evidence-links`` documents. Empty URLs with nothing else are dropped."""
    run, links = None, []
    for doc in documents:
        if not isinstance(doc, dict) or set(doc) - {"run", "links"}:
            raise ValueError("Evidence links file must be an object with run and links")
        if doc.get("run"):
            if run is not None and doc["run"] != run:
                raise ValueError("Evidence links files name different CI runs")
            run = doc["run"]
        for entry in doc.get("links", []):
            if (
                isinstance(entry, dict)
                and not entry.get("url")
                and not entry.get("path")
                and not entry.get("expired")
            ):
                continue  # e.g. no FAIL trial, so no fail video was uploaded
            links.append(_check(entry))
    out = {"links": links}
    if run:
        out["run"] = run
    return validate(out)


def seed_status(report, result_ids, seed):
    """Stored decision for ``seed`` among a run's results, or None."""
    status = {d["result_id"]: d["status"] for d in report["decisions"]}
    hits = [r for r in result_ids if r.endswith(f"-seed-{seed:02d}")]
    return status[hits[0]] if len(hits) == 1 else None


def _markdown_piece(entry, retention):
    if entry.get("expired"):
        return f"{entry['label']} ({kept_phrase(retention)})"
    target = entry.get("path") or entry.get("url")
    if target:
        return f"[{entry['label']}]({target})"
    return None


def lines(report, run, retention=None):
    """Markdown lines for one run (empty without stored links)."""
    stored = report.get("evidence_links")
    if not stored:
        return []
    out = []
    head = [f"[CI run]({stored['run']})"] if stored.get("run") else []
    for entry in stored["links"]:
        if "seed" not in entry:
            piece = _markdown_piece(entry, retention)
            if piece:
                head.append(piece)
    if head:
        out.append("**Evidence:** " + " · ".join(head))
    trials = {}
    for entry in stored["links"]:
        if "seed" in entry:
            stored_status = seed_status(report, run["result_ids"], entry["seed"])
            if stored_status != entry["status"]:
                raise ValueError(
                    f"Evidence link for seed {entry['seed']} says {entry['status']}, "
                    f"stored decision is {stored_status}"
                )
            key = (entry["status"] != "FAIL", entry["seed"])
            trials.setdefault(key, []).append(entry)
    name = narrative.repeat_name(report=report, result_ids=run.get("result_ids") or [])
    for (_, seed), items in sorted(trials.items()):
        word = "pass" if items[0]["status"] == "PASS" else "fail"
        icon = "▶️" if any(entry["kind"] == "video" for entry in items) else "📎"
        cells = " · ".join(
            piece for piece in (_markdown_piece(entry, retention) for entry in items) if piece
        )
        out.append(f"- {icon} {name} {seed} ({word}): {cells}")
    return out


def scrub_public(report):
    """Report copy for the public page. Artifact identifiers stay in report.json only."""
    links = report.get("evidence_links") if isinstance(report, dict) else None
    if not isinstance(links, dict):
        return report
    encoded = json.dumps(links)
    if _ARTIFACT_WORD.search(encoded) is None and _ARTIFACT_URL.search(encoded) is None:
        return report
    copied = copy.deepcopy(report)
    copied["evidence_links"] = _scrub(copied["evidence_links"])
    return copied


def _scrub(value):
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if not (isinstance(key, str) and is_artifact_reference(key))
            and not (isinstance(item, str) and is_artifact_reference(item))
        }
    if isinstance(value, list):
        kept = []
        for item in value:
            if isinstance(item, str) and is_artifact_reference(item):
                continue
            kept.append(_scrub(item))
        return kept
    return value


def html_target(entry):
    """Public address for a live file, or None when the page must not point at it."""
    if not isinstance(entry, dict) or entry.get("expired"):
        return None
    path = entry.get("path")
    if isinstance(path, str) and path and not is_artifact_reference(path):
        return path
    url = entry.get("url")
    if isinstance(url, str) and url and not is_artifact_reference(url):
        return url
    return None


def _esc(value):
    return html.escape(str(value), quote=True)


def _safe(value):
    if not isinstance(value, str) or is_artifact_reference(value):
        return ""
    return value


def _display_label(report, entry):
    if "seed" not in entry:
        return entry.get("label", "")
    suffix = f"-seed-{entry['seed']:02d}"
    result = next(
        (item for item in report["source_bundle"]["results"] if item["id"].endswith(suffix)),
        None,
    )
    name = narrative.repeat_name(result)
    return f"{name} {entry['seed']} ({entry['status']}): {entry.get('label', '')}"


def html_links(entries, retention):
    """Trial-cell evidence: a supplied path, or the kept-for state. Never an artifact URL."""
    parts = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = _safe(entry.get("label") or "")
        if entry.get("expired"):
            text = f"{_esc(label)} " if label else ""
            parts.append(f"<span class='evidence-kept'>{text}{_esc(kept_phrase(retention))}</span>")
            continue
        target = html_target(entry)
        if target:
            shown = label or target
            parts.append(f"<a href='{_esc(target)}'>{_esc(shown)}</a>")
        elif label:
            parts.append(_esc(label))
    return " ".join(parts)


def _html_item(report, entry, retention):
    label = _safe(_display_label(report, entry))
    why = _safe(entry.get("why") or "")
    lead = f"<p class='evidence-label'>{_esc(label)}</p>" if label else ""
    why_html = f"<p class='evidence-why'>{_esc(why)}</p>" if why else ""
    if entry.get("expired"):
        phrase = _esc(kept_phrase(retention))
        return f"<li class='is-kept'>{lead}{why_html}<p class='evidence-kept'>{phrase}</p></li>"
    target = html_target(entry)
    if entry.get("kind") == "video" and entry.get("path") and target:
        poster = entry.get("poster")
        poster_attr = f" poster='{_esc(poster)}'" if isinstance(poster, str) and poster else ""
        return (
            f"<li class='evidence-video'>{lead}{why_html}"
            f"<video controls preload='metadata' src='{_esc(target)}'{poster_attr}></video></li>"
        )
    if target:
        shown = label or target
        return f"<li><a href='{_esc(target)}'>{_esc(shown)}</a></li>"
    if label:
        return f"<li><span class='evidence-label'>{_esc(label)}</span></li>"
    return ""


def html_block(report, retention):
    """Evidence section for the public page. Empty when the caller stored no links."""
    stored = report.get("evidence_links")
    if not isinstance(stored, dict):
        return ""
    retention = check_retention(retention)
    links = [entry for entry in stored.get("links", []) if isinstance(entry, dict)]
    parts = ["<h2>Evidence</h2>"]
    if retention is not None:
        parts.append(f"<p class='evidence-kept-note'>{_esc(kept_phrase(retention))}</p>")
    items = []
    run = stored.get("run")
    if isinstance(run, str) and run and not is_artifact_reference(run):
        items.append(f"<li><a href='{_esc(run)}'>CI run</a></li>")
    for entry in links:
        item = _html_item(report, entry, retention)
        if item:
            items.append(item)
    if items:
        parts.append("<ul>" + "".join(items) + "</ul>")
    elif retention is None:
        return ""
    return "".join(parts)
