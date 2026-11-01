"""Bundle 1.1.0: render the verifier's stored decisions and run assessments, grade nothing."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from livingproof_capability_report import assessed
from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import digest, grade, load_bundle, render
from test_hallway import _links, bundle

POLICY = {"id": "all-required-v1", "version": "1.0.0"}
CONFIGS = [
    "unitree-g1-stock",
    "unitree-g1-playground",
    "unitree-go1-playground",
    "booster-t1-stock",
    "booster-t1-playground",
]


def as_verifier_bundle(manifest, report):
    """Rewrite a 1.0.0 bundle as capability-verifier 1.1.0 writes it, from stored values."""
    data = json.loads(manifest.read_text())
    by_id = {d["result_id"]: d for d in report["decisions"]}
    decisions = []
    for r in data["results"]:
        d = by_id[r["id"]]
        stored = {
            "status": d["status"],
            "reason": d["reason"],
            "failures": d.get("failures", []),
            "assessor_types": d.get("assessor_types", []),
        }
        r["decision"] = dict(stored, policy=POLICY)
        decisions.append(dict(result_id=r["id"], **stored))
    runs = []
    for s in report.get("summaries", []):
        run = {k: v for k, v in s.items() if k != "wilson95"}
        run["interval"] = {
            "method": "wilson",
            "level": 0.95,
            "lower": s["wilson95"][0],
            "upper": s["wilson95"][1],
        }
        run["rationale"] = f"{s['k']}/{s['n']} PASS, needs {s['required_passes']}"
        runs.append(run)
    data["schema_version"] = "1.1.0"
    data["assessment"] = {
        "format": assessed.FORMAT,
        "policy": POLICY,
        "aggregation": {"id": "k-of-n-wilson95", "version": "1.0.0"},
        "decisions": decisions,
        "runs": runs,
    }
    manifest.write_text(json.dumps(data, indent=2))
    return manifest


def without_bundle(report):
    return {k: v for k, v in report.items() if k not in ("source_bundle", "source_bundle_sha256")}


@pytest.fixture
def pair(tmp_path):
    manifest = bundle(tmp_path)
    graded = grade(load_bundle(manifest))
    return graded, as_verifier_bundle(manifest, graded)


def test_render_matches_what_grade_computed(pair):
    graded, manifest = pair
    stored = assessed.report_from_bundle(load_bundle(manifest))
    assert without_bundle(stored) == without_bundle(graded)
    assert stored["source_bundle_sha256"] == digest(stored["source_bundle"])
    assert stored["summaries"][0]["wilson95"] == graded["summaries"][0]["wilson95"]
    assert render(stored, "markdown") == render(graded, "markdown")
    assert render(json.loads(render(stored, "json")), "markdown") == render(graded, "markdown")


def test_render_does_not_regrade(pair):
    """A stored value is shown as stored, even when grade would compute another."""
    _, manifest = pair
    data = json.loads(manifest.read_text())
    data["assessment"]["runs"][0]["grade"] = "PASS"
    data["assessment"]["runs"][0]["k"] = 18
    manifest.write_text(json.dumps(data))
    stored = assessed.report_from_bundle(load_bundle(manifest))
    assert (stored["summaries"][0]["grade"], stored["summaries"][0]["k"]) == ("PASS", 18)


def test_grade_refuses_a_bundle_carrying_decisions(pair):
    _, manifest = pair
    with pytest.raises(ValueError, match="never regrade"):
        grade(load_bundle(manifest))


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
    (tmp_path / passing["evidence"][0]["path"]).write_text("changed")
    with pytest.raises(ValueError, match=f"result '{passing['id']}' is stored as PASS"):
        assessed.report_from_bundle(load_bundle(manifest))


def test_cli_renders_a_bundle_and_keeps_evidence_links(pair, tmp_path):
    graded, manifest = pair
    links = tmp_path / "links.json"
    links.write_text(json.dumps(_links()))
    runner = CliRunner()
    out = runner.invoke(
        cli, ["render", str(manifest), "--format", "markdown", "--evidence-links", str(links)]
    )
    assert out.exit_code == 0, out.output
    (tmp_path / "again").mkdir()
    with_links = grade(load_bundle(bundle(tmp_path / "again")), evidence_links=[_links()])
    assert out.output == render(with_links, "markdown")
    report_file = tmp_path / "report.json"
    out = runner.invoke(cli, ["render", str(manifest), "--format", "json", "-o", str(report_file)])
    assert out.exit_code == 0, out.output
    assert without_bundle(json.loads(report_file.read_text())) == without_bundle(graded)
    rerender = runner.invoke(cli, ["render", str(report_file), "--format", "markdown"])
    assert rerender.output == render(graded, "markdown")
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
