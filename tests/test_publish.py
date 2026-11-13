"""Public page: caller-supplied history, relative evidence paths, and retention wording.

The fixture is ``examples/bundle``, the verifier's stored G1 stock walk-hallway run.
The reporter does not invent a history link, a site path, or a retention number.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

import livingproof_capability_report
from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import load_bundle, render

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/bundle"
RUN = "https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7"
ART = RUN + "/artifacts/"


def example(tmp_path):
    index = 0
    while (tmp_path / f"bundle-{index}").exists():
        index += 1
    dest = tmp_path / f"bundle-{index}"
    shutil.copytree(EXAMPLE, dest)
    return dest / "manifest.json"


def stored(manifest, links=None):
    return report_from_bundle(load_bundle(manifest), links)

_ARTIFACT_URL = re.compile(r"actions/runs/\d+/artifacts", re.I)
_DAY_COUNT = re.compile(r"\d+\s*days?", re.I)
_RETENTION_DEFAULT = re.compile(r"retention\s*=\s*\d+")


def _assert_public(page):
    assert _ARTIFACT_URL.search(page) is None
    assert re.search(r"artifact", page, re.I) is None


def _page(tmp_path, links=None, **kwargs):
    return render(stored(example(tmp_path), links), "html", **kwargs)


def test_history_slot_is_rendered_exactly_when_supplied(tmp_path):
    page = _page(
        tmp_path,
        history={"href": "../", "label": "Run history"},
    )
    assert (
        "<nav class='run-history' aria-label='Run history'><a href='../'>Run history</a></nav>"
        in page
    )


def test_history_slot_is_absent_when_nothing_is_supplied(tmp_path):
    page = _page(tmp_path)
    assert "<nav class='run-history'" not in page
    assert "Run history" not in page


def test_history_slot_is_not_invented_from_the_stored_run(tmp_path):
    page = _page(tmp_path, [{"run": RUN, "links": []}])
    assert "<nav class='run-history'" not in page


def test_history_slot_needs_both_an_address_and_a_label(tmp_path):
    report = stored(example(tmp_path))
    with pytest.raises(ValueError, match="both an address and a label"):
        render(report, "html", history={"href": "../"})
    with pytest.raises(ValueError, match="both an address and a label"):
        render(report, "html", history={"label": "Run history"})


def test_relative_evidence_paths_are_rendered_exactly(tmp_path):
    links = [
        {
            "links": [
                {"label": "logs", "path": "evidence/run.log", "kind": "log"},
                {
                    "label": "MCAP",
                    "path": "evidence/seed-01.mcap",
                    "kind": "mcap",
                    "seed": 1,
                    "status": "PASS",
                    "url": ART + "4",
                },
                {
                    "label": "video",
                    "path": "evidence/seed-01.mp4",
                    "poster": "evidence/seed-01.jpg",
                    "why": "Typical pass",
                    "kind": "video",
                    "seed": 1,
                    "status": "PASS",
                },
                {"label": "coverage", "path": "notes/coverage.txt", "kind": "note"},
            ]
        }
    ]
    page = _page(tmp_path, links)
    for path in (
        "evidence/run.log",
        "evidence/seed-01.mcap",
        "notes/coverage.txt",
    ):
        assert f"href='{path}'" in page
        assert f"href='/{path}'" not in page
        assert f"href='evidence/{path}'" not in page
    assert "src='evidence/seed-01.mp4'" in page
    assert "poster='evidence/seed-01.jpg'" in page
    assert "Typical pass" in page
    assert ART not in page
    _assert_public(page)


@pytest.mark.parametrize("retention", [7, 30])
def test_expired_state_uses_the_caller_retention_value(tmp_path, retention):
    links = [
        {
            "links": [
                {"label": "logs", "path": "evidence/run.log", "kind": "log"},
                {
                    "label": "MCAP",
                    "path": "evidence/seed-04.mcap",
                    "kind": "mcap",
                    "seed": 4,
                    "status": "FAIL",
                    "expired": True,
                },
                {
                    "label": "video",
                    "path": "evidence/seed-01.mp4",
                    "kind": "video",
                    "seed": 1,
                    "status": "PASS",
                },
                {
                    "label": "video",
                    "path": "evidence/seed-04.mp4",
                    "kind": "video",
                    "seed": 4,
                    "status": "FAIL",
                    "expired": True,
                    "why": "Worst side-wall contact",
                },
            ]
        }
    ]
    report = stored(example(tmp_path), links)
    page = render(report, "html", retention=retention)
    phrase = f"Evidence kept for {retention} days"
    other = 30 if retention == 7 else 7
    assert phrase in page
    assert f"Evidence kept for {other} days" not in page
    items = re.findall(r"<li class='is-kept'>.*?</li>", page, re.S)
    assert len(items) >= 2
    kept = next(item for item in items if "video" in item)
    assert phrase in kept
    assert "chip-warn" not in kept and "chip-fail" not in kept
    assert "role='alert'" not in kept
    assert "warning" not in kept.lower() and "error" not in kept.lower()
    assert "href='evidence/seed-04.mcap'" not in page
    assert "src='evidence/seed-04.mp4'" not in page
    assert "href='evidence/seed-04.mp4'" not in page
    assert "<video controls preload='metadata' src='evidence/seed-01.mp4'>" in page
    assert "Worst side-wall contact" in kept
    assert "<video" not in kept
    _assert_public(page)
    with pytest.raises(ValueError, match="no default"):
        render(report, "html")


def test_public_html_omits_artifact_identifiers_that_report_json_keeps(tmp_path):
    links = [
        {
            "run": RUN,
            "links": [
                {"label": "evidence", "url": ART + "1", "kind": "artifact"},
                {"label": "video", "url": ART + "5", "kind": "video", "seed": 4, "status": "FAIL"},
            ],
        }
    ]
    report = stored(example(tmp_path), links)
    saved = json.loads(render(report, "json"))
    assert saved["evidence_links"]["links"][0]["kind"] == "artifact"
    assert saved["evidence_links"]["links"][0]["url"] == ART + "1"
    pages = [
        render(report, "html"),
        render(report, "html", history={"href": "history/", "label": "Earlier runs"}),
        _page(tmp_path),
        _page(
            tmp_path,
            [{"links": [{"label": "logs", "path": "evidence/run.log", "kind": "log"}]}],
            history={"href": "../", "label": "Run history"},
            retention=30,
        ),
    ]
    for page in pages:
        _assert_public(page)


def test_checked_in_public_pages_do_not_name_artifacts():
    robots = Path(__file__).parent / "fixtures/robots"
    for path in sorted(robots.glob("*.html")):
        _assert_public(path.read_text(encoding="utf-8"))


def test_source_has_no_hardcoded_retention_day_count():
    root = Path(livingproof_capability_report.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert _DAY_COUNT.search(text) is None, path
        assert _RETENTION_DEFAULT.search(text) is None, path


def test_cli_passes_history_retention_and_paths(tmp_path):
    manifest = example(tmp_path)
    links = manifest.parent / "links.json"
    links.write_text(
        json.dumps(
            {
                "links": [
                    {"label": "logs", "path": "evidence/run.log", "kind": "log"},
                    {
                        "label": "video",
                        "path": "evidence/seed-04.mp4",
                        "kind": "video",
                        "seed": 4,
                        "status": "FAIL",
                        "expired": True,
                    },
                ]
            }
        )
    )
    output = tmp_path / "report.html"
    result = CliRunner().invoke(
        cli,
        [
            "render",
            str(manifest),
            "--format",
            "html",
            "-o",
            str(output),
            "--evidence-links",
            str(links),
            "--evidence-retention",
            "7",
            "--history-href",
            "../",
            "--history-label",
            "Run history",
        ],
    )
    assert result.exit_code == 0, result.output
    page = output.read_text(encoding="utf-8")
    assert "<a href='../'>Run history</a>" in page
    assert "href='evidence/run.log'" in page
    assert "Evidence kept for 7 days" in page
    assert "src='evidence/seed-04.mp4'" not in page
    _assert_public(page)
