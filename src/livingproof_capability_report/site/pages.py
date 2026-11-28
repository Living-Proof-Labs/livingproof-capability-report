# SPDX-License-Identifier: Apache-2.0
"""Render static HTML pages, provenance blocks, navigation, and listings for `reports/`."""

from __future__ import annotations

import hashlib
import html
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from ..legacy_evidence import scenario_title as legacy_scenario_title
from .common import (
    _REPORTER_TAG,
    ANCHOR_REPORTER,
    COMMIT_SHA,
    EVALUATOR_ANCHOR,
    MARKED_INTEGRITY_STATUSES,
    SiteError,
    _plain_label,
    _require_single_robot,
    _stamp,
    _stored_text,
    listing_path,
    site_path,
)

ASSETS_DIR = Path(__file__).resolve().with_name("assets")
DOCS_HOME_URL = "https://docs.livingprooflabs.com/"
_REPO_PATH = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")

SITE_NAV_STYLES = """.site-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.6rem;
  margin: 0 0 0.85rem;
  font-size: 0.86rem;
}
.site-nav a {
  color: var(--teal-bright, #64dfc7);
  font-weight: 500;
  text-decoration: none;
}
.site-nav a:hover {
  text-decoration: underline;
}
.site-nav a[aria-current="page"] {
  color: var(--header-text, #f8fafc);
  font-weight: 650;
}
.site-nav-sep {
  color: var(--header-muted, #b7c5d6);
  opacity: 0.72;
}
"""
_ROBOT_TITLES = {
    "booster-t1": "Booster T1",
    "unitree-g1": "Unitree G1",
    "unitree-go1": "Unitree Go1",
}
THEME_SWITCH = (
    '<fieldset class="theme"><legend>Colour theme</legend>'
    '<label><input type="radio" name="theme" id="theme-system" value="system" checked> '
    "System</label>"
    '<label><input type="radio" name="theme" id="theme-light" value="light"> Light</label>'
    '<label><input type="radio" name="theme" id="theme-dark" value="dark"> Dark</label>'
    "</fieldset>"
)
LISTING_STYLE = (
    "body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:72rem;padding:0 1rem;"
    "color:#1b1f24}table{border-collapse:collapse}td,th{border:1px solid #d0d7de;"
    "padding:.35rem .6rem;text-align:left}code{font-size:.9em}"
)


def _load_asset(name: str, header: str) -> str:
    """Read a packaged asset next to this module (the action checkout, never the caller's).

    The source file starts with a license header line that is not part of the published
    asset, so the generated site stays byte-identical to the pre-split output.
    """
    text = (ASSETS_DIR / name).read_text(encoding="utf-8")
    first, sep, rest = text.partition("\n")
    if first != header or not sep:
        raise SiteError(f"{ASSETS_DIR / name}: missing the expected license header")
    return rest


def load_styles_css() -> str:
    return _load_asset("styles.css", "/* SPDX-License-Identifier: Apache-2.0 */")


def load_open_js() -> str:
    return _load_asset("open.js", "// SPDX-License-Identifier: Apache-2.0")


_SAFE_HOST = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.?"
)


def _valid_https_netloc(parsed: urllib.parse.SplitResult) -> bool:
    # urlsplit and the checks below refuse userinfo and malformed hosts and ports. An IP
    # literal such as [2001:db8::1] is refused too: the reporter never links to one.
    if not parsed.netloc:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    try:
        _ = parsed.port
        hostname = parsed.hostname
    except ValueError:
        return False
    if not hostname:
        return False
    return _SAFE_HOST.fullmatch(hostname) is not None


def safe_href(value: object, *, allow_https: bool = True) -> str | None:
    """Allow only https:// URLs (when `allow_https` is true) and relative links."""
    if not isinstance(value, str):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    cleaned = value.strip()
    if not cleaned or "\\" in cleaned or cleaned.startswith("//"):
        return None
    try:
        parsed = urllib.parse.urlsplit(cleaned)
    except ValueError:
        return None
    if parsed.scheme:
        if not allow_https or parsed.scheme.lower() != "https" or not _valid_https_netloc(parsed):
            return None
        return cleaned
    if parsed.netloc:
        return None
    return cleaned


def _evaluator_documents(report: object) -> list[dict]:
    if not isinstance(report, dict):
        return []
    docs: list[dict] = []
    bundle = report.get("source_bundle")
    if isinstance(bundle, dict):
        results = bundle.get("results")
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    continue
                items = result.get("evaluator_results")
                if isinstance(items, list):
                    docs.extend(d for d in items if isinstance(d, dict))
                prov = result.get("provenance")
                if isinstance(prov, dict):
                    p_items = prov.get("evaluator_results")
                    if isinstance(p_items, list):
                        docs.extend(d for d in p_items if isinstance(d, dict))
                    one = prov.get("evaluator_result")
                    if isinstance(one, dict):
                        docs.append(one)
                original = result.get("original_result")
                if isinstance(original, dict):
                    docs.append(original)
        assessment = bundle.get("assessment")
        integrity = assessment.get("integrity_results") if isinstance(assessment, dict) else None
        if isinstance(integrity, dict):
            for item in integrity.values():
                if isinstance(item, dict):
                    docs.append(item)
                elif isinstance(item, list):
                    docs.extend(d for d in item if isinstance(d, dict))
    summaries = report.get("summaries")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            items = summary.get("evaluator_results")
            if isinstance(items, list):
                docs.extend(d for d in items if isinstance(d, dict))
    return docs


def evaluator_slug(ev_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(ev_id)) or "evaluator"


def reporter_has_evaluator_anchors(record: dict) -> bool:
    releases = record.get("releases") if isinstance(record.get("releases"), dict) else {}
    reporter = releases.get("reporter") if isinstance(releases.get("reporter"), dict) else {}
    tag = _stored_text(reporter.get("tag"))
    found = _REPORTER_TAG.fullmatch(tag) if tag else None
    return found is not None and tuple(int(n) for n in found.groups()) >= ANCHOR_REPORTER


def page_evaluator_ids(report: object) -> set[str]:
    ids = set()
    for doc in _evaluator_documents(report):
        ev = doc.get("evaluator") if isinstance(doc.get("evaluator"), dict) else {}
        ev_id = _stored_text(ev.get("id"))
        if ev_id is not None:
            ids.add(ev_id)
    return ids


def evaluator_fragment(record: dict, ev_id: object, report: object = None) -> str:
    ev_id_str = _stored_text(ev_id)
    if ev_id_str is None or not reporter_has_evaluator_anchors(record):
        return EVALUATOR_ANCHOR
    ids = page_evaluator_ids(report)
    slug = evaluator_slug(ev_id_str)
    if ev_id_str not in ids or any(o != ev_id_str and evaluator_slug(o) == slug for o in ids):
        return EVALUATOR_ANCHOR
    return f"#evaluator-{slug}"


