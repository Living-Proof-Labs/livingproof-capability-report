"""Pins on `site --validated-viewer-run` that mutation of the exception logic left unpinned.

Found by reviewing #145 at 8ed5fac. Each group names what it holds fixed:

- the entry is one exact `ROBOT/VARIANT/runs/RUN_ID` path (globs, dots, encodings, unicode,
  whitespace, case, depth), refused before anything is written
- the one frame that is left out of the check matches the reporter's own markup exactly,
  and anything else on the page still gets every check
- a symlinked run, robot folder or trusted-viewer/ is not a validated run
- a listed run that `site` republishes anyway (evidence expiry, same-run replace) is kept
  as a plain page and the entry has no effect
- the two helpers that are now public
- the frame must be a whole element in the exact place `compose_viewer_page` puts it, not
  the same bytes inside a start tag, an attribute value or a script
"""

from __future__ import annotations

import re
import shutil

import pytest
from click.testing import CliRunner

from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.trusted_viewer import FRAME_END, FRAME_START
from test_site_validated_viewer_runs import (
    REPOSITORY,
    RUN,
    _digests,
    _history,
    _incoming,
    _next,
    _site,
)

ROBOT, VARIANT, _RUNS, RUN_ID = RUN.split("/")


def _frame(page: str) -> str:
    start = page.index("<iframe ")
    return page[start : page.index("</noscript>", start) + len("</noscript>")]


def _rewrite(reports, change) -> None:
    run = reports / RUN
    page = (run / "index.html").read_text(encoding="utf-8")
    (run / "index.html").write_text(change(page), encoding="utf-8")
    _site().write_published_checksums(run)


# --- the entry is one exact path ----------------------------------------------------------

BAD_ENTRIES = [
    f"{ROBOT}/{VARIANT}/runs/*",
    f"{ROBOT}/{VARIANT}/runs/{RUN_ID[:-1]}?",
    f"{ROBOT}/{VARIANT}/runs/[4]{RUN_ID[1:]}",
    f"{ROBOT}/{VARIANT}/runs/{{{RUN_ID}}}",
    f"*/{VARIANT}/runs/{RUN_ID}",
    f"**/runs/{RUN_ID}",
    f"./{RUN}",
    f"{ROBOT}/./{VARIANT}/runs/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/runs/..",
    f"{ROBOT}/{VARIANT}/runs/.",
    f"../{VARIANT}/runs/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/runs/../runs/{RUN_ID}",
    f"{RUN}/",
    f"/{RUN}",
    f"{ROBOT}//{VARIANT}/runs/{RUN_ID}",
    RUN.replace("/", "\\"),
    f"{ROBOT}/{VARIANT}/runs\\{RUN_ID}",
    f"{VARIANT}/runs/{RUN_ID}",
    f"{RUN}/index.html",
    RUN_ID,
    "",
    "/",
    "  ",
    f"{ROBOT}/{VARIANT}/runs/4612237/1783",
    f"{ROBOT}%2F{VARIANT}/runs/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/runs/46122371%2F783",
    f"{ROBOT}/{VARIANT}/runs/%2e%2e",
    f"{ROBOT}/{VARIANT}/runs/%252e%252e",
    f"{ROBOT}/{VARIANT}/runs/{RUN_ID}%41",
    f"{ROBOT}/{VARIANT}/runs/{RUN_ID[:-1]}\u0663",
    f"{ROBOT}/{VARIANT}/runs/{RUN_ID[:-1]}\uff13",
    f"{ROBOT}\uff0f{VARIANT}/runs/{RUN_ID}",
    f"{ROBOT[:-1]}\u0131/{VARIANT}/runs/{RUN_ID}",
    RUN.replace("unitree-g1", "UNITREE-G1"),
    RUN.replace("stock-mujoco", "Stock-Mujoco"),
    f"{ROBOT}/{VARIANT}/RUNS/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/run/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/evidence/{RUN_ID}",
    f"{ROBOT}/{VARIANT}/{RUN_ID}/{RUN_ID}",
    f" {RUN}",
    f"{RUN} ",
    f"{RUN}\n",
    f"{RUN}\t",
    f"{ROBOT}/{VARIANT}/runs/4612\n2371783",
    f"{RUN}\x00",
    f"~/{RUN}",
    f"-{RUN}",
    f"{RUN};x",
    f"{ROBOT}/{VARIANT}/runs/.hidden",
    f"{ROBOT}/{VARIANT}/runs/a..b",
    f"{ROBOT}/{VARIANT}/runs/{RUN_ID}0",
]


