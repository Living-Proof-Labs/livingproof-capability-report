"""Artifact checks; browser and independent review are explicitly separate."""
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
import json
import os
import re
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
from zipfile import ZipFile

import yaml

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / 'artifacts/docs/html'


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = set()
        self.links = []
        self.text = []
        self.feed(path.read_text())

    def handle_data(self, data):
        self.text.append(data)

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


def test_documented_command_serves_extracted_artifact(tmp_path):
    """Serve the documented directory from the uploaded ZIP's extraction root.

    Set REPORTER_DOCS_PREVIEW_ZIP to exercise an actual downloaded CI artifact.
    Otherwise archive the current upload selection with upload-artifact's common
    ancestor layout, so CI also catches a future upload-layout change.
    """
    archive_path = os.environ.get('REPORTER_DOCS_PREVIEW_ZIP')
    if not archive_path:
        workflow = yaml.safe_load((ROOT / '.github/workflows/documentation.yml').read_text())
        upload, = [s['with'] for s in workflow['jobs']['build']['steps']
                   if s.get('uses', '').startswith('actions/upload-artifact@')]
        files = set()
        for pattern in upload['path'].splitlines():
            for match in ROOT.glob(pattern):
                if match.is_dir():
                    files.update(p for p in match.rglob('*') if p.is_file())
                else:
                    files.add(match)
        assert files
        common = Path(os.path.commonpath(files))
        archive_path = tmp_path / 'preview.zip'
        with ZipFile(archive_path, 'w') as archive:
            for path in sorted(files):
                archive.write(path, path.relative_to(common))
    extracted = tmp_path / 'extracted'
    with ZipFile(archive_path) as archive:
        assert 'docs/html/index.html' in archive.namelist()
        archive.extractall(extracted)
    guide = (ROOT / 'docs/verification.md').read_text()
    directory = re.search(r'--directory ([^ ]+) --bind 127\.0\.0\.1', guide)[1]
    handler = partial(SimpleHTTPRequestHandler, directory=extracted / directory)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ('index.html', 'commands.html'):
            with urlopen(f'http://127.0.0.1:{server.server_port}/{path}', timeout=5) as response:
                assert response.status == 200
                assert response.read() == (extracted / 'docs/html' / path).read_bytes()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_published_paths_and_heading_bookmarks_survive():
    inventory = json.loads((ROOT / 'tests/docs/published-anchors.json').read_text())
    assert inventory['source_commit'] == 'fa1a4e708f3d1330667967fe420adcdf18cbb8ef'
    for name, anchors in inventory['pages'].items():
        page = Page(SITE / name)
        assert set(anchors) <= page.ids, (name, set(anchors) - page.ids)


def test_common_navigation_and_exact_docs_identity_on_every_page():
    record = json.loads((SITE / 'build.json').read_text())
    repo = 'https://github.com/Living-Proof-Labs/livingproof-capability-report'
    for path in SITE.glob('*.html'):
        if path.name == '404.html':
            continue
        page = Page(path)
        assert 'https://docs.livingprooflabs.com/' in page.links, path.name
        assert repo in page.links and repo + '/issues' in page.links, path.name
        local_links = {link.removeprefix('./') for link in page.links}
        assert 'license.html' in local_links and 'contributing.html' in local_links, path.name
        assert repo + '/tree/' + record['source_commit'] in page.links, path.name
        assert 'Docs: development' in path.read_text(), path.name
    assert record['guidelines'] == 'v6.0.0'
    assert record['guidelines_commit'] == '52a2f274576dab20e96ee1152b6c8d187cfbf377'
    provenance = (SITE / 'provenance.html').read_text()
    assert record['package_version'] in provenance
    assert 'Candidate metadata is not a claim of a published package release.' in provenance


def test_api_reference_matches_installed_wheel_and_consumer_example(tmp_path):
    import subprocess
    import sys

    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'artifacts/docs/packages')}
    probe = '''import inspect, json, sys
from pathlib import Path
import livingproof_capability_report as api
assert Path(api.__file__).is_relative_to(Path(sys.argv[1]))
loaded = api.load_bundle(sys.argv[2])
saved = api.grade(loaded)
assert len(saved['decisions']) == 8 and len(saved['groups']) == 4
assert {d['status'] for d in saved['decisions']} == {'PASS', 'FAIL', 'INSUFFICIENT_EVIDENCE'}
assert '<html' in api.render(saved, 'html')
print(json.dumps([{'name': n, 'signature': str(inspect.signature(getattr(api, n))),
                   'docstring': inspect.getdoc(getattr(api, n)) or ''} for n in api.__all__]))
'''
    actual = json.loads(subprocess.check_output(
        [sys.executable, '-c', probe, str(ROOT / 'artifacts/docs/packages'),
         str(ROOT / 'examples/bundle/manifest.json')], cwd=tmp_path, env=env, text=True))
    assert actual == json.loads((SITE / 'api.json').read_text())
    assert len(actual) == 5
    text = (ROOT / 'artifacts/docs/source/api.md').read_text()
    for function in actual:
        assert function['name'] + function['signature'] in text
        assert function['docstring'] in text


def test_task_reference_matches_current_native_listing():
    import subprocess

    listing = json.loads(subprocess.check_output(['task', '--color=false', '--list', '--json'], cwd=ROOT, text=True))
    text = (ROOT / 'artifacts/docs/source/tasks.md').read_text()
    for task in listing['tasks']:
        assert f"## {task['name']}" in text
        summary = subprocess.check_output(['task', '--color=false', '--summary', task['name']], cwd=ROOT, text=True)
        assert summary in text


def test_rendered_task_reference_has_no_terminal_color_controls():
    text = ''.join(Page(SITE / 'tasks.html').text)
    assert 'uv run --locked --no-sync' in text
    assert 'docker compose build development' in text
    assert not re.search(r'\x1b|\x9b|\[[0-9;]*m', text)