def _simple_page(title: str, body: str, up: str = "") -> str:
    safe_up = safe_href(up)
    nav = (
        f'<p><a href="{html.escape(safe_up, quote=True)}">← All verification reports</a></p>'
        if safe_up
        else ""
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{LISTING_STYLE}</style></head>"
        f"<body>{nav}<h1>{html.escape(title)}</h1>\n{body}\n</body></html>\n"
    )


def a(url: str, text: str) -> str:
    safe = safe_href(url)
    if safe is None:
        return html.escape(text)
    return f'<a href="{html.escape(safe, quote=True)}">{html.escape(text)}</a>'


def write_listing(folder: Path, record: dict, up: str) -> None:
    path = listing_path(record)
    if path is None or not site_path(path):
        return
    prefix = path.removesuffix(".html").removeprefix("evidence/") + "/"
    rows = "".join(
        "<tr><td>"
        + a(
            item["path"].removeprefix("evidence/"),
            item["path"].removeprefix(f"evidence/{prefix}"),
        )
        + f"</td><td>{item['bytes']}</td><td><code>{html.escape(item['sha256'])}</code></td></tr>"
        for item in record["files"]
    )
    title = _plain_label(record.get("label"))
    body = (
        f"<p>All {len(record['files'])} files copied to this site. "
        f"{a('../index.html', 'Back to the report')}</p>"
        f"<table><tr><th>File</th><th>Bytes</th><th>sha256</th></tr>{rows}</table>"
    )
    out = folder / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_simple_page(title, body, up=f"../{up}index.html"), encoding="utf-8")


def _spec_repository_url(spec: dict) -> str | None:
    repository = _stored_text(spec.get("repository"))
    if repository is None:
        return None
    repository = repository.rstrip("/").removesuffix(".git")
    if repository.startswith("https://"):
        try:
            parsed = urllib.parse.urlsplit(repository)
        except ValueError:
            return None
        if not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", parsed.netloc):
            return None
        if parsed.query or parsed.fragment:
            return None
        path = parsed.path.removeprefix("/")
        url = repository
    else:
        path = repository
        url = "https://github.com/" + repository
    if not _REPO_PATH.fullmatch(path) or path.rsplit("/", 1)[-1] in {".", ".."}:
        return None
    return url


def _spec_repository_label(spec: dict) -> str | None:
    url = _spec_repository_url(spec)
    if url:
        return urllib.parse.urlsplit(url).path.removeprefix("/")
    return _stored_text(spec.get("repository"))


def _spec_assessments(report: object) -> list[dict]:
    summaries = report.get("summaries", []) if isinstance(report, dict) else []
    assessed: list[dict] = []
    for summary in summaries if isinstance(summaries, list) else []:
        spec = summary.get("spec") if isinstance(summary, dict) else None
        if isinstance(spec, dict) and spec and spec not in assessed:
            assessed.append(spec)
    return assessed


def _spec_core(spec: object) -> tuple | None:
    if not isinstance(spec, dict) or not spec:
        return None
    repo_label = _spec_repository_label(spec)
    tag = _stored_text(spec.get("tag"))
    commit = _stored_text(spec.get("commit"))
    if repo_label is None and tag is None and commit is None:
        return None
    return (repo_label, tag, commit)


def _spec_line_html(spec: object, *, assessed: bool) -> str:
    core = _spec_core(spec)
    if core is None or not isinstance(spec, dict):
        return "Not recorded"
    _, tag, commit = core
    repository_url = _spec_repository_url(spec)
    pieces = []
    if tag is not None:
        label = html.escape(tag)
        if repository_url:
            href = f"{repository_url}/releases/tag/{urllib.parse.quote(tag, safe='')}"
            title = f"Release {tag}" + (f", commit {commit}" if commit is not None else "")
            pieces.append(
                f'<a href="{html.escape(href, quote=True)}" '
                f'title="{html.escape(title, quote=True)}">{label}</a>'
            )
        else:
            pieces.append(label)
    elif commit is not None:
        title = html.escape(f"Commit {commit}", quote=True)
        if repository_url and COMMIT_SHA.fullmatch(commit):
            pieces.append(
                f'<a href="{html.escape(repository_url, quote=True)}/commit/{commit}" '
                f'title="{title}" aria-label="{title}">commit</a>'
            )
        else:
            pieces.append(f'<span title="{title}">commit</span>')
    repository_label = _spec_repository_label(spec)
    if repository_label is not None:
        pieces.append(html.escape(repository_label))
    if assessed:
        cap = _stored_text(spec.get("capability"))
        if cap:
            pieces.append(html.escape(cap))
        rev = _stored_text(spec.get("revision"))
        if rev:
            pieces.append(html.escape("revision " + rev))
    return " · ".join(pieces)


def _spec_summary_html(generation: object, assessed: list[dict]) -> str:
    spec = assessed[0] if assessed else generation
    core = _spec_core(spec)
    if core is None or not isinstance(spec, dict):
        return "<strong>Spec</strong> not recorded"
    _, tag, _commit = core
    pieces = [html.escape(tag or "commit")]
    cap = _stored_text(spec.get("capability"))
    if cap:
        pieces.append(html.escape(cap))
    rev = _stored_text(spec.get("revision"))
    if rev:
        pieces.append(html.escape("revision " + rev))
    if len(assessed) > 1:
        pieces.append(f"+{len(assessed) - 1} more")
    return "<strong>Spec</strong> " + " · ".join(pieces)


_PROVENANCE_SUMMARY_STYLE = (
    "cursor:pointer;margin:0;font-size:inherit;font-weight:400;"
    "text-transform:none;letter-spacing:normal;color:inherit"
)
_PROVENANCE_SUMMARY_CSS = (
    "details.spec-provenance>summary::after{"
    'content:"Show";float:none;margin-left:.6rem;text-transform:none;'
    "letter-spacing:normal;font-weight:600;color:var(--link,#0b5cad)}"
    'details.spec-provenance[open]>summary::after{content:"Hide"}'
)


