"""Bundle 1.1.0: render the verifier's stored decisions and run assessments, grade nothing."""

import hashlib
from html import escape as html_escape
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report import assessed
from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import digest, load_bundle, render, require_decisions
from test_hallway import EXPECTED, _links, example

CONFIGS = [
    "unitree-g1-stock",
    "unitree-g1-playground",
    "unitree-go1-playground",
    "booster-t1-stock",
    "booster-t1-playground",
]


def without_bundle(report):
    return {k: v for k, v in report.items() if k not in ("source_bundle", "source_bundle_sha256")}


@pytest.fixture
def pair(tmp_path):
    """The frozen report (computed by the grade command before #30 removed it) and the 1.1.0 bundle."""
    return json.loads((EXPECTED / "report-without-bundle.json").read_text()), example(tmp_path)


def test_render_matches_the_frozen_report(pair):
    frozen, manifest = pair
    stored = assessed.report_from_bundle(load_bundle(manifest))
    assert without_bundle(stored) == frozen
    assert stored["source_bundle_sha256"] == digest(stored["source_bundle"])
    md = (EXPECTED / "report.md").read_text()
    assert render(stored, "markdown") == md
    assert render(json.loads(render(stored, "json")), "markdown") == md


def test_render_does_not_regrade(pair):
    """A stored value is shown as stored, even when the evidence would say otherwise."""
    _, manifest = pair
    data = json.loads(manifest.read_text())
    data["assessment"]["runs"][0]["grade"] = "PASS"
    data["assessment"]["runs"][0]["k"] = 18
    manifest.write_text(json.dumps(data))
    stored = assessed.report_from_bundle(load_bundle(manifest))
    assert (stored["summaries"][0]["grade"], stored["summaries"][0]["k"]) == ("PASS", 18)


def test_bundle_100_is_refused_with_a_pointer_to_the_verifier(pair, tmp_path):
    """Reporter #30: a bundle without decisions is not graded here, and nothing is written."""
    _, manifest = pair
    data = json.loads(manifest.read_text())
    data["schema_version"] = "1.0.0"
    data.pop("assessment")
    for r in data["results"]:
        r.pop("decision")
    manifest.write_text(json.dumps(data))
    assert CliRunner().invoke(cli, ["validate", str(manifest)]).exit_code == 0
    with pytest.raises(ValueError, match="this reporter does not grade"):
        require_decisions(load_bundle(manifest))
    output = tmp_path / "report.md"
    for fmt in ("markdown", "json", "table"):
        out = CliRunner().invoke(cli, ["render", str(manifest), "--format", fmt, "-o", str(output)])
        assert out.exit_code != 0
        assert "Bundle 1.0.0 has no decisions to render" in out.output
        assert "capability-verifier" in out.output and "bundle 1.1.0" in out.output
        assert "Traceback" not in out.output and not output.exists()


def test_grade_command_is_gone():
    result = CliRunner().invoke(cli, ["grade", "--help"])
    assert result.exit_code != 0 and "No such command 'grade'" in result.output


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda d: d["results"][2].pop("decision"),
            r"result '.+' is missing required field 'decision'",
        ),
        (
            lambda d: d["results"][2]["decision"].pop("status"),
            r"result '.+' decision is missing required field 'status'",
        ),
        (
            lambda d: d["results"][2]["decision"].pop("reason"),
            r"decision is missing required field 'reason'",
        ),
        (
            lambda d: d["results"][2]["decision"].pop("failures"),
            r"decision is missing required field 'failures'",
        ),
        (
            lambda d: d["results"][2]["decision"].pop("policy"),
            r"decision is missing required field 'policy'",
        ),
        (lambda d: d["results"][2]["decision"].update(status="MAYBE"), r"not a known status"),
        (lambda d: d.pop("assessment"), r"bundle is missing required field 'assessment'"),
        (
            lambda d: d["assessment"].pop("runs"),
            r"bundle assessment is missing required field 'runs'",
        ),
        (
            lambda d: d["assessment"]["runs"][0].pop("grade"),
            r"assessment run 0 is missing required field 'grade'",
        ),
        (
            lambda d: d["assessment"]["runs"][0]["interval"].pop("lower"),
            r"run 0 interval is missing required field 'lower'",
        ),
        (lambda d: d["assessment"]["runs"][0]["interval"].update(level=0.9), r"Wilson 95%"),
        (
            lambda d: d["assessment"]["decisions"].pop(2),
            r"assessment decisions are missing result '.+'",
        ),
        (
            lambda d: d["assessment"]["decisions"][2].update(status="PASS", reason="x"),
            r"decision differs",
        ),
        (lambda d: d["assessment"].update(format="other/1"), r"assessment format"),
    ],
)
def test_missing_or_wrong_field_fails_loudly(pair, change, message):
    _, manifest = pair
    data = json.loads(manifest.read_text())
    change(data)
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        assessed.report_from_bundle(load_bundle(manifest))
    result = CliRunner().invoke(cli, ["render", str(manifest), "--format", "markdown"])
    assert result.exit_code != 0 and "Bundle 1.1.0" in result.output


