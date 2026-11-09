"""The Chrome Web Store upload file: right contents, and manifest within store limits."""

import importlib.util
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_zip', ROOT / 'chrome_store' / 'build_zip.py')
build_zip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_zip)


def test_real_manifest_is_within_store_limits():
    manifest = json.loads((ROOT / 'chrome_extension' / 'manifest.json').read_text())
    assert build_zip.check_manifest(manifest) == []


def test_limits_are_enforced():
    manifest = {'name': 'x', 'version': '1', 'manifest_version': 3, 'description': 'd' * 140}
    assert any('132' in p for p in build_zip.check_manifest(manifest))


def test_zip_has_manifest_at_top_and_no_developer_files(tmp_path):
    out = build_zip.build_zip(dist_dir=tmp_path)
    names = zipfile.ZipFile(out).namelist()
    assert 'manifest.json' in names
    assert 'popup.html' in names and 'report.html' in names
    assert 'vendor/plotly.min.js' in names and 'lib/simulate.js' in names
    assert not any(n.startswith('tests/') or n == 'package.json' or '__pycache__' in n for n in names)
    version = json.loads((ROOT / 'chrome_extension' / 'manifest.json').read_text())['version']
    assert out.name == f'fantasy-schedule-luck-{version}.zip'


def test_every_file_the_extension_loads_is_packaged(tmp_path):
    """Scripts, styles and icons referenced by the pages and manifest must be in the zip."""
    import re
    names = set(zipfile.ZipFile(build_zip.build_zip(dist_dir=tmp_path)).namelist())
    ext = ROOT / 'chrome_extension'
    referenced = set()
    for page in ('popup.html', 'report.html'):
        referenced |= set(re.findall(r'(?:src|href)="([^"#:]+)"', (ext / page).read_text()))
    manifest = json.loads((ext / 'manifest.json').read_text())
    referenced |= set(manifest['icons'].values())
    for module in ext.glob('*.js'):
        referenced |= {p.lstrip('./') for p in re.findall(r"from '(\./[^']+)'", module.read_text())}
    missing = referenced - names
    assert not missing, f'not packaged: {sorted(missing)}'