def spec_provenance_html(record: dict, report: object) -> str:
    generation = (record.get("releases") or {}).get("specs")
    assessed = _spec_assessments(report)
    if len(assessed) == 1 and _spec_core(generation) == _spec_core(assessed[0]) is not None:
        lines = [("Generation and assessment", _spec_line_html(assessed[0], assessed=True))]
    elif not assessed and _spec_core(generation) is None:
        lines = [("Generation and assessment", "Not recorded")]
    else:
        lines = [("Generation", _spec_line_html(generation, assessed=False))]
        lines += [("Assessment", _spec_line_html(spec, assessed=True)) for spec in assessed] or [
            ("Assessment", "Not recorded")
        ]
    rows = "".join(
        f'<dt style="font-weight:600">{label}</dt><dd style="margin:0 0 .5rem">{line}</dd>'
        for label, line in lines
    )
    return (
        '<details class="spec-provenance" id="spec-provenance" '
        'style="margin:1.5rem 0 0;font-size:.875rem;overflow-wrap:anywhere">'
        f'<summary style="{_PROVENANCE_SUMMARY_STYLE}">'
        f"{_spec_summary_html(generation, assessed)}</summary>"
        f"<style>{_PROVENANCE_SUMMARY_CSS}</style>"
        f'<dl style="margin:.5rem 0 0">{rows}</dl>'
        '<p style="margin:0;font-size:.8rem;opacity:.75">'
        "Recorded at run time; not reassessed.</p></details>"
    )


def with_spec_provenance(public: str, record: dict, report: object) -> str:
    if 'id="spec-provenance"' in public:
        return public
    section = spec_provenance_html(record, report)
    for closing in (r"</main\s*>", r"</body\s*>"):
        found = list(re.finditer(closing, public, re.I))
        if found:
            return public[: found[-1].start()] + section + public[found[-1].start() :]
    return public + section


def _site_nav_html(overview_href: str, reports_href: str, *, on_reports_index: bool = False) -> str:
    reports_attr = ' aria-current="page"' if on_reports_index else ""
    return (
        '<nav class="site-nav" aria-label="Site">'
        f'<a href="{html.escape(DOCS_HOME_URL, quote=True)}">Documentation home</a>'
        '<span class="site-nav-sep" aria-hidden="true">/</span>'
        f'<a href="{html.escape(overview_href, quote=True)}">Overview</a>'
        '<span class="site-nav-sep" aria-hidden="true">/</span>'
        f'<a href="{html.escape(reports_href, quote=True)}"{reports_attr}>Reports</a>'
        "</nav>"
    )


def with_site_nav(public: str, *, overview_href: str, reports_href: str) -> str:
    nav = _site_nav_html(overview_href, reports_href)
    if '<nav class="site-nav"' in public:
        return public
    style_tag = f"<style>{SITE_NAV_STYLES}</style>"
    if "</head>" in public and ".site-nav" not in public:
        public = public.replace("</head>", f"{style_tag}</head>", 1)
    masthead_inner = re.search(
        r"<div\s+class=[\"'][^\"']*\bmasthead-inner\b[^\"']*[\"'][^>]*>", public, re.I
    )
    if masthead_inner:
        pos = masthead_inner.end()
        return public[:pos] + nav + public[pos:]
    body_open = re.search(r"<body[^>]*>", public, re.I)
    if body_open:
        pos = body_open.end()
        header = f'<header class="masthead"><div class="wrap masthead-inner">{nav}</div></header>'
        return public[:pos] + header + public[pos:]
    return nav + public


def redirect_page(target: str, title: str = "Latest report") -> str:
    safe_target = safe_href(target) or ""
    safe = html.escape(safe_target, quote=True)
    shown = html.escape(title)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0; url={safe}">'
        f'<link rel="canonical" href="{safe}">'
        f"<title>{shown}</title></head><body>"
        f'<p><a href="{safe}">{shown}</a></p>'
        "</body></html>\n"
    )


def _robot_title(robot: str) -> str:
    if robot in _ROBOT_TITLES:
        return _ROBOT_TITLES[robot]
    parts = []
    for part in robot.split("-"):
        if re.fullmatch(r"[a-z]+\d+", part) and len(part) <= 3:
            parts.append(part.upper())
        else:
            parts.append(part.capitalize())
    return " ".join(parts)


def _scenario_title(record: dict, variant: str) -> str:
    outcomes = record.get("outcome") or []
    capability = outcomes[0].get("capability", "") if outcomes else ""
    frozen = legacy_scenario_title(capability, variant)
    if frozen:
        return frozen
    return (capability or variant).replace("-", " ").capitalize()


def _variant_subtitle(record: dict, variant: str) -> str:
    robot = record.get("robot") if isinstance(record.get("robot"), dict) else {}
    config = _stored_text(robot.get("configuration")) or variant.split("-", 1)[0]
    tokens = variant.split("-")
    sim = ""
    if "mujoco" in tokens:
        sim = "MuJoCo"
    elif "gazebo" in tokens:
        sim = "Gazebo"
    return f"{config} · {sim}" if sim else config


def _record_grade(record: dict) -> str:
    outcomes = record.get("outcome") or []
    grades = [o.get("grade", "") for o in outcomes if isinstance(o, dict)]
    if "FAIL" in grades:
        return "FAIL"
    if "INSUFFICIENT_EVIDENCE" in grades:
        return "INSUFFICIENT_EVIDENCE"
    if grades and all(g == "UNSUPPORTED" for g in grades):
        return "UNSUPPORTED"
    if "PASS" in grades:
        return "PASS"
    return (grades[0] if grades else "") or "UNKNOWN"


def _grade_sort_rank(grade: str) -> int:
    return {
        "FAIL": 0,
        "INSUFFICIENT_EVIDENCE": 1,
        "PASS": 2,
        "UNSUPPORTED": 3,
    }.get(grade, 4)


def _badge_label(grade: str) -> str:
    if grade == "UNSUPPORTED":
        return "Not supported"
    if grade == "INSUFFICIENT_EVIDENCE":
        return "Insufficient evidence"
    return grade


def _badge_html(grade: str) -> str:
    cls = {
        "PASS": "badge-pass",
        "FAIL": "badge-fail",
        "UNSUPPORTED": "badge-muted",
        "INSUFFICIENT_EVIDENCE": "badge-warn",
    }.get(grade, "badge-muted")
    return f'<span class="badge {cls}">{html.escape(_badge_label(grade))}</span>'


def _utc_time_text(created: str) -> str:
    created_dt = _stamp(created)
    return f"{created_dt.day} {created_dt.strftime('%b %Y, %H:%M')} UTC"


def _time_html(created: str) -> str:
    utc_text = _utc_time_text(created)
    return (
        f'<time datetime="{html.escape(created, quote=True)}" '
        f'title="{html.escape(utc_text, quote=True)}">{html.escape(utc_text)}</time>'
    )


