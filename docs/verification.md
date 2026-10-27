# Verification and manual previews

Run `task setup`, `task verify`, then `task docs:verify` in the prepared
Python environment or the existing Docker development container. The same locked
Zensical and mkdocs-click tools are used by Task, Docker and the devcontainer.
No documentation tools are added to the runtime image. Host command `task dev:docs`
executes the same verification inside the shared development target; development
CI runs it on both native architectures. The documentation workflow uses an
equivalent prepared Python 3.12 environment with the same uv/Task pins and lock.

`task docs:verify` builds a wheel, installs it into an isolated target, exercises
named scenarios through that installed CLI from a temporary working directory,
and generates the manual and its command reference from that same installation.
The module-origin check rejects accidental source imports. Runtime dependencies
come from the locked development environment. This is an installed-wheel check,
not a clean OS, Debian, Docker runtime or network-installation check; those remain
in the existing package/smoke pipeline.

Download the documentation preview from the documentation workflow's artifacts
(retained **14 days**). Extract it and serve `docs/html/` with
`python -m http.server 8000 --directory docs/html --bind 127.0.0.1`, then visit
<http://127.0.0.1:8000/>. Browser assets and search require HTTP; opening a local
file is not the supported preview path.

The manual renders this repository's README, this guide and working agreement
from their canonical Markdown. Command options and nested commands are derived
from the installed Click group; terminal help is captured from that installation.
Task reference comes from `task --list --json` and `task --summary`.
Build provenance records source revision/dirty state, wheel digest, canonical
source digests and the CI run. Historical version manuals are not maintained;
consult the corresponding source tag for released behavior.

## Initial feature inventory and gaps

The initial scenarios are ordinary pytest cases with Given/When/Then docstrings.
Those same docstrings generate the behavior pages; JUnit supplies actual outcomes.
Stable case names identify validation, grading with retained failure evidence,
rendering stored decisions and invalid-input rejection. Missing cases are marked
UNTESTED; skipped cases are never counted as passes. Malformed or incomplete
JUnit fails documentation verification. No exhaustive feature percentage is claimed.

Existing tests cover policy/revision handling, examples, input guidance, terminal
rendering, version identity and plugin mounting. The bounded installed scenarios
do not cover all these contracts: human revision workflows, nested umbrella
installation, all export formats, architectures and distribution installations
remain outside this initial scenario inventory. Existing regression and package
checks remain required. No line coverage measurement is generated; scenario
outcomes are software verification, not robot capability or safety certification.

Individual scenarios and documentation checks appear in the CI job summary, with
raw JUnit retained even after failure. Failure keeps the workflow red. Browser
navigation, mobile layout, search-result opening and theme behavior still require
independent artifact review; static checks do not establish browser usability.
The parent independent reviewer must exercise the delivered preview before merge.

<a id="publication-status"></a>

## Published manual

Start with the [reporter manual](https://docs.livingprooflabs.com/livingproof-capability-report/).
Live browser verification on 2026-10-27 confirmed source revision
`fa1a4e708f3d1330667967fe420adcdf18cbb8ef`, command reference, four passing bounded
scenarios, navigation, search for `manifest` (19 results), navigation to the grade
anchor and reload, and dark theme. This records that deployed snapshot; it does
not establish that every installed release has the same behavior.

See [Pages operation](../.github/PAGES.md) for deployment boundaries and repeat
live verification after delivery. Related tooling:
[Livingproof manual](https://docs.livingprooflabs.com/livingproof/).

## Recipe adoption scope

The manual applies the released v6.0.0 documentation recipe. Authored Markdown
remains canonical; generated API, Click, Task and scenario pages describe the
installed candidate and observed results. The five functions in the package's
`__all__` are its public Python API; internal helpers are outside that interface.
Public API signatures and docstrings are inspected from the same installed wheel
as the command reference. The original published HTML paths and heading anchors
are retained and checked against the initial live-manual inventory.

The reporter continues to own bundle schemas, grading policies and rendering
contracts. Organization vision and the full manual directory belong to
[Documentation home](https://docs.livingprooflabs.com/); this adoption moves no
organization content. Common navigation and current rendered-manual links are
bounded reading exceptions, not floating executable dependencies or guidance.
