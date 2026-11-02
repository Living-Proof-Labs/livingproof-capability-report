# Python API

The supported import surface is the five operations exported through
`livingproof_capability_report.__all__`: `load_bundle`, `validate_bundle`,
`aggregate`, `report_from_bundle` and `render`. Their installed signatures and
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
regrading. See [bundle and grading contract](../README.md#bundle-and-grading-contract)
for validation, provenance and compatibility limits.

`validate_bundle` validates a decoded manifest without checking evidence bytes;
`load_bundle` reads a local manifest and its declared evidence. `aggregate` takes
result records and groups exact contexts without grading. `report_from_bundle` builds
the report from a bundle 1.1.0's stored decisions and run assessment; it computes no
grade and refuses a bundle without decisions. Invalid input can raise `ValueError`;
filesystem errors remain ordinary Python exceptions. These descriptions do not
relax the underlying validation or add automatic fetching or archive extraction.