def _release_html(record: dict, *, linked: bool = True) -> str:
    commit = record.get("commit") if isinstance(record.get("commit"), dict) else {}
    tag = _stored_text(record.get("release_tag") or record.get("bundle_tag") or commit.get("tag"))
    sha = _stored_text(commit.get("sha")) or ""
    commit_url = safe_href(_stored_text(commit.get("url")))
    if tag is not None:
        if commit_url and "/commit/" in commit_url:
            tag_url = safe_href(commit_url.split("/commit/", 1)[0] + f"/releases/tag/{tag}")
        else:
            tag_url = commit_url
        title = f"Release {tag}"
        if linked and tag_url:
            return (
                f'<a class="release" href="{html.escape(tag_url, quote=True)}" '
                f'title="{html.escape(title, quote=True)}">{html.escape(tag)}</a>'
            )
        return (
            f'<span class="release" title="{html.escape(title, quote=True)}">'
            f"{html.escape(tag)}</span>"
        )
    title = html.escape(
        "No release tag on this commit" + (f": {sha}" if sha else ""),
        quote=True,
    )
    if linked and commit_url:
        return (
            f'<a class="release is-fallback" href="{html.escape(commit_url, quote=True)}" '
            f'title="{title}">commit</a>'
        )
    return f'<span class="release is-fallback" title="{title}">commit</span>'


def _integrity_chip(
    title: str, status: str, prefix: str, linked: bool, fragment: str = EVALUATOR_ANCHOR
) -> str:
    tip = f"{title}: integrity status {status}"
    if status == "INCONCLUSIVE":
        tip += " (not graded)"
    words = "error" if status == "ERROR" else "not graded"
    icon = "\u2715" if status == "ERROR" else "?"
    klass = f"chip chip-integrity chip-integrity-{status.lower()}"
    body = f'<span aria-hidden="true">{icon}</span> {html.escape(title)} {words}'
    if linked:
        target = html.escape(prefix + fragment, quote=True)
        return (
            f'<a class="{klass}" href="{target}" title="{html.escape(tip, quote=True)}">{body}</a>'
        )
    return f'<span class="{klass}" title="{html.escape(tip, quote=True)}">{body}</span>'


def _chips_html(
    record: dict, prefix: str, *, linked: bool = True, extra: str = "", report: object = None
) -> str:
    grade = _record_grade(record)
    evaluators = record.get("failing_evaluators") or []
    items = []
    if grade not in ("PASS", "UNSUPPORTED") and isinstance(evaluators, list):
        for ev in evaluators:
            if not isinstance(ev, dict):
                continue
            title = _stored_text(ev.get("title"))
            href = _stored_text(ev.get("href"))
            if title is None or href is None:
                continue
            if ev.get("not_graded") is True:
                items.append(
                    _integrity_chip(
                        title,
                        "INCONCLUSIVE",
                        prefix,
                        linked,
                        evaluator_fragment(record, ev.get("id"), report),
                    )
                )
            elif linked:
                fragment = evaluator_fragment(record, ev.get("id"), report)
                tip = f"Open the {title} finding in the report"
                items.append(
                    f'<a class="chip" href="{html.escape(prefix + fragment, quote=True)}" '
                    f'title="{html.escape(tip, quote=True)}" '
                    f'aria-label="{html.escape(tip, quote=True)}">{html.escape(title)}</a>'
                )
            else:
                items.append(f'<span class="chip">{html.escape(title)}</span>')
    markers = record.get("integrity_status") or []
    if grade in ("PASS", "UNSUPPORTED") and isinstance(markers, list):
        for marker in markers:
            if not isinstance(marker, dict):
                continue
            title = _stored_text(marker.get("title"))
            status = marker.get("status")
            if title is None or status not in MARKED_INTEGRITY_STATUSES:
                continue
            if _stored_text(marker.get("id")) is None:
                continue
            items.append(
                _integrity_chip(
                    title,
                    status,
                    prefix,
                    linked,
                    evaluator_fragment(record, marker.get("id"), report),
                )
            )
    if extra:
        items.append(extra)
    if not items:
        return ""
    return f'<div class="chips">{"".join(items)}</div>'


def _spec_versions(record: dict, report: object) -> dict:
    generation = _stored_text(((record.get("releases") or {}).get("specs") or {}).get("tag"))
    assessed = _spec_assessments(report)

    def distinct(key: str) -> tuple | None:
        values = sorted({v for spec in assessed if (v := _stored_text(spec.get(key)))})
        return tuple(values) or None

    return {"generation": generation, "tags": distinct("tag"), "revisions": distinct("revision")}


def _spec_change(newer: dict, older: dict) -> str | None:
    def differs(key: str) -> bool:
        return newer[key] is not None and older[key] is not None and newer[key] != older[key]

    def label(value: object) -> str:
        return ", ".join(value) if isinstance(value, tuple) else str(value)

    pieces = []
    if differs("generation"):
        pieces.append(f"{older['generation']} → {newer['generation']}")
    elif differs("tags"):
        pieces.append(f"{label(older['tags'])} → {label(newer['tags'])}")
    if differs("revisions"):
        pieces.append(f"revision {label(older['revisions'])} → {label(newer['revisions'])}")
    return " · ".join(pieces) or None


def _spec_chip_html(change: str | None) -> str:
    if change is None:
        return ""
    return f'<span class="chip chip-spec">Spec changed: {html.escape(change)}</span>'


def _finding_html(record: dict) -> str:
    grade = _record_grade(record)
    if grade in ("PASS", "UNSUPPORTED"):
        return ""
    for ev in record.get("failing_evaluators") or []:
        if isinstance(ev, dict):
            summary = _stored_text(ev.get("summary"))
            if summary is not None:
                klass = "finding finding-neutral" if ev.get("not_graded") is True else "finding"
                return f'<p class="{klass}">{html.escape(summary)}</p>'
    for item in record.get("outcome") or []:
        if isinstance(item, dict):
            finding = _stored_text(item.get("finding"))
            if finding is not None:
                return f'<p class="finding">{html.escape(finding)}</p>'
    return ""


def _styled_document(
    title: str,
    css_href: str,
    skip_id: str,
    skip_label: str,
    masthead: str,
    main_body: str,
    *,
    script_href: str | None = None,
) -> str:
    script = (
        f'<script src="{html.escape(script_href, quote=True)}"></script>\n' if script_href else ""
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{html.escape(css_href, quote=True)}">\n'
        "<body>\n"
        f'<a class="skip" href="#{html.escape(skip_id, quote=True)}">'
        f"{html.escape(skip_label)}</a>\n"
        f'<header class="masthead"><div class="wrap masthead-inner">{masthead}</div></header>\n'
        f'<main class="page wrap" id="{html.escape(skip_id, quote=True)}">{main_body}</main>\n'
        f"{script}"
        "</body>\n"
        "</html>\n"
    )


