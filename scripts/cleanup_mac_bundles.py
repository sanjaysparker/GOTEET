"""Remove redundant GOTEET release bundles after the installed app is healthy."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workmate_client import call


def info(path):
    if path.is_symlink():
        raise RuntimeError(f'Refusing symlink: {path}')
    with (path / 'Contents/Info.plist').open('rb') as stream:
        return plistlib.load(stream)


def version(value):
    return tuple(int(part) for part in value.split('.'))


def main():
    installed = Path('/Applications/GOTEET.app')
    current = info(installed)
    if current['CFBundleIdentifier'] != 'in.droneos.goteet':
        raise RuntimeError('Installed bundle identity differs')
    health = call('GET', '/api/health')
    if not health.get('ok') or health.get('version') != current['CFBundleShortVersionString']:
        raise RuntimeError('Open the installed app and verify its health before cleanup')
    processes = subprocess.check_output(['ps', '-axo', 'command='], text=True)
    if str(installed / 'Contents/MacOS/GOTEET') not in processes:
        raise RuntimeError('The installed desktop is not running')
    candidates = list((ROOT / 'release').glob('GOTEET*.app'))
    candidates += list((ROOT / 'release').glob('mac-*/GOTEET.app'))
    candidates += list((ROOT / 'release').glob('intel/mac/GOTEET.app'))
    removed = 0
    for path in candidates:
        candidate = info(path)
        if candidate.get('CFBundleIdentifier') != current['CFBundleIdentifier']:
            raise RuntimeError(f'Unexpected bundle identity: {path}')
        if version(candidate['CFBundleShortVersionString']) > version(current['CFBundleShortVersionString']):
            raise RuntimeError(f'Install the newer build before cleanup: {path}')
        if str(path / 'Contents/MacOS/') in processes:
            raise RuntimeError(f'Close the staging app first: {path}')
        shutil.rmtree(path)
        removed += 1
        print(f'Removed release bundle: {path}')
    print(f'Kept {installed}; removed {removed} redundant release bundles.')


if __name__ == '__main__':
    main()