@pytest.mark.parametrize("entry", BAD_ENTRIES, ids=[repr(e) for e in BAD_ENTRIES])
def test_a_listed_entry_that_is_not_one_exact_run_path_is_refused_before_any_write(tmp_path, entry):
    reports = _history(tmp_path)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="--validated-viewer-run"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN, entry])
    assert _digests(reports) == before


@pytest.mark.parametrize("entry", [None, 46122371783, b"x", ["a"]])
def test_a_listed_entry_that_is_not_a_string_is_refused(tmp_path, entry):
    reports = _history(tmp_path)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="--validated-viewer-run"):
        _next(tmp_path, reports, validated_viewer_runs=[entry])
    assert _digests(reports) == before


def test_the_exact_entry_may_be_repeated_and_listed_with_other_runs(tmp_path):
    reports = _history(tmp_path)
    added = _next(tmp_path, reports, validated_viewer_runs=[RUN, RUN])
    assert [p.name for p in added] == ["46122371784"]


def test_the_cli_refuses_a_bad_entry_with_nothing_written(tmp_path):
    reports = _history(tmp_path)
    runs = _incoming(tmp_path, "46122371784", "2026-11-28T08:48:59Z")
    before = _digests(reports)
    for entry in (f"{ROBOT}/{VARIANT}/runs/*", f"{RUN}/", "unitree-g1/stock-mujoco-hallway/runs/9"):
        args = ["site", str(reports), "--runs", str(runs), "--repository", REPOSITORY]
        result = CliRunner().invoke(
            cli, [*args, "--validated-viewer-run", RUN, "--validated-viewer-run", entry]
        )
        assert result.exit_code != 0 and "--validated-viewer-run" in result.output, entry
        assert _digests(reports) == before


def test_the_cli_takes_the_flag_more_than_once(tmp_path):
    reports = _history(tmp_path)
    runs = _incoming(tmp_path, "46122371784", "2026-11-28T08:48:59Z")
    args = ["site", str(reports), "--runs", str(runs), "--repository", REPOSITORY]
    result = CliRunner().invoke(
        cli, [*args, "--validated-viewer-run", RUN, "--validated-viewer-run", RUN]
    )
    assert result.exit_code == 0, result.output


# --- a symlink is not a validated run ------------------------------------------------------


def test_a_symlinked_trusted_viewer_folder_is_not_a_validated_run(tmp_path):
    reports = _history(tmp_path)
    folder = reports / RUN / "trusted-viewer"
    real = tmp_path / "real-trusted-viewer"
    shutil.move(str(folder), str(real))
    folder.symlink_to(real, target_is_directory=True)
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="has no trusted-viewer/ folder"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert _digests(reports) == before