def _history_page_html(
    robot: str,
    variant: str,
    records: list[dict],
    reports: dict | None = None,
) -> str:
    newest = records[0]
    robot_title = _robot_title(robot)
    scenario_title = _scenario_title(newest, variant)
    subtitle = _variant_subtitle(newest, variant)
    count = len(records)
    plural = "s" if count != 1 else ""

    releases_dict = newest.get("releases") if isinstance(newest.get("releases"), dict) else {}
    releases_parts = []
    for name, release in releases_dict.items():
        if not isinstance(release, dict):
            continue
        rel_tag = _stored_text(release.get("tag"))
        rel_url = safe_href(_stored_text(release.get("url")))
        if rel_tag and rel_url:
            releases_parts.append(f"{html.escape(name)} {a(rel_url, rel_tag)}")
        elif rel_tag:
            releases_parts.append(f"{html.escape(name)} {html.escape(rel_tag)}")
    releases_suffix = (
        f'<span class="quiet"> · {" · ".join(releases_parts)}</span>' if releases_parts else ""
    )

    robot_info = newest.get("robot") if isinstance(newest.get("robot"), dict) else {}
    repo_str = _stored_text(robot_info.get("repository")) or robot
    repo_short = repo_str.rstrip("/").rsplit("/", 1)[-1]
    robot_tag = _stored_text(robot_info.get("tag"))
    robot_commit = _stored_text(robot_info.get("commit")) or ""
    robot_url = safe_href(_stored_text(robot_info.get("url")))
    robot_label = html.escape(f"{repo_short} {robot_tag or 'commit'}")
    robot_pin_title = (
        ""
        if robot_tag or not robot_commit
        else f' title="{html.escape("Commit " + robot_commit, quote=True)}"'
    )
    if robot_url:
        robot_line = (
            f'<a href="{html.escape(robot_url, quote=True)}"{robot_pin_title}>{robot_label}</a>'
        )
    else:
        robot_line = f"<span{robot_pin_title}>{robot_label}</span>"
    software_version = _stored_text(robot_info.get("software_version"))
    if software_version is not None:
        config = _stored_text(robot_info.get("configuration")) or ""
        sw_label = f"{config} {software_version}".strip()
        robot_line += f'<span class="quiet"> · software {html.escape(sw_label)}</span>'

    masthead = (
        f"{_site_nav_html('../../../index.html', '../../index.html')}"
        '<div class="masthead-top">'
        '<p class="crumb"><a href="../../index.html">← All verification reports</a></p>'
        f"{THEME_SWITCH}"
        "</div>"
        f'<p class="eyebrow">{html.escape(robot_title)} · {html.escape(subtitle)}</p>'
        f"<h1>{html.escape(scenario_title)}</h1>"
        f'<p class="lede">{count} run{plural}, newest first.</p>'
        f'<p class="meta-line">{a("latest/", "Latest report")}{releases_suffix}</p>'
        f'<p class="meta-line">{robot_line}</p>'
    )
    row_cards = []
    for position, record in enumerate(records):
        grade = _record_grade(record)
        row_class = "row is-fail" if grade in ("FAIL", "INSUFFICIENT_EVIDENCE") else "row is-pass"
        run_prefix = f"runs/{record['folder']}/"
        poster = record.get("poster")
        poster_name = (
            _stored_text(poster.get("name")) if isinstance(poster, dict) else None
        ) or "CI"
        below = records[position + 1] if position + 1 < len(records) else None
        change = None
        if below is not None:
            change = _spec_change(
                _spec_versions(record, (reports or {}).get(record["folder"])),
                _spec_versions(below, (reports or {}).get(below["folder"])),
            )
        chips = _chips_html(
            record,
            run_prefix,
            extra=_spec_chip_html(change),
            report=(reports or {}).get(record["folder"]),
        )
        finding = _finding_html(record)
        row_cards.append(
            f'<article class="{row_class}">'
            '<div class="row-top">'
            f"{_badge_html(grade)}"
            "<div>"
            f'<h2 class="title">{html.escape(scenario_title)}</h2>'
            f"{chips}{finding}"
            '<div class="row-meta">'
            f"{_release_html(record)}"
            '<span class="dot">·</span>'
            f"{_time_html(record['run']['created'])}"
            '<span class="dot">·</span>'
            f'<span class="poster">{html.escape(poster_name)}</span>'
            '<span class="dot">·</span>'
            f"{a(run_prefix, 'Report')}"
            "</div>"
            "</div>"
            "</div>"
            "</article>"
        )
    main_body = f'<div class="history">{"".join(row_cards)}</div>'
    return _styled_document(
        f"{robot_title} · {subtitle} · {scenario_title} · run history",
        "../../styles.css",
        "history",
        "Skip to history",
        masthead,
        main_body,
        script_href="../../open.js",
    )


def _index_card_html(robot: str, variant: str, records: list[dict]) -> str:
    newest = records[0]
    grade = _record_grade(newest)
    card_class = "card is-fail" if grade in ("FAIL", "INSUFFICIENT_EVIDENCE") else "card"
    scenario_title = _scenario_title(newest, variant)
    subtitle = _variant_subtitle(newest, variant)
    latest_href = f"{robot}/{variant}/latest/"
    history_href = f"{robot}/{variant}/"
    run_prefix = f"{robot}/{variant}/runs/{newest['folder']}/"
    chips = _chips_html(newest, run_prefix, linked=False)
    finding = _finding_html(newest)
    card_label = f"{scenario_title}, latest report ({_badge_label(grade)})"
    return (
        f'<article class="{card_class}">'
        '<div class="entry-main">'
        f"{_badge_html(grade)}"
        '<div class="entry-body">'
        f'<h3 class="title"><a class="card-link" href="{html.escape(latest_href, quote=True)}" '
        f'aria-label="{html.escape(card_label, quote=True)}">{html.escape(scenario_title)}</a></h3>'
        f'<p class="sub">{html.escape(subtitle)}</p>'
        f"{chips}{finding}"
        "</div>"
        '<div class="entry-side">'
        f'<div class="side-meta">{_release_html(newest, linked=False)}'
        f'<span class="dot">·</span>{_time_html(newest["run"]["created"])}</div>'
        '<div class="links"><a class="history-link" '
        f'href="{html.escape(history_href, quote=True)}">'
        f"History ({len(records)})</a></div>"
        "</div>"
        "</div>"
        "</article>"
    )


