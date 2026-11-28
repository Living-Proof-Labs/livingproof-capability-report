# SPDX-License-Identifier: Apache-2.0
"""Guards on the moved run-link sanitizer, the fail-closed run.url logic and the post-build check
that mutation testing left unpinned (Vera's check of livingproof-capability-report PR 143).

Each test below fails when the code it names is mutated; none changes behaviour.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import site_fixture
from click.testing import CliRunner
from test_site import ROOT, _make_run_folder

from livingproof_capability_report.cli import report
from livingproof_capability_report.site import assemble as site
from livingproof_capability_report.site.check import check_reports_tree

OWNER = "Living-Proof-Labs/verification-reports-action"
RUN = f"https://github.com/{OWNER}/actions/runs/46115314157"
CALLER = "Living-Proof-Labs/livingproof-unitree-g1"
SITE_PACKAGE = Path(site.__file__).parent


# --- the end of a run address ------------------------------------------------------------


@pytest.mark.parametrize(
    "end",
    [
        "",
        " ",
        "\n",
        "'",
        '"',
        "<",
        ">",
        ")",
        "]",
        ",",
        ".",
        "&quot;",
        "&#x27;",
        "&#39;",
        "&lt;",
        "&gt;",
    ],
)
def test_a_run_address_ends_at_each_closing_character(end: str):
    text = f"see {RUN}{end}" if end in {"", " ", "\n", "."} else f"x{RUN}{end}y"
    if end == ".":
        text += " next"
    assert not site.mentions_actions(text, repository=OWNER)
    assert site.strip_actions_text(text, repository=OWNER) == text
    assert site.run_address_re(OWNER).search(text)


@pytest.mark.parametrize(
    "tail",
    ["/", "/job/2", "?x=1", "#f", ".zip", ".x", ";a=1", ":80", "abc", "-x", "_x", "%2Fjob", "\\x"],
)
def test_a_run_address_followed_by_anything_else_is_a_near_miss(tail: str):
    text = f"<p>{RUN}{tail}</p>"
    assert site.mentions_actions(text, repository=OWNER)
    assert "/actions/" not in site.strip_actions_text(text, repository=OWNER)
    assert not site.is_run_address(RUN + tail, OWNER)


# --- is_run_address and run.url ----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        RUN.replace("https://", "http://"),
        RUN.replace("https://github.com", "HTTPS://GITHUB.COM"),
        RUN.replace("https://github.com", "https://GITHUB.com"),
        RUN.replace("Living-Proof-Labs", "living-proof-labs"),
        RUN.replace("verification-reports-action", "VERIFICATION-REPORTS-ACTION"),
        RUN.replace("/actions/", "/ACTIONS/"),
        RUN + "\n",
        " " + RUN,
        RUN + "/",
        RUN + "?x=1",
        RUN + "#x",
        RUN + "/job/2",
        "https://github.com/other-org/other-repo/actions/runs/46115314157",
        RUN.replace("/actions/runs/46115314157", "/actions/runs/"),
        RUN.replace("/actions/runs/46115314157", "/actions/runs/x"),
        "",
    ],
)
def test_only_the_exact_run_address_of_this_repository_is_accepted(url: str):
    assert not site.is_run_address(url, OWNER)
    problem = site.run_url_problem("a/run.json", {"run": {"url": url}}, OWNER)
    assert problem == "a/run.json run.url is not this repository's run"


def test_the_exact_run_address_of_this_repository_is_accepted():
    assert site.is_run_address(RUN, OWNER)
    assert site.run_url_problem("a/run.json", {"run": {"url": RUN}}, OWNER) is None


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        ([], "run.url is missing"),
        (None, "run.url is missing"),
        ("text", "run.url is missing"),
        ({}, "run.url is missing"),
        ({"run": 5}, "run.url is missing"),
        ({"run": None}, "run.url is missing"),
        ({"run": {}}, "run.url is missing"),
        ({"run": {"url": None}}, "run.url is missing"),
        ({"run": {"url": 5}}, "run.url is not this repository's run"),
        ({"run": {"url": [RUN]}}, "run.url is not this repository's run"),
        ({"run": {"url": {"href": RUN}}}, "run.url is not this repository's run"),
    ],
)
def test_a_malformed_run_record_is_a_run_url_problem(record, problem: str):
    assert site.run_url_problem("a/run.json", record, OWNER) == f"a/run.json {problem}"


def test_a_dot_in_the_repository_name_is_literal():
    caller = "acme/my.repo"
    assert site.is_run_address("https://github.com/acme/my.repo/actions/runs/1", caller)
    assert not site.is_run_address("https://github.com/acme/myXrepo/actions/runs/1", caller)
    other = "<p>https://github.com/acme/myXrepo/actions/runs/1</p>"
    assert site.mentions_actions(other, repository=caller)
    assert "/actions/" not in site.strip_actions_text(other, repository=caller)


@pytest.mark.parametrize("caller", ["a+b/c", "a/b(c)", "a/b|c", "a/b[c]", "a/b$"])
def test_regular_expression_characters_in_the_repository_are_literal(caller: str):
    own = f"https://github.com/{caller}/actions/runs/1"
    assert site.is_run_address(own, caller)
    assert not site.is_run_address("https://github.com/a/b/actions/runs/1", caller)
    assert not site.mentions_actions(f"<p>{own}</p>", repository=caller)


def test_a_set_of_repositories_is_matched_exactly_and_literally():
    callers = {"acme/my.repo", "acme/other"}
    assert site.is_run_address("https://github.com/acme/other/actions/runs/1", callers)
    assert site.is_run_address("https://github.com/acme/my.repo/actions/runs/1", callers)
    assert not site.is_run_address("https://github.com/acme/myXrepo/actions/runs/1", callers)
    assert not site.is_run_address("https://github.com/acme/other/actions/runs/1", set())


@pytest.mark.parametrize("caller", [None, "", set()])
def test_with_no_caller_no_address_is_allowed(caller):
    text = f"<p>{RUN}</p><a href='{RUN}'>CI run</a>"
    assert not site.is_run_address(RUN, caller)
    assert site.mentions_actions(text, repository=caller)
    assert "/actions/" not in site.strip_actions_text(text, repository=caller)
    assert not site.run_address_re(caller).search(RUN)
    assert site.run_url_problem("a/run.json", {"run": {"url": RUN}}, caller)


@pytest.mark.parametrize("caller", [None, ""])
def test_build_refuses_to_run_without_a_caller_and_writes_nothing(tmp_path: Path, caller):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    with pytest.raises(site.SiteError, match="caller repository"):
        site.build(tmp_path / "reports", tmp_path / "in", repository=caller)
    assert not (tmp_path / "reports").exists()


# --- public_page_problems on a tree --------------------------------------------------------


def _tree(tmp_path: Path, pages: dict[str, str], run_jsons: dict[str, object]) -> Path:
    reports = tmp_path / "reports"
    for name, record in run_jsons.items():
        folder = reports / "unitree-g1/stock/runs" / name
        folder.mkdir(parents=True)
        folder.joinpath("run.json").write_text(json.dumps(record), encoding="utf-8")
        folder.joinpath("index.html").write_text(pages.get(name, ""), encoding="utf-8")
    return reports


def _good(run_id: str) -> dict:
    return {"run": {"id": run_id, "url": f"https://github.com/{OWNER}/actions/runs/{run_id}"}}


def test_every_bad_run_json_is_named_not_only_the_first(tmp_path: Path):
    reports = _tree(
        tmp_path,
        {},
        {"1": {"run": {"id": "1"}}, "2": _good("2"), "3": {"run": {"url": "https://x/y"}}},
    )
    problems = site.public_page_problems(reports, repository=OWNER)
    assert problems == [
        "unitree-g1/stock/runs/1/run.json run.url is missing",
        "unitree-g1/stock/runs/3/run.json run.url is not this repository's run",
    ]
    assert site.run_url_problems(reports, repository=OWNER) == problems


def test_an_unreadable_run_json_does_not_hide_a_later_bad_one(tmp_path: Path):
    reports = _tree(tmp_path, {}, {"1": {}, "2": {}, "3": _good("3")})
    (reports / "unitree-g1/stock/runs/1/run.json").write_bytes(b"\xff\xfe not json")
    problems = site.public_page_problems(reports, repository=OWNER)
    assert problems == ["unitree-g1/stock/runs/2/run.json run.url is missing"]


@pytest.mark.parametrize("record", [[], "text", 5, {"run": 5}, {"run": []}, {"run": {"url": 5}}])
def test_a_run_json_of_the_wrong_shape_fails_the_tree_check(tmp_path: Path, record):
    reports = _tree(tmp_path, {}, {"1": record})
    assert site.public_page_problems(reports, repository=OWNER)


@pytest.mark.parametrize(
    "page",
    [
        "<p>https://github.com/living-proof-labs/verification-reports-action/actions/runs/1</p>",
        "<p>HTTPS://GITHUB.COM/o/r/ACTIONS/runs/1</p>",
        "<p>https://github.com/o/r/ACTIONS/runs/1</p>",
        "<a href=https://github.com/o/r/%61ctions/runs/1>x</a>",
        "<A HREF='https://github.com/o/r/%61ctions/runs/1'>x</A>",
        f"<a href={RUN}/job/2>x</a>",
        f"<a href={RUN} class=x>x</a><a href=https://github.com/o/r/&#97;ctions/runs/1>y</a>",
        "<a href='https://github.com/o/r/actions/runs/1'>x</a>",
    ],
)
def test_a_published_page_with_a_foreign_or_case_variant_actions_link_is_a_problem(
    tmp_path: Path, page: str
):
    reports = _tree(tmp_path, {"1": page}, {"1": _good("46115314157")})
    problems = site.public_page_problems(reports, repository=OWNER)
    assert problems == ["unitree-g1/stock/runs/1/index.html links to /actions/"], problems


@pytest.mark.parametrize(
    "page",
    [
        f"<a href={RUN}>x</a>",
        f"<a href={RUN} class=x>x</a>",
        f"<a class=x href={RUN} title=t>x</a>",
        f"<a href='{RUN}'>x</a>",
        f"<A HREF='{RUN}'>x</A>",
        "<a href=evidence/a.json>x</a> <a href=https://example.org/x>y</a>",
        f"<pre>&quot;run&quot;: &quot;{RUN}&quot;</pre>",
    ],
)
def test_a_published_page_with_only_this_repository_run_links_is_clean(tmp_path: Path, page: str):
    reports = _tree(tmp_path, {"1": page}, {"1": _good("46115314157")})
    assert site.public_page_problems(reports, repository=OWNER) == []
    assert site.strip_actions_text(page, repository=OWNER) == page


@pytest.mark.parametrize("word", ["artifact", "Artifacts"])
def test_a_published_page_naming_an_artifact_is_a_problem(tmp_path: Path, word: str):
    reports = _tree(tmp_path, {"1": f"<p>the {word}</p>"}, {"1": _good("46115314157")})
    assert site.public_page_problems(reports, repository=OWNER) == [
        "unitree-g1/stock/runs/1/index.html mentions an artifact"
    ]


# --- encoded /actions/ ----------------------------------------------------------------------


def _layers(count: int) -> str:
    """ "a" percent-encoded `count` times: %61, %2561, %252561, ..."""
    code = "%61"
    for _ in range(count - 1):
        code = code.replace("%", "%25")
    return code


@pytest.mark.parametrize("layers", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("quote", ["'", '"', ""])
def test_an_actions_hidden_by_several_layers_of_encoding_is_unwrapped(layers: int, quote: str):
    href = f"https://github.com/evil/repo/{_layers(layers)}ctions/runs/1"
    raw = f"<p><a href={quote}{href}{quote}>run</a></p>"
    assert site.mentions_actions(raw, repository=OWNER)
    assert site.strip_actions_text(raw, repository=OWNER) == "<p>run</p>"
    record = {"run": {"url": RUN}, "evidence": []}
    page = site.scrub_reporter_html(
        raw, record, trial=False, expired=False, days=7, repository=OWNER
    )
    assert page == "<p>run</p>"


def test_an_unquoted_href_keeps_its_own_end_at_the_first_space_or_bracket():
    kept = f"<a href={RUN} class=x>CI run</a><a href=evidence/a.json>a</a>"
    assert site.strip_actions_text(kept, repository=OWNER) == kept
    hostile = "<a href=https://github.com/o/r/actions/runs/1 class=x>x</a><a href=a.json>y</a>"
    assert site.strip_actions_text(hostile, repository=OWNER) == "x<a href=a.json>y</a>"


def test_an_upper_case_anchor_is_read_like_a_lower_case_one():
    raw = "<A HREF='https://github.com/o/r/%61ctions/runs/1'>x</A><A HREF=https://github.com/o/r/%61ctions/runs/2>y</A>"
    assert site.strip_actions_text(raw, repository=OWNER) == "xy"


# --- the hostile URLs of the PR 84 recheck, as anchor (quoted and unquoted) and as text -------

_ID = "46115314157"
_HOSTILE = [
    f"https://github.com/{OWNER}/actions/runs/78/job/2",
    "https://github.com/evil/repo/actions/runs/1",
    "https://github.com/Evil-Labs/verification-reports-action/actions/runs/1",
    f"https://github.com/living-proof-labs/verification-reports-action/actions/runs/{_ID}",
    f"https://github.com/Living-Proof-Labs/VERIFICATION-REPORTS-ACTION/actions/runs/{_ID}",
    f"https://github.com/LIVING-PROOF-LABS/verification-reports-action/actions/runs/{_ID}",
    f"{RUN}/job/123",
    f"{RUN}/attempts/2",
    f"{RUN}/artifacts/99",
    f"{RUN}/",
    f"{RUN}?pr=1",
    f"{RUN}#summary",
    f"{RUN}.zip",
    f"{RUN};a=1",
    f"{RUN}:80",
    f"{RUN}abc",
    f"{RUN}\\attempts\\2",
    f"{RUN}&amp;x=1",
    f"{RUN}&#47;job&#47;2",
    f"{RUN}%2Fattempts%2F2",
    f"https://github.com/{OWNER}/actions/workflows/verify.yml",
    f"https://github.com/{OWNER}/ACTIONS/runs/{_ID}",
    f"https://github.com/{OWNER}/%61ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&#97;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&#x61;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/act%69ons/runs/{_ID}",
    f"https://github.com/{OWNER}/%2561ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&amp;#97;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&amp;#x61;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&amp;amp;#97;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/%26%2397;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/%2526%252397;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/&#37;61ctions/runs/{_ID}",
    f"https://github.com/{OWNER}/%26%23x61;ctions/runs/{_ID}",
    f"https://github.com/{OWNER}%2Factions%2Fruns%2F{_ID}",
    f"https://github.com/{OWNER}%252Factions%252Fruns%252F{_ID}",
    f"https://github.com/living-proof-labs/verification-reports-action/&#97;ctions/runs/{_ID}",
    "https://github.com.evil.example/o/r/actions/runs/1",
    "https://evilgithub.com/o/r/actions/runs/1",
    "https://github.com@evil.example/o/r/actions/runs/1",
    f"https://evil.example/?u={RUN}",
    "http://github.com/o/r/actions/runs/1",
    f"http://github.com/{OWNER}/actions/runs/{_ID}",
    "HTTPS://GITHUB.COM/o/r/actions/runs/1",
    f"HTTPS://GITHUB.COM/{OWNER}/actions/runs/{_ID}",
    "https://api.github.com/repos/o/r/actions/runs/1",
    "https://api.github.com/repos/o/r/actions/artifacts/1/zip",
    "javascript:alert(1)//actions/runs/1",
    "javascript:alert(1)//%61ctions/runs/1",
    "//github.com/o/r/actions/runs/1",
    f"https://x@github.com/{OWNER}/actions/runs/{_ID}",
    f"https://github.com:443/{OWNER}/actions/runs/{_ID}",
    f"https://www.github.com/{OWNER}/actions/runs/{_ID}",
]


_QUOTED_HOSTILE = [
    (url, quote)
    for url in _HOSTILE
    for quote in ("'", '"', "")
    if quote or not re.search(r"[\s'\"<>]", url)
]


@pytest.mark.parametrize(("url", "quote"), _QUOTED_HOSTILE)
def test_a_hostile_run_link_is_never_kept_as_a_link(url: str, quote: str):
    raw = f"<p>ok <a href={quote}{url}{quote}>HOSTILE</a> end</p>"
    cleaned = site.strip_actions_text(raw, repository=OWNER)
    assert "HOSTILE" in cleaned and "<a" not in cleaned
    record = {"run": {"url": RUN}, "evidence": []}
    page = site.scrub_reporter_html(
        raw, record, trial=False, expired=False, days=7, repository=OWNER
    )
    assert "HOSTILE" in page and "<a" not in page
    assert site.mentions_actions(raw, repository=OWNER)
    assert not site.mentions_actions(cleaned, repository=OWNER)


_TEXT_HOSTILE = [
    url
    for url in _HOSTILE
    if "/actions/" in url.lower()
    and "%" not in url
    and url.lower().startswith("https://github.com/")
]


@pytest.mark.parametrize("url", _TEXT_HOSTILE)
def test_a_hostile_run_address_in_text_is_removed(url: str):
    raw = f"<p>see {url} end</p>"
    cleaned = site.strip_actions_text(raw, repository=OWNER)
    if url.startswith("HTTPS://") and f"/{OWNER}/" in url:
        # An upper-case scheme and host on this repository's own address is not stripped,
        # but it is still reported, so the build refuses the page (fail closed).
        assert site.mentions_actions(cleaned, repository=OWNER)
        return
    assert "/actions/" not in cleaned.lower()
    assert not site.mentions_actions(cleaned, repository=OWNER)


# --- the moved post-build check ----------------------------------------------------------------


def _built(tmp_path: Path) -> Path:
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    reports = tmp_path / "reports"
    site.build(reports, tmp_path / "in", repository=CALLER)
    assert check_reports_tree(reports, repository=CALLER) == []
    return reports


def _first_run(reports: Path) -> Path:
    return sorted(reports.glob("*/*/runs/*"))[0]


def test_the_check_reports_a_missing_index_and_marker(tmp_path: Path):
    reports = _built(tmp_path)
    (reports / "index.html").unlink()
    (reports / "site.json").unlink()
    issues = check_reports_tree(reports, repository=CALLER)
    assert "index.html missing" in issues and "site.json missing" in issues


@pytest.mark.parametrize("needle", ["livingproof-verification/", "Earlier history"])
def test_the_check_refuses_retired_wording_on_the_index(tmp_path: Path, needle: str):
    reports = _built(tmp_path)
    index = reports / "index.html"
    index.write_text(index.read_text(encoding="utf-8") + needle, encoding="utf-8")
    assert f"index.html still contains {needle!r}" in check_reports_tree(reports, repository=CALLER)


def test_the_check_reports_a_broken_relative_link(tmp_path: Path):
    reports = _built(tmp_path)
    index = reports / "index.html"
    index.write_text(index.read_text(encoding="utf-8") + "<a href='gone/index.html'>x</a>")
    assert "index.html: broken link gone/index.html" in check_reports_tree(
        reports, repository=CALLER
    )


def test_the_check_reports_a_root_relative_link(tmp_path: Path):
    reports = _built(tmp_path)
    index = reports / "index.html"
    index.write_text(index.read_text(encoding="utf-8") + "<a href='/x/y'>x</a>")
    assert "index.html: unexpected root-relative link /x/y" in check_reports_tree(
        reports, repository=CALLER
    )


def test_the_check_ignores_absolute_and_protocol_relative_links(tmp_path: Path):
    reports = _built(tmp_path)
    index = reports / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8")
        + "<a href='https://example.org/x'>x</a><a href='//example.org/y'>y</a>"
        "<a href='mailto:a@b.c'>z</a>"
    )
    assert check_reports_tree(reports, repository=CALLER) == []


def test_the_check_reports_a_checksum_mismatch_and_a_file_set_mismatch(tmp_path: Path):
    reports = _built(tmp_path)
    run = _first_run(reports)
    relative = run.relative_to(reports).as_posix()
    (run / "report.txt").write_text("changed", encoding="utf-8")
    assert f"{relative}/report.txt: sha256 mismatch" in check_reports_tree(
        reports, repository=CALLER
    )
    (run / "extra.txt").write_text("x", encoding="utf-8")
    issues = check_reports_tree(reports, repository=CALLER)
    assert any(item.startswith(f"{relative}: SHA256SUMS file set mismatch") for item in issues)
    (run / "SHA256SUMS").unlink()
    assert f"{relative}: missing SHA256SUMS" in check_reports_tree(reports, repository=CALLER)


def test_the_check_reports_a_foreign_actions_link_and_a_foreign_run_url(tmp_path: Path):
    reports = _built(tmp_path)
    run = _first_run(reports)
    relative = run.relative_to(reports).as_posix()
    index = reports / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8")
        + "<a href='https://github.com/evil/repo/actions/runs/1'>x</a>"
    )
    assert "index.html links to /actions/" in check_reports_tree(reports, repository=CALLER)
    stored = json.loads((run / "run.json").read_text(encoding="utf-8"))
    stored["run"]["url"] = "https://github.com/evil/repo/actions/runs/1"
    (run / "run.json").write_text(json.dumps(stored), encoding="utf-8")
    issues = check_reports_tree(reports, repository=CALLER)
    assert f"{relative}/run.json run.url is not this repository's run" in issues


def test_the_check_without_a_caller_rejects_every_run_url(tmp_path: Path):
    reports = _built(tmp_path)
    issues = check_reports_tree(reports)
    assert any("run.url is not this repository's run" in item for item in issues)
    assert any(item.endswith("links to /actions/") for item in issues)


# --- the run.url message (L4) -------------------------------------------------------------------


def test_the_run_url_message_names_the_caller_each_run_json_and_the_way_out(tmp_path: Path):
    _make_run_folder(tmp_path / "in", "a", run_id="100", caller="other-org/other-repo")
    _make_run_folder(tmp_path / "in", "b", run_id="200", caller="other-org/other-repo")
    with pytest.raises(site.SiteError) as error:
        site.build(tmp_path / "reports", tmp_path / "in", repository=OWNER)
    message = str(error.value)
    assert message.startswith(f"run.url must be a run of this repository ({OWNER}): ")
    assert message.count("run.json run.url is not this repository's run") == 2
    assert "runs/100/run.json" in message and "runs/200/run.json" in message
    assert message.endswith(". Drop that run with --exclude-run, or start the history again.")
    assert "Actions links or artifact wording" not in message


# --- the page-level guard (second line of defence) -----------------------------------------------

_REPORTER_PAGE = (ROOT / "tests/fixtures/reporter/report-v3.15.4.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "hostile",
    [
        "<p>https://github.com/o/r/acartifacttions/runs/1</p>",
        "<p><a href='https://github.com/o/r/acartifacttions/runs/1'>x</a></p>",
        "<p><a href='https://github.com/o/r/%61cartifacttions/runs/1'>x</a></p>",
    ],
)
def test_deleting_the_word_artifact_cannot_assemble_an_actions_link(tmp_path: Path, hostile: str):
    page = _REPORTER_PAGE.replace("</body>", hostile + "</body>", 1)
    assert hostile in page
    _make_run_folder(tmp_path / "in", "hallway", run_id="100", html_override=page, caller=OWNER)
    with pytest.raises(site.SiteError, match="public page still names an artifact or links to"):
        site.build(tmp_path / "reports", tmp_path / "in", repository=OWNER)


# --- evidence links in report.json ---------------------------------------------------------------


def test_publish_evidence_links_keeps_only_this_repository_run_and_https_non_actions_urls():
    stored = {
        "run": "https://github.com/evil/repo/actions/runs/1",
        "links": [
            {"label": "mine", "kind": "note", "url": RUN},
            {
                "label": "theirs",
                "kind": "note",
                "url": "https://github.com/evil/repo/actions/runs/1",
            },
            {"label": "plain", "kind": "note", "url": "http://example.org/x"},
            {"label": "ok", "kind": "note", "url": "https://example.org/x"},
            {"label": "noturl", "kind": "note"},
        ],
    }
    document = {"evidence_links": json.loads(json.dumps(stored))}
    assert site.publish_evidence_links(document, {"links": []}, repository=OWNER)
    public = document["evidence_links"]
    assert "run" not in public
    assert [item["label"] for item in public["links"]] == ["mine", "ok"]
    own = {"evidence_links": {"run": RUN, "links": []}}
    site.publish_evidence_links(own, {"links": [{"label": "n", "path": "p"}]}, repository=OWNER)
    assert own["evidence_links"] == {"run": RUN, "links": [{"label": "n", "path": "p"}]}


@pytest.mark.parametrize(
    "url",
    ["https://example.org/artifacts/1", "https://example.org/x?artifact=1", "ARTIFACT"],
)
def test_a_report_link_that_names_an_artifact_loses_its_url(url: str):
    document = {"evidence_links": {"links": [{"label": "x", "kind": "note", "url": url}]}}
    assert site.strip_actions_links(document, repository=OWNER)
    assert "url" not in document["evidence_links"]["links"][0]


def test_a_report_link_that_is_not_text_is_left_alone():
    document = {"evidence_links": {"run": 5, "links": [{"label": "x", "url": 7}]}}
    assert not site.strip_actions_links(document, repository=OWNER)
    assert document["evidence_links"] == {"run": 5, "links": [{"label": "x", "url": 7}]}


# --- the command ----------------------------------------------------------------------------------


def _site(*args: str):
    return CliRunner().invoke(report, ["site", *args], catch_exceptions=False)


def test_the_site_command_passes_allow_replace_run_id_through(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    reports = str(tmp_path / "reports")
    args = [reports, "--runs", str(tmp_path / "in"), "--repository", CALLER]
    assert _site(*args).exit_code == 0
    again = _site(*args)
    assert again.exit_code == 1 and "already published in history and is immutable" in again.output
    assert _site(*args, "--allow-replace-run-id", "100").exit_code == 0


def test_the_site_command_refuses_a_foreign_run_url_with_the_run_url_message(tmp_path: Path):
    _make_run_folder(tmp_path / "in", "a", run_id="100", caller="other-org/other-repo")
    result = _site(str(tmp_path / "reports"), "--runs", str(tmp_path / "in"), "--repository", OWNER)
    assert result.exit_code == 1
    assert f"run.url must be a run of this repository ({OWNER})" in result.output
    assert "Actions links or artifact wording" not in result.output


def test_the_site_command_needs_a_caller(tmp_path: Path):
    site_fixture.write(tmp_path / "in", run_id="100", created="2026-11-20T06:00:00Z")
    result = CliRunner().invoke(
        report,
        ["site", str(tmp_path / "reports"), "--runs", str(tmp_path / "in")],
        env={"GITHUB_REPOSITORY": ""},
    )
    assert (
        result.exit_code == 2 and "--repository (or GITHUB_REPOSITORY) is required" in result.output
    )
    assert not (tmp_path / "reports").exists()


# --- dead code (L3) ----------------------------------------------------------------------------------


def _unused_functions(sources: dict[str, str], elsewhere: str) -> list[str]:
    """Top-level functions that nothing but their own definition mentions."""
    everything = elsewhere + "\n".join(sources.values())
    unused = []
    for name, text in sources.items():
        for node in ast.parse(text).body:
            if isinstance(node, ast.FunctionDef):
                mentions = len(re.findall(rf"\b{re.escape(node.name)}\b", everything))
                definitions = len(re.findall(rf"\bdef {re.escape(node.name)}\b", everything))
                if mentions - definitions < 1:
                    unused.append(f"{name}:{node.name}")
    return unused


def test_the_unused_function_check_can_fail():
    sources = {
        "a.py": "def used():\n    return 1\n\n\ndef dead():\n    return used()\n",
        "b.py": "def _private_dead():\n    pass\n",
    }
    assert _unused_functions(sources, "") == ["a.py:dead", "b.py:_private_dead"]
    assert _unused_functions(sources, "dead(); _private_dead()") == []


def test_no_top_level_function_in_the_site_package_is_unused():
    sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(SITE_PACKAGE.glob("*.py"))}
    elsewhere = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(
            [*(ROOT / "tests").glob("*.py"), ROOT / "src/livingproof_capability_report/cli.py"]
        )
        if p != Path(__file__)
    )
    assert _unused_functions(sources, elsewhere) == []


@pytest.mark.parametrize(
    "url",
    [
        RUN.replace("https://", "http://"),
        RUN.replace("https://github.com", "HTTPS://GITHUB.COM"),
        RUN.replace("https://github.com", "https://GITHUB.com"),
        RUN.replace("https://github.com", "https://Github.com"),
        RUN.replace("Living-Proof-Labs", "living-proof-labs"),
    ],
)
def test_a_text_address_that_is_not_exactly_this_repository_run_page_is_reported(url: str):
    assert site.mentions_actions(f"<p>{url}</p>", repository=OWNER)
    assert not site.run_address_re(OWNER).search(url)
