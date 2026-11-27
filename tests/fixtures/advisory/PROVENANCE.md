# Advisory fixtures

`battery-thermal/result.json` and `battery-thermal/notes.txt` are vendored from
livingproof-evaluator tag v1.10.0, commit
d46062a9300611e32ad76749e67a8f035489ebce
(`examples/advisory/battery-thermal/`).

- `battery-thermal/result.json` sha256 b1d66c7c005d471972857c9716377d9303245b1a7ff3394ba2758d509898c3e5
- `battery-thermal/notes.txt` sha256 672452afe3c3af41a8580455addb04c6e6696ce19e3117e4446a962fb448d7bc

`schema/` is the evaluator-result schema closure from that same tag and commit
(`schema/evaluator-result.schema.json` and the files it references).

`gait-noise/result.json` is a made-up advisory evaluator with its own id, title
and purpose. It is not from livingproof-evaluator. It validates against that
schema, and it shows a second result renders as its own card with no reporter
change.

`no-media/not-run.json` is a made-up `advisory_not_run` record, keyed by
`no-media`. A missing recording is a refusal, not an exit-0 result.