def _index_page_html(history: dict[tuple[str, str], list[dict]]) -> str:
    robots = {robot for robot, _ in history}
    robot = _require_single_robot(robots)
    robot_title = _robot_title(robot) if robot else "Living Proof Labs"

    variants = [(variant, records) for (_, variant), records in sorted(history.items())]
    ordered = sorted(
        variants,
        key=lambda item: (
            _grade_sort_rank(_record_grade(item[1][0])),
            _scenario_title(item[1][0], item[0]).lower(),
            _variant_subtitle(item[1][0], item[0]).lower(),
            item[0],
        ),
    )
    total_count = len(ordered)
    all_latest = [recs[0] for _, recs in ordered]

    if total_count == 0:
        body_html = '<p class="status">No verification reports published yet.</p>'
    else:
        fail_count = sum(1 for r in all_latest if _record_grade(r) == "FAIL")
        insuff_count = sum(1 for r in all_latest if _record_grade(r) == "INSUFFICIENT_EVIDENCE")
        pass_count = sum(1 for r in all_latest if _record_grade(r) == "PASS")
        unsup_count = sum(1 for r in all_latest if _record_grade(r) == "UNSUPPORTED")
        unknown_count = total_count - fail_count - insuff_count - pass_count - unsup_count

        if fail_count:
            noun = "result" if fail_count == 1 else "results"
            status_line = (
                f'<p class="status"><strong>{fail_count} latest {noun} failed.</strong> '
                "Failing scenarios are listed first below.</p>"
            )
        elif all(_record_grade(r) == "PASS" for r in all_latest):
            noun = "result" if total_count == 1 else "results"
            Verb = "passes" if total_count == 1 else "pass"
            status_line = f'<p class="all-pass">All {total_count} latest {noun} {Verb}.</p>'
        else:
            labels = {
                "PASS": "passed",
                "INSUFFICIENT_EVIDENCE": "insufficient evidence",
                "UNSUPPORTED": "not supported",
            }
            tally = {label: 0 for label in (*labels.values(), "unknown")}
            for rec in all_latest:
                tally[labels.get(_record_grade(rec), "unknown")] += 1
            summary = ", ".join(f"{c} {lbl}" for lbl, c in tally.items() if c)
            noun = "result" if total_count == 1 else "results"
            status_line = f'<p class="status">{total_count} latest {noun}: {summary}.</p>'

        scenario_noun = "scenario" if total_count == 1 else "scenarios"
        count_parts = [f"{total_count} {scenario_noun}"]
        if fail_count:
            count_parts.append(f'<span class="fail-count">{fail_count} failed</span>')
        if insuff_count:
            count_parts.append(f'<span class="fail-count">{insuff_count} insufficient</span>')
        if pass_count:
            count_parts.append(f'<span class="pass-count">{pass_count} passed</span>')
        if unsup_count:
            count_parts.append(f'<span class="pass-count">{unsup_count} not supported</span>')
        if unknown_count:
            count_parts.append(f'<span class="counts">{unknown_count} unknown</span>')
        counts_html = '<span class="count-sep">·</span>'.join(count_parts)

        dots = []
        cards = []
        assert robot is not None
        for variant, records in ordered:
            newest = records[0]
            grade = _record_grade(newest)
            scenario_title = _scenario_title(newest, variant)
            pip_cls, pip_status = {
                "FAIL": ("pip-fail", "failed"),
                "PASS": ("pip-pass", "passed"),
                "INSUFFICIENT_EVIDENCE": ("pip-warn", "insufficient evidence"),
                "UNSUPPORTED": ("pip-muted", "not supported"),
            }.get(grade, ("pip-muted", grade.lower()))
            dots.append(
                f'<span class="pip {pip_cls}" '
                f'title="{html.escape(f"{scenario_title}: {pip_status}", quote=True)}"></span>'
            )
            cards.append(_index_card_html(robot, variant, records))

        latest_record = max(
            all_latest,
            key=lambda r: (r["run"]["created"], r.get("folder", "")),
        )
        meta_latest = (
            f"{_release_html(latest_record, linked=False)}"
            '<span class="dot">·</span>'
            f"{_time_html(latest_record['run']['created'])}"
        )
        summary_bar = (
            '<div class="summary-bar">'
            f'<div class="counts">{counts_html}</div>'
            f'<span class="dots">{"".join(dots)}<span class="pip-more" hidden></span></span>'
            f'<span class="meta-latest">{meta_latest}</span>'
            "</div>"
        )
        scenarios_section = (
            '<section aria-labelledby="scenarios">'
            '<h2 class="scenarios-label" id="scenarios">Scenarios</h2>'
            f'<div class="stack">{"".join(cards)}</div>'
            "</section>"
        )
        body_html = status_line + summary_bar + scenarios_section

    masthead = (
        f"{_site_nav_html('../index.html', 'index.html', on_reports_index=True)}"
        '<div class="masthead-top">'
        f'<p class="eyebrow">{html.escape(robot_title)}</p>'
        f"{THEME_SWITCH}"
        "</div>"
        "<h1>Verification reports</h1>"
        '<p class="lede">The latest result for each scenario, with failures first.</p>'
    )
    page_title = f"{robot_title} · verification reports" if robot else "Verification reports"
    return _styled_document(
        page_title,
        "styles.css",
        "results",
        "Skip to results",
        masthead,
        body_html,
        script_href="open.js",
    )


# ---------------------------------------------------------------- published report HTML policy
#
# A run folder's report.html is published on the Pages origin, and a forged run folder can
# recompute SHA256SUMS, so the site checks the markup itself. The check is a parser-based
# allowlist built from the reporter's own vocabulary (livingproof-capability-report v3.x).
# Markup that passes is published byte for byte. Anything outside the allowlist refuses the
# report rather than being rewritten, so there is no sanitizer output to get wrong. The one
# exception is a <script>: the reporter's scripts are pinned by SHA-256, and an unknown one
# is removed with a warning, because a reporter release can change them and the page still
# works without them.