def test_a_trusted_viewer_that_is_a_file_is_not_a_validated_run(tmp_path):
    reports = _history(tmp_path)
    folder = reports / RUN / "trusted-viewer"
    shutil.rmtree(folder)
    folder.write_text("x", encoding="utf-8")
    before = _digests(reports)
    with pytest.raises(_site().SiteError, match="has no trusted-viewer/ folder"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert _digests(reports) == before


@pytest.mark.parametrize("which", ["run", "robot"])
def test_a_symlinked_run_or_robot_folder_is_refused_and_nothing_is_written(tmp_path, which):
    reports = _history(tmp_path)
    target = reports / RUN if which == "run" else reports / ROBOT
    real = tmp_path / f"real-{which}"
    shutil.move(str(target), str(real))
    target.symlink_to(real, target_is_directory=True)
    with pytest.raises(_site().SiteError):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
    assert not (reports / ROBOT / VARIANT / "runs" / "46122371784").exists()


# --- the one frame, and only the frame -----------------------------------------------------


def _swap(old: str, new: str):
    def change(page: str) -> str:
        assert old in page
        return page.replace(old, new, 1)

    return change


FRAME_FAULTS = {
    "attribute order": _swap(
        'sandbox="allow-scripts allow-same-origin" loading="lazy"',
        'loading="lazy" sandbox="allow-scripts allow-same-origin"',
    ),
    "sandbox removed": _swap(' sandbox="allow-scripts allow-same-origin"', ""),
    "sandbox widened": _swap('allow-same-origin"', 'allow-same-origin allow-top-navigation"'),
    "title changed": _swap('title="Recorded replay"', 'title="x"'),
    "srcdoc added": _swap("<iframe title", '<iframe srcdoc="<b>x</b>" title'),
    "onload added": _swap("<iframe title", '<iframe onload="x()" title'),
    "id added": _swap("<iframe title", '<iframe id="a" title'),
    "src ../ inside": _swap("trusted-viewer/viewer.html#", "trusted-viewer/../evidence/x.html#"),
    "src ../ before": _swap('src="trusted-viewer/', 'src="../trusted-viewer/'),
    "src %2e%2e": _swap("trusted-viewer/viewer.html#", "trusted-viewer/%2e%2e/x.html#"),
    "src %2E%2E%2F": _swap("trusted-viewer/viewer.html#", "trusted-viewer/%2E%2E%2Fx.html#"),
    "src double slash": _swap("trusted-viewer/viewer.html#", "trusted-viewer//viewer.html#"),
    "src backslash": _swap("trusted-viewer/viewer.html#", "trusted-viewer\\viewer.html#"),
    "src dot segment": _swap("trusted-viewer/viewer.html#", "trusted-viewer/./viewer.html#"),
    "src dotted name": _swap("trusted-viewer/viewer.html#", "trusted-viewer/a.b.html#"),
    "src hidden file": _swap("trusted-viewer/viewer.html#", "trusted-viewer/.viewer.html#"),
    "src absolute": _swap('src="trusted-viewer/', 'src="/trusted-viewer/'),
    "src https": _swap('src="trusted-viewer/', 'src="https://x.example/trusted-viewer/'),
    "src javascript:": _swap('src="trusted-viewer/', 'src="javascript:alert(1)//trusted-viewer/'),
    "src data:": _swap('src="trusted-viewer/viewer.html#', 'src="data:text/html,<b>x</b>#'),
    "src upper case folder": _swap('src="trusted-viewer/', 'src="TRUSTED-VIEWER/'),
    "src folder prefix only": _swap("trusted-viewer/viewer.html#", "trusted-viewerx/viewer.html#"),
    "src folder name run on": _swap("trusted-viewer/viewer.html#", "trusted-viewerviewer.html#"),
    "src not html": _swap("viewer.html#", "viewer.js#"),
    "src html.exe": _swap("viewer.html#", "viewer.html.exe#"),
    "src htmlx": _swap("viewer.html#", "viewer.htmlx#"),
    "src any char for the dot": _swap("viewer.html#", "viewerxhtml#"),
    "src unicode name": _swap("viewer.html#", "v\u0131ewer.html#"),
    "src fullwidth slash": _swap("trusted-viewer/viewer", "trusted-viewer\uff0fviewer"),
    "no fragment": _swap("viewer.html#", "viewer.html"),
    "query not fragment": _swap("viewer.html#", "viewer.html?"),
    "fragment javascript:": _swap("viewer.html#", "viewer.html#javascript:x=1&amp;"),
    "fragment with a space": _swap("viewer.html#", "viewer.html#a= b&amp;"),
    "fragment with a slash": _swap("viewer.html#", "viewer.html#a=b/c&amp;"),
    "fragment with a semicolon": _swap("viewer.html#", "viewer.html#a=b;c&amp;"),
    "fragment with a colon": _swap("viewer.html#", "viewer.html#a=b:c&amp;"),
    "fragment with a quote char": _swap("viewer.html#", "viewer.html#a='b'&amp;"),
    "fragment with a double quote": _swap("viewer.html#", 'viewer.html#a=b"c&amp;'),
    "fragment value that is a double quote": _swap("viewer.html#", 'viewer.html#a="&amp;'),
    "fragment key with a double quote": _swap("viewer.html#", 'viewer.html#a"b=c&amp;'),
    "fragment with a second hash": _swap("viewer.html#", "viewer.html#a=b#c&amp;"),
    "fragment empty key": _swap("viewer.html#", "viewer.html#=b&amp;"),
    "fragment key without =": _swap("viewer.html#", "viewer.html#abc&amp;"),
    "fragment raw ampersand": _swap("&amp;", "&"),
    "fragment doubled ampersand": _swap("&amp;", "&amp;&amp;"),
    "fragment trailing ampersand": _swap('" style="display', '&amp;" style="display'),
    "style changed": _swap("height:660px", "height:1px"),
    "style fixed position": _swap('max-width:100%">', 'max-width:100%;position:fixed;top:0">'),
    "noscript changed": _swap("Replay needs JavaScript", "Pay now"),
    "tag upper case": _swap("<iframe title", "<IFRAME title"),
    "no frame at all": lambda page: page.replace(_frame(page), ""),
    "frame in a comment instead": lambda page: page.replace(_frame(page), f"<!--{_frame(page)}-->"),
    "second frame": lambda page: page.replace("</body>", _frame(page) + "</body>"),
    "second frame in a comment": lambda page: page.replace(
        "</body>", f"<!--{_frame(page)}--></body>"
    ),
    "plain iframe besides": lambda page: page.replace(
        "</body>", '<iframe src="trusted-viewer/viewer.html"></iframe></body>'
    ),
    "unknown script": _swap("</body>", "<script>alert(1)</script></body>"),
    "script src": _swap("</body>", '<script src="x.js"></script></body>'),
    "img onerror": _swap("</body>", "<img src=x onerror=alert(1)></body>"),
    "javascript link": _swap("</body>", '<a href="javascript:alert(1)">x</a></body>'),
    "embed": _swap("</body>", '<embed src="x"></body>'),
    "form": _swap("</body>", '<form action="https://x.example"></form></body>'),
    "comment": _swap("</body>", "<!-- x --></body>"),
}


@pytest.mark.parametrize("fault", sorted(FRAME_FAULTS))
def test_a_listed_run_still_refuses_anything_but_the_one_exact_frame(tmp_path, fault):
    reports = _history(tmp_path)
    _rewrite(reports, FRAME_FAULTS[fault])
    with pytest.raises(_site().SiteError):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])


