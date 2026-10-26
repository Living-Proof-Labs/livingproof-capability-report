"""Thin Click group, reusable as a future parent's nested report command."""
from pathlib import Path

import click
from jsonschema import ValidationError

from .core import decode, grade, load_bundle, render


def errors(function):
    from functools import wraps
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise click.ClickException(str(exc)) from exc
    return invoke


@click.group()
@click.version_option(package_name="livingproof-capability-report")
def report():
    """Validate a bundle, grade its evidence, then render the saved report.

    Start with a bundle manifest: it contains version information, evidence
    paths and assessment references. Individual observation files are evidence
    referenced by that manifest, not standalone reporter input.

    Run this example from the repository root or extracted source archive:

    \b
    livingproof-capability-report validate examples/bundle/manifest.json
    livingproof-capability-report grade examples/bundle/manifest.json -o report.json
    livingproof-capability-report render report.json

    For your own bundle, substitute its manifest path. Validate checks structure
    and evidence integrity; grade saves decisions; render displays them without
    regrading. Output files must be new; choose another name when rerunning.
    """


@report.command("validate")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@errors
def validate_command(manifest):
    """Validate a bundle MANIFEST and its evidence integrity (no grading).

    Pass the manifest JSON, not an individual evidence/observation file.
    It contains version information, evidence paths and assessment references.

    From the repository root or extracted source archive:

    \b
    livingproof-capability-report validate examples/bundle/manifest.json
    livingproof-capability-report grade examples/bundle/manifest.json -o report.json
    livingproof-capability-report render report.json

    Validation checks integrity; grade saves decisions; render displays them.
    """
    loaded = load_bundle(manifest)
    click.echo("Valid bundle structure")
    for result, evidence in loaded["evidence_state"].items():
        for name, state in evidence.items():
            click.echo(f"{result}/{name}: {state}")
    if any(state != "verified" for states in loaded["evidence_state"].values()
           for state in states.values()):
        raise click.ClickException("Evidence is incomplete or changed")


@report.command("grade")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--human", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--policy", default="all-required-v1@1.0.0", show_default=True)
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
@errors
def grade_command(manifest, human, policy, output):
    """Grade a bundle MANIFEST into a new JSON report (no overwriting).

    Use the bundle manifest, not an individual observation. From the repository
    root or extracted source archive, validate first, then save and view a report:

    \b
    livingproof-capability-report validate examples/bundle/manifest.json
    livingproof-capability-report grade examples/bundle/manifest.json -o report.json
    livingproof-capability-report render report.json

    Choose a new output filename when rerunning.
    """
    result = grade(load_bundle(manifest), policy, decode(human.read_text()) if human else None)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(render(result))
    click.echo(str(output))


@report.command("render")
@click.argument("report_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", type=click.Choice(["table", "json", "html", "csv"]), default=None,
              help="Default: table on stdout; HTML when --output is supplied (v1 compatibility).")
@click.option("--output", "-o", type=click.Path(path_type=Path),
              help="Write a new file; otherwise print to stdout. Existing files are never overwritten.")
@errors
def render_command(report_file, format, output):
    """Render saved decisions; never regrade or overwrite existing files.

    REPORT_FILE is the JSON report created by grade, not the bundle manifest or
    an observation. Create it first with the bundled example from the repository
    root or extracted source archive:

    \b
    livingproof-capability-report validate examples/bundle/manifest.json
    livingproof-capability-report grade examples/bundle/manifest.json -o report.json
    livingproof-capability-report render report.json
    livingproof-capability-report render report.json --format html -o report.html

    Default stdout is a terminal table. Choose new output filenames when rerunning.
    """
    selected_format = format or ("html" if output is not None else "table")
    content = render(decode(report_file.read_text(encoding="utf-8")), selected_format)
    if output is None:
        click.echo(content, nl=False, color=False)
        return
    with output.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)
    click.echo(str(output))


@report.command("human-template")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--result", "result_id", required=True)
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
@errors
def human_template(manifest, result_id, output):
    """Create an insufficient assessment for a person to review and complete."""
    import json
    from .core import digest
    bundle = load_bundle(manifest)["bundle"]
    selected = next((r for r in bundle["results"] if r["id"] == result_id), None)
    if selected is None:
        raise ValueError("Unknown result identifier")
    contribution = {"schema_version": "1.0.0", "assessments": [{
        "result_id": result_id, "result_sha256": digest(selected), "assessment": {
            "id": "human-review", "evaluator": "human-fixture", "kind": "human",
            "version": "1.0.0", "mandatory": False, "status": "INSUFFICIENT_EVIDENCE",
            "rationale": "Review the referenced evidence and record your reasoning here",
            "evidence_ids": [e["id"] for e in selected["evidence"]],
            "provenance": {"reviewer": "Replace with reviewer identity",
                           "recorded_at": "Replace with review date",
                           "source": "human file contribution; identity is self-declared"}}}]}
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(contribution, indent=2) + "\n")