def test_stored_pass_with_changed_evidence_is_refused(pair, tmp_path):
    _, manifest = pair
    data = json.loads(manifest.read_text())
    passing = next(r for r in data["results"] if r["decision"]["status"] == "PASS")
    (manifest.parent / passing["evidence"][0]["path"]).write_text("changed")
    with pytest.raises(ValueError, match=f"result '{passing['id']}' is stored as PASS"):
        assessed.report_from_bundle(load_bundle(manifest))


def test_cli_renders_a_bundle_and_keeps_evidence_links(pair, tmp_path):
    frozen, manifest = pair
    links = tmp_path / "links.json"
    links.write_text(json.dumps(_links()))
    runner = CliRunner()
    out = runner.invoke(
        cli, ["render", str(manifest), "--format", "markdown", "--evidence-links", str(links)]
    )
    assert out.exit_code == 0, out.output
    assert out.output == (EXPECTED / "report-with-links.md").read_text()
    report_file = tmp_path / "report.json"
    out = runner.invoke(cli, ["render", str(manifest), "--format", "json", "-o", str(report_file)])
    assert out.exit_code == 0, out.output
    assert without_bundle(json.loads(report_file.read_text())) == frozen
    rerender = runner.invoke(cli, ["render", str(report_file), "--format", "markdown"])
    assert rerender.output == (EXPECTED / "report.md").read_text()
    refused = runner.invoke(cli, ["render", str(report_file), "--evidence-links", str(links)])
    assert refused.exit_code != 0 and "bundle 1.1.0 manifest only" in refused.output


GOLDEN = os.environ.get("LIVINGPROOF_GOLDEN")
BUNDLES = os.environ.get("LIVINGPROOF_GOLDEN_BUNDLES")
sha = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731


@pytest.mark.skipif(
    not (GOLDEN and BUNDLES),
    reason="set LIVINGPROOF_GOLDEN (reports from 1.10.0) and LIVINGPROOF_GOLDEN_BUNDLES (1.1.0 bundles)",
)
def test_golden_reports_are_byte_identical(tmp_path):
    """report.md and the PR comment are sha256-identical to the 1.10.0 golden files.

    report.json embeds the bundle it came from, so it can only differ there: every other
    key is byte-identical, and the bundle is the 1.0.0 bundle plus the 1.1.0 fields.
    """
    runner = CliRunner()
    golden, bundles = Path(GOLDEN), Path(BUNDLES)
    for config in CONFIGS:
        (tmp_path / config).mkdir()
        manifest = bundles / config / "bundle/manifest.json"
        for fmt, name in (("json", "report.json"), ("markdown", "report.md")):
            out = runner.invoke(
                cli, ["render", str(manifest), "--format", fmt, "-o", str(tmp_path / config / name)]
            )
            assert out.exit_code == 0, out.output
        md = (tmp_path / config / "report.md").read_bytes()
        assert sha(md) == sha((golden / config / "report.md").read_bytes()), config
        mine = json.loads((tmp_path / config / "report.json").read_text())
        theirs = json.loads((golden / config / "report.json").read_text())
        assert list(mine) == list(theirs)
        assert json.dumps(without_bundle(mine), indent=2) == json.dumps(
            without_bundle(theirs), indent=2
        )
        source = mine["source_bundle"]
        source.pop("assessment")
        source["schema_version"] = "1.0.0"
        for r in source["results"]:
            r.pop("decision")
        source["producer"]["commit"] = theirs["source_bundle"]["producer"]["commit"]
        assert source == theirs["source_bundle"], config
    empty = tmp_path / "comments.json"
    empty.write_text("[]")
    for robot in ("unitree-g1", "unitree-go1", "booster-t1"):
        reports = sorted(str(p) for p in tmp_path.glob(f"{robot}-*/report.md"))
        out = runner.invoke(
            cli,
            [
                "comment",
                "--repo",
                "Living-Proof-Labs/example",
                "--pr",
                "1",
                "--dry-run",
                "--comments",
                str(empty),
                *reports,
            ],
        )
        assert out.exit_code == 0, out.output
        expected = (golden / f"comment-{robot}.md").read_bytes()
        assert sha(out.output.encode()) == sha(expected), robot


