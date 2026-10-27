"""Stage public packages after registry verification; keep CI image archives internal."""
import hashlib
import shutil
import sys
from pathlib import Path


def stage(source: Path, target: Path) -> list[Path]:
    patterns = ('*.whl', 'livingproof*.tar.gz', '*.deb', 'requirements.txt',
                'wheelhouse-*.tar.gz', 'compatibility-*.json', 'compatibility-*.md')
    assets = sorted({path for pattern in patterns for path in source.glob(pattern)})
    for required in ('livingproof_capability_report-*.whl', 'livingproof_common-*.whl',
                     'livingproof_capability_report-*.tar.gz',
                     'livingproof-capability-report_*_all.deb',
                     'python3-livingproof-common_*_all.deb', 'requirements.txt',
                     'wheelhouse-amd64.tar.gz', 'wheelhouse-arm64.tar.gz',
                     'compatibility-amd64.json', 'compatibility-arm64.json',
                     'compatibility-amd64.md', 'compatibility-arm64.md'):
        if not list(source.glob(required)):
            raise ValueError(f'Missing required release asset: {required}')
    target.mkdir(exist_ok=False)
    for path in assets:
        shutil.copyfile(path, target / path.name)
    checksums = {}
    for path in assets:
        with path.open('rb') as stream:
            checksums[path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    for architecture in ('amd64', 'arm64'):
        selected = [p for p in assets if architecture in p.name or
                    (architecture == 'amd64' and not any(a in p.name for a in ('amd64', 'arm64')))]
        (target / f'SHA256SUMS-{architecture}').write_text(''.join(
            f'{checksums[path.name]}  {path.name}\n'
            for path in selected))
    (target / 'SHA256SUMS').write_text(''.join(
        (target / f'SHA256SUMS-{architecture}').read_text()
        for architecture in ('amd64', 'arm64')))
    return assets


if __name__ == '__main__':
    stage(Path(sys.argv[1]), Path(sys.argv[2]))
