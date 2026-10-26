# Living Proof Labs capability report

[![Tests, builds and compatibility](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/Living-Proof-Labs/livingproof-capability-report/actions/workflows/verify.yml)
[![Latest release](https://img.shields.io/github/v/release/Living-Proof-Labs/livingproof-capability-report)](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases/latest)
[![License](https://img.shields.io/github/license/Living-Proof-Labs/livingproof-capability-report)](LICENSE)

An installable Python library and thin Click command group for portable capability
results. Validate evidence bundles, grade under an explicit versioned policy, and
render stored decisions as lossless JSON, offline HTML or explicitly flattened CSV.
This is a deterministic fixture demonstration, not robot safety certification.
No server, simulator, source checkout or Task installation is needed by consumers.

## Install a release

Download the wheel or Debian package and `SHA256SUMS` from
[Releases](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases).
The Debian package is `Architecture: all`: it ships only pure-Python reporter
files and metadata. Apt installs architecture-appropriate `python3-click` and
`python3-jsonschema` dependencies. All files are managed by dpkg; no pip writes
into system Python, private interpreter, native wheel or vendored virtual
environment is included. The native support matrix is documented below.

```sh
sudo apt install ./livingproof-capability-report_1.2.0_all.deb
livingproof-capability-report --help
```

Alternatively, use a Python 3.11+ virtual environment (never system-wide pip):

```sh
python3 -m venv .venv
.venv/bin/pip install ./livingproof_capability_report-1.2.0-py3-none-any.whl
.venv/bin/livingproof-capability-report --help
```

The wheel installer resolves dependencies normally; the architecture-specific downloadable wheelhouse targets CPython 3.12 and
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
livingproof-capability-report grade examples/bundle/manifest.json -o report.json
livingproof-capability-report render report.json
livingproof-capability-report render report.json --format html -o report.html
livingproof-capability-report render report.json --format csv -o report.csv
```

`validate` checks the manifest structure and evidence digests; `grade` saves the
policy decisions; `render` displays the saved report (a terminal table by default).
For your own portable bundle, replace `examples/bundle/manifest.json` with its
manifest path. Installed packages do not require a checkout to report your bundle.

The **manifest** describes the results, contract versions, assessments and
relative evidence paths with their digests. An **observation**, such as
`examples/bundle/evidence/pass.json`, contains measurements referenced by that
manifest. It is not standalone reporter input: pass the manifest to `validate`
and `grade`, and the generated report to `render`. Do not add `schema_version`
to observation files to make them look like manifests. Keep the evidence files
at the relative paths declared by their manifest.

Outputs must be new files. Rendering never invokes grading or silently substitutes
a newer policy. JSON retains the entire source manifest, original producer
results, assessments, evidence references, contributed human assessments,
integrity observations, exact-context groups and stored decisions. Evidence bytes
stay in the portable bundle. HTML is self-contained, escaped, script-free and
usable offline. CSV is deliberately flattened: one decision per row, with
spreadsheet-formula protection; it is not a round-trip representation.

Importable API:

```python
from livingproof_capability_report import load_bundle, grade, render
saved = grade(load_bundle("examples/bundle/manifest.json"))
html = render(saved, "html")
```

The installed distribution advertises `livingproof_capability_report.cli:report`
as `report` in the `livingproof.capability.commands` entry-point group. A compatible
umbrella can mount that same Click group as `livingproof capability report` when
both packages are installed in the same Python environment. Neither library
depends on the other; the standalone command and Python API remain unchanged.
Version v1.3.0 predates this metadata; it remains usable standalone.

## Bundle and grading contract

Version 1.0.0 manifests use the packaged `bundle.schema.json`. Each result includes
an identifier, released catalog tag and commit, capability/revision, system and
environment versions, relative evidence paths with SHA-256 digests, assessments,
provenance and the original producer result. Unknown extension fields are retained.
Duplicate JSON keys, non-finite numbers, undeclared evidence references, absolute
paths, traversal and symlinks are rejected. URLs are never fetched. Digests detect
changed bytes; they do not authenticate who produced the evidence.

Policy `all-required-v1@1.0.0` supports the exact catalog versions below and declared
evaluator versions: pause-rules 1.0.0/1.1.0, mock-ai 1.0.0 and human-fixture 1.0.0.
Mock-agent results are scripted fixtures, not model calls. Exactly one assessment
from each member is required; the deterministic assessment must be mandatory.
An observed failure wins even if another member or evidence is missing. Otherwise,
missing/changed evidence, missing/duplicate members or insufficient assessments
remain INSUFFICIENT_EVIDENCE. Unsupported contracts, evaluators or policies are
INCOMPATIBLE, not failures. There is no averaging and no overall numeric score.
Aggregation groups exact spec, system and environment contexts separately from grading.

## Compatibility evidence

The example bundle is produced by
[capability-verifier v1.1.0](https://github.com/Living-Proof-Labs/capability-verifier/tree/v1.1.0).
It preserves the existing producer behavior from v1.0.2 and adds portable export.
The catalog's original v1.1.1 and additive v1.2.0 releases contain different contracts;
the strict revision does not replace or relabel the original fixtures.

| Catalog / pause revision | Fixture version / observation | Stored grade |
| --- | --- | --- |
| [v1.1.1](https://github.com/Living-Proof-Labs/robot-capability-specs/tree/v1.1.1) / 1.0.0 (500 ms) | 1.0.0 / 120 ms | PASS |
| [v1.2.0](https://github.com/Living-Proof-Labs/robot-capability-specs/tree/v1.2.0) / 2.0.0 (250 ms) | 1.0.0 / 120 ms | PASS |
| v1.1.1 / 1.0.0 | 2.0.0 / 300 ms | PASS |
| v1.2.0 / 2.0.0 | 2.0.0 / 300 ms | FAIL |
| Either contract | 1.0.0 / mandatory inhibition false | FAIL |
| Either contract | 1.0.0 / elapsed time missing | INSUFFICIENT_EVIDENCE |

## Contribute a human assessment

For a result missing its human assessment, generate a separate editable file:

```sh
livingproof-capability-report human-template bundle/manifest.json \
  --result RESULT_ID -o human.json
```

Read the referenced evidence. Fill in your identity, review date, rationale and
`status` (PASS, FAIL or INSUFFICIENT_EVIDENCE) in `human.json`. Keep the result digest,
result identifier, evaluator/version and evidence identifiers unchanged. Then:

```sh
livingproof-capability-report grade bundle/manifest.json --human human.json -o reviewed.json
```

The file is bound to the exact original result digest. It is a self-declared review,
not authenticated approval. The original bundle and original assessments are retained.
This policy adds missing assessments; it does not silently replace existing reviews.
Adding a second human assessment makes membership insufficient (any retained FAIL
still wins). Resolving conflicting reviews requires a future explicit policy.
The bundled examples already include recorded human fixtures, so adding a human
review to them demonstrates duplicate handling rather than filling a missing review.

## Contributors and delivery

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

The verify job uploads JUnit results even when tests fail. Its run summary and
Reporter tests check show individual tests and failure annotations. Fork pull
requests receive the summary and artifact without a write-token check. This
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

The opt-in `all-required-v2@1.0.0` policy accepts multiple assessments for each
required role (deterministic, mock-agent and human). The default remains
`all-required-v1@1.0.0`; its membership rules and existing command exit behavior
are unchanged. Bundle, human contribution and report versions remain `1.0.0`.
No producer changes are required. Assessments retain evaluator identity/version,
assessment identifier, evidence references, rationale, status and provenance.
Mock-agent entries are fixture conclusions, never real model calls; the new
policy explicitly marks them `fixture: true` in its explanation.

The new policy supports the existing pinned pause contracts and evaluator versions,
plus `human-review@1.0.0` with nonempty, self-declared `reviewer` and `recorded_at`
provenance. It evaluates each run separately. Unsupported contracts, evaluators or
policies yield `INCOMPATIBLE`, even if a retained assessment failed; the failure
is still visible in the explanation. For supported inputs any retained failure
wins, including mandatory failures. Otherwise every declared evidence digest must
verify, all three roles must be present, every assessment must pass with evidence
references, and at least one deterministic assessment must be mandatory. There
is no majority vote or automatic replacement of dissent or insufficient reviews.

```sh
livingproof-capability-report grade bundle/manifest.json \
  --policy all-required-v2@1.0.0 -o initial.json
livingproof-capability-report human-template bundle/manifest.json \
  --result RESULT_ID --assessment-id review-2026-10-26 \
  --reviewer 'Reviewer name' --recorded-at '2026-10-26T00:00:00Z' -o human.json
# Complete the rationale and conclusion in human.json, then:
livingproof-capability-report grade bundle/manifest.json \
  --policy all-required-v2@1.0.0 --previous initial.json --human human.json \
  -o revision-2.json
```

The new report embeds the complete `previous_report` and its
`previous_report_sha256`, increments `grade_revision`, and retains cumulative
human contributions alongside the unchanged `source_bundle` and `evidence_state`.
A revision requires the same original bundle and recorded evidence integrity
labels; a change in those labels requires a separate report. These labels do not
snapshot evidence bytes (see the integrity limitation below). Contributions bind to the original
result digest, cannot introduce undeclared references, and cannot reuse an
assessment identifier within a run. Prior reports remain renderable without
regrading, including when their policy is no longer supported. These digests
identify content; they do not authenticate reviewers or sign reports.

New-policy decisions add `coordinate`, `assessment_details`, `evidence_groups`,
`mandatory_failures` and `dissent`. Evidence groups associate references with
assessment identifiers within a specific run, never combine grades across runs.
JSON and HTML retain full history. Terminal output explains current decisions;
CSV adds policy, revision, assessments and evidence groups as quoted JSON cells
for new-policy reports, while legacy CSV columns remain unchanged.

For continuous integration, `grade --require-pass` writes the report first and
then exits 1 if any coordinate is not `PASS` (including incompatibility or
insufficient evidence). Ordinary `grade` keeps its historical success-on-write
behavior. Tests exercise the nonzero path and retain its JSON, HTML, CSV and
terminal reports under `artifacts/`; both verification workflows upload artifacts
regardless of test success. Expected failing capability cases are successful tests
only when the asserted command actually fails and retains its report. Unexpected
test failures continue to fail Task and continuous integration.

The compatibility matrix producer can declare an execution mismatch through the
existing extensible provenance field, without changing bundle version:

```json
{"provenance": {"compatibility": {
  "status": "INCOMPATIBLE", "scope": "execution",
  "reason": "Released executor supports pause revision 1.0.0 only"
}}}
```

Both policies recognize this declaration before capability grading. It must have
that status/scope and a nonempty reason; malformed declarations are rejected.
Empty assessments or `original_result.status` alone do not establish execution
incompatibility. Run and fixture provenance are preserved unchanged.

Revision integrity checks compare the recorded labels (`verified`, `missing`,
`digest_mismatch`), not snapshots of evidence bytes. Different contents that both
mismatch the declared digest have the same label and can produce a linked
revision; both grades remain insufficient unless a retained failure takes
precedence. History preserves the original declared evidence digests and prior
integrity observations, but does not prove that missing or mismatched evidence
bytes stayed unchanged. Use a separate bundle/report to record changed evidence.

## Identify the version you are testing

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
