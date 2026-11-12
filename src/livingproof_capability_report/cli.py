"""Thin Click group, reusable as a future parent's nested report command."""

from pathlib import Path

import click
from jsonschema import ValidationError

from .core import decode, load_bundle, render, require_decisions


def errors(function):
    from functools import wraps

    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise click.ClickException(str(exc)) from exc

    return invoke


def show_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    from .version import current_version

    identity, package_version, source = current_version()
    click.echo(f"livingproof-capability-report, version {identity}")
    click.echo(f"Package: {package_version}; identity source: {source}")
    ctx.exit()


@click.group()
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=show_version,
    help="Show release or development identity, package version and provenance source.",
)
def report():
    """Validate a bundle, then render the capability verifier's stored decisions.

    Start with a bundle 1.1.0 manifest written by capability-verifier: it contains version
    information, evidence paths, assessments, and the verifier's per-result decisions and
    run assessments. This reporter never grades; a bundle 1.0.0 (no decisions) is refused.

    Run this example from the repository root or extracted source archive:

    \b
    livingproof-capability-report validate examples/bundle/manifest.json
    livingproof-capability-report render examples/bundle/manifest.json --format json -o report.json
    livingproof-capability-report render report.json

    For your own bundle, substitute its manifest path. Validate checks structure and evidence
    integrity; render shows the stored decisions as they are. Output files must be new;
    choose another name when rerunning.
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
    livingproof-capability-report render examples/bundle/manifest.json --format json -o report.json
    livingproof-capability-report render report.json

    Validation checks integrity; render displays the verifier's stored decisions.
    """
    loaded = load_bundle(manifest)
    click.echo("Valid bundle structure")
    for result, evidence in loaded["evidence_state"].items():
        for name, state in evidence.items():
            click.echo(f"{result}/{name}: {state}")
    if any(
        state != "verified"
        for states in loaded["evidence_state"].values()
        for state in states.values()
    ):
        raise click.ClickException("Evidence is incomplete or changed")


@report.command("render")
@click.argument("report_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--format",
    type=click.Choice(["table", "json", "html", "csv", "markdown"]),
    default=None,
    help="Default: table on stdout; HTML when --output is supplied (v1 compatibility).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Write a new file; otherwise print to stdout. Existing files are never overwritten.",
)
@click.option("--report-url", help="Markdown only: link to the full report.")
@click.option("--clips-url", help="Markdown only: link to all clips.")
@click.option("--lock-diff-url", help="Markdown only: link to the verification.lock.json diff.")
@click.option(
    "--evidence-links",
    "evidence_links",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Bundle 1.1.0 input only: JSON file of CI run, artifact and per-trial media links.",
)
@errors
def render_command(
    report_file, format, output, report_url, clips_url, lock_diff_url, evidence_links
):
    """Render stored decisions; never grade or overwrite existing files.

    REPORT_FILE is a bundle 1.1.0 manifest from capability-verifier, or a JSON report saved
    from one with ``--format json``. The verifier's decisions and run assessments are
    rendered as they are; nothing is graded. A bundle 1.0.0 has no decisions and is refused:
    assess it with capability-verifier first. From the repository root or extracted source
    archive:

    \b
    livingproof-capability-report render examples/bundle/manifest.json --format json -o report.json
    livingproof-capability-report render report.json
    livingproof-capability-report render report.json --format html -o report.html
    livingproof-capability-report render examples/bundle/manifest.json --format markdown -o report.md

    Default stdout is a terminal table. Choose new output filenames when rerunning.
    """
    from . import assessed

    stored = decode(report_file.read_text(encoding="utf-8"))
    require_decisions(stored)
    observations = None
    if assessed.is_assessed(stored):
        loaded = load_bundle(report_file)
        stored = assessed.report_from_bundle(
            loaded,
            [decode(p.read_text(encoding="utf-8")) for p in evidence_links] or None,
        )
        from .steps import durations_by_result

        observations = durations_by_result(loaded["bundle"], report_file.parent)
    elif evidence_links:
        raise ValueError("--evidence-links applies to a bundle 1.1.0 manifest only")
    selected_format = format or ("html" if output is not None else "table")
    links = {"report": report_url, "clips": clips_url, "lock_diff": lock_diff_url}
    content = render(
        stored,
        selected_format,
        links if any(links.values()) else None,
        observations=observations,
    )
    if output is None:
        click.echo(content, nl=False, color=False)
        return
    with output.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)
    click.echo(str(output))


@report.command("comment")
@click.argument(
    "reports", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--repo", required=True, help="OWNER/NAME of the pull request's repository.")
@click.option("--pr", required=True, type=int, help="Pull request number.")
@click.option("--dry-run", is_flag=True, help="Read existing comments; print, post nothing.")
@click.option(
    "--comments",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="With --dry-run: a JSON list of existing comments instead of the API (offline).",
)
@errors
def comment_command(reports, repo, pr, dry_run, comments):
    """Post or update the one PR comment holding the markdown REPORTS (render output).

    Each REPORT is a markdown file from ``render --format markdown``; they are joined, sorted
    by path, under the hidden marker. The comment carrying the marker is updated in place.
    """
    from . import comment

    text = comment.body(p.read_text(encoding="utf-8") for p in sorted(reports))
    if comments is not None:
        if not dry_run:
            raise ValueError("--comments needs --dry-run")
        listed = decode(comments.read_text(encoding="utf-8"))

        def call(method, path, payload=None):
            return listed, ""
    else:
        secret = comment.token()

        def call(method, path, payload=None):
            return comment.http(method, path, payload, secret)

    method, path = comment.publish(repo, pr, text, call, dry_run)
    click.echo(f"{'would ' if dry_run else ''}{method} {path} ({len(text)} chars)")
    if dry_run:
        click.echo(text, nl=False)