def test_the_reporters_frame_markup_is_pinned():
    # The check matches FRAME_START and FRAME_END, so widening either one in the reporter
    # would widen the exception with it. A change here is a trust decision, not a refactor.
    assert FRAME_START == (
        '<iframe title="Recorded replay" sandbox="allow-scripts allow-same-origin" '
        'loading="lazy" src="'
    )
    assert FRAME_END == (
        '" style="display:block;width:100%;height:660px;border:1px solid #bcc;max-width:100%">'
        "</iframe><noscript>Replay needs JavaScript; Recorded data remains available.</noscript>"
    )


def test_the_composed_page_holds_exactly_the_markup_the_check_accepts(tmp_path):
    reports = _history(tmp_path)
    frame = _frame((reports / RUN / "index.html").read_text(encoding="utf-8"))
    assert frame.startswith(FRAME_START) and frame.endswith(FRAME_END)
    assert re.fullmatch(
        re.escape(FRAME_START)
        + r"trusted-viewer/viewer\.html#file=data%2Frecording\.json&amp;sha256=[a-f0-9]{64}&amp;run=[A-Za-z0-9._~%-]+&amp;configuration=[A-Za-z0-9._~%-]+&amp;trial=[1-9][0-9]*"
        + re.escape(FRAME_END),
        frame,
    )


