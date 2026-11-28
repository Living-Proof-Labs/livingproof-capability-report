"""`site --validated-viewer-run`: restored trusted-viewer runs the caller has already checked.

verification-reports-action validates a restored viewer run (manifest, release asset, data
and trial binding, the exact native panel) before it calls `site`, then composes viewers
after it (va#86). The flag lets those runs through the restored-page recheck. It is narrow:
exact run paths only, it skips only the one viewer frame on the run's index.html, and every
other restored-page check still runs. A listed run without `trusted-viewer/`, or one that is
not in the history, is refused before anything is written.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.trusted_viewer import TrustedViewer
from livingproof_capability_report.viewer_page import compose_viewer_page

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/site-real-g1/46122371783"
REPOSITORY = "Living-Proof-Labs/verification-reports-action"
RUN = "unitree-g1/stock-mujoco-hallway/runs/46122371783"
VIEWER = b"<!doctype html><p>Fixture viewer</p>"


def _site():
    import livingproof_capability_report.site as site

    return site


def _digests(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _incoming(tmp_path: Path, run_id: str, created: str) -> Path:
    runs = tmp_path / f"incoming-{run_id}"
    shutil.copytree(FIXTURE, runs)
    folder = next(runs.glob("*/*"))
    record = json.loads((folder / "run.json").read_bytes())
    record["run"].update(
        id=run_id, created=created, url=f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"
    )
    (folder / "run.json").write_text(json.dumps(record))
    _site().write_published_checksums(folder)
    return runs


def _history(tmp_path: Path, *, decorate: bool = True) -> Path:
    """The real G1 run published once, with a Health viewer composed onto its page."""
    site = _site()
    reports = tmp_path / "reports"
    site.build(reports, FIXTURE, repository=REPOSITORY)
    run = reports / RUN
    if decorate:
        report = json.loads((run / "report.json").read_bytes())
        (run / "trusted-viewer/data").mkdir(parents=True)
        (run / "trusted-viewer/viewer.html").write_bytes(VIEWER)
        shutil.copyfile(run / "health.json", run / "trusted-viewer/data/recording.json")
        pin = TrustedViewer(
            "livingproof-health",
            "1.2.0",
            "Living Proof Labs",
            "trusted-viewer/viewer.html",
            hashlib.sha256(VIEWER).hexdigest(),
            "livingproof-evaluator-health/1",
        )
        page = compose_viewer_page(
            (run / "index.html").read_text(encoding="utf-8"),
            report,
            trusted_viewers=[pin],
            asset_root=run,
            validate_shell=lambda value: site.checked_report_html(value, "existing shell"),
        )
        assert page.count("<iframe ") == 1
        (run / "index.html").write_text(page, encoding="utf-8")
        site.write_published_checksums(run)
    return reports


def _next(tmp_path: Path, reports: Path, **options):
    return _site().build(
        reports,
        _incoming(tmp_path, "46122371784", "2026-11-28T08:48:59Z"),
        repository=REPOSITORY,
        **options,
    )


def test_checked_report_html_and_write_published_checksums_are_public():
    site = _site()
    assert {"checked_report_html", "write_published_checksums"} <= set(site.__all__)
    assert site.checked_report_html.__doc__ and site.write_published_checksums.__doc__
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "checked_report_html" in readme and "write_published_checksums" in readme
    assert "--validated-viewer-run" in readme


def test_an_unlisted_restored_viewer_run_is_still_refused(tmp_path):
    reports = _history(tmp_path)
    with pytest.raises(_site().SiteError, match="<iframe> is not allowed"):
        _next(tmp_path, reports)


def test_a_listed_restored_viewer_run_is_kept_byte_for_byte(tmp_path):
    reports = _history(tmp_path)
    before = {k: v for k, v in _digests(reports).items() if k.startswith(RUN + "/")}
    added = _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert [p.name for p in added] == ["46122371784"]
    after = {k: v for k, v in _digests(reports).items() if k.startswith(RUN + "/")}
    assert after == before
    assert _site().check_reports_tree(reports, repository=REPOSITORY) == []


def test_the_cli_passes_each_listed_run(tmp_path):
    reports = _history(tmp_path)
    runs = _incoming(tmp_path, "46122371784", "2026-11-28T08:48:59Z")
    args = ["site", str(reports), "--runs", str(runs), "--repository", REPOSITORY]
    refused = CliRunner().invoke(cli, args)
    assert refused.exit_code != 0 and "<iframe> is not allowed" in refused.output
    result = CliRunner().invoke(cli, [*args, "--validated-viewer-run", RUN])
    assert result.exit_code == 0, result.output
    assert "Added unitree-g1/stock-mujoco-hallway/runs/46122371784" in result.output


def test_a_listed_run_without_a_trusted_viewer_folder_is_refused_before_any_write(tmp_path):
    reports = _history(tmp_path, decorate=False)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="has no trusted-viewer/ folder"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert _digests(reports) == before


def test_a_listed_run_that_is_not_in_the_history_is_refused_before_any_write(tmp_path):
    reports = _history(tmp_path)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="is not a run in the history"):
        _next(
            tmp_path,
            reports,
            validated_viewer_runs=[RUN, "unitree-g1/stock-mujoco-hallway/runs/46122371700"],
        )
    assert _digests(reports) == before


@pytest.mark.parametrize(
    "entry",
    [
        "unitree-g1/stock-mujoco-hallway/runs/*",
        "unitree-g1/stock-mujoco-hallway/runs/4612237178?",
        "unitree-g1/stock-mujoco-hallway/runs/[4]6122371783",
        "unitree-g1/*/runs/46122371783",
        "unitree-g1/stock-mujoco-hallway/runs/**",
        "unitree-g1/stock-mujoco-hallway/runs/46122371783/",
        "unitree-g1/stock-mujoco-hallway/runs/46122371783/index.html",
        "./unitree-g1/stock-mujoco-hallway/runs/46122371783",
        "unitree-g1/stock-mujoco-hallway/runs/../runs/46122371783",
        "/unitree-g1/stock-mujoco-hallway/runs/46122371783",
        "unitree-g1\\stock-mujoco-hallway\\runs\\46122371783",
        "unitree-g1/stock-mujoco-hallway/46122371783",
        "stock-mujoco-hallway/runs/46122371783",
        "46122371783",
        "",
    ],
)
def test_only_an_exact_run_path_is_accepted(tmp_path, entry):
    reports = _history(tmp_path)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="validated-viewer-run"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN, entry])
    assert _digests(reports) == before


def test_a_listed_run_that_is_also_excluded_is_refused(tmp_path):
    reports = _history(tmp_path)
    with pytest.raises(_site().SiteError, match="also excluded"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN], exclude_runs=["46122371783"])


def _tamper(reports: Path, fault: str) -> None:
    run = reports / RUN
    page = (run / "index.html").read_text(encoding="utf-8")
    frame_start = page.index("<iframe ")
    frame_end = page.index("</noscript>", frame_start) + len("</noscript>")
    frame = page[frame_start:frame_end]
    if fault == "extra-frame":
        page = page.replace("</body>", '<iframe src="trusted-viewer/viewer.html"></iframe></body>')
    elif fault == "second-viewer-frame":
        page = page.replace("</body>", frame + "</body>")
    elif fault == "changed-frame":
        page = page.replace('loading="lazy"', 'loading="eager"', 1)
    elif fault == "frame-outside-trusted-viewer":
        page = page.replace('src="trusted-viewer/viewer.html#', 'src="evidence/viewer.html#', 1)
    elif fault == "frame-with-extra-attribute":
        page = page.replace(
            '<iframe title="Recorded replay"', '<iframe onload="x()" title="Recorded replay"', 1
        )
    elif fault == "unknown-script":
        page = page.replace("</body>", "<script>alert(1)</script></body>")
    elif fault == "script-in-frame-src":
        page = page.replace(
            'src="trusted-viewer/viewer.html#', 'src="javascript:alert(1)//viewer.html#', 1
        )
    elif fault == "frame-in-report-html":
        text = (run / "report.html").read_text(encoding="utf-8")
        (run / "report.html").write_text(
            text.replace("</body>", frame + "</body>"), encoding="utf-8"
        )
    elif fault == "unpublished-evidence":
        (run / "evidence/payload.exe").write_bytes(b"MZ")
    else:
        raise AssertionError(fault)
    (run / "index.html").write_text(page, encoding="utf-8")
    _site().write_published_checksums(run)


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("extra-frame", "<iframe> is not allowed"),
        ("second-viewer-frame", "one trusted viewer frame"),
        ("changed-frame", "one trusted viewer frame"),
        ("frame-outside-trusted-viewer", "one trusted viewer frame"),
        ("frame-with-extra-attribute", "one trusted viewer frame"),
        ("script-in-frame-src", "one trusted viewer frame"),
        ("unknown-script", "not a known reporter script"),
        ("frame-in-report-html", "<iframe> is not allowed"),
        ("unpublished-evidence", "evidence of this type is not published"),
    ],
)
def test_every_other_restored_page_check_still_runs_for_a_listed_run(tmp_path, fault, message):
    reports = _history(tmp_path)
    _tamper(reports, fault)
    with pytest.raises(_site().SiteError, match=message):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
