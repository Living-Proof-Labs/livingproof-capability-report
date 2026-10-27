# Contribute

Read [collaboration-guidelines v6.0.0](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v6.0.0/AGENTS.md)
and its linked procedures at that version, alongside this repository's
[working agreement](AGENTS.md). Guidance is deliberately pinned to v6.0.0;
the release workflow remains pinned to v3.0.0 to preserve the separately tested
release/package process. Updating guidance does not upgrade release automation.

Use an isolated checkout and a focused pull request. In the prepared Python 3.12
or development-container environment, run `task setup` and `task verify`.
Run `task docs:verify` for manual changes. The generated Task reference describes
commands; [verification](docs/verification.md) explains preview extraction and
installed-package checks. Host wrappers `task dev:build`, `task dev:verify` and
`task dev:docs` require Docker on the host. Inside the development container use
`task setup`, `task verify` and `task docs:verify` directly, without nested Docker.

Keep collection, aggregation, grading and rendering separate. Retain original
results and provenance. Never imply robot safety certification. Consumers do not
need a checkout or Task; Python environments must respect system-managed Python.
Independent review should exercise the delivered artifact, with reproducible
results, before merge. Preserve existing published paths and fragments.

## Help / report an issue

Use [repository issues](https://github.com/Living-Proof-Labs/livingproof-capability-report/issues)
for nonsensitive questions or reproducible problems. Include the command, both
version output lines, expected and actual behavior, and a small sanitized example.
Do not include credentials or private evidence. This repository does not currently
document a private security-reporting destination; public issues are not a place
for sensitive vulnerability details. No private support channel is promised.

## Scope and licensing

The reporter owns its bundle, grading and rendering contracts. See
[Documentation home](https://docs.livingprooflabs.com/) for other manuals and
[licensing](docs/license.md) for applicable terms. Current manual and source-directory
links are reading aids; the exact adopted guidance above remains authoritative.
