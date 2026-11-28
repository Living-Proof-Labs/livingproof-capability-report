# SPDX-License-Identifier: Apache-2.0
"""Assemble a single-robot verification reports section (`reports/`) for GitHub Pages.

Ported from verification-reports-action `src/reports_site.py` (va#75). The action keeps
fetching the earlier Pages history; this module only renders and checks.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path, PurePosixPath

from .details import DetailsPathError, cited_details_uris, read_cited_details, safe_relative
from .common import (
    ARTIFACT_WORD,
    COMMIT_SHA,
    EVALUATOR_ANCHOR,
    MARKED_INTEGRITY_STATUSES,
    RELEASE_TAG,
    SiteError,
    _plain_label,
    _require_single_robot,
    _stamp,
    _stored_text,
    listing_path,
    site_path,
)
from .pages import (
    DOCS_HOME_URL,
    _evaluator_documents,
    _history_page_html,
    _index_page_html,
    _spec_repository_url,
    checked_report_html,
    load_open_js,
    load_styles_css,
    redirect_page,
    safe_href,
    with_site_nav,
    with_spec_provenance,
    write_listing,
)

MARKER = "site.json"

__all__ = [
    "DOCS_HOME_URL",
    "MARKER",
    "SiteError",
    "build",
    "parse_exclude_runs",
    "render",
    "safe_href",
    "validate_exclude_run_id",
]

SEGMENT = re.compile(r"[a-z0-9][a-z0-9.-]*")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REPORT_FILES = ("report.html", "report.json", "report.md", "report.txt")
REQUIRED_RUN_FILES = (*REPORT_FILES, "SHA256SUMS", "run.json")
MAX_RUN_EVIDENCE_BYTES = 25_000_000
DEFAULT_RETENTION_DAYS = 7
ORIGINAL_HTML = "report.html.orig"

ARTIFACT_LINK = re.compile(
    r"<a href=(['\"])(https://github\.com/[^'\"<>]+/actions/runs/[0-9]+/artifacts/([0-9]+))\1>"
    r"(.*?)</a>",
    re.S,
)
# The one Actions address a public page may carry is a CI run page of this
# repository: https://github.com/<this owner>/<this repo>/actions/runs/<id>.
# The address must end after the id (not .zip, ;a=1, :80, a query, a fragment).
# An artifact, job, attempt, workflow file or another repository is refused.
_REPO_SEGMENT = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_RUN_TAIL = r"/actions/runs/[0-9]+"
_ADDRESS_END = r"(?=$|[\s'\"<>)\],]|\.(?![A-Za-z0-9]))"


def _run_body(repository: str | set[str] | None = None) -> str:
    if isinstance(repository, set):
        if not repository:
            repo = f"{_REPO_SEGMENT}/{_REPO_SEGMENT}"
        else:
            repo = "(?:" + "|".join(re.escape(item) for item in sorted(repository)) + ")"
    elif repository:
        repo = re.escape(repository)
    else:
        repo = f"{_REPO_SEGMENT}/{_REPO_SEGMENT}"
    return f"{repo}{_RUN_TAIL}"


def run_address_re(repository: str | set[str] | None = None) -> re.Pattern[str]:
    return re.compile(r"https://github\.com/" + _run_body(repository) + _ADDRESS_END)


def actions_url_re(repository: str | set[str] | None = None) -> re.Pattern[str]:
    return re.compile(
        r"https://github\.com/(?!" + _run_body(repository) + _ADDRESS_END + r")\S*?/actions/\S*",
        re.I,
    )


def is_run_address(url: str, repository: str | set[str] | None = None) -> bool:
    return re.fullmatch(r"https://github\.com/" + _run_body(repository), url) is not None


RUN_ADDRESS = run_address_re()
ACTIONS_ANCHOR = re.compile(
    r"<a\s[^>]*?href=(['\"])([^'\"<>]*/actions/[^'\"<>]*)\1[^>]*>(.*?)</a>", re.S | re.I
)
ACTIONS_URL = actions_url_re()
EVIDENCE_ANCHOR = re.compile(
    r"<a\s[^>]*?href=(['\"])(evidence/[^'\"<>]+)\1[^>]*>(.*?)</a>", re.S | re.I
)
EVIDENCE_VIDEO = re.compile(
    r"<video\b(?:(?!</video\b).)*?evidence/[^'\"<>\s]+(?:(?!</video\b).)*?</video\s*>",
    re.S | re.I,
)
EVIDENCE_IMG = re.compile(r"<img\b[^>]*?\bsrc=(['\"])(evidence/[^'\"<>]+)\1[^>]*/?>", re.S | re.I)
KEPT_FOR_COPY = re.compile(r"Evidence kept for \d+ days?")

MEDIA_SUFFIXES = {
    ".mcap",
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
# Evidence types the site publishes. Anything else is not copied, so a MIME mapping on Pages
# (GitHub serves .xsd and .rng as application/xml, which a browser runs as XHTML) cannot put
# an active document on the Pages origin. This is what reporters emit (MCAP, video, images,
# media.json and logs), plus plain-text and data formats a browser only displays.
PUBLISHED_EVIDENCE_SUFFIXES = frozenset(MEDIA_SUFFIXES | {".json", ".txt", ".log", ".md", ".csv"})

SEED_LABEL = re.compile(r"^seed (?=\d)")


# ---------------------------------------------------------------- validation & outcomes


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_json_object(path: Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SiteError(f"{path}: not valid JSON ({error.msg} at line {error.lineno})") from None
    except OSError as error:
        raise SiteError(f"{path}: cannot read file ({error})") from error
    if not isinstance(parsed, dict):
        raise SiteError(f"{path}: expected a JSON object, found {type(parsed).__name__}")
    return parsed


def read_report(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SiteError(f"{path}: not valid JSON ({error.msg} at line {error.lineno})") from None


def check_evaluators(report: object, where: Path) -> None:
    if not isinstance(report, dict) or "source_bundle" not in report:
        return
    bundle = report.get("source_bundle")
    results = bundle.get("results") if isinstance(bundle, dict) else None
    summaries = report.get("summaries")
    unsupported = (
        isinstance(summaries, list)
        and bool(summaries)
        and all(isinstance(s, dict) and s.get("grade") == "UNSUPPORTED" for s in summaries)
    )
    if not results:
        if unsupported:
            return
        raise SiteError(
            f"{where}: no assessed trials in source_bundle.results, so no evaluator "
            "result to show. Only an UNSUPPORTED report with no trials run publishes "
            "without one."
        )
    for index, result in enumerate(results, start=1):
        trial = result.get("id") if isinstance(result, dict) else None
        trial = trial if _text(trial) else f"trial {index}"
        evaluated = result.get("evaluator_results") if isinstance(result, dict) else None
        if not isinstance(evaluated, list) or not evaluated:
            raise SiteError(
                f"{where}: {trial} has no evaluator result. The report would show a "
                "placeholder evaluator. Append the evaluator results to the bundle "
                "before rendering the report."
            )
        for item in evaluated:
            evaluator = item.get("evaluator") if isinstance(item, dict) else None
            name = evaluator.get("id") if isinstance(evaluator, dict) else None
            name = name if _text(name) else "(no id)"
            descriptor = item.get("descriptor") if isinstance(item, dict) else None
            if not isinstance(descriptor, dict):
                raise SiteError(f"{where}: {trial} evaluator {name} has no descriptor")
            for field in ("title", "purpose"):
                if not _text(descriptor.get(field)):
                    raise SiteError(f"{where}: {trial} evaluator {name} descriptor has no {field}")


REPORT_VERSIONS = {"1.0.0"}
SUMMARY_FIELDS = ("capability", "system", "grade")


def reproducibility_statement(summary: dict) -> str | None:
    block = summary.get("reproducibility")
    if not isinstance(block, dict) or block.get("compared") is not True:
        return None
    return _stored_text(block.get("statement"))


def reproducibility_finding(summary: dict) -> str | None:
    block = summary.get("reproducibility")
    if not isinstance(block, dict) or block.get("compared") is not True:
        return None
    finding = block.get("finding")
    if isinstance(finding, dict):
        return _stored_text(finding.get("detail"))
    return _stored_text(finding)


def outcome(report: object, where: str = "report.json") -> list[dict]:
    if not isinstance(report, dict):
        raise SiteError(f"{where}: expected a JSON object, found {type(report).__name__}")
    version = report.get("report_version")
    if not isinstance(version, str) or version not in REPORT_VERSIONS:
        raise SiteError(
            f"{where}: report_version {version!r} is not one this site reads "
            f"({', '.join(sorted(REPORT_VERSIONS))})"
        )
    summaries = report.get("summaries")
    if not isinstance(summaries, list) or not summaries:
        raise SiteError(f"{where}: report_version {version} without a non-empty summaries list")
    for index, s in enumerate(summaries):
        if not isinstance(s, dict):
            raise SiteError(f"{where}: summaries[{index}] is {type(s).__name__}, not an object")
        missing = [f for f in SUMMARY_FIELDS if f not in s]
        if not isinstance(s.get("system"), dict) or "id" not in s["system"]:
            missing.append("system.id")
        if missing:
            raise SiteError(f"{where}: summaries[{index}] lacks {', '.join(missing)}")
    rows = []
    for s in summaries:
        row: dict = {
            "capability": s["capability"],
            "system": s["system"]["id"],
            "grade": s["grade"],
            "passed": s.get("k"),
            "trials": s.get("n"),
            "required": s.get("required_passes"),
        }
        statement = reproducibility_statement(s)
        if statement is not None:
            row["statement"] = statement
        else:
            finding = reproducibility_finding(s)
            if finding is not None:
                row["finding"] = finding
        rows.append(row)
    return rows


THRESHOLDS_NAME = "thresholds.json"


def _cited_path(uri: object) -> str | None:
    if not isinstance(uri, str) or not uri or "\\" in uri or "://" in uri or uri.startswith("/"):
        return None
    parts = PurePosixPath(uri).parts
    if not parts or any(part in ("", ".", "..") for part in parts) or parts[-1] != THRESHOLDS_NAME:
        return None
    return "/".join(parts)


def grading_inputs(source: Path, report: object) -> list[dict]:
    bundle = report.get("source_bundle") if isinstance(report, dict) else None
    results = bundle.get("results") if isinstance(bundle, dict) else None
    cited: dict[str, str] = {}
    for result in results if isinstance(results, list) else []:
        evaluated = result.get("evaluator_results") if isinstance(result, dict) else None
        for item in evaluated if isinstance(evaluated, list) else []:
            inputs = item.get("inputs") if isinstance(item, dict) else None
            for entry in inputs if isinstance(inputs, list) else []:
                if not isinstance(entry, dict):
                    continue
                uri = entry.get("uri")
                named = (
                    isinstance(uri, str) and uri.rstrip("/").rsplit("/", 1)[-1] == THRESHOLDS_NAME
                )
                if entry.get("role") != "thresholds" and not named:
                    continue
                relative = _cited_path(uri)
                if relative is None:
                    raise SiteError(
                        f"{source}: substituted: an evaluator result cites {uri!r}, not a "
                        f"{THRESHOLDS_NAME} inside the report"
                    )
                digest = entry.get("sha256")
                previous = cited.setdefault(relative, digest)
                if previous != digest:
                    raise SiteError(
                        f"{source}: substituted: {relative} is cited with two different "
                        f"sha256 values ({previous} and {digest})"
                    )
    listed = _parse_sha256sums(source / "SHA256SUMS") if (source / "SHA256SUMS").is_file() else {}
    found = []
    for relative, digest in sorted(cited.items()):
        path = source.joinpath(*PurePosixPath(relative).parts)
        current = path
        while current != source:
            if current.is_symlink():
                raise SiteError(f"{source}: substituted: {relative} is a symlink")
            current = current.parent
        if not path.is_file():
            raise SiteError(
                f"{source}: missing: {relative} is cited by the evaluator results but is not "
                "in the run folder"
            )
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if relative in listed and listed[relative] != actual:
            raise SiteError(f"{path}: does not match SHA256SUMS")
        if actual != digest:
            raise SiteError(
                f"{source}: altered: {relative} sha256 is {actual}, not the cited {digest!r}"
            )
        found.append({"role": "thresholds", "path": relative, "sha256": actual, "bytes": data})
    return found


def _parse_sha256sums(sums_path: Path) -> dict[str, str]:
    listed: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, sep, name = line.partition("  ")
        cleaned = name.strip()
        if not sep or not cleaned:
            raise SiteError(f"{sums_path}: malformed checksum line {line!r}")
        parts = PurePosixPath(cleaned).parts
        if cleaned.startswith("/") or "\\" in cleaned or any(p in ("", ".", "..") for p in parts):
            raise SiteError(f"{sums_path}: unsafe path {cleaned!r} in SHA256SUMS")
        listed[cleaned] = digest.strip()
    return listed


def check_reports(directory: Path) -> object:
    for required in REQUIRED_RUN_FILES:
        req_path = directory / required
        if req_path.is_symlink():
            raise SiteError(f"{directory}: {required} must not be a symlink")
        if not req_path.is_file():
            raise SiteError(f"{directory}: missing {required}")
    listed = _parse_sha256sums(directory / "SHA256SUMS")
    for name in REPORT_FILES:
        if name not in listed:
            raise SiteError(f"{directory}: SHA256SUMS has no entry for {name}")
    for name, expected in listed.items():
        path = directory.joinpath(*PurePosixPath(name).parts)
        if path.is_symlink() or not path.is_file():
            raise SiteError(f"{directory}: missing {name} listed in SHA256SUMS")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected != actual:
            raise SiteError(f"{path}: does not match SHA256SUMS")
    report = read_report(directory / "report.json")
    outcome(report, str(directory / "report.json"))
    check_evaluators(report, directory / "report.json")
    return report


def release_tag(commit: str, git_dir: Path | None = None) -> str | None:
    if not git_dir or not COMMIT_SHA.fullmatch(commit):
        return None

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(git_dir), *args], capture_output=True, text=True, check=False
        )
        return done.stdout.strip() if done.returncode == 0 else ""

    found = []
    for name in git("tag", "--list", "--points-at", commit).splitlines():
        if (
            RELEASE_TAG.fullmatch(name)
            and git("rev-parse", f"refs/tags/{name}^{{commit}}") == commit
        ):
            found.append(name)
    return max(found, key=lambda name: tuple(map(int, name[1:].split(".")))) if found else None


def _robot_slug_from_record(record: dict, where: Path) -> str:
    explicit = _stored_text(record.get("robot_slug") or record.get("robot_id"))
    if explicit is not None:
        slug = explicit.removeprefix("livingproof-").lower()
    else:
        robot = record.get("robot")
        if isinstance(robot, dict):
            sub_id = _stored_text(robot.get("slug") or robot.get("id"))
            if sub_id is not None:
                slug = sub_id.removeprefix("livingproof-").lower()
            else:
                repo = _stored_text(robot.get("repository"))
                if repo is None:
                    raise SiteError(f"{where}: robot.repository is missing in run.json")
                repo_tail = repo.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
                slug = repo_tail.removeprefix("livingproof-").lower()
        elif isinstance(robot, str) and robot.strip():
            slug = robot.strip().removeprefix("livingproof-").lower()
        else:
            raise SiteError(f"{where}: missing robot metadata in run.json")
    if not SEGMENT.fullmatch(slug):
        raise SiteError(f"{where}: unsafe robot path segment {slug!r}")
    return slug


def _normalize_run_record(
    raw_record: dict,
    report: object,
    where: Path,
    *,
    git_dir: Path | None = None,
) -> tuple[str, str, str, dict]:
    robot_slug = _robot_slug_from_record(raw_record, where)
    variant = _stored_text(raw_record.get("variant"))
    if variant is not None and variant.startswith(f"{robot_slug}-"):
        stripped = variant.removeprefix(f"{robot_slug}-")
        if stripped:
            variant = stripped
    robot_raw = raw_record.get("robot")
    config = _stored_text(robot_raw.get("configuration")) if isinstance(robot_raw, dict) else None
    if variant is not None and config is not None and config.lower() not in variant.split("-"):
        variant = f"{variant}-{config.lower()}"
    if variant is None or not SEGMENT.fullmatch(variant):
        raise SiteError(f"{where}: invalid or missing variant {raw_record.get('variant')!r}")

    run_block = raw_record.get("run")
    if not isinstance(run_block, dict):
        raise SiteError(f"{where}: run.json lacks a 'run' object")
    run_id = _stored_text(run_block.get("id"))
    if run_id is None or not RUN_ID.fullmatch(run_id) or run_id in {".", ".."}:
        raise SiteError(f"{where}: invalid or missing run.id {run_block.get('id')!r}")
    created = _stored_text(run_block.get("created"))
    if created is None:
        raise SiteError(f"{where}: missing run.created timestamp")
    _stamp(created)

    computed_outcomes = outcome(report, str(where.with_name("report.json")))
    stored_outcomes = raw_record.get("outcome")
    if stored_outcomes is not None:
        if not isinstance(stored_outcomes, list) or len(stored_outcomes) != len(computed_outcomes):
            raise SiteError(f"{where}: run.json outcome count disagrees with report.json")
        for idx, (stored_item, computed_item) in enumerate(zip(stored_outcomes, computed_outcomes)):
            if (
                not isinstance(stored_item, dict)
                or stored_item.get("grade") != computed_item["grade"]
            ):
                raise SiteError(
                    f"{where}: run.json outcome[{idx}] grade disagrees with report.json"
                )

    record = dict(raw_record)
    record["variant"] = variant
    record["outcome"] = computed_outcomes

    robot_raw = raw_record.get("robot")
    if isinstance(robot_raw, dict):
        robot_info = dict(robot_raw)
        repo = _stored_text(robot_info.get("repository")) or robot_slug
        commit_sha = _stored_text(robot_info.get("commit")) or ""
        robot_info.setdefault("repository", repo)
        robot_info.setdefault("commit", commit_sha)
        if not _stored_text(robot_info.get("url")):
            tag = _stored_text(robot_info.get("tag"))
            base_repo = repo if repo.startswith("https://") else f"https://github.com/{repo}"
            if tag:
                robot_info["url"] = f"{base_repo}/releases/tag/{tag}"
            elif commit_sha:
                robot_info["url"] = f"{base_repo}/tree/{commit_sha}"
            else:
                robot_info["url"] = base_repo
    else:
        robot_info = {
            "repository": robot_slug,
            "commit": "",
            "url": f"https://github.com/{robot_slug}",
        }
    if not _stored_text(robot_info.get("software_version")) and isinstance(report, dict):
        for summary in report.get("summaries") or []:
            if isinstance(summary, dict) and isinstance(summary.get("system"), dict):
                sw = _stored_text(summary["system"].get("version"))
                if sw is not None:
                    robot_info["software_version"] = sw
                    break
    record["robot"] = robot_info

    commit_raw = raw_record.get("commit")
    commit_info = dict(commit_raw) if isinstance(commit_raw, dict) else {}
    sha = _stored_text(commit_info.get("sha")) or _stored_text(robot_info.get("commit")) or ""
    commit_info["sha"] = sha
    if not _stored_text(commit_info.get("url")) and sha:
        repo_url = _spec_repository_url({"repository": robot_info.get("repository")})
        if repo_url:
            commit_info["url"] = f"{repo_url}/commit/{sha}"
    existing_tag = _stored_text(commit_info.get("tag"))
    if existing_tag is not None:
        if not RELEASE_TAG.fullmatch(existing_tag):
            raise SiteError(f"{where}: unexpected release tag {existing_tag!r}")
    elif sha and git_dir is not None:
        resolved_tag = release_tag(sha, git_dir)
        if resolved_tag is not None:
            commit_info["tag"] = resolved_tag
    record["commit"] = commit_info

    poster = raw_record.get("poster")
    if not isinstance(poster, dict) or not _stored_text(poster.get("name")):
        record["poster"] = {"type": "ci", "name": "CI"}

    releases = raw_record.get("releases")
    record["releases"] = dict(releases) if isinstance(releases, dict) else {}

    failing = failing_evaluators(report)
    if failing:
        record["failing_evaluators"] = failing
    else:
        record.pop("failing_evaluators", None)

    markers = integrity_markers(report)
    if markers:
        record["integrity_status"] = markers
    else:
        record.pop("integrity_status", None)

    return robot_slug, variant, run_id, record


# ---------------------------------------------------------------- evaluators & chips


def _finding_summary(findings: list, descriptor: dict) -> str | None:
    for item in findings:
        if isinstance(item, dict):
            text = _stored_text(item.get("text")) or _stored_text(item.get("summary"))
            if text is not None:
                return text
        elif isinstance(item, str):
            text = _stored_text(item)
            if text is not None:
                return text
    return _stored_text(descriptor.get("details_copy"))


INCONCLUSIVE_COPY = "Not graded: no check applied to this run."


def failing_evaluators(report: object) -> list[dict]:
    if not isinstance(report, dict):
        return []
    summaries = report.get("summaries")
    if isinstance(summaries, list) and summaries:
        grades = [s.get("grade") for s in summaries if isinstance(s, dict)]
        if grades and all(g in ("PASS", "UNSUPPORTED") for g in grades):
            return []
    seen: dict[str, dict] = {}
    for doc in _evaluator_documents(report):
        ev = doc.get("evaluator") if isinstance(doc.get("evaluator"), dict) else {}
        ev_id = _stored_text(ev.get("id"))
        if ev_id is None:
            continue
        desc = doc.get("descriptor") if isinstance(doc.get("descriptor"), dict) else {}
        raw_findings = (
            desc.get("findings") if isinstance(desc.get("findings"), list) else doc.get("findings")
        )
        findings = raw_findings if isinstance(raw_findings, list) else []
        grade = desc.get("grade") if "grade" in desc else doc.get("grade")
        integrity = doc.get("integrity") if isinstance(doc.get("integrity"), dict) else {}
        run_info = integrity.get("run") if isinstance(integrity.get("run"), dict) else {}
        status = run_info.get("test_system_status")
        spoke = (
            bool(findings)
            or grade == "FAIL"
            or (isinstance(grade, (int, float)) and not isinstance(grade, bool) and grade < 100)
            or (isinstance(status, str) and status.upper() in {"ERROR", "WARN", "FAIL"})
            or status == "INCONCLUSIVE"
        )
        if not spoke:
            continue
        title = _stored_text(ev.get("display_name")) or _stored_text(desc.get("title")) or ev_id
        summary = _finding_summary(findings, desc)
        if summary is None and status == "INCONCLUSIVE":
            summary = INCONCLUSIVE_COPY
        if ev_id not in seen:
            entry: dict = {"id": ev_id, "title": title, "href": EVALUATOR_ANCHOR}
            if summary is not None:
                entry["summary"] = summary
            if status == "INCONCLUSIVE":
                entry["not_graded"] = True
            seen[ev_id] = entry
        elif "summary" not in seen[ev_id] and summary is not None:
            seen[ev_id]["summary"] = summary
    return list(seen.values())


def integrity_markers(report: object) -> list[dict]:
    if not isinstance(report, dict):
        return []
    found: dict[str, dict] = {}
    for doc in _evaluator_documents(report):
        integrity = doc.get("integrity") if isinstance(doc.get("integrity"), dict) else {}
        run_info = integrity.get("run") if isinstance(integrity.get("run"), dict) else {}
        status = run_info.get("test_system_status")
        if status not in MARKED_INTEGRITY_STATUSES:
            continue
        ev = doc.get("evaluator") if isinstance(doc.get("evaluator"), dict) else {}
        ev_id = _stored_text(ev.get("id"))
        if ev_id is None or ev_id in found:
            continue
        desc = doc.get("descriptor") if isinstance(doc.get("descriptor"), dict) else {}
        title = _stored_text(ev.get("display_name")) or _stored_text(desc.get("title")) or ev_id
        found[ev_id] = {"id": ev_id, "title": title, "status": status}
    return list(found.values())


# ---------------------------------------------------------------- evidence & run folders


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _infer_evidence_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mcap":
        return "mcap"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in {".log", ".txt"}:
        return "log"
    return "note"


def _publishable_evidence(path: Path) -> bool:
    if path.suffix.lower() in PUBLISHED_EVIDENCE_SUFFIXES:
        return True
    if path.suffix.lower() != ".html":  # .html was always skipped quietly
        print(f"::warning::{path}: not publishing evidence of this type", file=sys.stderr)
    return False


def _copy_run_evidence(
    source: Path, destination: Path, stored_evidence: object
) -> list[dict] | None:
    evidence_src = source / "evidence"
    source_files: list[Path] = []
    if evidence_src.exists():
        if evidence_src.is_symlink():
            raise SiteError(f"{source}: evidence directory must not be a symlink")
        for item in sorted(evidence_src.rglob("*")):
            if item.is_symlink():
                raise SiteError(f"{source}: symlink inside evidence is not allowed ({item})")
            if item.is_file() and _publishable_evidence(item):
                source_files.append(item)

    if isinstance(stored_evidence, list) and stored_evidence:
        budget = MAX_RUN_EVIDENCE_BYTES
        copied_all = set()
        records = []
        for raw_entry in stored_evidence:
            if not isinstance(raw_entry, dict):
                continue
            entry = json.loads(json.dumps(raw_entry))
            files_meta = entry.get("files") if isinstance(entry.get("files"), list) else []
            resolved_files: list[Path] = []
            for fmeta in files_meta:
                rel_str = fmeta.get("path") if isinstance(fmeta, dict) else None
                if not isinstance(rel_str, str) or not rel_str.startswith("evidence/"):
                    continue
                parts = PurePosixPath(rel_str).parts
                if any(p in ("", ".", "..") for p in parts):
                    raise SiteError(f"{source}: unsafe evidence file path {rel_str!r}")
                candidate = source.joinpath(*parts)
                if (
                    candidate.is_file()
                    and not candidate.is_symlink()
                    and _publishable_evidence(candidate)
                ):
                    resolved_files.append(candidate)
            if resolved_files:
                size = sum(p.stat().st_size for p in resolved_files)
                if size > budget:
                    entry["preserved"] = False
                    entry["files"] = []
                    entry["reason"] = f"over the per-run evidence budget ({size} bytes)"
                else:
                    budget -= size
                    copied_entries = []
                    for p in resolved_files:
                        rel = p.relative_to(source)
                        dest_file = destination / rel
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(p, dest_file)
                        copied_all.add(p)
                        copied_entries.append(
                            {
                                "path": rel.as_posix(),
                                "sha256": _sha256(dest_file),
                                "bytes": p.stat().st_size,
                            }
                        )
                    entry["preserved"] = True
                    entry["files"] = copied_entries
            records.append(entry)
        remaining = [p for p in source_files if p not in copied_all]
        for p in remaining:
            size = p.stat().st_size
            rel = p.relative_to(source)
            if size > budget:
                records.append(
                    {
                        "label": p.stem.replace("-", " "),
                        "kind": _infer_evidence_kind(p),
                        "preserved": False,
                        "files": [],
                        "reason": f"over the per-run evidence budget ({size} bytes)",
                    }
                )
            else:
                budget -= size
                dest_file = destination / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dest_file)
                records.append(
                    {
                        "label": p.stem.replace("-", " "),
                        "kind": _infer_evidence_kind(p),
                        "preserved": True,
                        "files": [
                            {
                                "path": rel.as_posix(),
                                "sha256": _sha256(dest_file),
                                "bytes": size,
                            }
                        ],
                    }
                )
        return records or None

    if not source_files:
        return None

    budget = MAX_RUN_EVIDENCE_BYTES
    records = []
    for p in source_files:
        size = p.stat().st_size
        rel = p.relative_to(source)
        kind = _infer_evidence_kind(p)
        label = p.stem.replace("-", " ").replace("_", " ")
        if size > budget:
            records.append(
                {
                    "label": label,
                    "kind": kind,
                    "preserved": False,
                    "files": [],
                    "reason": f"over the per-run evidence budget ({size} bytes)",
                }
            )
            continue
        budget -= size
        dest_file = destination / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest_file)
        records.append(
            {
                "label": label,
                "kind": kind,
                "preserved": True,
                "files": [
                    {
                        "path": rel.as_posix(),
                        "sha256": _sha256(dest_file),
                        "bytes": size,
                    }
                ],
            }
        )
    return records


def discover_run_folders(runs_dir: Path) -> list[Path]:
    """Find run folders inside `runs_dir` (including `runs_dir` itself if it holds `run.json`)."""
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise SiteError(
            f"Runs directory {runs_dir} does not exist. Provide a directory of run folders "
            "each containing report.html, report.json, report.md, report.txt, SHA256SUMS, "
            "and run.json."
        )
    if (runs_dir / "run.json").is_file():
        return [runs_dir]
    found: list[Path] = []
    for run_json in sorted(runs_dir.rglob("run.json")):
        rel_parts = run_json.relative_to(runs_dir).parts
        if "evidence" in rel_parts[:-1]:
            continue
        if run_json.is_file() and not run_json.is_symlink():
            found.append(run_json.parent)
    if not found:
        raise SiteError(
            f"No run folders containing run.json were found in {runs_dir}. "
            "Each run folder must hold report.html, report.json, report.md, report.txt, "
            "SHA256SUMS, and run.json."
        )
    return found


def runs(
    reports_dir: Path,
    *,
    exclude_runs: set[str] | frozenset[str] = frozenset(),
    skipped_excluded: list[tuple[str, str, str]] | None = None,
) -> dict[tuple[str, str], list[dict]]:
    """Return `{(robot, variant): [run records, newest first]}` from `runs/*/run.json`."""
    found: dict[tuple[str, str], list[dict]] = {}
    if not reports_dir.is_dir():
        return found
    for path in sorted(reports_dir.glob("*/*/runs/*/run.json")):
        if path.is_symlink() or not path.is_file():
            continue
        robot = path.parts[-5]
        variant = path.parts[-4]
        folder = path.parent.name
        if (
            not SEGMENT.fullmatch(robot)
            or not SEGMENT.fullmatch(variant)
            or not RUN_ID.fullmatch(folder)
            or any(p.is_symlink() for p in list(path.parents)[:4])
        ):
            raise SiteError(f"{path}: unsafe run path in the reports directory")
        if folder in exclude_runs:
            print(
                f"::warning::Excluded restored run {folder} "
                f"({robot}/{variant}/runs/{folder}) from the reports site.",
                file=sys.stderr,
            )
            if skipped_excluded is not None:
                skipped_excluded.append((robot, variant, folder))
            continue
        record = read_json_object(path)
        run_block = record.get("run")
        if not isinstance(run_block, dict):
            raise SiteError(f"{path}: run.json lacks a 'run' object")
        if _stored_text(run_block.get("created")) is None:
            raise SiteError(f"{path}: missing run.created timestamp")
        record["folder"] = folder
        found.setdefault((robot, variant), []).append(record)
    for records in found.values():
        records.sort(key=lambda r: (r["run"]["created"], r["folder"]), reverse=True)
    return found


def validate_exclude_run_id(entry: object) -> str:
    if not isinstance(entry, str) or not entry:
        raise SiteError(
            f"Invalid exclude-runs entry {entry!r}: must be a non-empty run folder name."
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in entry):
        raise SiteError(
            f"Invalid exclude-runs entry {entry!r}: must not contain control characters."
        )
    if "/" in entry or "\\" in entry or entry in {".", ".."} or ".." in entry:
        raise SiteError(f"Invalid exclude-runs entry {entry!r}: must be a plain run folder name.")
    if not RUN_ID.fullmatch(entry):
        raise SiteError(f"Invalid exclude-runs entry {entry!r}: must be a plain run folder name.")
    return entry


def parse_exclude_runs(raw: str) -> tuple[str, ...]:
    normalized = raw.replace("\r\n", "\n")
    if any((ord(ch) < 32 or ord(ch) == 127) and ch not in "\n\t" for ch in normalized):
        raise SiteError("exclude-runs must not contain control characters.")
    if not normalized.strip():
        return ()
    if "," in normalized:
        tokens: list[str] = []
        for part in normalized.split(","):
            part_tokens = part.split()
            if not part_tokens:
                raise SiteError("exclude-runs must not contain empty entries.")
            tokens.extend(part_tokens)
    else:
        tokens = normalized.split()
    return tuple(dict.fromkeys(validate_exclude_run_id(entry) for entry in tokens))


def _publish_cited_details(source: Path, folder: Path, report: object) -> None:
    """Copy advisory details files cited by the report. They are report files.

    Each path must be listed in the run's SHA256SUMS, stay relative, not be a
    symlink, and match that sha. They are not evidence and are not expired here.
    """
    if not isinstance(report, dict):
        return
    listed = _parse_sha256sums(source / "SHA256SUMS")
    for uri in cited_details_uris(report):
        try:
            data = read_cited_details(source, uri, listed)
            relative = safe_relative(uri)
        except DetailsPathError as exc:
            raise SiteError(str(exc)) from exc
        destination = folder.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def add_run_folder(
    reports_dir: Path,
    source: Path,
    *,
    restored_keys: set[tuple[str, str, str]],
    seen_in_batch: set[tuple[str, str, str]],
    allow_replace_run_id: str | None = None,
    git_dir: Path | None = None,
    exclude_runs: set[str] | frozenset[str] = frozenset(),
) -> tuple[Path, tuple[str, str, str], dict]:
    report_data = check_reports(source)
    inputs = grading_inputs(source, report_data)
    raw_record = read_json_object(source / "run.json")
    robot, variant, run_id, record = _normalize_run_record(
        raw_record, report_data, source / "run.json", git_dir=git_dir
    )
    if run_id in exclude_runs:
        raise SiteError(
            f"Run {run_id!r} in {source} matches exclude-runs; "
            "exclude-runs only applies to restored history, not runs added in the same build."
        )
    key = (robot, variant, run_id)
    if key in seen_in_batch:
        raise SiteError(
            f"Duplicate run folder for {robot}/{variant} run {run_id!r} in input directory."
        )
    seen_in_batch.add(key)

    folder = reports_dir / robot / variant / "runs" / run_id
    if key in restored_keys and run_id != allow_replace_run_id:
        raise SiteError(
            f"Run {robot}/{variant}/runs/{run_id} is already published in history and is immutable."
        )
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

    for name in (*REPORT_FILES, "SHA256SUMS"):
        shutil.copyfile(source / name, folder / name)
    for item in inputs:
        destination = folder.joinpath(*PurePosixPath(item["path"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item["bytes"])
    _publish_cited_details(source, folder, report_data)

    if inputs:
        record["grading_inputs"] = [
            {k: item[k] for k in ("role", "path", "sha256")} for item in inputs
        ]
    preserved = _copy_run_evidence(source, folder, raw_record.get("evidence"))
    if preserved is not None:
        record["evidence"] = preserved

    (folder / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return folder, key, record


# ---------------------------------------------------------------- pruning & run page publishing


def validate_retention_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise SiteError(f"evidence-retention-days must be a positive integer, got {days!r}")
    return days


def evidence_expired(created: str, now: str, days: int) -> bool:
    return _stamp(now) - _stamp(created) >= timedelta(days=days)


def prune_expired_evidence(reports_dir: Path, now: str, days: int) -> tuple[list[str], set[Path]]:
    """Remove copied MCAP, video, and media under runs older than `days`.

    Returns `(removed_relative_paths, affected_run_folders)`. Report pages,
    `run.json`, `thresholds.json`, and `SHA256SUMS` remain.
    """
    validate_retention_days(days)
    removed: list[str] = []
    affected: set[Path] = set()
    if not now or not reports_dir.is_dir():
        return removed, affected
    for record_path in sorted(reports_dir.glob("*/*/runs/*/run.json")):
        if record_path.is_symlink() or not record_path.is_file():
            continue
        record = read_json_object(record_path)
        created = (record.get("run") or {}).get("created")
        if not isinstance(created, str) or not evidence_expired(created, now, days):
            continue
        run_folder = record_path.parent
        evidence = run_folder / "evidence"
        if evidence.is_dir():
            for path in sorted(evidence.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                if (
                    path.suffix.lower() in MEDIA_SUFFIXES
                    or path.name == "media.json"
                    or path.suffix.lower() == ".html"
                ):
                    path.unlink()
                    removed.append(path.relative_to(reports_dir).as_posix())
                    affected.add(run_folder)
            for subdir in sorted(evidence.rglob("*"), reverse=True):
                if subdir.is_dir() and not any(subdir.iterdir()):
                    subdir.rmdir()
            if evidence.exists() and not any(evidence.iterdir()):
                evidence.rmdir()
        index_html = run_folder / "index.html"
        if index_html.is_file():
            text = index_html.read_text(encoding="utf-8", errors="replace")
            if KEPT_FOR_COPY.search(text) or 'href="evidence/' in text or "href='evidence/" in text:
                affected.add(run_folder)
    return removed, affected


def link_path(record: dict, *, expired: bool) -> str | None:
    if expired or not record.get("preserved"):
        return None
    listing = listing_path(record)
    if listing and site_path(listing):
        return listing
    paths = [
        site_path(item.get("path")) for item in record.get("files") or [] if isinstance(item, dict)
    ]
    kept = [path for path in paths if path]
    if len(kept) == 1:
        return kept[0]
    return None


def evidence_links_document(records: list[dict] | None, *, expired: bool) -> dict:
    links = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind not in {"video", "mcap", "log", "note"}:
            continue
        entry: dict = {"label": _plain_label(record.get("label")), "kind": kind}
        if type(record.get("seed")) is int and record.get("status") in {"PASS", "FAIL"}:
            entry["seed"] = record["seed"]
            entry["status"] = record["status"]
        if expired or not record.get("preserved") or not record.get("files"):
            if record.get("preserved"):
                entry["expired"] = True
                links.append(entry)
            continue
        target = link_path(record, expired=False)
        if target is None:
            for item in record.get("files") or []:
                path = site_path(item.get("path")) if isinstance(item, dict) else None
                if path:
                    links.append(entry | {"path": path, "expired": False})
            continue
        entry["path"] = target
        entry["expired"] = False
        links.append(entry)
    document = {"links": links}
    blob = json.dumps(document)
    if "run" in document or "://" in blob or "/actions/" in blob or ARTIFACT_WORD.search(blob):
        raise SiteError("refusing to pass a non-site evidence link to the reporter")
    return document


def drop_listing_pages(folder: Path) -> None:
    evidence = folder / "evidence"
    if not evidence.is_dir():
        return
    for path in evidence.glob("*.html"):
        path.unlink()


def trial_model(node: object) -> bool:
    if isinstance(node, dict):
        original = node.get("original_result")
        if isinstance(original, dict) and "index" in original:
            return True
        plan = node.get("plan")
        if isinstance(plan, dict) and isinstance(plan.get("trials"), dict):
            return True
        return any(trial_model(value) for value in node.values())
    if isinstance(node, list):
        return any(trial_model(value) for value in node)
    return False


def display_label(label: str, trial: bool) -> str:
    if trial:
        return SEED_LABEL.sub("trial ", label, count=1)
    return label


def caller_repository(record: dict) -> str | None:
    """The repository that produced this run, from run.url, or None when it is missing."""
    url = (record.get("run") or {}).get("url")
    if not isinstance(url, str):
        return None
    match = re.fullmatch(
        r"https://github\.com/(" + _REPO_SEGMENT + r"/" + _REPO_SEGMENT + r")/actions/runs/[0-9]+",
        url,
    )
    return match.group(1) if match else None


def mentions_actions(text: str, repository: str | set[str] | None = None) -> bool:
    """True for any /actions/ address other than an allowed CI run page."""
    return "/actions/" in run_address_re(repository).sub("", text).lower()


def html_is_dirty(text: str, repository: str | set[str] | None = None) -> bool:
    return ARTIFACT_WORD.search(text) is not None or mentions_actions(text, repository)


def _is_actions_url(value: object, repository: str | set[str] | None = None) -> bool:
    if not isinstance(value, str):
        return False
    if ARTIFACT_WORD.search(value):
        return True
    return mentions_actions(value, repository) and not is_run_address(value, repository)


def strip_actions_links(report: dict, repository: str | set[str] | None = None) -> bool:
    links = report.get("evidence_links")
    if not isinstance(links, dict):
        return False
    changed = False
    if _is_actions_url(links.get("run"), repository):
        links.pop("run", None)
        changed = True
    entries = links.get("links")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and _is_actions_url(entry.get("url"), repository):
                entry.pop("url", None)
                changed = True
    return changed


def publish_evidence_links(
    report: dict, links: dict, repository: str | set[str] | None = None
) -> bool:
    stored = report.get("evidence_links")
    if not isinstance(stored, dict) and not links.get("links"):
        return False
    kept = []
    if isinstance(stored, dict):
        kept = [
            entry
            for entry in stored.get("links") or []
            if isinstance(entry, dict)
            and isinstance(entry.get("url"), str)
            and entry["url"].startswith("https://")
            and not _is_actions_url(entry["url"], repository)
        ]
    public = {"links": [dict(entry) for entry in links.get("links", [])] + kept}
    run = stored.get("run") if isinstance(stored, dict) else None
    if isinstance(run, str) and is_run_address(run, repository):
        public = {"run": run, **public}
    if public == stored:
        return False
    report["evidence_links"] = public
    return True


def strip_actions_text(text: str, repository: str | set[str] | None = None) -> str:
    def unwrap(match: re.Match) -> str:
        href = match.group(2)
        return match.group(0) if is_run_address(href, repository) else match.group(3)

    text = ACTIONS_ANCHOR.sub(unwrap, text)
    text = actions_url_re(repository).sub("", text)
    return ARTIFACT_WORD.sub("", text)


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise SiteError(f"{path}: not valid UTF-8 at byte {error.start} ({error.reason})") from None


def reporter_html(folder: Path) -> str:
    parked = folder / ORIGINAL_HTML
    if parked.is_file():
        text = _read_utf8_text(parked)
        parked.unlink()
        return text
    report = folder / "report.html"
    if report.is_file():
        return _read_utf8_text(report)
    return ""


def write_published_checksums(folder: Path) -> None:
    names = sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    if any(name == ORIGINAL_HTML or name.endswith("/" + ORIGINAL_HTML) for name in names):
        raise SiteError(f"{folder}: {ORIGINAL_HTML} is not a published file")
    lines = [f"{_sha256(folder / name)}  {name}" for name in names]
    (folder / "SHA256SUMS").write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def publish_report_files(
    folder: Path,
    html_text: str,
    *,
    expired: bool = False,
    days: int = DEFAULT_RETENTION_DAYS,
    repository: str | set[str] | None = None,
) -> None:
    parked = folder / ORIGINAL_HTML
    if parked.is_file():
        parked.unlink()
    report_path = folder / "report.json"
    if report_path.is_file():
        report = read_report(report_path)
        if isinstance(report, dict) and strip_actions_links(report, repository=repository):
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if html_text:
        cleaned_html = strip_actions_text(html_text, repository=repository)
        if expired:
            cleaned_html = scrub_expired_evidence_html(cleaned_html, days)
        cleaned_html = unlink_unpublished_evidence(cleaned_html, folder)
        cleaned_html = checked_report_html(cleaned_html, str(folder / "report.html"))
        (folder / "report.html").write_text(cleaned_html, encoding="utf-8")
    for name in ("report.md", "report.txt"):
        path = folder / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = strip_actions_text(text, repository=repository)
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")
    write_published_checksums(folder)


def _unpublished_evidence(folder: Path, reference: str) -> bool:
    """True when an ``evidence/...`` reference does not name a file this run folder holds."""
    bare = reference.split("#", 1)[0].split("?", 1)[0]
    if site_path(bare) is None:
        return True
    target = folder / urllib.parse.unquote(bare)
    return target.is_symlink() or not target.is_file()


def unlink_unpublished_evidence(text: str, folder: Path) -> str:
    """Show a link to evidence the site did not publish as plain text, not as a dead link.

    A file over the run's evidence budget, or of a type the site does not copy, is not in
    the run folder, and the reporter cannot know that when it renders the link.
    """

    def video(match: re.Match) -> str:
        reference = re.search(r"evidence/[^'\"<>\s]+", match.group(0))
        if reference and _unpublished_evidence(folder, reference.group(0)):
            return ""
        return match.group(0)

    def anchor(match: re.Match) -> str:
        return match.group(3) if _unpublished_evidence(folder, match.group(2)) else match.group(0)

    return EVIDENCE_ANCHOR.sub(anchor, EVIDENCE_VIDEO.sub(video, text))


def scrub_expired_evidence_html(text: str, days: int) -> str:
    """Remove local `evidence/...` links and media tags once retention has pruned copies."""
    expired_note = f"Evidence expired after {days} days"
    text = EVIDENCE_VIDEO.sub(f'<p class="evidence-expired">{expired_note}</p>', text)
    text = EVIDENCE_IMG.sub("", text)

    def unwrap_evidence_anchor(match: re.Match) -> str:
        inner = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        if inner:
            return f"{html.escape(inner)} ({expired_note})"
        return expired_note

    text = EVIDENCE_ANCHOR.sub(unwrap_evidence_anchor, text)
    text = KEPT_FOR_COPY.sub(expired_note, text)
    text = re.sub(r"\bis-kept\b", "is-expired", text)
    return text


def scrub_reporter_html(text: str, record: dict, *, trial: bool, expired: bool, days: int) -> str:
    by_id = {
        str(entry["artifact"]["id"]): entry
        for entry in record.get("evidence") or []
        if isinstance(entry, dict)
        and isinstance(entry.get("artifact"), dict)
        and "id" in entry["artifact"]
    }

    def shown(label: str) -> str:
        cleaned = ARTIFACT_WORD.sub("", label).strip()
        return cleaned or "evidence"

    def replace(match: re.Match) -> str:
        label = shown(display_label(match.group(4), trial))
        entry = by_id.get(match.group(3))
        target = None if entry is None else link_path(entry, expired=expired)
        if target:
            return f"<a href='{html.escape(target, quote=True)}'>{html.escape(label)}</a>"
        if expired and entry is not None and entry.get("preserved"):
            return f"{html.escape(label)} (Evidence expired after {days} days)"
        return html.escape(label)

    def unwrap(match: re.Match) -> str:
        href = match.group(2)
        if is_run_address(href, caller_repository(record)):
            return match.group(0)
        return html.escape(shown(match.group(3)))

    repository = caller_repository(record)
    text = ARTIFACT_LINK.sub(replace, text)
    text = ACTIONS_ANCHOR.sub(unwrap, text)
    text = actions_url_re(repository).sub("", text)
    text = ARTIFACT_WORD.sub("", text)
    if expired:
        text = scrub_expired_evidence_html(text, days)
    return text


def publish_run_page(folder: Path, record: dict, *, now: str, days: int, trial: bool) -> None:
    html_text = reporter_html(folder)
    created = (record.get("run") or {}).get("created", "")
    expired = bool(now) and bool(created) and evidence_expired(created, now, days)
    drop_listing_pages(folder)
    if not expired:
        for entry in record.get("evidence") or []:
            if isinstance(entry, dict):
                write_listing(folder, entry, up="../../../../")
    links = evidence_links_document(record.get("evidence"), expired=expired)
    report_path = folder / "report.json"
    report = read_report(report_path)
    repository = caller_repository(record)
    if isinstance(report, dict) and (
        strip_actions_links(report, repository=repository)
        | publish_evidence_links(report, links, repository=repository)
    ):
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # The page is the Reporter's HTML. This action adds no card.
    html_text_for_page = html_text
    public = scrub_reporter_html(
        html_text_for_page, record, trial=trial, expired=expired, days=days
    )
    public = unlink_unpublished_evidence(public, folder)
    public = with_site_nav(
        public,
        overview_href="../../../../../index.html",
        reports_href="../../../../index.html",
    )
    public = with_spec_provenance(public, record, report)
    # Checked after every rewrite, so deleting a word cannot assemble new markup.
    public = checked_report_html(public, str(folder / "index.html"))
    if html_is_dirty(public, repository=repository):
        raise SiteError(
            f"{folder / 'index.html'}: public page still names an artifact or links to /actions/"
        )
    (folder / "index.html").write_text(public, encoding="utf-8")
    publish_report_files(folder, html_text, expired=expired, days=days, repository=repository)


_TEXT_SUFFIXES = {
    ".html",
    ".json",
    ".txt",
    ".md",
    ".svg",
    ".orig",
    ".xml",
    ".css",
    ".js",
    ".yml",
    ".yaml",
}


def published_text(path: Path) -> bool:
    if not path.is_file() or path.name == "run.json":
        return False
    if path.suffix.lower() in _TEXT_SUFFIXES or path.name.endswith(".orig"):
        return True
    return path.name in {"SHA256SUMS"}


class _DuplicateJsonKey(ValueError):
    """An object in the evidence manifest repeats a key."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    document: dict = {}
    for key, value in pairs:
        if key in document:
            raise _DuplicateJsonKey(key)
        document[key] = value
    return document


