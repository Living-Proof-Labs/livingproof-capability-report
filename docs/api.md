# Python API

The supported import surface is the five operations exported through
`livingproof_capability_report.__all__`: `load_bundle`, `validate_bundle`,
`aggregate`, `grade` and `render`. Their installed signatures and docstrings are
generated below. Internal helpers and the internal Click implementation are not
additional supported library interfaces. Install the reporter package using the
[release instructions](../README.md#install-a-release).

```python
from livingproof_capability_report import load_bundle, grade, render

loaded = load_bundle("examples/bundle/manifest.json")
saved = grade(loaded)
html = render(saved, "html")
```

Run this example from a checkout containing the documented producer bundle. It
produces eight stored coordinate decisions across four exact contexts, including
PASS, FAIL and INSUFFICIENT_EVIDENCE. Those grades describe the fixture evidence,
not a test runner outcome or robot safety certification. `render(saved)` defaults
to lossless JSON; `render(saved, "html")` formats stored decisions without regrading.
See [bundle and grading contract](../README.md#bundle-and-grading-contract) and
[assessment revisions](../README.md#retain-human-reviews-as-grade-revisions) for
policy, validation, provenance and compatibility limits.

`validate_bundle` validates a decoded manifest without checking evidence bytes;
`load_bundle` reads a local manifest and its declared evidence. `aggregate` takes
result records and groups exact contexts without grading. `grade` returns a new
report without discarding original results. Invalid input can raise `ValueError`;
filesystem errors remain ordinary Python exceptions. These descriptions do not
relax the underlying validation or add automatic fetching or archive extraction.
