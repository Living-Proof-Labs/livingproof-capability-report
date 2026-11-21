# SPDX-License-Identifier: Apache-2.0
"""Tests for #111: run completion time and per-evaluator graded timestamps."""

import copy
import json
from pathlib import Path
import re

import pytest

from livingproof_capability_report import assessed, core

ROOT = Path(__file__).parents[1]
CORNER_MANIFEST = ROOT / "tests/fixtures/corner/g1-stock/manifest.json"
SCENARIO_RESULT = ROOT / "tests/fixtures/evaluator-result-scenario.json"
INTEGRITY_PASS = ROOT / "tests/fixtures/integrity/success.json"


def _corner_report():
    loaded = core.load_bundle(CORNER_MANIFEST)
    return assessed.report_from_bundle(loaded)


def _with_timestamps(
    *,
    trial_times=("2026-11-20T06:40:00Z", "2026-11-20T06:42:00Z"),
    scenario_time="2026-11-20T06:43:00Z",
    integrity_time="2026-11-20T09:42:00Z",
):
    report = _corner_report()
    bundle = copy.deepcopy(report["source_bundle"])
    results = bundle["results"]
    base = results[0]
    new_results = []
    for index, completed_at in enumerate(trial_times, start=1):
        res = copy.deepcopy(base)
        res["id"] = f"stock-seed-0{index}"
        if completed_at is not None:
            res["timestamps"] = {
                "started_at": completed_at,
                "completed_at": completed_at,
            }
        else:
            res.pop("timestamps", None)
        for er in res.get("evaluator_results") or []:
            if scenario_time is not None:
                er["timestamps"] = {"started_at": scenario_time, "completed_at": scenario_time}
            else:
                er.pop("timestamps", None)
        new_results.append(res)
    bundle["results"] = new_results
    run = bundle["assessment"]["runs"][0]
    run["result_ids"] = [r["id"] for r in new_results]
    run["n"] = len(new_results)
    run["k"] = len(new_results)
    bundle["assessment"]["decisions"] = [
        {"result_id": r["id"], "status": r["decision"]["status"], "reason": r["decision"]["reason"]}
        for r in new_results
    ]

    if integrity_time is not None:
        integrity_doc = json.loads(INTEGRITY_PASS.read_text(encoding="utf-8"))
        integrity_doc["integrity"]["run"]["id"] = run["run_id"]
        integrity_doc["timestamps"] = {
            "started_at": integrity_time,
            "completed_at": integrity_time,
        }
        bundle["assessment"]["integrity_results"] = {"livingproof-integrity": integrity_doc}

    report["source_bundle"] = bundle
    report["source_bundle_sha256"] = core.digest(bundle)
    report["decisions"] = [
        {
            "result_id": r["id"],
            "status": r["decision"]["status"],
            "reason": r["decision"]["reason"],
            "failures": r["decision"]["failures"],
            "assessor_types": r["decision"]["assessor_types"],
        }
        for r in new_results
    ]
    report["summaries"][0]["result_ids"] = run["result_ids"]
    report["summaries"][0]["n"] = run["n"]
    report["summaries"][0]["k"] = run["k"]
    return report


def test_run_header_and_evaluator_panels_show_utc_fallback_and_late_note():
    report = _with_timestamps()
    html = core.render(report, "html")

    # Run time is in the result header (latest trial completed_at: 06:42:00Z).
    assert (
        "<p class='run-time'>Ran <time datetime='2026-11-20T06:42:00Z' "
        "title='20 Nov 2026, 06:42 UTC'>20 Nov 2026, 06:42 UTC</time></p>"
    ) in html

    # Scenario evaluator graded 1 min after run -> no late note.
    assert (
        "<p class='meta'>Graded <time datetime='2026-11-20T06:43:00Z' "
        "title='20 Nov 2026, 06:43 UTC'>20 Nov 2026, 06:43 UTC</time></p>"
    ) in html

    # Integrity evaluator graded 3 h after run -> neutral late note.
    assert (
        "<p class='meta'>Graded <time datetime='2026-11-20T09:42:00Z' "
        "title='20 Nov 2026, 09:42 UTC'>20 Nov 2026, 09:42 UTC</time></p>"
        "<p class='meta late-note'>Graded 3 h after the run</p>"
    ) in html

    # Evaluator tab buttons themselves stay clean (no timestamps inside <summary>).
    for summary_html in re.findall(r"<summary class='eval-mark[^']*'[^>]*>.*?</summary>", html):
        assert "<time" not in summary_html
        assert "Graded" not in summary_html

    # No relative age text anywhere; deterministic output.
    lowered = html.lower()
    for forbidden in ("just now", "minutes ago", "hours ago", "days ago", "yesterday"):
        assert forbidden not in lowered
    assert core.render(report, "html") == html