def _wording_text(path: Path, text: str) -> str:
    """Scan text, ignoring only the key name configuration.profile.controller.artifact.

    The evidence manifest records the controller provenance under that key. The key name is
    structure. Its values, and every other `artifact` key, are still scanned. A repeated key
    is not a valid object: the parser would keep only the last one and hide the earlier
    value, so the raw text is scanned instead.
    """
    if path.name != "manifest.json" or "evidence" not in path.parts:
        return text
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, _DuplicateJsonKey):
        return text
    node: object = document
    for part in ("configuration", "profile", "controller"):
        if not isinstance(node, dict):
            return text
        node = node.get(part)
    if not isinstance(node, dict) or not isinstance(node.get("artifact"), dict):
        return text
    # Keep the object's values in the scan. Drop only this key name.
    stand_in = "kept"
    while stand_in in node:
        stand_in += "_"
    node[stand_in] = node.pop("artifact")
    return json.dumps(document)


def _site_repositories(reports_dir: Path) -> set[str]:
    repos: set[str] = set()
    for path in reports_dir.rglob("run.json"):
        if not path.is_file() or path.name != "run.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and (repo := caller_repository(record)):
            repos.add(repo)
    return repos


def _path_repository(reports_dir: Path, path: Path, site_repos: set[str]) -> str | set[str] | None:
    """A run folder is bound to that run's repository; other pages may use any site repo."""
    for parent in (path, *path.parents):
        record_path = parent / "run.json"
        if not record_path.is_file():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            break
        if isinstance(record, dict) and (repo := caller_repository(record)):
            return repo
        break
    return site_repos or None


