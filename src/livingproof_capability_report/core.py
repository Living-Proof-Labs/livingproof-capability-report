"""Versioned portable bundles and conservative, explicit grading policy."""
import copy
import csv
import hashlib
import html
import io
import json
import re
import textwrap
from collections import Counter
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from .policy import POLICY_V2, decide, explain

PASS, FAIL, INSUFFICIENT, INCOMPATIBLE = (
    "PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "INCOMPATIBLE"
)
POLICY = "all-required-v1@1.0.0"
CONTRACTS = [('https://github.com/Living-Proof-Labs/robot-capability-specs', 'v1.1.1', '60b7572df9f5e5c5ab5757a0b4674da16de2b0df', '1.0.0'), ('https://github.com/Living-Proof-Labs/robot-capability-specs', 'v1.2.0', 'f06c4a17a55d649ff78961c7391f90e34fab929d', '2.0.0')]
MEMBERS = {"pause-rules": "deterministic", "mock-ai": "mock-agent", "human-fixture": "human"}


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
        raise ValueError(f"Invalid bundle at {list(errors[0].path)}: {errors[0].message}")
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
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or any(p in {"", ".", ".."} for p in name.split("/"))):
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


def grade(loaded, policy=POLICY, human=None, previous=None):
    """Return a new report; keep every original result and contributed assessment."""
    bundle = validate_bundle(loaded["bundle"])
    contributions = copy.deepcopy(human or {"schema_version": "1.0.0", "assessments": []})
    schema = decode(Path(__file__).with_name("human.schema.json").read_text())
    Draft202012Validator(schema).validate(contributions)
    if previous is not None:
        render(previous)  # Validate stored input, without applying any current grading policy.
        if (previous["source_bundle"] != bundle
                or previous["evidence_state"] != loaded["evidence_state"]):
            raise ValueError("Grade revision must retain the original bundle and evidence state")
        contributions["assessments"] = (
            copy.deepcopy(previous["human_contributions"]["assessments"])
            + contributions["assessments"])
    known = {r["id"]: r for r in bundle["results"]}
    for contribution in contributions["assessments"]:
        result = known.get(contribution["result_id"])
        if result is None or contribution["result_sha256"] != digest(result):
            raise ValueError("Human contribution does not match the original result digest")
        a = contribution["assessment"]
        if a["evaluator"] not in {"human-fixture", "human-review"} or a["kind"] != "human":
            raise ValueError("Contribution must be a human assessment")
        if not set(a["evidence_ids"]) <= {e["id"] for e in result["evidence"]}:
            raise ValueError("Human contribution refers to undeclared evidence")
    decisions = []
    for result in bundle["results"]:
        additions = [c["assessment"] for c in contributions["assessments"]
                     if c["result_id"] == result["id"]]
        assessments = result["assessments"] + additions
        if len({a["id"] for a in assessments}) != len(assessments):
            raise ValueError("Duplicate assessment identifier across original and human contributions")
        for a in assessments:
            if a["evaluator"] == "human-review" and any(
                not isinstance(a["provenance"].get(key), str)
                or not a["provenance"][key].strip() for key in ("reviewer", "recorded_at")
            ):
                raise ValueError("Human review requires reviewer and recorded_at provenance")
        states = loaded["evidence_state"].get(result["id"], {})
        supported = (policy in {POLICY, POLICY_V2} and result["spec"]["capability"] == "pause"
                     and tuple(result["spec"][key] for key in
                               ("repository", "tag", "commit", "revision")) in CONTRACTS)
        members = dict(MEMBERS)
        if policy == POLICY_V2:
            members["human-review"] = "human"
        supported = supported and all(
            a["evaluator"] in members and a["kind"] == members[a["evaluator"]]
            and a["version"] in ({"1.0.0", "1.1.0"} if a["evaluator"] == "pause-rules"
                                  else {"1.0.0"}) for a in assessments
        )
        complete = bool(result["evidence"]) and all(
            states.get(e["id"]) == "verified" for e in result["evidence"]
        )
        membership = Counter(a["evaluator"] for a in assessments)
        compatibility = result["provenance"].get("compatibility")
        if "compatibility" in result["provenance"] and (
            not isinstance(compatibility, dict)
            or compatibility.get("status") != INCOMPATIBLE
            or compatibility.get("scope") != "execution"
            or not isinstance(compatibility.get("reason"), str)
            or not compatibility["reason"].strip()
        ):
            raise ValueError("Invalid execution compatibility declaration")
        if compatibility is not None:
            status, reason = INCOMPATIBLE, compatibility["reason"]
        elif not supported:
            status, reason = INCOMPATIBLE, "Unsupported contract, evaluator or policy version"
        elif policy == POLICY_V2:
            status, reason = decide(assessments, complete)
        elif any(a["status"] == FAIL for a in assessments):
            status, reason = FAIL, "A retained assessment failed; failures are never averaged away"
        elif not complete:
            status, reason = INSUFFICIENT, "Evidence missing or digest mismatch"
        elif (membership != Counter(MEMBERS.keys()) or any(
                a["status"] != PASS or not a["evidence_ids"] for a in assessments)
                or not any(a["evaluator"] == "pause-rules" and a["mandatory"]
                           for a in assessments)):
            status, reason = INSUFFICIENT, "Missing, duplicate or insufficient required assessment"
        else:
            status, reason = PASS, "All required assessments pass with verified evidence"
        decision = {"result_id": result["id"], "status": status, "reason": reason}
        if policy == POLICY_V2:
            decision.update(explain(result, assessments, states))
        decisions.append(decision)
    report = {"report_version": "1.0.0", "policy": policy, "source_bundle": bundle,
            "source_bundle_sha256": digest(bundle), "human_contributions": contributions,
            "evidence_state": copy.deepcopy(loaded["evidence_state"]),
            "groups": aggregate(bundle["results"]), "decisions": decisions}
    if policy == POLICY_V2 or previous is not None:
        report["grade_revision"] = 1 if previous is None else previous.get("grade_revision", 1) + 1
    if previous is not None:
        report["previous_report_sha256"] = digest(previous)
        report["previous_report"] = copy.deepcopy(previous)
    return report


