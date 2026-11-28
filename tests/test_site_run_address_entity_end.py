# SPDX-License-Identifier: Apache-2.0
"""A run address inside HTML-escaped text ends at the entity that closes it (#84 L3).

The reporter embeds its report JSON, HTML-escaped, in a details block of the run page:
``&quot;run&quot;: &quot;https://github.com/o/r/actions/runs/1&quot;``. Treating ``&quot;`` as a
suffix removed the address and the closing quote, which truncated that JSON on the published
page. ``&amp;x=1`` and ``&#47;job`` are still suffixes.

Ported from verification-reports-action tests/test_run_address_entity_end.py (va PR 84, head a27a1a0).
"""

from pathlib import Path

import pytest

from livingproof_capability_report.site import assemble as site
from test_site import ROOT, _make_run_folder

OWNER_REPO = "Living-Proof-Labs/verification-reports-action"
RUN = f"https://github.com/{OWNER_REPO}/actions/runs/46110994356"


@pytest.mark.parametrize("entity", ["&quot;", "&#x27;", "&#39;", "&lt;", "&gt;"])
def test_a_run_address_closed_by_an_html_entity_is_kept(entity: str):
    text = f"<pre>&quot;run&quot;: &quot;{RUN}{entity}\n</pre>"
    assert site.strip_actions_text(text, repository=OWNER_REPO) == text
    assert not site.mentions_actions(text, repository=OWNER_REPO)


@pytest.mark.parametrize("suffix", ["&amp;x=1", "&#47;job&#47;2", "&amp;", "&quot", "&#x27"])
def test_a_run_address_followed_by_another_entity_is_still_a_near_miss(suffix: str):
    text = f"<p>{RUN}{suffix}</p>"
    assert site.mentions_actions(text, repository=OWNER_REPO)
    assert RUN not in site.strip_actions_text(text, repository=OWNER_REPO)


def test_the_embedded_report_json_on_a_real_run_page_keeps_its_run_address(tmp_path: Path):
    # The real G1 report of Verify run 46110994356 (reporter 3.17.0).
    fixture = ROOT / "tests/fixtures/reporter/report-v3.17.0-g1-evidence-links.html"
    text = fixture.read_text(encoding="utf-8")
    embedded = f"&quot;run&quot;: &quot;{RUN}&quot;"
    assert embedded in text
    media = {"video/trial-01-fail.mp4": b"mp4", "mcap/mcap/trial-01.mcap": b"mcap"}
    _make_run_folder(
        tmp_path / "in",
        "hallway",
        run_id="46110994356",
        html_override=text,
        evidence_files=media,
        caller=OWNER_REPO,
    )
    site.build(tmp_path / "reports", tmp_path / "in", repository=OWNER_REPO)
    run = next((tmp_path / "reports").glob("*/*/runs/46110994356"))
    for name in ("index.html", "report.html"):
        assert embedded in (run / name).read_text(encoding="utf-8"), name


def test_the_embedded_lossless_report_json_survives_intact(tmp_path: Path):
    # Vera's manual check of Verify runs 46115314157 and 46118968220: the details
    # block that holds the HTML-escaped report JSON must be published uncut.
    fixture = ROOT / "tests/fixtures/reporter/report-v3.17.0-g1-evidence-links.html"
    text = fixture.read_text(encoding="utf-8")
    start = text.find("<details class='lossless'>")
    end = text.find("</details>", start)
    assert start != -1 and end != -1
    block = text[start : end + len("</details>")]
    assert f"&quot;run&quot;: &quot;{RUN}&quot;" in block
    media = {"video/trial-01-fail.mp4": b"mp4", "mcap/mcap/trial-01.mcap": b"mcap"}
    _make_run_folder(
        tmp_path / "in",
        "hallway",
        run_id="46110994356",
        html_override=text,
        evidence_files=media,
        caller=OWNER_REPO,
    )
    site.build(tmp_path / "reports", tmp_path / "in", repository=OWNER_REPO)
    run = next((tmp_path / "reports").glob("*/*/runs/46110994356"))
    for name in ("index.html", "report.html"):
        assert block in (run / name).read_text(encoding="utf-8"), name
