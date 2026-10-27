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

## Publication status

The public manual is not yet enabled or verified. See the
[Pages activation plan](../.github/PAGES.md) for the exact approval boundary.
Only after live verification should the README link prominently to the public
manual and the organization documentation directory include it. Related tooling:
[Livingproof manual](https://docs.livingprooflabs.com/livingproof/).
