"""Generate a bounded manual from canonical sources and an installed wheel."""
import ast
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/docs'
SOURCES = {'README.md': 'index.md', 'docs/verification.md': 'verification.md',
           '.github/PAGES.md': 'pages.md', 'AGENTS.md': 'working-agreement.md',
           'CONTRIBUTING.md': 'contributing.md', 'docs/api.md': 'api.md',
           'docs/license.md': 'license.md'}
REPO = 'https://github.com/Living-Proof-Labs/livingproof-capability-report'


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    wheels = OUT / 'wheels'
    wheels.mkdir(parents=True, exist_ok=True)
    run(['uv', 'build', '--wheel', '--out-dir', str(wheels)], cwd=ROOT)
    candidates = list(wheels.glob('*.whl'))
    if len(candidates) != 1:
        raise RuntimeError('Use a fresh checkout: expected exactly one candidate wheel')
    run(['uv', 'pip', 'install', '--no-deps', '--target', str(OUT / 'packages'),
         '--reinstall', str(candidates[0])])


def scenarios():
    tree = ast.parse((ROOT / 'tests/features/test_installed.py').read_text())
    return [(n.name, ast.get_docstring(n)) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]


def results():
    path = ROOT / 'artifacts/feature-tests.xml'
    if not path.exists():
        return {name: 'UNTESTED' for name, _ in scenarios()}
    cases = ET.parse(path).findall('.//testcase')
    expected = {name for name, _ in scenarios()}
    if len(cases) != len(expected) or {c.attrib['name'] for c in cases} != expected:
        raise RuntimeError('Incomplete or duplicate scenario results')
    return {c.attrib['name']: ('FAILED' if c.find('failure') is not None or
                              c.find('error') is not None else
                              'SKIPPED' if c.find('skipped') is not None else 'PASSED')
            for c in cases}


def rewrite(text, source, commit):
    def link(match):
        target = match[2]
        if target == 'https://docs.livingprooflabs.com/livingproof-capability-report/':
            return f'[{match[1]}](index.md)'
        if ':' in target or target.startswith('#'):
            return match[0]
        path, sep, fragment = target.partition('#')
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        destination = 'LICENSE' if path == 'LICENSE' else SOURCES.get(
            path, f'{REPO}/blob/{commit}/{path}')
        return f'[{match[1]}]({destination}{sep}{fragment})'
    return re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', link, text)


