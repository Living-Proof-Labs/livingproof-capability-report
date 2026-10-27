"""Public releases retain packages while image transfers remain CI artifacts."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_assets', ROOT / 'tools/release_assets.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def populate(root):
    names = ['livingproof_capability_report-1.2.0.whl', 'livingproof_common-1.0.0.whl',
             'livingproof_capability_report-1.2.0.tar.gz', 'livingproof-capability-report_1.2.0_all.deb', 'python3-livingproof-common_1.0.0_all.deb',
             'requirements.txt']
    for arch in ('amd64', 'arm64'):
        names += [f'wheelhouse-{arch}.tar.gz', f'compatibility-{arch}.json',
                  f'compatibility-{arch}.md']
    for name in names + ['image-amd64.tar', 'image-arm64.tar', 'SHA256SUMS',
                         'SHA256SUMS-amd64', 'SHA256SUMS-arm64']:
        (root / name).write_text(name)
    return names


def test_public_assets_preserve_packages_and_checksums_without_images(tmp_path):
    names = populate(tmp_path)
    target = tmp_path / 'public'
    module.stage(tmp_path, target)
    assert {p.name for p in target.iterdir()} == set(names) | {
        'SHA256SUMS', 'SHA256SUMS-amd64', 'SHA256SUMS-arm64'}
    assert (tmp_path / 'image-amd64.tar').exists()
    assert (tmp_path / 'image-arm64.tar').exists()
    for line in (target / 'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ')
        assert checksum == hashlib.sha256((target / name).read_bytes()).hexdigest()
    assert len((target / 'SHA256SUMS').read_text().splitlines()) == len(names)


def test_missing_architecture_package_blocks_staging(tmp_path):
    populate(tmp_path)
    (tmp_path / 'wheelhouse-arm64.tar.gz').unlink()
    with pytest.raises(ValueError, match='wheelhouse-arm64'):
        module.stage(tmp_path, tmp_path / 'public')
    assert not (tmp_path / 'public').exists()


def test_workflow_gates_public_assets_on_registry_verification():
    import yaml
    jobs = yaml.safe_load((ROOT / '.github/workflows/verify.yml').read_text())['jobs']
    assert 'verify-registry' in jobs['publish-release']['needs']
    assert 'gh release upload' not in str(jobs['publish'])
    assert 'gh release upload' not in str(jobs['manifest'])
    assert 'tools/release_assets.py' in str(jobs['publish-release'])
    for job in ('verify', 'publish'):
        transfers = [s for s in jobs[job]['steps'] if s.get('with', {}).get('path') == 'dist/']
        assert transfers and all(s['with']['retention-days'] == 14 for s in transfers)


@pytest.mark.parametrize('missing', [
    'livingproof_capability_report-1.2.0.whl', 'livingproof_common-1.0.0.whl',
    'livingproof-capability-report_1.2.0_all.deb', 'python3-livingproof-common_1.0.0_all.deb',
])
def test_missing_shared_package_blocks_staging(tmp_path, missing):
    populate(tmp_path)
    (tmp_path / missing).unlink()
    with pytest.raises(ValueError, match='Missing required release asset'):
        module.stage(tmp_path, tmp_path / 'public')
