"""Artifact checks; browser and independent review are explicitly separate."""
import hashlib
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / 'artifacts/docs/html'


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])


def test_all_local_pages_assets_and_fragments():
    pages = {p.resolve(): Page(p) for p in SITE.rglob('*.html')}
    assert len(pages) >= 9
    for path, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or url.path.startswith('/'):
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= 'index.html'
            assert target.exists(), (path.name, link)
            if url.fragment and target in pages:
                assert unquote(url.fragment) in pages[target].ids, (path.name, link)


def test_installed_command_options_present():
    commands = json.loads((SITE / 'commands.json').read_text())
    html = (SITE / 'commands.html').read_text()
    assert len(commands) >= 5
    sections = re.split(r'<h[23] id="([^"]+)">', html)
    by_name = dict(zip(sections[1::2], sections[2::2], strict=True))
    for command in commands:
        section = by_name[command['name'].split()[-1]]
        for option in command['options']:
            assert option in section, (command['name'], option)


def test_provenance_and_actual_outcomes():
    record = json.loads((SITE / 'build.json').read_text())
    assert len(record['source_commit']) == 40
    for source, expected in record['sources'].items():
        assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == expected
    assert len(record['scenario_results']) == 4
    assert set(record['scenario_results'].values()) == {'PASSED'}
    wheel = ROOT / 'artifacts/docs/wheels' / record['wheel']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == record['wheel_sha256']


def test_canonical_navigation_themes_and_search_assets():
    html = (SITE / 'index.html').read_text()
    assert 'https://docs.livingprooflabs.com/livingproof-capability-report/' in html
    assert 'scenarios.html' in html and 'commands.html' in html
    assert 'Switch to dark mode' in html and 'Switch to system preference' in html
    assert any('search' in p.name for p in SITE.rglob('*') if p.is_file())
