"""Versioned portable bundles: validate, load and render stored decisions; never grade."""

import copy
import csv
import hashlib
import html
import io
import json
import re
import textwrap
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from . import hallway
from . import links as elinks

PASS, FAIL, INSUFFICIENT, INCOMPATIBLE = ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "INCOMPATIBLE")
GRADES = (PASS, FAIL, INSUFFICIENT, INCOMPATIBLE)
# Bundle 1.0.0 carries assessments but no decisions; the reporter no longer grades (#30).
UNGRADED = "1.0.0"


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_bundle(bundle):
    """Validate the manifest, without reading evidence or assigning grades."""
    schema = decode(Path(__file__).with_name("bundle.schema.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(bundle), key=lambda e: str(e.path))
    if errors:
        message = f"Invalid bundle at {list(errors[0].path)}: {errors[0].message}"
        if (
            isinstance(bundle, dict)
            and not {"schema_version", "producer", "results"}.intersection(bundle)
            and isinstance(bundle.get("requested"), str)
            and isinstance(bundle.get("observed"), str)
            and isinstance(bundle.get("motion_inhibited"), bool)
            and isinstance(bundle.get("assessments"), dict)
        ):
            message = (
                "Expected a bundle manifest containing version information, evidence paths "
                "and assessment references. This looks like an individual pause observation.\n"
                "Use the containing bundle's manifest. For the bundled example, run from "
                "the repository root:\n"
                "  livingproof-capability-report validate examples/bundle/manifest.json\n"
                "Then render it to view the verifier's stored decisions; see "
                "livingproof-capability-report --help for the full workflow.\n"
                "Do not add schema_version to the observation.\n"
                f"Details: {message}"
            )
        raise ValueError(message)
    canonical(bundle)  # Reject non-finite numbers in extension/provenance fields too.
    ids = [r["id"] for r in bundle["results"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate result identifier")
    for result in bundle["results"]:
        evidence = {e["id"] for e in result["evidence"]}
        if len(evidence) != len(result["evidence"]):
            raise ValueError("Duplicate evidence identifier")
        assessments = result["assessments"]
        if len({a["id"] for a in assessments}) != len(assessments):
            raise ValueError("Duplicate assessment identifier")
        for item in result["evidence"]:
            safe_relative(item["path"])
        for assessment in assessments:
            if not set(assessment["evidence_ids"]) <= evidence:
                raise ValueError("Assessment refers to undeclared evidence")
    return copy.deepcopy(bundle)


def safe_relative(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or path.is_absolute()
        or any(p in {"", ".", ".."} for p in name.split("/"))
    ):
        raise ValueError(f"Unsafe bundle path: {name!r}")
    return path


def load_bundle(manifest):
    """Read local portable evidence only. Never fetch URLs or extract archives."""
    manifest = Path(manifest)
    bundle = validate_bundle(decode(manifest.read_text(encoding="utf-8")))
    root = manifest.parent.resolve()
    evidence_state = {}
    for result in bundle["results"]:
        evidence_state[result["id"]] = {}
        for item in result["evidence"]:
            relative = safe_relative(item["path"])
            path = root.joinpath(*relative.parts)
            # Reject all symlink components, including links that stay inside the root.
            if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
                raise ValueError(f"Symlink evidence is unsupported: {relative}")
            if not path.resolve().is_relative_to(root):
                raise ValueError("Evidence escapes bundle directory")
            state = "missing"
            if path.is_file():
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                state = "verified" if actual == item["sha256"] else "digest_mismatch"
            evidence_state[result["id"]][item["id"]] = state
    return {"bundle": bundle, "evidence_state": evidence_state}


def aggregate(results):
    """Partition exact contract/system/environment combinations; never grade."""
    groups = {}
    for result in results:
        key = canonical({k: result[k] for k in ("spec", "system", "environment")})
        groups.setdefault(key, []).append(result["id"])
    return [{"context": decode(key), "result_ids": ids} for key, ids in sorted(groups.items())]


def require_decisions(bundle):
    """Refuse a bundle without the verifier's decisions: the reporter never grades.

    ``bundle`` is a decoded manifest or what ``load_bundle`` returns.
    """
    if isinstance(bundle, dict) and isinstance(bundle.get("bundle"), dict):
        bundle = bundle["bundle"]
    version = bundle.get("schema_version") if isinstance(bundle, dict) else None
    if version == UNGRADED:
        raise ValueError(
            "Bundle 1.0.0 has no decisions to render, and this reporter does not grade. "
            "Assess the evidence with capability-verifier (v1.9.0 or later writes bundle 1.1.0 "
            "with its decisions and run assessments), then render that bundle's manifest"
        )


def check_grade(grade):
    """A stored summary grade must be one the verifier writes; anything else is refused."""
    if not isinstance(grade, str) or grade not in GRADES:
        raise ValueError(f"Report summary grade is {grade!r}; expected one of {', '.join(GRADES)}")
    return grade


def render(report, format="json", links=None):
    """Render stored decisions, never invoke grading or apply a current policy.

    Every format refuses the same stored reports: an unknown, null or non-string summary
    grade stops JSON, Markdown, HTML, CSV and table output alike.
    """
    if report.get("report_version") != "1.0.0":
        raise ValueError("Unsupported report version")
    for s in report.get("summaries") or []:
        check_grade(s.get("grade") if isinstance(s, dict) else None)
    bundle = validate_bundle(report["source_bundle"])
    if digest(bundle) != report["source_bundle_sha256"]:
        raise ValueError("Source bundle digest does not match report")
    decisions = report["decisions"]
    if (
        len(decisions) != len(bundle["results"])
        or {d["result_id"] for d in decisions} != {r["id"] for r in bundle["results"]}
        or any(d["status"] not in {PASS, FAIL, INSUFFICIENT, INCOMPATIBLE} for d in decisions)
    ):
        raise ValueError("Invalid stored decisions")
    if "evidence_links" in report:
        elinks.validate(report["evidence_links"])
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if format == "markdown":
        return hallway.markdown(report, links)
    results = {r["id"]: r for r in bundle["results"]}
    rows = [
        {
            "result_id": d["result_id"],
            "spec_tag": results[d["result_id"]]["spec"]["tag"],
            "revision": results[d["result_id"]]["spec"]["revision"],
            "environment": canonical(results[d["result_id"]]["environment"]),
            "status": d["status"],
            "reason": d["reason"],
        }
        for d in decisions
    ]
    if format == "table":
        text = terminal_table(rows, aggregate(bundle["results"]))
        from . import sections

        details = []
        for s in report.get("summaries", []):
            details.append(
                f"Run {s['system']['id']}: {s['k']} of {s['n']} trials passed; overall "
                f"{s['grade']}. {s['required_passes']} of {s['n']} required; 95% interval "
                f"{hallway._interval(s['wilson95'])} (Wilson, stored "
                f"[{s['wilson95'][0]:.4f}, {s['wilson95'][1]:.4f}])"
            )
            if sections.stored_run(report, s).get("failure_summary"):
                details.append("  Actual: " + sections.actual(report, s))
        details += [
            "Policy: " + canonical(report["policy"]),
            "Grade revision: " + str(report.get("grade_revision", 1)),
        ]
        for decision in decisions:
            details.append(json.dumps(decision, ensure_ascii=True, sort_keys=True))
        return text + "\n".join(details) + "\n"
    if format == "csv":
        if any("assessment_details" in d for d in decisions):
            for row, decision in zip(rows, decisions):
                row.update(
                    policy=report["policy"],
                    grade_revision=str(report.get("grade_revision", 1)),
                    assessments=canonical(decision.get("assessment_details", [])),
                    evidence_groups=canonical(decision.get("evidence_groups", [])),
                )
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Explicitly flattened and spreadsheet-safe; JSON remains lossless.
            writer.writerow(
                {k: "'" + v if re.match(r"^[\s]*[=+@-]", v) else v for k, v in row.items()}
            )
        return stream.getvalue()
    if format != "html":
        raise ValueError("Unknown output format")

    def escape(value):
        return html.escape(str(value), quote=True)

    from . import sections

    runs = [s for s in report.get("summaries") or [] if isinstance(s, dict)]
    in_runs = {r for s in runs for r in s.get("result_ids", [])}
    description = bundle.get("description") if isinstance(bundle.get("description"), dict) else None
    # Results outside any stored run keep a plain row; no Environment JSON column (#40).
    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(row[k])}</td>"
            for k in ("result_id", "spec_tag", "revision", "status", "reason")
        )
        + "</tr>"
        for row in rows
        if row["result_id"] not in in_runs
    )
    full = escape(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    evidence = ""
    stored = report.get("evidence_links")
    if stored:
        items = [("CI run", stored["run"])] if stored.get("run") else []
        items += [
            (
                e["label"]
                if "seed" not in e
                else f"seed {e['seed']} ({e['status']}): {e['label']}",
                e["url"],
            )
            for e in stored["links"]
        ]
        evidence = (
            "<h2>Evidence</h2><ul>"
            + "".join(f"<li><a href='{escape(u)}'>{escape(t)}</a></li>" for t, u in items)
            + "</ul>"
        )
    headers = "".join(sections.header(report, s, description) for s in runs)
    summary = html_summary(report, bundle, escape)
    detail = "".join(
        "<section class='run-detail'>"
        + sections.context(report, s, description)
        + sections.failures(report, s)
        + sections.trials(report, s)
        + "</section>"
        for s in runs
    )
    others = ""
    if table:
        others = (
            ("<h2>Other results</h2>" if runs else "")
            + "<table><thead><tr><th>Result</th><th>Catalog</th><th>Revision</th>"
            "<th>Status</th><th>Reason</th></tr></thead><tbody>" + table + "</tbody></table>"
        )
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'>"
        "<title>Living Proof Labs capability report</title>"
        "<style>body{font:16px system-ui;margin:2rem;max-width:90rem}"
        "td,th{border:1px solid #aaa;padding:.6rem;text-align:left;vertical-align:top}"
        "table{border-collapse:collapse}dt{font-weight:600}dd{margin:0 0 .4rem 1rem}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        ".verdict{border:2px solid #444;padding:1rem;margin:1rem 0}"
        ".verdict .grade{font-size:2rem;margin:.2rem 0}.verdict .robot{font-weight:600}"
        ".muted{color:#666}.limit{color:#444;font-size:.9rem}"
        ".note{border-left:4px solid #b60;padding:.4rem .8rem;background:#fff6e8}"
        ".chips{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.4rem}"
        ".chip{border:1px solid #393;border-radius:1rem;padding:.1rem .6rem}"
        "</style><h1>Living Proof Labs capability report</h1>"
        "<p>Fixture evidence, not robot safety certification. Stored decisions; "
        "no regrading. Incompatible environments and revisions remain separate.</p>"
        + headers
        + summary
        + detail
        + others
        + evidence
        + "<details><summary>Full lossless report</summary><pre>"
        + full
        + "</pre></details></html>\n"
    )


def html_summary(report, bundle, escape):
    """The supplied run summaries and provenance, shown above the trial table.

    Everything comes from stored fields (``summaries``, ``policy``, the source bundle's
    ``assessment`` and ``producer``); a field that is absent is left out, and nothing is
    graded or recalculated here.
    """

    def ref(value):
        if not isinstance(value, dict):
            return None if value is None else str(value)
        name = value.get("id") or value.get("tag")
        version = value.get("version") or value.get("revision")
        return f"{name}@{version}" if name and version else name

    def items(pairs):
        return "".join(
            f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in pairs if v not in (None, "")
        )

    parts = []
    for s in report.get("summaries") or []:
        check_grade(s.get("grade"))
        spec = s.get("spec") if isinstance(s.get("spec"), dict) else {}
        observed = (
            f"{s['k']} of {s['n']} trials passed; overall {s['grade']}"
            if s.get("k") is not None and s.get("n") is not None and s.get("grade")
            else None
        )
        interval = s.get("wilson95")
        title = " ".join(x for x in (ref(s.get("system")), s.get("grade")) if x)
        parts.append(
            f"<section class='run'><h3>{escape(title or 'Run')}</h3><dl>"
            + items(
                [
                    ("Robot", ref(s.get("system"))),
                    ("Run", s.get("run_id")),
                    ("Overall status", s.get("grade")),
                    ("Observed", observed),
                    (
                        "Threshold",
                        None
                        if s.get("required_passes") is None
                        else f"{s['required_passes']} of {s.get('n', '?')} trials required",
                    ),
                    (
                        "Wilson 95% (stored)",
                        f"{round(interval[0] * 100)}–{round(interval[1] * 100)}%"
                        if isinstance(interval, list) and len(interval) == 2
                        else None,
                    ),
                    ("Capability", s.get("capability")),
                    (
                        "Spec",
                        " ".join(
                            str(x)
                            for x in (
                                spec.get("tag"),
                                spec.get("revision") and f"revision {spec['revision']}",
                                spec.get("commit"),
                            )
                            if x
                        ),
                    ),
                    ("Environment", ref(s.get("environment"))),
                ]
            )
            + "</dl></section>"
        )
    assessment = bundle.get("assessment") if isinstance(bundle.get("assessment"), dict) else {}
    producer = bundle.get("producer") if isinstance(bundle.get("producer"), dict) else {}
    provenance = items(
        [
            ("Policy", report.get("policy")),
            ("Grade revision", str(report.get("grade_revision", 1))),
            ("Aggregation", ref(assessment.get("aggregation"))),
            ("Assessment format", assessment.get("format")),
            (
                "Assessed by",
                " ".join(str(x) for x in (ref(producer), producer.get("commit")) if x),
            ),
            ("Bundle", bundle.get("schema_version") and f"schema {bundle['schema_version']}"),
        ]
    )
    if not parts and not provenance:
        return ""
    return (
        "<section id='summary'><h2>Summary</h2>"
        + "".join(parts)
        + (f"<h3>Provenance</h3><dl>{provenance}</dl>" if provenance else "")
        + "</section>"
    )


def terminal_table(rows, groups):
    """Plain ASCII table of stored decisions; safe for terminals and redirected output."""

    def safe(value):
        # Escape terminal controls (including ANSI and bidi controls), preserve data in exports.
        return json.dumps(str(value), ensure_ascii=True)[1:-1]

    columns = [
        ("Result", "result_id", 30),
        ("Catalog", "spec_tag", 10),
        ("Revision", "revision", 8),
        ("Status", "status", 21),
    ]
    widths = [
        min(limit, max(len(title), *(len(safe(row[key])) for row in rows)))
        for title, key, limit in columns
    ]
    separator = "-+-".join("-" * width for width in widths)
    lines = [
        "Living Proof Labs capability report",
        "Stored decisions; no regrading.",
        "",
        " | ".join(title.ljust(width) for (title, _, _), width in zip(columns, widths)),
        separator,
    ]
    for row in rows:
        cells = [
            textwrap.wrap(safe(row[key]), width=width) or [""]
            for (_, key, _), width in zip(columns, widths)
        ]
        for index in range(max(map(len, cells))):
            lines.append(
                " | ".join(
                    (cell[index] if index < len(cell) else "").ljust(width)
                    for cell, width in zip(cells, widths)
                ).rstrip()
            )
    lines += ["", "Separate contexts (no overall grade):"]
    for group in groups:
        context = group["context"]
        lines.append("  " + safe(canonical(context)))
        lines.append("    Results: " + ", ".join(safe(i) for i in group["result_ids"]))
    lines += [
        "",
        "Fixture evidence, not robot safety certification.",
        "Use --format json/html/csv for full export details.",
    ]
    return "\n".join(lines) + "\n"