KNOWN_REPORTER_SCRIPTS = frozenset(
    {
        # <script data-eval-tabs>, reporter v3.12.0, v3.12.1 to v3.13.2, v3.14.0 to v3.15.4.
        "f80671dbdb7866984cc3c26202461753d1b79a77c6568209ba0a184f935e84f9",
        "12b0d29d518b9a7836e6583d6bd4673e44798427bdcfc47f1af96d4e74a00f25",
        "b1bac501529a257799babc2601f70c201a430b29fb6b7637dcec5e4808f1d036",
        # <script data-report-times>, reporter v3.15.0 to v3.15.4.
        "6ef03a512acca84357119a1445dd6be7080da5a99f64f6b8a17197145d7fea88",
    }
)
_HTML_ELEMENTS = frozenset(
    """html head body meta title style script main header footer nav section article aside
    div span p br hr h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table caption thead tbody tfoot tr th
    td details summary fieldset legend label input strong em b i u s small mark code pre kbd
    samp sub sup abbr blockquote q cite time a video img figure figcaption""".split()
)
_SVG_ELEMENTS = frozenset(
    "svg g path circle rect ellipse line polyline polygon text tspan title desc".split()
)
_VOID_ELEMENTS = frozenset({"meta", "br", "hr", "input", "img"})
_GLOBAL_ATTRS = frozenset({"id", "class", "title", "role", "lang", "dir", "tabindex", "hidden"})
_ELEMENT_ATTRS = {
    "a": {"href"},
    "video": {"src", "poster", "controls", "preload", "muted", "loop", "playsinline"},
    "img": {"src", "alt", "width", "height", "loading", "decoding"},
    "meta": {"charset", "name", "content"},
    "input": {"type", "name", "value", "checked", "disabled"},
    "label": {"for"},
    "th": {"scope", "colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
    "details": {"open", "name"},
    "time": {"datetime"},
    "ol": {"start", "reversed"},
}
_SVG_ATTRS = frozenset(
    """viewbox xmlns width height fill fill-opacity fill-rule clip-rule stroke stroke-width
    stroke-linecap stroke-linejoin stroke-dasharray stroke-dashoffset stroke-opacity
    stroke-miterlimit d cx cy r rx ry x y x1 y1 x2 y2 dx dy points transform opacity
    focusable font-family font-size font-weight text-anchor dominant-baseline pathlength
    visibility preserveaspectratio""".split()
)
_SCRIPT_ATTRS = frozenset({"data-eval-tabs", "data-report-times"})
_URL_ATTRS = frozenset({"href", "src", "poster"})
_MEDIA_URL_ATTRS = frozenset({"src", "poster"})
_META_NAMES = frozenset({"viewport", "color-scheme"})
_ATTR_SOURCE = r"""[a-zA-Z_:][-a-zA-Z0-9_:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?"""
_STRICT_START_TAG = re.compile(rf"<[a-zA-Z][a-zA-Z0-9]*(?:\s+{_ATTR_SOURCE})*\s*/?>")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")\s]*)", re.I)
_CSS_FORBIDDEN = ("\\", "/*", "@import", "image-set", "expression(", "javascript:")
_CSS_SAFE_URL_PREFIXES = ("data:font/woff2;base64,", "data:font/woff;base64,")


def _css_is_inert(css: str) -> bool:
    """CSS may not fetch anything: the only url() it may use is an inline font."""
    flat = _CSS_COMMENT.sub("", css).lower()
    if any(token in flat for token in _CSS_FORBIDDEN):
        return False
    urls = _CSS_URL.findall(flat)
    if len(urls) != flat.count("url("):
        return False
    return all(url.startswith(_CSS_SAFE_URL_PREFIXES) for url in urls)


# html.parser does not tokenize the way a browser does, and how far it differs depends on the
# Python patch release: before the 2025 fixes it read <title> and <textarea> as ordinary
# elements and missed script ends such as "</script x>". So the source is first tokenized by
# the small scanner below, which follows the browser's rules and refuses anything the two
# could read differently. Every "<" must begin a plain start tag, a plain end tag or the
# doctype; no attribute value holds "<" or ">", and an unquoted one does not end in "/"; and
# <script>, <style>, <title> and <textarea> run to their exact lower-case close tag with no
# other "</" or "<!--" before it, and no "<" at all in <title> or <textarea>. Only then is the
# allowlist below applied, so its result does not depend on the interpreter's html.parser.
_SCAN_SPACE = "[\t\n\f\r ]"
_SCAN_ATTR = (
    rf"{_SCAN_SPACE}+[a-zA-Z_:][-a-zA-Z0-9_:.]*"
    rf"(?:{_SCAN_SPACE}*={_SCAN_SPACE}*"
    r"""(?:"[^"<>]*"|'[^'<>]*'|[^\t\n\f\r "'=<>`]+(?<!/)(?=[\t\n\f\r >])))?"""
)
_SCAN_START_TAG = re.compile(rf"<([a-zA-Z][a-zA-Z0-9]*)(?:{_SCAN_ATTR})*{_SCAN_SPACE}*(/?)>")
_SCAN_END_TAG = re.compile(r"</[a-zA-Z][a-zA-Z0-9]*>")
_SCAN_DOCTYPE = re.compile(r"<!doctype html>", re.I)
_SCAN_RAW_TEXT = frozenset({"script", "style"})
_SCAN_RCDATA = frozenset({"title", "textarea"})


def _scan_markup(text: str) -> None:
    """Refuse markup that a browser and some html.parser release could tokenize differently."""

    def refuse(offset: int, reason: str) -> None:
        line = text.count("\n", 0, offset) + 1
        column = offset - (text.rfind("\n", 0, offset) + 1) + 1
        raise SiteError(f"line {line} column {column}: {reason}")

    pos = 0
    while (pos := text.find("<", pos)) != -1:
        match = _SCAN_DOCTYPE.match(text, pos) or _SCAN_END_TAG.match(text, pos)
        if match:
            pos = match.end()
            continue
        match = _SCAN_START_TAG.match(text, pos)
        if not match:
            refuse(pos, "'<' does not begin a plainly written tag")
        name = match.group(1).lower()
        pos = match.end()
        if name not in _SCAN_RAW_TEXT and name not in _SCAN_RCDATA:
            continue
        if match.group(2):
            refuse(match.start(), f"<{name}/> is not allowed")
        close = text.find("</", pos)
        if close == -1 or text[close : close + len(name) + 3] != f"</{name}>":
            refuse(close if close != -1 else pos, f"<{name}> does not end with a plain </{name}>")
        body = text[pos:close]
        if "<!--" in body or (name in _SCAN_RCDATA and "<" in body):
            refuse(pos, f"<{name}> holds markup")
        pos = close + len(name) + 3


