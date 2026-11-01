"""Evidence links: CI run, artifacts and per-trial media, carried in report.json.

Links are stored next to the decisions, never inside the source bundle, so they change
no digest and no grade. Each ``--evidence-links`` file is a JSON object::

    {"run": "https://github.com/OWNER/REPO/actions/runs/1",
     "links": [{"label": "evidence", "url": "https://...", "kind": "artifact"},
               {"label": "video", "url": "https://...", "kind": "video",
                "seed": 1, "status": "PASS"}]}

Files are merged in order; a second ``run`` must match the first. A per-trial link names
the verifier's status for that seed, and rendering refuses a link whose status disagrees
with the stored decision, so a "pass" video can never point at a failed trial.
"""

import re

KINDS = ("artifact", "video", "mcap")
_URL = re.compile(r"^https://[^\s()<>\[\]|`]+$")
_LABEL = re.compile(r"^[^\[\]()|`<>\n]{1,80}$")


def _check(entry):
    if not isinstance(entry, dict):
        raise ValueError("Evidence link must be an object")
    unknown = set(entry) - {"label", "url", "kind", "seed", "status"}
    if unknown:
        raise ValueError(f"Unknown evidence link fields: {', '.join(sorted(unknown))}")
    if not isinstance(entry.get("label"), str) or not _LABEL.match(entry["label"]):
        raise ValueError("Evidence link label must be 1-80 plain characters")
    if not isinstance(entry.get("url"), str) or not _URL.match(entry["url"]):
        raise ValueError(f"Evidence link URL must be https without spaces: {entry.get('url')!r}")
    if entry.get("kind") not in KINDS:
        raise ValueError(f"Evidence link kind must be one of {', '.join(KINDS)}")
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
    """Merge ``--evidence-links`` documents; empty URLs (skipped uploads) are dropped."""
    run, links = None, []
    for doc in documents:
        if not isinstance(doc, dict) or set(doc) - {"run", "links"}:
            raise ValueError("Evidence links file must be an object with run and links")
        if doc.get("run"):
            if run is not None and doc["run"] != run:
                raise ValueError("Evidence links files name different CI runs")
            run = doc["run"]
        for entry in doc.get("links", []):
            if isinstance(entry, dict) and not entry.get("url"):
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


def lines(report, run):
    """Markdown lines for one hallway run (empty without stored links)."""
    stored = report.get("evidence_links")
    if not stored:
        return []
    out = []
    head = [f"[CI run]({stored['run']})"] if stored.get("run") else []
    head += [f"[{e['label']}]({e['url']})" for e in stored["links"] if "seed" not in e]
    if head:
        out.append("**Evidence:** " + " · ".join(head))
    trials = {}
    for e in stored["links"]:
        if "seed" in e:
            stored_status = seed_status(report, run["result_ids"], e["seed"])
            if stored_status != e["status"]:
                raise ValueError(
                    f"Evidence link for seed {e['seed']} says {e['status']}, "
                    f"stored decision is {stored_status}"
                )
            trials.setdefault((e["status"] != "FAIL", e["seed"]), []).append(e)
    for (_, seed), items in sorted(trials.items()):
        word = "pass" if items[0]["status"] == "PASS" else "fail"
        icon = "▶️" if any(e["kind"] == "video" for e in items) else "📎"
        cells = " · ".join(f"[{e['label']}]({e['url']})" for e in items)
        out.append(f"- {icon} seed {seed} ({word}): {cells}")
    return out