def render(report, format="json"):
    """Render stored decisions, never invoke grading or apply a current policy."""
    if report.get("report_version") != "1.0.0":
        raise ValueError("Unsupported report version")
    bundle = validate_bundle(report["source_bundle"])
    if digest(bundle) != report["source_bundle_sha256"]:
        raise ValueError("Source bundle digest does not match report")
    if "previous_report" in report:
        previous = report["previous_report"]
        if (digest(previous) != report.get("previous_report_sha256")
                or report.get("grade_revision") != previous.get("grade_revision", 1) + 1
                or previous["source_bundle"] != bundle
                or previous["evidence_state"] != report["evidence_state"]
                or report["human_contributions"]["assessments"][:len(
                    previous["human_contributions"]["assessments"])]
                != previous["human_contributions"]["assessments"]):
            raise ValueError("Invalid grade revision history")
        render(previous)
    decisions = report["decisions"]
    if (len(decisions) != len(bundle["results"])
            or {d["result_id"] for d in decisions} != {r["id"] for r in bundle["results"]}
            or any(d["status"] not in {PASS, FAIL, INSUFFICIENT, INCOMPATIBLE} for d in decisions)):
        raise ValueError("Invalid stored decisions")
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    results = {r["id"]: r for r in bundle["results"]}
    rows = [{"result_id": d["result_id"], "spec_tag": results[d["result_id"]]["spec"]["tag"],
             "revision": results[d["result_id"]]["spec"]["revision"],
             "environment": canonical(results[d["result_id"]]["environment"]),
             "status": d["status"], "reason": d["reason"]} for d in decisions]
    if format == "table":
        text = terminal_table(rows, aggregate(bundle["results"]))
        details = ["Policy: " + canonical(report["policy"]),
                   "Grade revision: " + str(report.get("grade_revision", 1))]
        for decision in decisions:
            details.append(json.dumps(decision, ensure_ascii=True, sort_keys=True))
        return text + "\n".join(details) + "\n"
    if format == "csv":
        if any("assessment_details" in d for d in decisions):
            for row, decision in zip(rows, decisions):
                row.update(policy=report["policy"],
                           grade_revision=str(report.get("grade_revision", 1)),
                           assessments=canonical(decision.get("assessment_details", [])),
                           evidence_groups=canonical(decision.get("evidence_groups", [])))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Explicitly flattened and spreadsheet-safe; JSON remains lossless.
            writer.writerow({k: "'" + v if re.match(r"^[\s]*[=+@-]", v) else v
                             for k, v in row.items()})
        return stream.getvalue()
    if format != "html":
        raise ValueError("Unknown output format")
    def escape(value):
        return html.escape(str(value), quote=True)
    table = "".join("<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row.values())
                    + "</tr>" for row in rows)
    full = escape(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width'>"
            "<title>Living Proof Labs capability report</title>"
            "<style>body{font:16px system-ui;margin:2rem;max-width:90rem}"
            "td,th{border:1px solid #aaa;padding:.6rem;text-align:left}"
            "table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "</style><h1>Living Proof Labs capability report</h1>"
            "<p>Fixture evidence, not robot safety certification. Stored decisions; "
            "no regrading. Incompatible environments and revisions remain separate.</p>"
            "<table><thead><tr><th>Result</th><th>Catalog</th><th>Revision</th>"
            "<th>Environment</th><th>Status</th><th>Reason</th></tr></thead><tbody>"
            + table + "</tbody></table><details><summary>Full lossless report</summary><pre>"
            + full + "</pre></details></html>\n")


def terminal_table(rows, groups):
    """Plain ASCII table of stored decisions; safe for terminals and redirected output."""
    def safe(value):
        # Escape terminal controls (including ANSI and bidi controls), preserve data in exports.
        return json.dumps(str(value), ensure_ascii=True)[1:-1]

    columns = [("Result", "result_id", 30), ("Catalog", "spec_tag", 10),
               ("Revision", "revision", 8), ("Status", "status", 21)]
    widths = [min(limit, max(len(title), *(len(safe(row[key])) for row in rows)))
              for title, key, limit in columns]
    separator = "-+-".join("-" * width for width in widths)
    lines = ["Living Proof Labs capability report", "Stored decisions; no regrading.", "",
             " | ".join(title.ljust(width) for (title, _, _), width in zip(columns, widths)),
             separator]
    for row in rows:
        cells = [textwrap.wrap(safe(row[key]), width=width) or [""]
                 for (_, key, _), width in zip(columns, widths)]
        for index in range(max(map(len, cells))):
            lines.append(" | ".join((cell[index] if index < len(cell) else "").ljust(width)
                                    for cell, width in zip(cells, widths)).rstrip())
    lines += ["", "Separate contexts (no overall grade):"]
    for group in groups:
        context = group["context"]
        lines.append("  " + safe(canonical(context)))
        lines.append("    Results: " + ", ".join(safe(i) for i in group["result_ids"]))
    lines += ["", "Fixture evidence, not robot safety certification.",
              "Use --format json/html/csv for full export details."]
    return "\n".join(lines) + "\n"