class _ReportHtmlPolicy(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_starts = [0]
        for match in re.finditer("\n", text):
            self.line_starts.append(match.end())
        self.stack: list[str] = []
        self.open_counts: dict[str, int] = {}
        self.svg_depth = 0
        self.script_start: int | None = None
        self.unknown_scripts: list[tuple[int, int, str]] = []

    def source_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def refuse(self, reason: str) -> None:
        line, column = self.getpos()
        raise SiteError(f"line {line} column {column + 1}: {reason}")

    def in_svg(self) -> bool:
        return self.svg_depth > 0

    def check_tag_source(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = self.get_starttag_text() or ""
        if not _STRICT_START_TAG.fullmatch(source):
            self.refuse(f"<{tag}> is not plainly written")
        names = [name for name, _ in attrs]
        if len(set(names)) != len(names):
            self.refuse(f"<{tag}> has a repeated attribute")

    def check_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        svg = tag in _SVG_ELEMENTS and (tag == "svg" or self.in_svg())
        for name, value in attrs:
            if svg and name in _SVG_ATTRS:
                if value is not None and not _css_is_inert(value):
                    self.refuse(f"<{tag} {name}> may fetch a resource")
                continue
            if name == "style":
                if value is None or not _css_is_inert(value):
                    self.refuse(f"<{tag} style> may fetch a resource")
                continue
            if not (
                name in _GLOBAL_ATTRS
                or name.startswith(("aria-", "data-"))
                or name in _ELEMENT_ATTRS.get(tag, ())
            ):
                self.refuse(f"<{tag}> attribute {name!r} is not allowed")
            if name in _MEDIA_URL_ATTRS:
                if safe_href(html.unescape(value or ""), allow_https=False) is None:
                    self.refuse(f"<{tag} {name}> is not a relative link")
            elif name in _URL_ATTRS and safe_href(html.unescape(value or "")) is None:
                self.refuse(f"<{tag} {name}> is not an https or relative link")
        found = dict(attrs)
        if tag == "meta" and not (
            set(found) == {"charset"}
            and (found["charset"] or "").lower() == "utf-8"
            or set(found) == {"name", "content"}
            and (found["name"] or "").lower() in _META_NAMES
        ):
            self.refuse("<meta> may only set charset=utf-8, viewport or color-scheme")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.check_tag_source(tag, attrs)
        if self.in_svg():
            if tag not in _SVG_ELEMENTS:
                self.refuse(f"<{tag}> is not allowed inside <svg>")
        elif tag not in _HTML_ELEMENTS and tag != "svg":
            self.refuse(f"<{tag}> is not allowed")
        if tag == "script":
            if len(attrs) != 1 or attrs[0][0] not in _SCRIPT_ATTRS or attrs[0][1] is not None:
                self.refuse("<script> is not one of the reporter's scripts")
            self.script_start = self.source_offset()
        else:
            self.check_attrs(tag, attrs)
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)
            self.open_counts[tag] = self.open_counts.get(tag, 0) + 1
            if tag == "svg":
                self.svg_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A browser ignores "/>" on an HTML element, so <style/> or <script/> would open a
        # raw-text element here that this parser closes at once.
        svg = tag in _SVG_ELEMENTS and (tag == "svg" or self.in_svg())
        if not (tag in _VOID_ELEMENTS or svg):
            self.refuse(f"<{tag}/> is not a void or SVG element")
        self.check_tag_source(tag, attrs)
        # Outside <svg> the rule above already limits this to void HTML elements and <svg>.
        if self.in_svg() and tag not in _SVG_ELEMENTS:
            self.refuse(f"<{tag}> is not allowed inside <svg>")
        self.check_attrs(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _HTML_ELEMENTS and tag not in _SVG_ELEMENTS:
            self.refuse(f"</{tag}> is not allowed")
        if tag == "script" and self.script_start is not None:
            start = self.source_offset()
            if self.text[start : start + 9].lower() != "</script>":
                self.refuse("</script> is not plainly written")
            element = self.text[self.script_start : start + 9]
            digest = hashlib.sha256(element.encode("utf-8")).hexdigest()
            if digest not in KNOWN_REPORTER_SCRIPTS:
                self.unknown_scripts.append((self.script_start, start + 9, digest))
            self.script_start = None
        if self.in_svg():
            # Inside <svg> a browser's tree depends on exact nesting, so require it.
            if self.stack[-1] != tag:
                self.refuse(f"</{tag}> does not close the open <{self.stack[-1]}> inside <svg>")
            popped = self.stack.pop()
            self.open_counts[popped] -= 1
            if popped == "svg":
                self.svg_depth -= 1
        elif self.open_counts.get(tag, 0) > 0:
            while True:
                popped = self.stack.pop()
                self.open_counts[popped] -= 1
                if popped == tag:
                    break

    def handle_data(self, data: str) -> None:
        current = self.stack[-1] if self.stack else ""
        if current == "style":
            if not _css_is_inert(data):
                self.refuse("<style> may fetch a resource")
            return
        if current == "script":
            return
        if "<" in data:
            self.refuse("text holds a raw '<'")

    def handle_comment(self, data: str) -> None:
        self.refuse("comments are not allowed")

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            self.refuse(f"<!{decl}> is not allowed")

    def handle_pi(self, data: str) -> None:
        self.refuse("processing instructions are not allowed")

    def unknown_decl(self, data: str) -> None:
        self.refuse("CDATA and other declarations are not allowed")


def _parsed_policy(text: str) -> _ReportHtmlPolicy:
    """Apply the element and attribute allowlist with html.parser (the second layer)."""
    policy = _ReportHtmlPolicy(text)
    policy.feed(text)
    policy.close()
    if policy.stack and policy.stack[-1] in {"script", "style"}:
        raise SiteError(f"report.html ends inside <{policy.stack[-1]}>")
    return policy


MAX_REPORT_HTML_BYTES = 8 * 1024 * 1024
_SCRIPT_WARNING_EXAMPLES = 3


def checked_report_html(text: str, where: str) -> str:
    """Return `text` unchanged if it passes the published HTML policy, else refuse it.

    Two independent layers: `_scan_markup` tokenizes the source the way a browser does and
    refuses anything html.parser could read differently, then `_parsed_policy` applies the
    allowlist. Unknown <script> elements are cut out with a warning.
    """
    if len(text) > MAX_REPORT_HTML_BYTES or len(text.encode("utf-8")) > MAX_REPORT_HTML_BYTES:
        raise SiteError(f"{where}: report.html exceeds the {MAX_REPORT_HTML_BYTES}-byte limit")
    if any((ord(ch) < 32 and ch not in "\t\n\r\f") or ord(ch) == 127 for ch in text):
        raise SiteError(f"{where}: report.html holds a control character")
    try:
        _scan_markup(text)
        policy = _parsed_policy(text)
    except SiteError as exc:
        raise SiteError(f"{where}: {exc}") from None
    # The scan makes each <script> run from a plain start tag to its exact </script>, and text
    # outside tags holds no "<", so cutting one out cannot join new markup: no second pass.
    scripts = policy.unknown_scripts
    if not scripts:
        return text
    # One summary line and a few examples: a forged page can hold many thousands of scripts.
    for _, _, digest in scripts[:_SCRIPT_WARNING_EXAMPLES]:
        print(
            f"::warning::{where}: removed a <script> that is not a known reporter "
            f"script (sha256 {digest})",
            file=sys.stderr,
        )
    if len(scripts) > _SCRIPT_WARNING_EXAMPLES:
        print(
            f"::warning::{where}: removed {len(scripts)} <script> elements that are not known "
            f"reporter scripts in all ({len(scripts) - _SCRIPT_WARNING_EXAMPLES} more not listed)",
            file=sys.stderr,
        )
    # Keep the text between scripts and join it once: cutting one script at a time copies the
    # whole page per script, which is quadratic in the number of scripts.
    kept = []
    pos = 0
    for start, end, _ in scripts:
        kept.append(text[pos:start])
        pos = end
    kept.append(text[pos:])
    return "".join(kept)
