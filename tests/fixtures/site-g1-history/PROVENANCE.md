# Real G1 history fixture

`unitree-g1/stock-mujoco-hallway/runs/45754832566/` is the published run folder of the
real Unitree G1 hallway (Verify run 45754832566), copied unchanged from
verification-reports-action `tests/fixtures/old-runs/published/production/` at 2e74cce.

`../site-golden/g1-history.SHA256SUMS` is what the action's own renderer
(`src/reports_site.py`, at both 2e74cce and PR 84 head aa14bf0) writes when this run is the
restored history and one new run is added. `tests/test_site.py` builds the same input with
the `site` package and must match it byte for byte (va#75).

`../site-golden/SHA256SUMS` is the action's `tests/fixtures/site-golden/SHA256SUMS`, copied
unchanged; `site_fixture.build_golden_site` is the action's `tools/site_golden.py` build.