def public_page_problems(reports_dir: Path) -> list[str]:
    problems = []
    if not reports_dir.is_dir():
        return problems
    site_repos = _site_repositories(reports_dir)
    for path in sorted(reports_dir.rglob("*")):
        if not published_text(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(reports_dir).as_posix()
        if ARTIFACT_WORD.search(_wording_text(path, text)):
            problems.append(f"{relative} mentions an artifact")
        allowed = _path_repository(reports_dir, path, site_repos)
        if mentions_actions(text, repository=allowed):
            problems.append(f"{relative} links to /actions/")
    return problems


def remember_stored_wording(folder: Path, record: dict) -> bool:
    outcomes = record.get("outcome")
    report_path = folder / "report.json"
    if not isinstance(outcomes, list) or not report_path.is_file():
        return False
    report = read_report(report_path)
    summaries = report.get("summaries") if isinstance(report, dict) else None
    if not isinstance(summaries, list) or len(summaries) != len(outcomes):
        return False
    changed = False
    for item, summary in zip(outcomes, summaries):
        if not isinstance(item, dict) or not isinstance(summary, dict):
            continue
        if _stored_text(item.get("statement")) or _stored_text(item.get("finding")):
            continue
        if item.get("passed") is not None and item.get("trials") is not None:
            continue
        statement = reproducibility_statement(summary)
        if statement is not None:
            item["statement"] = statement
            changed = True
            continue
        finding = reproducibility_finding(summary)
        if finding is not None:
            item["finding"] = finding
            changed = True
    if not changed:
        return False
    stored = read_json_object(folder / "run.json")
    stored["outcome"] = outcomes
    (folder / "run.json").write_text(json.dumps(stored, indent=2) + "\n", encoding="utf-8")
    return True


def recheck_restored_run(folder: Path) -> None:
    """Check a run restored from the last deployment that this build does not republish.

    Its pages and evidence were published by an earlier build, so a gap fixed since then
    would otherwise be carried into every later deployment. The build fails rather than
    rewriting them; reset-history rebuilds the site from run folders.
    """
    evidence = folder / "evidence"
    # The site writes each evidence listing as evidence/<name>.html. A restored one is a
    # page on the Pages origin like report.html, so it gets the same check.
    listings = sorted(evidence.glob("*.html")) if evidence.is_dir() else []
    for path in [folder / "report.html", folder / "index.html", *listings]:
        if not path.is_file():
            continue
        text = _read_utf8_text(path)
        if checked_report_html(text, f"restored {path}") != text:
            raise SiteError(
                f"restored {path}: holds a <script> that is not a known reporter script"
            )
    if not evidence.is_dir():
        return
    for path in sorted(evidence.rglob("*")):
        if not path.is_file() or path in listings:
            continue
        if path.suffix.lower() not in PUBLISHED_EVIDENCE_SUFFIXES:
            raise SiteError(f"restored {path}: evidence of this type is not published")


# ---------------------------------------------------------------- render & build


def render(
    reports_dir: Path,
    *,
    now: str = "",
    days: int = DEFAULT_RETENTION_DAYS,
    publish_folders: set[Path] | None = None,
) -> dict[tuple[str, str], list[dict]]:
    validate_retention_days(days)
    _, pruned_folders = prune_expired_evidence(reports_dir, now, days)
    history = runs(reports_dir)
    _require_single_robot({robot for robot, _ in history})

    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "styles.css").write_text(load_styles_css(), encoding="utf-8")
    (reports_dir / "open.js").write_text(load_open_js(), encoding="utf-8")

    needs_publish = set(publish_folders or set()) | pruned_folders
    for (robot, variant), records in sorted(history.items()):
        base = reports_dir / robot / variant
        latest = base / "latest"
        if latest.exists():
            shutil.rmtree(latest)
        loaded_reports = {
            record["folder"]: read_report(base / "runs" / record["folder"] / "report.json")
            for record in records
        }
        trials = {folder: trial_model(rep) for folder, rep in loaded_reports.items()}
        newest = records[0]
        latest.mkdir(parents=True, exist_ok=True)
        (latest / "index.html").write_text(
            redirect_page(f"../runs/{newest['folder']}/"), encoding="utf-8"
        )
        for record in records:
            run_folder = base / "runs" / record["folder"]
            wording_updated = remember_stored_wording(run_folder, record)
            if wording_updated:
                write_published_checksums(run_folder)
            if (run_folder / ORIGINAL_HTML).is_file() or not (run_folder / "index.html").is_file():
                needs_publish.add(run_folder)
            if run_folder in needs_publish:
                publish_run_page(
                    run_folder,
                    record,
                    now=now,
                    days=days,
                    trial=trials[record["folder"]],
                )
            else:
                recheck_restored_run(run_folder)
        (base / "index.html").write_text(
            _history_page_html(robot, variant, records, loaded_reports), encoding="utf-8"
        )

    (reports_dir / "index.html").write_text(_index_page_html(history), encoding="utf-8")
    return history