# --- other pages and other runs ------------------------------------------------------------


def test_the_frame_is_not_accepted_in_an_evidence_listing_of_the_listed_run(tmp_path):
    reports = _history(tmp_path)
    run = reports / RUN
    frame = _frame((run / "index.html").read_text(encoding="utf-8"))
    (run / "evidence").mkdir(exist_ok=True)
    (run / "evidence/listing.html").write_text(
        f"<!doctype html><html><body>{frame}</body></html>", encoding="utf-8"
    )
    _site().write_published_checksums(run)
    with pytest.raises(_site().SiteError, match="<iframe> is not allowed"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])


def test_listing_one_run_does_not_exempt_another_decorated_run(tmp_path):
    site = _site()
    reports = _history(tmp_path, decorate=False)
    other = f"{ROBOT}/{VARIANT}/runs/46122371700"
    site.build(
        reports, _incoming(tmp_path, "46122371700", "2026-11-27T08:00:00Z"), repository=REPOSITORY
    )
    # take the composed page and viewer assets of a decorated history and put them on both
    # runs, so both pages hold a frame
    decorated = _history(tmp_path / "second")
    page = (decorated / RUN / "index.html").read_text(encoding="utf-8")
    shutil.copytree(decorated / RUN / "trusted-viewer", reports / RUN / "trusted-viewer")
    (reports / RUN / "index.html").write_text(page, encoding="utf-8")
    shutil.copytree(decorated / RUN / "trusted-viewer", reports / other / "trusted-viewer")
    (reports / other / "index.html").write_text(page, encoding="utf-8")
    site.write_published_checksums(reports / RUN)
    site.write_published_checksums(reports / other)
    with pytest.raises(site.SiteError, match="46122371700/index.html"):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])


# --- a listed run that `site` republishes anyway --------------------------------------------


def _state(reports):
    run = reports / RUN
    folder = run / "trusted-viewer"
    return (
        "<iframe " in (run / "index.html").read_text(encoding="utf-8"),
        sorted(p.relative_to(run).as_posix() for p in folder.rglob("*") if p.is_file())
        if folder.exists()
        else None,
    )


def test_an_entry_for_a_run_whose_evidence_expired_has_no_effect(tmp_path):
    # `site` rewrites the page as a plain one (no frame); the entry changes nothing, listed
    # or not, and the viewer assets stay for the caller to compose again.
    results = []
    for name, entries in (("unlisted", []), ("listed", [RUN])):
        reports = _history(tmp_path / name)
        _next(tmp_path / name, reports, validated_viewer_runs=entries, now="2027-01-01T00:00:00Z")
        assert _site().check_reports_tree(reports, repository=REPOSITORY) == []
        results.append((_state(reports), _digests(reports / RUN)))
    assert results[0] == results[1]
    frame, assets = results[0][0]
    assert frame is False
    assert assets == ["trusted-viewer/data/recording.json", "trusted-viewer/viewer.html"]


def test_an_entry_for_a_run_that_a_same_run_replace_overwrites_has_no_effect(tmp_path):
    results = []
    for name, entries in (("unlisted", []), ("listed", [RUN])):
        reports = _history(tmp_path / name)
        incoming = _incoming(tmp_path / name, RUN_ID, "2026-11-28T05:00:00Z")
        _site().build(
            reports,
            incoming,
            repository=REPOSITORY,
            allow_replace_run_id=RUN_ID,
            validated_viewer_runs=entries,
        )
        results.append((_state(reports), _digests(reports / RUN)))
    assert results[0] == results[1]
    assert results[0][0] == (False, None)


