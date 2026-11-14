"""The reporter reads any scenario. Stored hallway bundles stay readable.

The v3.7.0 goldens are the render of the real robot bundles at that tag, which
is current main. The corner description is not a released scenario:
robot-capability-specs v2.2.1 has no walk-corner description.json, so the
fixture is built to validate against that tag's scenario-description schema.
"""

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator

import livingproof_capability_report
from livingproof_capability_report.assessed import report_from_bundle
from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.core import load_bundle, markdown_filename, render
from livingproof_capability_report.legacy_evidence import kind
from test_hallway import example
from test_sections import bundle, report, top

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(livingproof_capability_report.__file__).parent
GOLDEN = Path(__file__).parent / "fixtures/v3.7.0"
SPEC = Path(__file__).parent / "fixtures/scenario-description"
SCHEMA_SHA256 = "be989f8ae0cb843f045dbe6f0ef9325cd261a24d7974fdef0970b751c1ea1df4"
REMOVED_LABEL = "<dt>Fits the hallway</dt>"
# Stored check name -> evaluator id on the schema-built description.
_CORNER_CHECKS = {
    "hallway-exit-reached": "reaches-exit",
    "hallway-lateral-limit": "turns-the-corner",
    "hallway-wall-contact": "clears-walls",
    "hallway-fall": "stays-upright",
}


def test_bundle_schema_keeps_an_id_and_a_version():
    schema = json.loads((PACKAGE / "bundle.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].startswith("https://")
    assert schema["$id"].endswith("/bundle.schema.json")
    assert schema["version"] == "1.1.0"
    Draft202012Validator.check_schema(schema)
    manifest = json.loads((ROOT / "examples/bundle/manifest.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)


@pytest.mark.parametrize("name", ["g1", "go1", "t1"])
def test_hallway_reports_match_v3_7_0(name):
    """Same steps, labels, limits and grades as v3.7.0, without the removed label."""
    stored = report(bundle(name))
    markdown = render(stored, "markdown")
    html = top(render(stored, "html")) + "\n"
    assert markdown == (GOLDEN / f"{name}.md").read_text(encoding="utf-8")
    golden_html = (GOLDEN / f"{name}.html").read_text(encoding="utf-8")
    assert REMOVED_LABEL in golden_html
    assert html == golden_html.replace(REMOVED_LABEL, "")
    assert REMOVED_LABEL not in html


def test_markdown_filename_comes_from_stored_scenario_data():
    named = markdown_filename(report(bundle("g1")))
    assert named == "walk-hallway.markdown"
    plain = report_from_example_capability()
    assert markdown_filename(plain) == "walk-hallway.markdown"
    assert named != "hallway.markdown"


def report_from_example_capability():
    """The example bundle has no description, so the name is the stored capability."""
    manifest = ROOT / "examples/bundle/manifest.json"
    return report_from_bundle(load_bundle(manifest))


def test_a_directory_output_uses_the_scenario_filename(tmp_path):
    manifest = example(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    result = CliRunner().invoke(
        cli, ["render", str(manifest), "--format", "markdown", "--output", str(out)]
    )
    assert result.exit_code == 0, result.output
    written = out / "walk-hallway.markdown"
    assert written.is_file()
    assert not (out / "hallway.markdown").exists()
    stored = report_from_bundle(load_bundle(manifest))
    assert written.read_text(encoding="utf-8") == render(stored, "markdown")


def _corner_description():
    schema_path = SPEC / "scenario-description.schema.json"
    raw = schema_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SCHEMA_SHA256
    source = json.loads((SPEC / "SOURCE.json").read_text(encoding="utf-8"))
    assert source["tag"] == "v2.2.1"
    assert source["sha256"] == SCHEMA_SHA256
    schema = json.loads(raw)
    description = json.loads((SPEC / "walk-corner.description.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(description)
    return description


def _corner_bundle():
    """Real G1 evidence with the schema-built description's own step ids."""
    data = bundle("g1")
    data["description"] = _corner_description()
    for result in data["results"]:
        donor = next(
            item for item in result["assessments"] if item.get("evaluator") == "hallway-fall"
        )
        extra = copy.deepcopy(donor)
        extra["id"] = f"{donor['id']}-route"
        extra["evaluator"] = "stays-on-route"
        assessor = (extra.get("provenance") or {}).get("assessor")
        if isinstance(assessor, dict):
            assessor["id"] = "stays-on-route"
        result["assessments"].append(extra)
        for item in result["assessments"]:
            evaluator = item.get("evaluator")
            if evaluator in _CORNER_CHECKS:
                item["evaluator"] = _CORNER_CHECKS[evaluator]
                assessor = (item.get("provenance") or {}).get("assessor")
                if isinstance(assessor, dict) and assessor.get("id") in _CORNER_CHECKS:
                    assessor["id"] = _CORNER_CHECKS[assessor["id"]]
    return data


def test_corner_description_renders_its_own_step_names():
    description = _corner_description()
    stored = report(_corner_bundle())
    page = render(stored, "html")
    for criterion in description["mission"]["success_criteria"]:
        text = criterion["text"]
        assert kind(criterion["evaluator"]) is None
        assert f"<h3 class='step-name'>{text}<span class='colon'>" in page
    assert markdown_filename(stored) == "walk-corner.markdown"
    assert "Walk around the corner" in page
    assert REMOVED_LABEL not in page


def test_scenario_names_stay_in_the_legacy_reader():
    pattern = re.compile(r"hallway|corner", re.IGNORECASE)
    offenders = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".json"}:
            continue
        if path.name == "legacy_evidence.py":
            continue
        if pattern.search(path.name) or pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []
