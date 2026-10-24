# Living Proof Labs capability report

An installable Python library and thin Click command group for portable capability
results. Validate evidence bundles, grade under an explicit versioned policy, and
render stored decisions as lossless JSON, offline HTML or explicitly flattened CSV.
This is a deterministic fixture demonstration, not robot safety certification.
No server, simulator, source checkout or Task installation is needed by consumers.

## Install a release

Download the wheel or Debian package and `SHA256SUMS` from
[Releases](https://github.com/Living-Proof-Labs/livingproof-capability-report/releases).
The Debian package targets Ubuntu 24.04 on amd64 and keeps dependencies in
`/opt/livingproof-capability-report`; it does not install into system Python.

```sh
sudo apt install ./livingproof-capability-report_1.0.0_amd64.deb
livingproof-capability-report --help
```

Alternatively, use a Python 3.12+ virtual environment (never system-wide pip):

```sh
python3 -m venv .venv
.venv/bin/pip install ./livingproof_capability_report-1.0.0-py3-none-any.whl
.venv/bin/livingproof-capability-report --help
```

The wheel installer resolves dependencies normally; the downloadable wheelhouse
supports offline installation with `--no-index --find-links=./wheels`. The source
archive is also attached. Release package versions come from the release tag;
there are no generated version commits. Python 3.12 on Linux is tested. Other
Python versions and platforms are not yet verified.

The release job builds `ghcr.io/living-proof-labs/livingproof-capability-report:1.0.0`
with the installed wheel and the reporting command as its entrypoint. A saved
`image.tar` is attached even if registry publication is unavailable; use
`docker load -i image.tar` before the commands below. Registry publication and
anonymous availability are separate checks; see the release job for their results.

```sh
docker run --rm -v "$PWD/bundle:/data:ro" \
  ghcr.io/living-proof-labs/livingproof-capability-report:1.0.0 validate manifest.json
```

## Report a portable bundle

```sh
livingproof-capability-report validate bundle/manifest.json
livingproof-capability-report grade bundle/manifest.json -o report.json
livingproof-capability-report render report.json --format html -o report.html
livingproof-capability-report render report.json --format csv -o report.csv
```

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
saved = grade(load_bundle("bundle/manifest.json"))
html = render(saved, "html")
```

The Click group is `livingproof_capability_report.cli.report`, ready to be attached
to a future `livingproof capability report` group. Neither package needs to depend
on the other. No root command or general plugin framework is implemented here.

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

CI attaches wheel, source archive, Debian package, dependency wheelhouse, saved image
and SHA-256 checksums. The shared release workflow is pinned to
[collaboration-guidelines v2.1.0](https://github.com/Living-Proof-Labs/collaboration-guidelines/tree/v2.1.0).
Release builds install the exact published package version. Clean containers test
wheel and Debian installations without mounting source. A normal `docker run`
tests the convenience entrypoint; a separate shell override tests the same image
as a job container. Providers can override entrypoints or require a shell; identical
startup behavior across CI providers is not claimed. JUnit expectation tests stay
separate from the capability decisions. No PyPI publication or new credentials.

Original code and fixture adaptations are Apache-2.0; see [LICENSE](LICENSE).

## Test results in GitHub

The verify job uploads JUnit results even when tests fail. Its run summary and
Reporter tests check show individual tests and failure annotations. Fork pull
requests receive the summary and artifact without a write-token check. This
provides per-run history for comparison; this integration does not implement a
historical trends dashboard or promise automatic trend correlation.
