"""Reporter #98: readable provenance labels keep exact commit destinations."""

import copy
import json
import re
from html import escape
from html.parser import HTMLParser

import pytest

from livingproof_capability_report.core import html_summary, render
from test_hallway import example, stored

SPEC_REPO = "https://github.com/Living-Proof-Labs/robot-capability-specs"
VERIFIER_REPO = "https://github.com/Living-Proof-Labs/capability-verifier"
SPEC_SHA = "abcdef1234567890abcdef1234567890abcdef12"
ASSESSOR_SHA = "1234567890abcdef1234567890abcdef12345678"
HEX = re.compile(r"\b[0-9a-fA-F]{7,40}\b")


class Content(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.text = ""
        self.links = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("aria-label", "alt"):
            assert not HEX.search(attrs.get(key, ""))
        if tag == "a":
            self.links.append(attrs)

    def handle_data(self, text):
        self.text += text


@pytest.mark.parametrize(
    "tag,version,label",
    [
        ("v2.3.0", "2.4.0", "v2.4.0"),
        ("", "", "commit"),
        ("", "0.0.0", "commit"),
        (SPEC_SHA, "0.0.0+g1234567890", "commit"),
    ],
)
def test_summary_commit_labels_and_exact_links(tag, version, label):
    report = {
        "summaries": [
            {
                "grade": "PASS",
                "spec": {
                    "repository": SPEC_REPO,
                    "tag": tag,
                    "commit": SPEC_SHA,
                    "revision": "1.0.0",
                },
            }
        ]
    }
    bundle = {
        "producer": {
            "id": "capability-verifier",
            "version": version,
            "commit": ASSESSOR_SHA,
        }
    }
    before = copy.deepcopy((report, bundle))
    markup = html_summary(report, bundle, lambda value: escape(str(value), quote=True))
    content = Content(markup)
    assert not HEX.search(content.text), content.text
    assert f">{tag if tag and not HEX.search(tag) else 'commit'}</a>" in markup
    assert f">{label}</a>" in markup
    assert {link["href"] for link in content.links} == {
        f"{SPEC_REPO}/commit/{SPEC_SHA}",
        f"{VERIFIER_REPO}/commit/{ASSESSOR_SHA}",
    }
    assert (report, bundle) == before


@pytest.mark.parametrize("tag", ["v1.6.0", ""])
def test_markdown_catalog_links_and_json_provenance(tmp_path, tag):
    report = stored(example(tmp_path))
    for summary in report["summaries"]:
        summary["spec"]["tag"] = tag
    before = render(report, "json")
    markdown = render(report, "markdown")
    footer = markdown.split("<sub>Policy", 1)[1]
    content = Content(footer)
    assert not HEX.search(content.text), content.text
    spec = report["summaries"][0]["spec"]
    assert f">{tag or 'commit'}</a>" in footer
    assert f"{spec['repository']}/commit/{spec['commit']}" in footer
    assert render(report, "json") == before
    assert json.loads(before)["source_bundle"]["results"][0]["spec"]["commit"] == spec["commit"]


def test_links_escape_stored_fields_and_do_not_invent_unknown_repositories():
    from livingproof_capability_report.provenance import commit_link

    reference = {"repository": SPEC_REPO, "commit": SPEC_SHA, "tag": 'v2.3.0<"&'}
    content = Content(commit_link(reference))
    assert content.text == reference["tag"]
    assert content.links[0]["href"] == f"{SPEC_REPO}/commit/{SPEC_SHA}"
    for repository in ("javascript:alert(1)", "https://github.com.evil.test/org/repo"):
        assert not Content(commit_link(dict(reference, repository=repository))).links
    unknown = {"id": "other-verifier", "version": "1.0.0", "commit": ASSESSOR_SHA}
    assert not Content(commit_link(unknown, assessor=True)).links
    assert ASSESSOR_SHA not in Content(commit_link(unknown, assessor=True)).text


def test_explicit_assessor_tag_wins_over_version():
    from livingproof_capability_report.provenance import commit_link

    markup = commit_link(
        {
            "id": "capability-verifier",
            "version": "0.0.0",
            "tag": "v2.4.1",
            "commit": ASSESSOR_SHA,
        },
        assessor=True,
    )
    assert Content(markup).text == "capability-verifier@v2.4.1"
    assert Content(markup).links[0]["href"] == f"{VERIFIER_REPO}/commit/{ASSESSOR_SHA}"


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("tagged", [True, False], ids=["tagged", "untagged"])
def test_rendered_provenance_at_phone_and_desktop_width(tmp_path, width, tagged):
    from pathlib import Path

    from livingproof_capability_report.core import digest
    from test_evaluator_cards import _chromium

    report = stored(example(tmp_path))
    if not tagged:
        for summary in report["summaries"]:
            summary["spec"]["tag"] = ""
        report["source_bundle"]["producer"]["version"] = "0.0.0"
        report["source_bundle_sha256"] = digest(report["source_bundle"])
    before = render(report, "json")
    manager, browser = _chromium()
    try:
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.set_content(render(report, "html"))
        page.locator("summary[role=tab]").first.click()
        summary = page.locator("#summary")
        summary.wait_for(state="visible")
        assert not HEX.search(summary.inner_text())
        for value in page.locator("[aria-label], [alt]").evaluate_all(
            "nodes => nodes.flatMap(node => [node.getAttribute('aria-label'), node.getAttribute('alt')])"
        ):
            assert not HEX.search(value or "")
        spec = report["summaries"][0]["spec"]
        producer = report["source_bundle"]["producer"]
        for repository, sha, label in (
            (SPEC_REPO, spec["commit"], spec["tag"] if tagged else "commit"),
            (VERIFIER_REPO, producer["commit"], "v1.3.2" if tagged else "commit"),
        ):
            anchor = summary.locator(f'a[href="{repository}/commit/{sha}"]')
            assert anchor.inner_text() == label
            assert anchor.get_attribute("title") == sha
        assert summary.evaluate("node => node.scrollWidth <= node.clientWidth")
        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        name = f"issue98-{'tagged' if tagged else 'untagged'}-{width}"
        page.screenshot(path=str(artifacts / f"{name}.png"))
        summary.screenshot(path=str(artifacts / f"{name}-summary.png"))
        assert render(report, "json") == before
    finally:
        browser.close()
        manager.stop()