def test_winter_timestamp_aest_and_missing_timestamps():
    # Missing timestamps on both run and evaluator -> Time not recorded.
    missing = _with_timestamps(
        trial_times=(None,),
        scenario_time=None,
        integrity_time=None,
    )
    missing_html = core.render(missing, "html")
    assert "<p class='run-time is-missing'>Time not recorded</p>" in missing_html
    assert "<p class='meta is-missing'>Time not recorded</p>" in missing_html

    # Winter timestamp (June) -> UTC fallback in static HTML.
    winter = _with_timestamps(
        trial_times=("2026-06-18T05:00:00Z",),
        scenario_time="2026-06-18T05:01:00Z",
        integrity_time="2026-06-18T05:25:00Z",
    )
    winter_html = core.render(winter, "html")
    assert (
        "<time datetime='2026-06-18T05:00:00Z' title='18 Jun 2026, 05:00 UTC'>"
        "18 Jun 2026, 05:00 UTC</time>"
    ) in winter_html
    assert "<p class='meta late-note'>Graded 25 min after the run</p>" in winter_html


def test_browser_viewer_timezones_no_js_mobile_and_print(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = Path("/usr/bin/chromium")
    launch_kwargs = {"executable_path": str(chromium)} if chromium.is_file() else {}

    report = _with_timestamps()
    winter_report = _with_timestamps(
        trial_times=("2026-06-18T05:00:00Z",),
        scenario_time="2026-06-18T05:01:00Z",
        integrity_time=None,
    )
    nov_file = tmp_path / "report-nov.html"
    jun_file = tmp_path / "report-jun.html"
    nov_file.write_text(core.render(report, "html"), encoding="utf-8")
    jun_file.write_text(core.render(winter_report, "html"), encoding="utf-8")

    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(**launch_kwargs)
            except Exception as exc:
                pytest.skip(f"no Chromium available: {exc}")
            try:
                # 1. Australia/Sydney (en-AU): AEDT in Nov, AEST in Jun, plus 320px & print/PDF.
                sydney = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    timezone_id="Australia/Sydney",
                    locale="en-AU",
                )
                page = sydney.new_page()
                page.goto(nov_file.as_uri())
                assert page.locator(".run-time").inner_text() == "Ran 20 Nov 2026, 17:42 AEDT"
                page.locator(".eval-mark").first.click()
                assert (
                    page.locator(".eval-tabpanel .meta", has_text="Graded ").first.inner_text()
                    == "Graded 20 Nov 2026, 17:43 AEDT"
                )
                page.screenshot(path=tmp_path / "desktop-sydney.png", full_page=True)

                # Print media and PDF.
                page.emulate_media(media="print")
                assert page.locator(".run-time").is_visible()
                assert page.locator(".run-time").inner_text() == "Ran 20 Nov 2026, 17:42 AEDT"
                page.screenshot(path=tmp_path / "print-sydney.png", full_page=True)
                pdf_path = tmp_path / "report-print.pdf"
                page.pdf(path=pdf_path, format="A4")
                assert pdf_path.read_bytes().startswith(b"%PDF-")

                # Winter (AEST).
                page.emulate_media(media="screen")
                page.goto(jun_file.as_uri())
                assert page.locator(".run-time").inner_text() == "Ran 18 Jun 2026, 15:00 AEST"
                sydney.close()

                # 2. America/Los_Angeles (en-US): PST in Nov, PDT in Jun.
                la = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    timezone_id="America/Los_Angeles",
                    locale="en-US",
                )
                page = la.new_page()
                page.goto(nov_file.as_uri())
                assert page.locator(".run-time").inner_text() == "Ran 19 Nov 2026, 22:42 PST"
                page.goto(jun_file.as_uri())
                assert page.locator(".run-time").inner_text() == "Ran 17 Jun 2026, 22:00 PDT"
                la.close()

                # 3. Mobile 320px: run time and evaluator panel times fit within 320px.
                mobile = browser.new_context(
                    viewport={"width": 320, "height": 844},
                    timezone_id="Australia/Sydney",
                    locale="en-AU",
                )
                page = mobile.new_page()
                page.goto(nov_file.as_uri())
                run_time = page.locator(".run-time")
                assert run_time.inner_text() == "Ran 20 Nov 2026, 17:42 AEDT"
                box = run_time.bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= 320
                page.locator(".eval-mark").first.click()
                graded = page.locator(".eval-tabpanel .meta", has_text="Graded ").first
                gbox = graded.bounding_box()
                assert gbox and gbox["x"] >= 0 and gbox["x"] + gbox["width"] <= 320
                page.screenshot(path=tmp_path / "mobile-320.png", full_page=True)
                mobile.close()

                # 4. No-JS fallback: UTC.
                no_js = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=False,
                    timezone_id="Australia/Sydney",
                    locale="en-AU",
                )
                page = no_js.new_page()
                page.goto(nov_file.as_uri())
                assert page.locator(".run-time").inner_text() == "Ran 20 Nov 2026, 06:42 UTC"
                no_js.close()
            finally:
                browser.close()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip(f"no Chromium available: {exc}")
        raise