def build(
    reports_dir: Path,
    runs_dir: Path,
    *,
    now: str | None = None,
    days: int = DEFAULT_RETENTION_DAYS,
    allow_replace_run_id: str | None = None,
    git_dir: Path | None = None,
    exclude_runs: Iterable[str] = (),
) -> list[Path]:
    validate_retention_days(days)
    excluded = tuple(dict.fromkeys(validate_exclude_run_id(entry) for entry in exclude_runs))
    excluded_set = frozenset(excluded)
    skipped_excluded: list[tuple[str, str, str]] = []
    existing = runs(reports_dir, exclude_runs=excluded_set, skipped_excluded=skipped_excluded)
    restored_keys = {
        (robot, variant, rec["folder"])
        for (robot, variant), recs in existing.items()
        for rec in recs
    }
    seen_in_batch: set[tuple[str, str, str]] = set()
    sources = discover_run_folders(runs_dir)

    added_folders: list[Path] = []
    timestamps: list[str] = []
    for source in sources:
        folder, _key, record = add_run_folder(
            reports_dir,
            source,
            restored_keys=restored_keys,
            seen_in_batch=seen_in_batch,
            allow_replace_run_id=allow_replace_run_id,
            git_dir=git_dir,
            exclude_runs=excluded_set,
        )
        added_folders.append(folder)
        timestamps.append(record["run"]["created"])

    removed_ids: set[str] = set()
    if excluded_set:
        for robot, variant, run_id in skipped_excluded:
            base = reports_dir / robot / variant
            shutil.rmtree(base / "runs" / run_id)
            removed_ids.add(run_id)
            runs_root = base / "runs"
            if runs_root.is_dir() and not any(runs_root.iterdir()):
                shutil.rmtree(base)
                robot_root = reports_dir / robot
                if robot_root.is_dir() and not any(robot_root.iterdir()):
                    robot_root.rmdir()
        for run_id in excluded:
            if run_id not in removed_ids:
                print(
                    f"::warning::exclude-runs entry {run_id!r} was not found in restored history.",
                    file=sys.stderr,
                )

    all_runs = runs(reports_dir)
    robot = _require_single_robot({r for r, _ in all_runs})

    effective_now = now
    if not effective_now:
        effective_now = max(
            timestamps,
            key=lambda ts: _stamp(ts),
        )
    else:
        _stamp(effective_now)

    history = render(
        reports_dir,
        now=effective_now,
        days=days,
        publish_folders=set(added_folders),
    )
    if problems := public_page_problems(reports_dir):
        raise SiteError(
            "published pages contain Actions links or artifact wording: " + ", ".join(problems)
        )

    total_runs = sum(len(recs) for recs in history.values())
    marker_payload = {
        "robot": robot,
        "scenarios": len(history),
        "runs": total_runs,
        "updated": effective_now,
    }
    (reports_dir / MARKER).write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
    return added_folders
