# Living Proof Labs capability report

**Start here: [documentation](https://docs.livingprooflabs.com/livingproof-capability-report/).**

Documentation previews: [build and verification guide](docs/verification.md) (14-day CI artifacts).

[![Tests, builds and compatibility](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/verify.yml)
[![Package release](https://img.shields.io/github/v/release/Living-Proof-Labs/livingproof-capability-report)](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases/latest)
[![License](https://img.shields.io/github/license/Living-Proof-Labs/livingproof-capability-report)](LICENSE)

An installable Python library and thin Click command group for portable capability
results. Validate evidence bundles and render the decisions that
[capability-verifier](https://github.com/Living-Proof-Labs/capability-verifier) stored in
them as lossless JSON, offline HTML, markdown or explicitly flattened CSV. The reporter
never grades.
This is a deterministic fixture demonstration, not robot safety certification.
No server, simulator, source checkout or Task installation is needed by consumers.

## Install a release

Download the wheel or Debian package and `SHA256SUMS` from
[Releases](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases).
The Debian package is `Architecture: all`: it ships only pure-Python reporter
files and metadata. Apt installs architecture-appropriate `python3-click`,
`python3-jsonschema`, and `python3-defusedxml` dependencies. All files are managed by dpkg; no pip writes
into system Python, private interpreter, native wheel or vendored virtual
environment is included. The native support matrix is documented below.

```sh
sudo apt install ./python3-livingproof-common_1.0.0_all.deb ./livingproof-capability-report_*_all.deb
livingproof-capability-report --help
```

Alternatively, use a Python 3.11+ virtual environment (never system-wide pip):

```sh
python3 -m venv .venv
.venv/bin/pip install ./livingproof_common-1.0.0-py3-none-any.whl ./livingproof_capability_report-*.whl
.venv/bin/livingproof-capability-report --help
```

The common wheel and `python3-livingproof-common_1.0.0_all.deb` are included as
unchanged, checksum-verified upstream release assets. Install the common Debian
package alongside the reporter `.deb` with apt. No PyPI or apt index is assumed
for this library. Other wheel dependencies resolve normally; the architecture-specific downloadable wheelhouse targets CPython 3.12 and
supports offline installation with `--no-index --find-links=./wheels`. The source
archive is also attached. Release package versions come from the release tag;
there are no generated version commits. Python 3.11, 3.12 and 3.13 are exercised through the distribution packages below.
Other Python versions and platforms are not claimed.

The release job builds `ghcr.io/living-proof-labs/livingproof-capability-report:1.2.0`
with the installed wheel and the reporting command as its entrypoint. Saved `image-amd64.tar` and `image-arm64.tar` files are attached even if registry
publication is unavailable. `docker load -i image-arm64.tar` loads the
architecture-specific `:1.2.0-arm64` tag; use that tag when working offline.
A published multi-architecture registry tag selects the native architecture automatically.
Version 1.2.0 initially encountered a `write_package` denial. The
[recovery workflow](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/recover-registry.yml)
verifies and publishes its original saved images after the approved repository
Actions access correction. Consult that run for actual registry availability. Registry publication and
anonymous availability are separate checks; see the release job for their results.

```sh
docker load -i image-arm64.tar  # use the amd64 asset/tag on amd64
docker run --rm -v "$PWD/bundle:/data:ro" \
  ghcr.io/living-proof-labs/livingproof-capability-report:1.2.0-arm64 validate manifest.json
```

## Report a portable bundle

With the reporter installed, run this quickstart from the repository root (or
from the extracted source archive containing `examples/`):

```sh
livingproof-capability-report validate examples/bundle/manifest.json
livingproof-capability-report render examples/bundle/manifest.json --format json -o report.json
livingproof-capability-report render report.json
livingproof-capability-report render report.json --format html -o report.html
livingproof-capability-report render report.json --format csv -o report.csv
```

`validate` checks the manifest structure and evidence digests; `render` reads the
verifier's stored decisions from a bundle 1.1.0 manifest (or a saved `report.json`)
and displays them (a terminal table by default). For your own bundle, replace
`examples/bundle/manifest.json` with its manifest path. Installed packages do not
require a checkout to report your bundle.

The example is a walk-hallway run written by capability-verifier: 20 seeded trials of
the stock Unitree G1, 12 of which pass. The **manifest** describes the results, contract
versions, assessments, the verifier's decisions and run assessment, and relative evidence
paths with their digests. Evidence files, such as `examples/bundle/evidence/stock-seed-01.json`,
are referenced by that manifest; they are not standalone reporter input. Keep them at the
relative paths declared by their manifest.

Outputs must be new files. Rendering never grades or silently substitutes a newer
policy. JSON retains the entire source manifest, original producer results,
assessments, evidence references, integrity observations, exact-context groups and
stored decisions. Evidence bytes stay in the portable bundle. HTML is self-contained,
escaped, script-free and usable offline. CSV is deliberately flattened: one decision
per row, with spreadsheet-formula protection; it is not a round-trip representation.

Importable API:

```python
from livingproof_capability_report import load_bundle, render, report_from_bundle
saved = report_from_bundle(load_bundle("examples/bundle/manifest.json"))
html = render(saved, "html")
```

The installed distribution advertises `livingproof_capability_report.cli:report`
as `report` in the `livingproof.capability.commands` entry-point group. A compatible
umbrella can mount that same Click group as `livingproof capability report` when
both packages are installed in the same Python environment. Neither library
depends on the other; the standalone command and Python API remain unchanged.
Version v1.3.0 predates this metadata; it remains usable standalone.

## Bundle and grading contract

Grading belongs to capability-verifier. It assesses the evidence and writes a bundle with
`schema_version` 1.1.0 that carries its decisions; this reporter only checks and renders
them ([reporter #30](https://github.com/Living-Proof-Labs/livingproof-capability-report/issues/30)).

The packaged `bundle.schema.json` accepts `schema_version` 1.0.0 and 1.1.0. Each result
includes an identifier, released catalog tag and commit, capability/revision, system and
environment versions, relative evidence paths with SHA-256 digests, assessments,
provenance and the original producer result. Unknown extension fields are retained.
Duplicate JSON keys, non-finite numbers, undeclared evidence references, absolute
paths, traversal and symlinks are rejected. URLs are never fetched. Digests detect
changed bytes; they do not authenticate who produced the evidence.

A 1.0.0 bundle still validates, but it has no decisions, so `render` refuses it with an
error that points to the verifier: assess the evidence with capability-verifier v1.9.0
or later, which writes bundle 1.1.0, and render that. There is no averaging and no
overall numeric score. Aggregation groups exact spec, system and environment contexts.

## Version 2.0.0: render the verifier's grading (bundle 1.1.0)

Reporter 2.0.0 is a major release. capability-verifier (from the release that adds
`--bundle-version 1.1.0`) grades walk-hallway evidence itself and writes the outcome
into a bundle with `schema_version` 1.1.0: each result carries a `decision` (status,
reason, structured failures, assessor types, policy), and the bundle carries an
`assessment` in robot-capability-specs' `livingproof-run-assessment/0.1` format (every
decision, plus per run k of N, the Wilson 95% interval, the grade and its rationale).

    livingproof-capability-report render bundle/manifest.json --format json -o report.json
    livingproof-capability-report render bundle/manifest.json --format markdown -o report.md

`render` accepts that manifest directly and computes nothing: statuses, k, N, interval and
grade are shown as stored. `report.json` is the same report document 1.x `grade` wrote
(`summaries` keep the `wilson95` pair), so `report.md` and the `comment` body are
byte-identical to what 1.x produced from the same evidence. `--evidence-links` adds CI
links (see below). A missing or malformed required field is an error naming the field
and the result. Evidence is still checked: a stored PASS whose evidence is missing or
changed is refused.

What changes for callers:

- The packaged bundle schema accepts `schema_version` 1.0.0 and 1.1.0.
- `grade`, `human-template`, the policies (`--policy`, `--human`, `--previous`,
  `--require-pass`) and the `grade` Python function are removed
  ([#30](https://github.com/Living-Proof-Labs/livingproof-capability-report/issues/30)).
  Bundles 1.0.0 are refused by `render`; produce 1.1.0 with capability-verifier instead.
- Saved `report.json` files from earlier releases, including grade revisions, still
  render as stored.
- How human reviews apply to 1.1.0 bundles is not decided yet.

## What the HTML report shows

`--format html` opens with a summary card: the stored success ring, the success
count and percentage (for example "12 successes, 60%"), the
mission title when the feature spec has one, and one mark per evaluator result.
Finding rows appear only when a result's descriptor lists them. The ring is the
stored rate. A finding that is not in the verdict tier does not change it. Opening
a mark shows that result's descriptor (title, version, purpose, source, tier, and
detail text) and, for the run record, the sections below. Those sections use the
feature spec (`description`), the run assessment, and descriptor text. A spec
sentence that restates a plan, such as `description.mission.grading`, is not
shown: a stock sentence can still say "20 runs" on a 3-trial assessment. The
acceptance line is that required count as a percentage of `n`, for example
"90% required". Step names are
the spec's `success_criteria` text. The stored Wilson 95% interval, when the
assessment has one, is muted text in the run detail, not on the ring. Today's
bundles do not carry a descriptor yet, so the mark uses the fallback name and
the letter disc and says so.

Every value is read from the stored report and its source bundle and HTML-escaped;
nothing is regraded or recomputed, and a field the report does not carry is left out.
The trial table (Result, Catalog, Revision, Environment, Status, Reason) follows.
The collapsed `<details>` block embeds the stored JSON. Addresses that point at a
GitHub Actions artifact are left out of that public copy; `report.json` still keeps
them. `--format table`
prints the policy and grade revision as trailing lines; `--format csv` adds `policy` and
`grade_revision` columns only when the decisions carry `assessment_details`.

## Compatibility evidence

`examples/bundle` is a walk-hallway bundle 1.1.0 in the layout capability-verifier
writes: stock Unitree G1, catalog v1.6.0, 20 seeds, 12 PASS and 8 FAIL, run grade FAIL
(18 of 20 needed). Its rendered markdown and report are pinned in
`tests/fixtures/hallway-expected`; they were produced by the 1.x `grade` path before it
was removed, so the tests show `render` reproduces that output byte for byte from the
stored decisions. The earlier pause example (a 1.0.0 bundle) was removed with grading.

## Contribute a human assessment

The `human-template` command and human re-grading were removed with the reporter's
grading ([#30](https://github.com/Living-Proof-Labs/livingproof-capability-report/issues/30)).
How human reviews are recorded for bundle 1.1.0 is not decided yet; reports saved by
earlier releases keep their human contributions and still render.

## Contributors and delivery

Read [Contribute](CONTRIBUTING.md) for the deliberately adopted
[collaboration-guidelines v6.0.0](https://github.com/Living-Proof-Labs/collaboration-guidelines/tree/v6.0.0)
and local instructions. This guidance pin is separate from the release workflow below.

Install Python 3.12, uv, Docker and Task 3.54.0, then use `task setup`, `task verify`,
`VERSION=0.0.0 task package` and `VERSION=0.0.0 task smoke` from a fresh checkout.
Task delegates to locked native tools. `PACKAGE_NETWORK=host` optionally selects
Docker networking for environments that require it; no daemon configuration changes.
Packaging uses the official Python build backend, pip, venv and `dpkg-deb`.

CI attaches wheel, source archive, Debian package, native dependency wheelhouses, saved images
and SHA-256 checksums. The shared release workflow is pinned to
[collaboration-guidelines v3.0.0](https://github.com/Living-Proof-Labs/collaboration-guidelines/tree/v3.0.0).
Release builds install the exact published package version. Clean containers test
wheel and Debian installations without mounting source. A normal `docker run`
tests the convenience entrypoint; a separate shell override tests the same image
as a job container. Providers can override entrypoints or require a shell; identical
startup behavior across CI providers is not claimed. JUnit expectation tests stay
separate from the capability decisions. No PyPI publication or new credentials.

Original code and fixture adaptations are Apache-2.0; see [LICENSE](LICENSE).

## Debian and ARM support

The authoritative compatibility results are generated by the
[CI matrix](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/verify.yml),
not manually contributed machine claims. Each run summary and package artifact
contains `compatibility-amd64.json` / `.md` and `compatibility-arm64.json` / `.md`.
Published versions attach those same machine-generated reports to
[Releases](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases).
They record actual OS/version details, architecture, Python, installation method,
native versus emulated execution, outcome and the evidence run URL. A missing
probe is explicitly NOT_COMPLETED, never counted as supported.

The current automated coverage targets Debian 12, Debian 13 and Ubuntu 24.04,
plus wheel/source/image installations, on amd64 and arm64. Consult a release's
records for what actually passed rather than assuming a configured target passed.

The jobs use `ubuntu-24.04` and `ubuntu-24.04-arm` hosts, with matching-architecture
clean distribution containers. This is native CPU testing, not QEMU emulation or
testing on a particular Googlebook. Installation, commands, importable logic and
removal are checked; distribution-owned dependencies remain after removal.
Release verification installs the same candidate `all.deb` on both CPUs before
publication, then checks anonymous downloads against the published checksums.

The older v1.0.0 package really is amd64/Python-3.12-specific: its private environment
contains `rpds.cpython-312-x86_64-linux-gnu.so`. Do not force its architecture or
install it on Debian's Python 3.11/3.13. Version 1.2 uses distribution dependencies
with tested minimum versions instead. Apt owns any native dependencies; their
architecture labels remain intact. This is a packaging change, not a file rename.
If upgrading an old installation, apt removes the old package-owned `/opt` files.

Use `cat /etc/os-release`, `python3 --version`, and `dpkg --print-architecture`
to match a device to these automated results. Debian variants outside the coverage are not
verified. The ARM Docker image includes its own Python runtime, so a host's
Python minor version does not control it; working Docker support is still needed.
No changes to a user's device or system Python are performed by this project.

Multi-architecture releases publish immutable version-specific `-amd64` and
`-arm64` images, then one versioned manifest after both native checks pass.
Published previous tags are unchanged. Check `SHA256SUMS` for the common wheel,
source archive and `all.deb`, plus architecture-specific images and wheelhouses.

## Test results in GitHub

The verify job uploads JUnit results even when tests fail. The job summary lists
individual cases. The Reporter tests check is created already completed, so a
failed follow-up update cannot leave it in progress. A missing or unreadable
report fails the job. A failure to create or update that check is a warning and
does not by itself fail the job. Fork pull requests receive the summary and
artifact without a write-token check. Raw reports are retained for 14 days. This
provides per-run history for comparison; this integration does not implement a
historical trends dashboard or promise automatic trend correlation.

## Terminal rendering and compatibility

`livingproof-capability-report render report.json` prints a concise table to
standard output, without color or ANSI sequences. It shows stored decisions and
separate contexts, never an overall grade or regrading. This invocation was an
error in v1.0.0 because `--output` was required; adding it is backward-compatible.

Existing `render report.json -o report.html` commands still default to HTML. Use
`--format table -o report.txt` for a saved table, or explicit `--format json`,
`--format html`, or `--format csv` with stdout or a new output file. Library
`render(report)` continues to default to lossless JSON. Scripts should name their
format explicitly. Existing output files are never overwritten.

Release automation assembles packages and checksums on a draft, verifies native
image consumption and the same Debian asset on both architectures, then publishes
the complete immutable release. Historical v1.0.1 and v1.1.0 release records lack
package assets because their earlier workflow attempted upload after publication;
use v1.2.0 or later for these packaging improvements.

## Container development

The `development` target in [Dockerfile](Dockerfile) supplies Python, pinned uv,
Task and Git. It shares the Python base with the small installed-package runtime
target; development dependencies come from the same committed `uv.lock` used by
CI. The release image retains only the installed application and its dependencies.

With Docker Compose and Task on a Linux host (the host wrappers are tested on Linux):

```sh
task dev:build
task dev:verify
task dev:shell
```

The [devcontainer](.devcontainer/devcontainer.json) builds that same target for
VS Code, Cursor and GitHub Codespaces. Reopen in the container; its creation hook
runs `task setup`. Inside, use `task check`, `task test` and `task verify` directly.
No Docker daemon, host Docker socket, privileged mode or Docker-in-Docker is
required inside the development environment. Package/image building remains a
host/CI task because it requires Docker.

[Development CI](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/development.yml)
builds this Docker target on native AMD64 and ARM64 and runs those same Task
commands. This verifies the image and setup/verification lifecycle, not a live
Codespaces session or a particular editor launch. No paid Codespace or new account
grant is provisioned by these checks.

## Retain human reviews as grade revisions

Grade revisions (`all-required-v2@1.0.0`, `--previous`, `--require-pass`) were
removed with the reporter's grading. Earlier reports that embed a `previous_report`
and `grade_revision` still render their own stored decisions without regrading; the
embedded history is kept in JSON but no longer checked or rendered. For a CI gate, use
the verifier's run grade in the bundle's `assessment`.

## Identify the version you are testing

Version policy is supplied by released [livingproof-common v1.0.0](https://github.com/Living-Proof-Labs/livingproof-common/releases/tag/v1.0.0).
The reporter supplies only its own package and repository context; no version
algorithm is copied here. Build and runtime dependencies pin the same library.

Run `livingproof-capability-report --version` and include both output lines in a
problem report. For example:

```text
livingproof-capability-report, version 1.4.0-dev.3+branch.fix-input-a1b2c3d4.gabcdef123456.dirty
Package: 1.4.1.dev3; identity source: checkout
```

The first line identifies source state. A clean checkout or build exactly on a
`vX.Y.Z` release tag displays plain `X.Y.Z`. Development identities include the
nearest release tag, Git's commit distance from that tag, a bounded branch label,
the first 12 commit-hash characters, and `clean` or `dirty`. Tracked modifications,
staged changes and nonignored untracked files count as dirty. Ignored build
outputs do not. The dirty marker identifies a state, not a digest of uncommitted
contents; two different dirty trees can display the same identity.

Only branch names present in local `origin` tracking refs for this public
repository are eligible for display. Other local branches display `local`;
detached checkouts use a unique matching public tracking branch if available,
otherwise `detached`. Public slugs are at most 33 characters, including a hash
suffix to distinguish normalized/truncated names. These local observations are
not authenticated origin or release attestations. URLs, local paths and private
local branch names are not printed or stored in build provenance.

`dev.empty` means Git has no commits. `dev.untagged.N` means there is no usable
release tag and N commits are visible from the history root, not since a release.
Shallow histories display `dev.unknown` with a `shallow` marker; missing Git or
provenance displays `0.0.0-dev.unknown+nogit.unknown`. Unknown state is never
presented as a clean release.

The second line reports the installed PEP 440 package version and the identity
source. `checkout` is refreshed from the reporter's own source tree on each call,
so editable installs reflect changes without reinstalling; the caller's working
directory is never used. `recorded-build` uses provenance embedded in the wheel
or source distribution, retained by Debian and container packaging without `.git`.
If a live checkout's Git cannot be read, `checkout-unavailable` reports unknown
current identity instead of presenting a stale build snapshot as current.

Package metadata still comes from the existing
[Hatch-VCS](https://github.com/ofek/hatch-vcs) / setuptools-scm integration, with
its stock `no-local-version` scheme to avoid wall-clock dirty dates. The display
identity is separate from package ordering: it is SemVer-shaped but is not a
release number to pass to an installer. Release `VERSION` overrides control
package metadata, not observed source identity. A small
[Hatch build hook](https://hatch.pypa.io/1.13/plugins/build-hook/custom/) embeds
`_build_provenance.json`; source-distribution rebuilds retain that snapshot.
No current timestamp is included. Identical source observations and package
versions produce identical provenance JSON. The installed-package smoke tests
check its retention and CLI agreement for wheels, source distributions, Debian
packages and container images.

## Walk-hallway results

capability-verifier grades walk-hallway trials one per result and stores each decision
in the bundle, with the failed checks' structured fields
`{check, observed, limit, unit, t, seed, wall}`. Its run assessment gives k of N, the
Wilson 95% interval, the required passes and the run grade; the report keeps them as a
`summaries` entry per run.

    livingproof-capability-report render bundle/manifest.json --format markdown -o summary.md

writes a PR-comment summary in Art's layout. It starts with a stable
`<!-- livingproof-verification -->` marker so CI can update one comment in place. Then it gives
a header (scenario, N, speed, pass bar, lock sha), a grade table, a plain verdict and
"Why runs failed" bullets (each seed counted once, under its first failure). Per-seed tables
are in `<details>`, followed by a footer. Thumbnails appear only when results carry
`provenance.assets`. `--report-url`, `--clips-url` and `--lock-diff-url` add a links row.

`livingproof-capability-report comment --repo OWNER/NAME --pr N reports/*/report.md` posts the
rendered markdown as one pull-request comment under `<!-- livingproof-capability-report -->`,
updating that comment in place on later runs. It uses `GITHUB_TOKEN` (needs
`pull-requests: write`) and the REST API directly; `--dry-run` posts nothing.

`render MANIFEST --evidence-links FILE` (repeatable; bundle 1.1.0 manifest only) stores
evidence links in the report under `evidence_links`, outside the source bundle, so no
digest or grade changes. This file is the one caller input for evidence paths:

```json
{"run": "https://github.com/OWNER/REPO/actions/runs/1",
 "links": [
   {"label": "logs", "path": "evidence/logs.txt", "kind": "log"},
   {"label": "MCAP", "path": "evidence/seed-01.mcap", "kind": "mcap", "seed": 1, "status": "PASS"},
   {"label": "video", "path": "evidence/seed-01.mp4", "poster": "evidence/seed-01.jpg",
    "why": "Typical pass", "kind": "video", "seed": 1, "status": "PASS"},
   {"label": "coverage", "path": "evidence/coverage.txt", "kind": "note"},
   {"label": "video", "path": "evidence/seed-04.mp4", "kind": "video",
    "seed": 4, "status": "FAIL", "expired": true}]}
```

`path` is a relative site path (or a site-root path such as `/runs/current/evidence/log.txt`).
The public page copies that string into `href` or, for a live video, into the player
`src`. It is not joined to a hidden base and it is not rewritten. `poster` and `why`
are optional and appear only when present; the reporter does not choose which videos
to feature and does not write a coverage sentence of its own. Kinds are `log`, `mcap`,
`video`, `note` and `artifact`. An optional https `url` is kept in `report.json`. When
that url is a GitHub Actions artifact address, the public page does not show it or the
word artifact. Entries with an empty URL, no path and no expired flag are dropped.

Set `"expired": true` on a file the site has pruned. The page then shows a
success-framed state, `Evidence kept for N days`, and does not link or play that file.
Pass the same `N` the site uses to prune, once, with `--evidence-retention N`. The
reporter has no default and will not render an expired file without it. The same value
is the note on live evidence. For example, `--evidence-retention 7` reads "Evidence
kept for 7 days" and `--evidence-retention 30` reads "Evidence kept for 30 days".

`--history-href` and `--history-label` add one navigation slot on the HTML page, so the
styled report can be published with no wrapper around it. Href is a relative site path
or an https URL, rendered exactly. Omit both and the page has no slot; the reporter
does not invent a link. Supplying only one of them is an error.

```
livingproof-capability-report render bundle/manifest.json --format html -o report.html \
  --evidence-links links.json --evidence-retention 7 \
  --history-href ../ --history-label "Run history"
```

These three flags also apply when rendering a saved `report.json` to HTML, except
`--evidence-links`, which still applies only while reading a bundle 1.1.0 manifest.
Absent flags keep the previous render, except that a public page no longer shows a
GitHub Actions artifact address. Markdown still lists a stored https url when no
`path` was supplied, so an existing links file keeps its pull-request text. Rendering
refuses a per-trial link whose status disagrees with the stored decision for that seed.