def _html_summary(html):
    """The HTML before the trial table, and before the collapsed full report."""
    assert html.index("<section id='summary'>") < html.index("<table>") < html.index("<details>")
    assert "<details open" not in html
    return html[html.index("<section id='summary'>") : html.index("<table>")]


def test_html_shows_the_stored_run_summary_above_the_trials(pair):
    """Reporter #23: a robot FAIL report is understandable with <details> collapsed."""
    _, manifest = pair
    stored = assessed.report_from_bundle(load_bundle(manifest))
    html = render(stored, "html")
    top = _html_summary(html)
    s = stored["summaries"][0]
    for text in (
        "unitree-g1/stock@1.1.0",
        f"<dd>{s['run_id']}</dd>",
        "<dt>Overall status</dt><dd>FAIL</dd>",
        "<dt>Observed</dt><dd>12/20 PASS</dd>",
        "<dt>Threshold</dt><dd>18/20 PASS required</dd>",
        "<dt>Policy</dt><dd>all-required-v1@1.0.0</dd>",
        "<dt>Aggregation</dt><dd>k-of-n-wilson95@1.0.0</dd>",
        "<dt>Assessed by</dt><dd>capability-verifier@",
    ):
        assert text in top, text
    # The lossless JSON is unchanged, and still only inside <details>.
    assert render(json.loads(render(stored, "json")), "json") == render(stored, "json")
    full = html[html.index("<details>") :]
    assert html_escape(render(stored, "json").rstrip("\n")) in full


def test_html_summary_shows_stored_values_without_regrading(pair):
    _, manifest = pair
    data = json.loads(manifest.read_text())
    data["assessment"]["runs"][0]["grade"] = "PASS"  # stored value wins, even if inconsistent
    manifest.write_text(json.dumps(data))
    top = _html_summary(render(assessed.report_from_bundle(load_bundle(manifest)), "html"))
    assert "<dt>Overall status</dt><dd>PASS</dd>" in top
    assert "<dt>Observed</dt><dd>12/20 PASS</dd>" in top


def test_html_summary_escapes_every_value(pair):
    _, manifest = pair
    stored = assessed.report_from_bundle(load_bundle(manifest))
    evil = "<script>alert('x')</script>&\""
    stored["summaries"][0]["run_id"] = evil
    stored["summaries"][0]["system"] = {"id": evil, "version": "1"}
    stored["summaries"][0]["grade"] = evil
    stored["policy"] = evil
    top = _html_summary(render(stored, "html"))
    assert "<script>" not in top and "alert('x')" not in top
    safe = html_escape(evil)
    assert f"<dt>Run</dt><dd>{safe}</dd>" in top
    assert f"<dt>Overall status</dt><dd>{safe}</dd>" in top
    assert f"<dt>Policy</dt><dd>{safe}</dd>" in top
    assert f"<dt>Robot</dt><dd>{safe}@1</dd>" in top


def test_html_summary_leaves_out_absent_fields(pair):
    _, manifest = pair
    stored = assessed.report_from_bundle(load_bundle(manifest))
    del stored["summaries"]
    top = _html_summary(render(stored, "html"))
    assert "Observed" not in top and "Threshold" not in top and "Overall status" not in top
    assert "<dt>Policy</dt><dd>all-required-v1@1.0.0</dd>" in top
