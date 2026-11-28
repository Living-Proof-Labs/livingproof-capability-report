# SPDX-License-Identifier: Apache-2.0
"""Fixture run folders for a single-robot `reports/` build.

Copied byte for byte in behaviour from verification-reports-action `tools/site_fixture.py`
so the golden digests below pin the same site the action rendered before va#75.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from livingproof_capability_report.site import check_reports_tree
from livingproof_capability_report.site.assemble import REPORT_FILES

__all__ = ["DEFAULT_SCENARIOS", "check_reports_tree", "write"]

DEFAULT_SCENARIOS = (
    {
        "variant": "stock-mujoco-hallway",
        "capability": "walk-hallway",
        "configuration": "stock",
        "grade": "FAIL",
        "k": 12,
        "n": 20,
        "required_passes": 18,
        "finding": "Drifted 0.66 m from the hallway centreline.",
        "with_evidence": True,
    },
    {
        "variant": "stock-mujoco-corner-left",
        "capability": "walk-corner-left",
        "configuration": "stock",
        "grade": "PASS",
        "k": 1,
        "n": 1,
        "required_passes": 1,
        "finding": None,
        "with_evidence": False,
    },
    {
        "variant": "stock-mujoco-corner-right",
        "capability": "walk-corner-right",
        "configuration": "stock",
        "grade": "INSUFFICIENT_EVIDENCE",
        "k": 0,
        "n": 1,
        "required_passes": 1,
        "finding": "Recording stopped before the corner exit.",
        "with_evidence": False,
    },
)


def write(
    directory: Path,
    *,
    run_id: str = "100",
    created: str = "2026-11-23T00:00:00Z",
    repository: str = "Living-Proof-Labs/livingproof-unitree-g1",
    commit: str = "a" * 40,
    tag: str | None = "v2.3.32",
    scenarios: tuple[dict, ...] = DEFAULT_SCENARIOS,
) -> list[Path]:
    """Write per-scenario run folders in the expected input layout."""
    written: list[Path] = []
    robot_slug = repository.rsplit("/", 1)[-1].removeprefix("livingproof-").lower()
    for item in scenarios:
        variant = item["variant"]
        folder = directory / f"{robot_slug}-{variant}"
        folder.mkdir(parents=True, exist_ok=True)

        ev_doc: dict = {
            "format": "livingproof-evaluator-result/1.1.0",
            "evaluator": {"id": "livingproof-scenario", "display_name": "Scenario"},
            "descriptor": {
                "title": "Scenario",
                "purpose": "Evaluates scenario completion and bounds.",
            },
        }
        if item.get("finding"):
            ev_doc["grade"] = "FAIL"
            ev_doc["findings"] = [{"summary": item["finding"]}]

        report = {
            "report_version": "1.0.0",
            "source_bundle": {
                "results": [
                    {
                        "id": f"{variant}-trial-01",
                        "evaluator_results": [ev_doc],
                    }
                ]
            },
            "summaries": [
                {
                    "capability": item["capability"],
                    "spec": {
                        "repository": "Living-Proof-Labs/robot-capability-specs",
                        "tag": "v3.1.0",
                        "commit": "b" * 40,
                        "capability": item["capability"],
                        "revision": "0.2.0",
                    },
                    "system": {
                        "id": f"{robot_slug}/{item['configuration']}",
                        "version": "1.1.1",
                    },
                    "grade": item["grade"],
                    "k": item["k"],
                    "n": item["n"],
                    "required_passes": item["required_passes"],
                }
            ],
        }
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        run_url = f"https://github.com/{repository}/actions/runs/{run_id.split('-')[0]}"
        ci_run = f"<p><a href='{run_url}'>CI run</a></p>"
        evidence_html = f"<section id='evidence'>{ci_run}</section>"
        if item.get("with_evidence"):
            ev_dir = folder / "evidence"
            ev_dir.mkdir(parents=True, exist_ok=True)
            (ev_dir / "trials.mcap").write_bytes(b"fixture mcap bytes")
            (ev_dir / "trial-01-fail.mp4").write_bytes(b"fixture mp4 bytes")
            evidence_html = (
                f"<section id='evidence'><p class='is-kept'>Evidence kept for 7 days</p>{ci_run}"
                "<p><a href='evidence/trials.mcap'>MCAP recording</a></p>"
                "<video controls src='evidence/trial-01-fail.mp4'></video></section>"
            )

        html_body = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{variant}</title></head><body><main>"
            f"<section id='summary'><div id='evaluator-livingproof-scenario'>"
            f"<h1>{variant}: {item['grade']}</h1></div></section>"
            f"{evidence_html}</main></body></html>\n"
        )
        (folder / "report.html").write_text(html_body, encoding="utf-8")
        (folder / "report.md").write_text(
            f"# {variant}\n\nGrade: {item['grade']}\n", encoding="utf-8"
        )
        (folder / "report.txt").write_text(f"{variant}: {item['grade']}\n", encoding="utf-8")

        commit_block: dict = {
            "sha": commit,
            "url": f"https://github.com/{repository}/commit/{commit}",
        }
        if tag:
            commit_block["tag"] = tag

        run_record = {
            "variant": variant,
            "verification": f"{robot_slug}-{variant}",
            "run": {
                "id": run_id,
                "url": f"https://github.com/{repository}/actions/runs/{run_id.split('-')[0]}",
                "created": created,
            },
            "commit": commit_block,
            "robot": {
                "repository": repository,
                "commit": commit,
                "configuration": item["configuration"],
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
                    "tag": "v3.1.0",
                    "commit": "b" * 40,
                    "url": "https://github.com/Living-Proof-Labs/robot-capability-specs/releases/tag/v3.1.0",
                },
                "verifier": {
                    "repository": "Living-Proof-Labs/capability-verifier",
                    "tag": "v2.11.4",
                    "commit": "c" * 40,
                    "url": "https://github.com/Living-Proof-Labs/capability-verifier/releases/tag/v2.11.4",
                },
                "reporter": {
                    "repository": "Living-Proof-Labs/livingproof-capability-report",
                    "tag": "v3.15.4",
                    "commit": "d" * 40,
                    "url": "https://github.com/Living-Proof-Labs/livingproof-capability-report/releases/tag/v3.15.4",
                },
            },
        }
        (folder / "run.json").write_text(json.dumps(run_record, indent=2) + "\n", encoding="utf-8")
        (folder / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
                for n in REPORT_FILES
            ),
            encoding="utf-8",
        )
        written.append(folder)
    return written


def build_golden_site(work: Path) -> Path:
    """The action's `tools/site_golden.py` two-build site, unchanged."""
    from livingproof_capability_report.site import build

    reports = work / "reports"
    write(work / "in1", run_id="100", created="2026-11-20T06:00:00Z")
    write(
        work / "in2",
        run_id="200",
        created="2026-11-29T06:00:00Z",
        commit="b" * 40,
        tag="v2.3.33",
    )
    build(reports, work / "in1")
    build(reports, work / "in2", days=7)
    return reports


def digests(reports: Path) -> str:
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(reports).as_posix()}\n"
        for path in sorted(reports.rglob("*"))
        if path.is_file()
    )
