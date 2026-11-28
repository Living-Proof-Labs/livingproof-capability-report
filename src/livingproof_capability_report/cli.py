"""Thin Click group, reusable as a future parent's nested report command."""

from pathlib import Path

import click
from jsonschema import ValidationError

from .core import decode, load_bundle, markdown_filename, render, require_decisions


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
    help=(
        "Bundle 1.1.0 input only: JSON file of evidence links. "
        "Each link may set path to a relative site path, rendered exactly on the public page. "
        "Set expired true when the site has pruned that file. "
        "An optional https url is kept in report.json and is omitted from the public page "
        "when it is a GitHub Actions artifact address. Kinds: artifact, video, mcap, log, note."
    ),
)
@click.option(
    "--history-href",
    default=None,
    help=(
        "HTML only: address for the run-history slot, a relative site path or https URL. "
        "Rendered only together with --history-label. Omit both to render no slot."
    ),
)
@click.option(
    "--history-label",
    default=None,
    help="HTML only: visible label for the run-history slot. Required with --history-href.",
)
@click.option(
    "--evidence-retention",
    type=int,
    default=None,
    help=(
        "Days the site keeps evidence files. The public page says "
        "'Evidence kept for N days' for live files and 'Evidence expired after N days' "
        "for pruned files, using this value. "
        "Required when a link is expired. There is no default."
    ),
)
@click.option(
    "--trusted-viewers",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Caller-only JSON list of trusted viewer pins; never evaluator output. HTML only.",
)
@click.option(
    "--asset-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Local report assets, including pinned viewer and adjacent data. Required for viewers.",
)
@errors
def render_command(
    report_file,
    format,
    output,
    report_url,
    clips_url,
    lock_diff_url,
    evidence_links,
    history_href,
    history_label,
    evidence_retention,
    trusted_viewers,
    asset_root,
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
    A directory passed to ``--output`` with ``--format markdown`` is filled with
    ``<scenario>.markdown``, named from the scenario id in the bundle.
    """
    from . import assessed

    stored = decode(report_file.read_text(encoding="utf-8"))
    require_decisions(stored)
    observations = None
    evaluator_results = None
    if assessed.is_assessed(stored):
        loaded = load_bundle(report_file)
        stored = assessed.report_from_bundle(
            loaded,
            [decode(p.read_text(encoding="utf-8")) for p in evidence_links] or None,
        )
        from .evaluators import load_evidence_results
        from .steps import durations_by_result

        observations = durations_by_result(loaded["bundle"], report_file.parent)
        evaluator_results = load_evidence_results(loaded["bundle"], report_file.parent)
    elif evidence_links:
        raise ValueError("--evidence-links applies to a bundle 1.1.0 manifest only")
    selected_format = format or ("html" if output is not None else "table")
    links = {"report": report_url, "clips": clips_url, "lock_diff": lock_diff_url}
    history = None
    if history_href or history_label:
        history = {"href": history_href, "label": history_label}
    from .trusted_viewer import TrustedViewer

    viewers = None
    if trusted_viewers is not None:
        pins = decode(trusted_viewers.read_text(encoding="utf-8"))
        if not isinstance(pins, list):
            raise ValueError("Trusted viewer pins must be a caller-owned list")
        viewers = [TrustedViewer(**pin) for pin in pins]
    if viewers and output is not None:
        if asset_root is None or output.parent.resolve() != asset_root.resolve():
            raise ValueError("Viewer HTML output must be in the verified asset root")
        # Do not allow a symlink path to redirect the page away from verified assets.
        for path in (output, *output.parents, asset_root, *asset_root.parents):
            if path.is_symlink():
                raise ValueError("Viewer HTML output and asset paths cannot contain symlinks")
        if output.exists():
            raise ValueError("Viewer HTML output must be a new file, not a staged input")
    content = render(
        stored,
        selected_format,
        links if any(links.values()) else None,
        observations=observations,
        evaluator_results=evaluator_results,
        history=history,
        retention=evidence_retention,
        trusted_viewers=viewers,
        asset_root=asset_root,
    )
    if output is not None and output.is_dir():
        if selected_format != "markdown":
            raise click.ClickException(
                "A directory --output is only for --format markdown; pass a file name"
            )
        output = output / markdown_filename(stored)
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


@report.command("site")
@click.argument("reports_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--runs",
    "runs_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory of incoming run folders (report.html, report.json, report.md, "
    "report.txt, SHA256SUMS and run.json each).",
)
@click.option(
    "--evidence-retention-days",
    type=int,
    default=7,
    show_default=True,
    help="Days to keep copied MCAP, video and media files before pruning them.",
)
@click.option("--now", default=None, help="UTC ISO-8601 reference time for evidence pruning.")
@click.option(
    "--allow-replace-run-id",
    default=None,
    help="Current run id that may replace its own folder on a same-run retry.",
)
@click.option(
    "--git-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Checkout used to find the release tag that points at each tested commit.",
)
@click.option(
    "--exclude-run",
    "exclude_runs",
    multiple=True,
    help="Restored run folder name to drop before rendering. Repeat for more.",
)
def site_command(
    reports_dir, runs_dir, evidence_retention_days, now, allow_replace_run_id, git_dir, exclude_runs
):
    """Add the run folders in --runs to REPORTS_DIR and render the reports section.

    REPORTS_DIR may already hold earlier runs (for example restored from the last Pages
    deploy); they are rechecked and kept. The command writes the reports index, one history
    page per scenario, a latest/ redirect and each run's published page, then checks every
    link and checksum. It never fetches anything and never regrades a run.

    \b
    livingproof-capability-report site reports --runs incoming
    """
    from .site import MARKER, SiteError, build, check_reports_tree

    try:
        added = build(
            reports_dir,
            runs_dir,
            now=now or None,
            days=evidence_retention_days,
            allow_replace_run_id=allow_replace_run_id or None,
            git_dir=git_dir,
            exclude_runs=exclude_runs,
        )
        issues = check_reports_tree(reports_dir)
        if issues:
            raise SiteError("Generated reports/ check failed: " + "; ".join(issues))
        marker = decode((reports_dir / MARKER).read_text(encoding="utf-8"))
    except SiteError as exc:
        raise click.ClickException(str(exc)) from exc
    for folder in added:
        click.echo(f"Added {folder.relative_to(reports_dir).as_posix()}")
    click.echo(f"Built {reports_dir} ({marker['scenarios']} scenarios, {marker['runs']} runs).")
