# Python API

The supported import surface includes the operations exported through
`livingproof_capability_report.__all__`: `load_bundle`, `validate_bundle`,
`aggregate`, `report_from_bundle` and `render`, plus the `EvaluatorPresentation` type. Their installed signatures and
docstrings are generated below. Internal helpers and the internal Click
implementation are not additional supported library interfaces. Install the
reporter package using the [release instructions](../README.md#install-a-release).

```python
from livingproof_capability_report import load_bundle, render, report_from_bundle

loaded = load_bundle("examples/bundle/manifest.json")
saved = report_from_bundle(loaded)
html = render(saved, "html")
```

Run this example from a checkout containing the example bundle, a walk-hallway run
written by capability-verifier. It produces 20 stored trial decisions (12 PASS, 8 FAIL)
and one run summary graded FAIL by the verifier. Those grades describe the example
evidence, not a test runner outcome or robot safety certification. `render(saved)`
defaults to lossless JSON; `render(saved, "html")` formats stored decisions without
regrading, with the run summary, policy and grade revision shown above the trial table
(see [what the HTML report shows](../README.md#what-the-html-report-shows)). See [bundle and grading contract](../README.md#bundle-and-grading-contract)
for validation, provenance and compatibility limits.

`validate_bundle` validates a decoded manifest without checking evidence bytes;
`load_bundle` reads a local manifest and its declared evidence. `aggregate` takes
result records and groups exact contexts without grading. `report_from_bundle` builds
the report from a bundle 1.1.0's stored decisions and run assessment; it computes no
grade and refuses a bundle without decisions. Invalid input can raise `ValueError`;
filesystem errors remain ordinary Python exceptions. These descriptions do not
relax the underlying validation or add automatic fetching or archive extraction.

## Optional advisory contributions

`render(report, "html", evaluator_presentations=[...])` accepts up to 16
`EvaluatorPresentation` instances. This is a presentation API, not an evaluator
result schema or a grading input. The caller first validates the source payload,
its provenance and its trial bindings. The renderer checks that each contribution
names the report's `source_bundle_sha256`; that equality is not an attestation.
It never reads files or fetches URLs on behalf of a contribution.

```python
from livingproof_capability_report import EvaluatorPresentation, render

advisory = EvaluatorPresentation(
    id="recording-notes",
    title="Recording notes",
    version="1.0.0",
    purpose="Describe the recorded samples; no verdict is assigned.",
    details="The observation source contains no robot health telemetry.",
    source_bundle_sha256=saved["source_bundle_sha256"],
    details_href="observations.json",
)
html = render(saved, "html", evaluator_presentations=[advisory])
```

The versioned wire object has exactly these constructor fields plus explicit
`format: "livingproof-evaluator-presentation/1"` and `state: "advisory"`.
Use `EvaluatorPresentation.from_dict(document)` to decode it. Unknown fields,
formats and states are refused. The id is a lowercase slug of at most 64
characters; title, version, purpose and details are nonempty plain text, bounded
at 80, 64, 400 and 2000 characters respectively. Text is escaped, never executed.
`details_href` is optional and permits only a relative JSON or text file path
with plain alphanumeric, underscore and hyphen segments; no traversal, schemes,
queries or fragments. The publisher remains responsible for validating and safely
retaining that referenced file. No arbitrary HTML, JavaScript, icons, grades or
findings are accepted by this API.

Each contribution appears as an independent peer with a neutral **Advisory** cue,
no pass/fail pip, no grade, and no invented evaluation timestamp. Its details use
the same disclosure and keyboard controls as other peers. The common strip wraps
on narrow screens when contributions are present. Duplicate ids or collisions
with existing evaluator identities fail rather than replace a sibling.

Omit the argument (or supply an empty list) for the existing rendering path, with
no placeholder. Contributions do not mutate the report, its source bundle or the
stored Scenario and Run Integrity results. They are HTML-only; supplying a
nonempty list for another format raises `ValueError`. Preserve the original
portable report and evidence when generating a site page with contributions.

## Caller-pinned replay assets

`render(report, "html", trusted_viewers=[TrustedViewer(...)], asset_root=path)`
can place a trusted static viewer inside an existing advisory evaluator panel.
This optional caller input is separate from evaluator results. The caller chooses,
verifies and stages immutable released executable bytes; never construct these pins
from evaluator-provided URLs or code. Reporter does not download assets.

Each `TrustedViewer` declares `evaluator_id`, `evaluator_version`,
`evaluator_publisher`, `viewer_href`, `viewer_sha256` and `recording_format`.
The first three must match exactly one advisory result. `viewer_href` is a local
HTML path. The caller stages the report's original JSON details file in the asset
root and an identical copy at `data/recording.json` beside that viewer.
Reporter checks bounded local files, refuses symlinks, verifies both hashes and
requires exactly one recording trial matching the selected report observation,
run, configuration and positive integer trial index (booleans are not indices).
The recording envelope has `format` and `trials`; its sole trial has the same
`format` and a `trial` identity with `run_id`, `configuration`, `index` and
`observation_sha256`. This is an explicit viewer input compatibility requirement,
not a change to the evaluator result schema.

The iframe receives only the adjacent JSON path, published digest and selected
identity in its fragment. The trusted viewer must independently verify those bytes
before displaying data. It runs scripts on the reports origin: the sandbox is not
an isolation boundary against a malicious caller-selected executable. Only pin
reviewed code approved for that origin. Missing JavaScript retains the existing
Recorded data link. No declaration leaves HTML unchanged; an absent evaluator
adds no panel. A matching evaluator with invalid assets or ambiguous identity
fails before output. No portable report, evidence, grade or evaluator result changes.

The existing CLI accepts a caller-owned JSON list of these field objects:

```sh
livingproof-capability-report render report.json --format html \
  --trusted-viewers trusted-viewers.json --asset-root ./report-assets \
  --output ./report-assets/index.html
```

Use a new output path. Run the normal upstream report generation before this
step; a stale source-bundle digest remains an error, not a repair instruction.
This interface does not change site history, navigation, restoration or deployment.
