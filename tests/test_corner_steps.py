"""walk-corner step cards: a check whose observed value is a list of places renders.

capability-verifier v1.24.0 grades ``corner-turned`` with ``observed`` as the places the
robot passed through (``[{"place": "corner", "time": 3.88}]``) and ``threshold`` as the
places required (``["corner"]``). The HTML step card formatted every non-wall observed
value as metres, so a real walk-corner bundle failed to render HTML with
``float() argument must be a string or a real number, not 'list'``
(robot-capability-specs#40 step 12).
"""

from pathlib import Path

from click.testing import CliRunner

from livingproof_capability_report.cli import report as cli
from livingproof_capability_report.steps import _observed

CORNER = Path(__file__).parent / "fixtures/corner/g1-stock/manifest.json"


def test_a_real_walk_corner_bundle_renders_html(tmp_path):
    out = tmp_path / "report.html"
    result = CliRunner().invoke(cli, ["render", str(CORNER), "--format", "html", "-o", str(out)])
    assert result.exit_code == 0, result.output
    page = out.read_text()
    assert "corner at 3.88 s" in page
    assert "(required corner)" in page
    assert "float()" not in page


def test_list_and_text_observed_values_are_written_out_not_formatted_as_metres():
    step = {"id": "corner-turned", "kind": "other"}
    details = {
        "observed": [{"place": "corner", "time": 3.88}, {"place": "exit<b>", "time": 12.26}],
        "threshold": ["corner", "exit<b>"],
    }
    text = _observed(step, details, "PASS", {})
    assert text == ("corner at 3.88 s, exit&lt;b&gt; at 12.26 s (required corner, exit&lt;b&gt;)")
    assert _observed(step, {"observed": [], "threshold": ["corner"]}, "FAIL", {}) == (
        "none (required corner)"
    )
    assert _observed(step, {"observed": "left", "threshold": None}, "FAIL", {}) == "left"


def test_numeric_observed_values_keep_the_limit_wording():
    step = {"id": "hallway-lateral-limit", "kind": "lateral"}
    text = _observed(step, {"observed": 0.5965, "threshold": 0.49}, "FAIL", {})
    assert text == "0.5965 m (limit 0.49 m)"