def build():
    source = OUT / 'source'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'LICENSE').write_bytes((ROOT / 'LICENSE').read_bytes())
    commit = run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).strip()
    wheel, = (OUT / 'wheels').glob('*.whl')
    outcomes = results()
    provenance = {
        'source_commit': commit,
        'source_dirty': bool(run(['git', 'status', '--porcelain'], cwd=ROOT).strip()),
        'wheel': wheel.name, 'wheel_sha256': digest(wheel),
        'guidelines': 'v6.0.0',
        'guidelines_commit': '52a2f274576dab20e96ee1152b6c8d187cfbf377',
        'sources': {path: digest(ROOT / path) for path in SOURCES},
        'scenario_source_sha256': digest(ROOT / 'tests/features/test_installed.py'),
        'results_sha256': (digest(ROOT / 'artifacts/feature-tests.xml')
                           if (ROOT / 'artifacts/feature-tests.xml').exists() else None),
        'run_url': (f'{REPO}/actions/runs/' + os.environ['GITHUB_RUN_ID']
                    if 'GITHUB_RUN_ID' in os.environ else None),
        'scenario_results': outcomes,
    }
    for path, dest in SOURCES.items():
        (source / dest).write_text(rewrite((ROOT / path).read_text(), path, commit))
    lines = ['# Installed feature scenarios', '',
             'Four bounded examples, not exhaustive coverage or robot safety certification.',
             'No software line coverage was measured. See verification for gaps.', '']
    for name, description in scenarios():
        lines += [f'## {name}', '', f'Result: **{outcomes[name]}**', '',
                  '```text', description, '```', '']
    (source / 'scenarios.md').write_text('\n'.join(lines))
    env = {**os.environ, 'PYTHONPATH': str(OUT / 'packages')}
    probe = '''import inspect
import importlib.metadata
import json
from pathlib import Path
import click
import livingproof_capability_report as package
from livingproof_capability_report.cli import report
assert Path(package.__file__).is_relative_to(Path.cwd() / 'packages'), package.__file__
def walk(command, name):
    ctx = click.Context(command, info_name=name)
    rows = [{'name': name, 'help': command.get_help(ctx),
             'options': [o for p in command.params if isinstance(p, click.Option) for o in p.opts]}]
    if isinstance(command, click.Group):
        for child in command.list_commands(ctx):
            rows += walk(command.get_command(ctx, child), name + ' ' + child)
    return rows
api = [{'name': name, 'signature': str(inspect.signature(getattr(package, name))),
        'docstring': inspect.getdoc(getattr(package, name)) or ''}
       for name in package.__all__]
print(json.dumps({'commands': walk(report, 'livingproof-capability-report'),
                  'api': api, 'package_version': importlib.metadata.version(
                      'livingproof-capability-report')}))
'''
    installed = json.loads(run([sys.executable, '-c', probe], cwd=OUT, env=env))
    commands = installed['commands']
    provenance['package_version'] = installed['package_version']
    (source / 'api.json').write_text(json.dumps(installed['api'], indent=2) + '\n')
    with (source / 'api.md').open('a') as stream:
        stream.write('\n## Installed signatures and docstrings\n\n')
        for function in installed['api']:
            stream.write(f"### {function['name']}\n\n```python\n"
                         f"{function['name']}{function['signature']}\n```\n\n"
                         f"{function['docstring']}\n\n")
    (source / 'commands.json').write_text(json.dumps(commands, indent=2))
    (source / 'commands.md').write_text(
        '# Installed command reference\n\n'
        '::: mkdocs-click\n    :module: livingproof_capability_report.cli\n'
        '    :command: report\n    :prog_name: livingproof-capability-report\n'
        '    :depth: 1\n')
    (source / 'terminal-help.md').write_text('# Installed terminal help\n\n' + '\n'.join(
        f"## {c['name']}\n\n```text\n{c['help']}\n```\n" for c in commands))
    (source / 'build.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (source / 'provenance.md').write_text(
        '# Development documentation\n\n'
        f"[Exact documentation source]({REPO}/tree/{commit})\n\n"
        f"Installed candidate package metadata: `{installed['package_version']}`.\n"
        'Candidate metadata is not a claim of a published package release.\n'
        f'[Published package releases]({REPO}/releases) are separate from this manual.\n\n'
        'Historical manuals are not maintained. Consult the corresponding '
        f'[source release tag]({REPO}/tags) for earlier behavior.\n\n'
        '[Machine-readable build record](build.json)\n\n```json\n' +
        json.dumps(provenance, indent=2) + '\n```\n')
    task_list = json.loads(run(['task', '--color=false', '--list', '--json'], cwd=ROOT))
    (source / 'tasks.md').write_text('# Task reference\n\n'
        'Use setup/verify/docs commands inside the prepared environment. `dev:*` tasks\n'
        'are host wrappers requiring Docker; do not invoke them inside the container.\n\n'
        + '\n'.join(
        f"## {t['name']}\n\n```text\n" + run(['task', '--color=false', '--summary', t['name']], cwd=ROOT) +
        '\n```\n' for t in task_list['tasks']))
    identity = (f'> [Docs: development · {commit[:12]}]({REPO}/tree/{commit})'
                + (' (uncommitted changes)' if provenance['source_dirty'] else '')
                + '. [Version and source](provenance.md).\n\n')
    for page in source.glob('*.md'):
        page.write_text(identity + page.read_text())
    config = yaml.safe_load((ROOT / 'docs/site/mkdocs.yml').read_text())
    config.update(docs_dir='source', site_dir='html', repo_url=REPO, repo_name='Source', nav=[
        {'Documentation home': 'https://docs.livingprooflabs.com/'},
        {'Start here': 'index.md'},
        {'Guides': [{'Installation and quickstart': 'index.html#install-a-release'},
                    {'Python consumer example': 'api.md'}]},
        {'Reference': [{'Commands': 'commands.md'}, {'API': 'api.md'},
                       {'Tasks': 'tasks.md'},
                       {'Contracts': 'index.html#bundle-and-grading-contract'},
                       {'Installed terminal help': 'terminal-help.md'}]},
        {'Scenarios and results': 'scenarios.md'}, {'Verification': 'verification.md'},
        {'Contribute': 'contributing.md'}, {'Version and source': 'provenance.md'},
        {'Help / report an issue': REPO + '/issues'}, {'License': 'license.md'},
        {'Maintainers': [{'Pages': 'pages.md'}, {'Working agreement': 'working-agreement.md'}]}])
    (OUT / 'mkdocs.yml').write_text(yaml.safe_dump(config, sort_keys=False))
    subprocess.run([sys.executable, '-m', 'zensical', 'build', '--clean', '-f',
                    str(OUT / 'mkdocs.yml')], cwd=OUT, env=env, check=True)


if __name__ == '__main__':
    {'prepare': prepare, 'build': build}[sys.argv[1]]()