# --- the two helpers that are now public ---------------------------------------------------


def test_checked_report_html_returns_a_clean_page_unchanged_and_refuses_an_iframe(tmp_path):
    site = _site()
    reports = _history(tmp_path, decorate=False)
    page = (reports / RUN / "index.html").read_text(encoding="utf-8")
    assert site.checked_report_html(page, "x") == page
    framed = (_history(tmp_path / "b") / RUN / "index.html").read_text(encoding="utf-8")
    with pytest.raises(site.SiteError, match="^restored page: .*<iframe> is not allowed"):
        site.checked_report_html(framed, "restored page")


def test_checked_report_html_cuts_only_a_marked_script_with_an_unknown_body(tmp_path, capsys):
    # A script that carries the reporter's marker attribute but not the reporter's bytes is
    # cut out with a warning, so a caller must compare the result with its input. Any other
    # script is refused.
    site = _site()
    page = (_history(tmp_path, decorate=False) / RUN / "index.html").read_text(encoding="utf-8")
    marked = page.replace("</body>", "<script data-report-times>alert(1)</script></body>")
    assert site.checked_report_html(marked, "p") == page
    assert "removed a <script> that is not a known reporter script" in capsys.readouterr().err
    with pytest.raises(site.SiteError, match="not one of the reporter's scripts"):
        site.checked_report_html(page.replace("</body>", "<script>x</script></body>"), "p")


def test_checked_report_html_refuses_the_wrong_kind_of_input():
    site = _site()
    for bad in (None, 5, b"<p>x</p>"):
        with pytest.raises((TypeError, AttributeError, site.SiteError)):
            site.checked_report_html(bad, "x")


def test_write_published_checksums_lists_every_other_file_sorted(tmp_path):
    folder = tmp_path / "run"
    (folder / "b" / "c").mkdir(parents=True)
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "b" / "c" / "d.txt").write_text("d", encoding="utf-8")
    (folder / "SHA256SUMS").write_text("stale\n", encoding="utf-8")
    _site().write_published_checksums(folder)
    names = [line.split("  ", 1)[1] for line in (folder / "SHA256SUMS").read_text().splitlines()]
    assert names == ["a.txt", "b/c/d.txt"]
    again = (folder / "SHA256SUMS").read_text(encoding="utf-8")
    _site().write_published_checksums(folder)
    assert (folder / "SHA256SUMS").read_text(encoding="utf-8") == again


def test_write_published_checksums_covers_the_trusted_viewer_files(tmp_path):
    reports = _history(tmp_path)
    sums = (reports / RUN / "SHA256SUMS").read_text(encoding="utf-8")
    assert "  trusted-viewer/viewer.html\n" in sums
    assert "  trusted-viewer/data/recording.json\n" in sums
    assert "SHA256SUMS" not in sums


# --- finding 1: the frame has to be a whole element in the composed panel ------------------

POSITIONS = {
    "inside a start tag": r"<a ",
    "inside an attribute value": r"<a [^>]*href=\"",
    "inside a known script": r"<script[^>]*>",
}


@pytest.mark.parametrize("where", sorted(POSITIONS))
def test_the_frame_bytes_inside_a_tag_a_value_or_a_script_are_not_accepted(tmp_path, where):
    reports = _history(tmp_path)

    def change(page: str) -> str:
        frame = _frame(page)
        plain = page.replace(frame, "")
        at = re.search(POSITIONS[where], plain).end()
        return plain[:at] + frame + plain[at:]

    _rewrite(reports, change)
    with pytest.raises(_site().SiteError):
        _next(tmp_path, reports, validated_viewer_runs=[RUN])
