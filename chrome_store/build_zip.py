"""
Build the Chrome Web Store upload file for the extension.

Zips the contents of chrome_extension/ (manifest.json at the top level),
leaving out developer-only files, and checks the manifest against the
store's limits first.

Usage (from the project root):
    uv run python chrome_store/build_zip.py
Writes dist/fantasy-schedule-luck-<version>.zip
"""

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'chrome_extension'
DIST = ROOT / 'dist'

# Developer-only files and folders that don't belong in the package
EXCLUDED_DIRS = {'tests', '__pycache__', 'node_modules'}
EXCLUDED_FILES = {'package.json', 'package-lock.json', '.DS_Store'}

# Chrome Web Store limits for manifest fields
LIMITS = {'name': 75, 'description': 132, 'short_name': 12}


def check_manifest(manifest: dict) -> list[str]:
    """Problems the store would reject the upload for (empty when fine)."""
    problems = []
    for field, limit in LIMITS.items():
        value = manifest.get(field)
        if value is not None and len(value) > limit:
            problems.append(f'manifest "{field}" is {len(value)} characters; the limit is {limit}')
    for field in ('name', 'version', 'description', 'manifest_version'):
        if field not in manifest:
            problems.append(f'manifest is missing "{field}"')
    return problems


def package_files(extension_dir: Path = EXTENSION) -> list[Path]:
    """Files to ship, relative to the extension folder, in a stable order."""
    files = []
    for path in sorted(extension_dir.rglob('*')):
        relative = path.relative_to(extension_dir)
        if path.is_dir() or path.name in EXCLUDED_FILES:
            continue
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        files.append(relative)
    return files


def build_zip(extension_dir: Path = EXTENSION, dist_dir: Path = DIST) -> Path:
    manifest = json.loads((extension_dir / 'manifest.json').read_text(encoding='utf-8'))
    problems = check_manifest(manifest)
    if problems:
        raise SystemExit('Not building, the store would reject this:\n  - ' + '\n  - '.join(problems))

    dist_dir.mkdir(parents=True, exist_ok=True)
    out = dist_dir / f'fantasy-schedule-luck-{manifest["version"]}.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for relative in package_files(extension_dir):
            archive.write(extension_dir / relative, relative.as_posix())
    return out


def main():
    out = build_zip()
    size_mb = out.stat().st_size / 1e6
    print(f'Built {out.relative_to(ROOT)} ({size_mb:.1f} MB). Upload it on the Chrome Web Store dashboard.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
