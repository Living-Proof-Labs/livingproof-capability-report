"""Pruned evidence says it expired (livingproof-verification#54, Rivet's 16 Nov decision).

A live file keeps "Evidence kept for N days". An ``expired: true`` entry reads
"Evidence expired after N days" with class ``is-expired`` in all four places: the
trial chip, the Evidence card note (when every file is gone), each item, and the
item's class. N still comes only from the caller's retention value.
"""

import re

import pytest

from livingproof_capability_report.core import render
from test_publish import example, stored

MIXED = {
    "links": [
        {"label": "logs", "path": "evidence/run.log", "kind": "log"},
        {
            "label": "video",
            "path": "evidence/seed-01.mp4",
            "kind": "video",
            "seed": 1,
            "status": "PASS",
        },
        {
            "label": "video",
            "path": "evidence/seed-04.mp4",
            "kind": "video",
            "seed": 4,
            "status": "FAIL",
            "expired": True,
            "why": "Worst side-wall contact",
        },
    ]
}

PRUNED = {
    "links": [
        {"label": "logs", "path": "evidence/run.log", "kind": "log", "expired": True},
        {
            "label": "video",
            "path": "evidence/seed-01.mp4",
            "kind": "video",
            "seed": 1,
            "status": "PASS",
            "expired": True,
        },
    ]
}


@pytest.mark.parametrize("retention", [7, 30])
def test_an_expired_item_says_expired_and_a_live_run_keeps_the_kept_note(tmp_path, retention):
    page = render(stored(example(tmp_path), [MIXED]), "html", retention=retention)
    expired = f"Evidence expired after {retention} days"
    items = re.findall(r"<li class='is-expired'>.*?</li>", page, re.S)
    assert len(items) == 1
    assert expired in items[0] and "Worst side-wall contact" in items[0]
    assert "<li class='is-kept'>" not in page
    assert "src='evidence/seed-04.mp4'" not in page
    # Live files are still on the site: the card note keeps the kept-for wording.
    assert f"<p class='evidence-kept-note'>Evidence kept for {retention} days</p>" in page
    # Trial chip for the pruned seed.
    assert re.search(rf"<span class='evidence-expired'>[^<]*{expired}</span>", page)
    assert "<span class='evidence-kept'>" not in page


def test_a_fully_pruned_run_never_says_kept(tmp_path):
    page = render(stored(example(tmp_path), [PRUNED]), "html", retention=7)
    assert "Evidence kept for" not in page
    assert "<li class='is-kept'>" not in page and "class='evidence-kept'" not in page
    assert "<p class='evidence-expired-note'>Evidence expired after 7 days</p>" in page
    assert len(re.findall(r"<li class='is-expired'>", page)) == 2
    assert "href='evidence/run.log'" not in page


def test_markdown_names_the_expired_file_as_expired(tmp_path):
    text = render(stored(example(tmp_path), [MIXED]), "markdown", retention=7)
    assert "video (Evidence expired after 7 days)" in text
    assert "Evidence kept for 7 days" not in text
