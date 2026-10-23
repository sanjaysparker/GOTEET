"""Architecture audit and isolated smoke test of the actual packaged service."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

bundle = Path(sys.argv[1]).resolve()
executables = [bundle/'Contents/MacOS/GOTEET', bundle/'Contents/Resources/payload/workmate-api/workmate-api']
count = 0
for path in bundle.rglob('*'):
    if not path.is_file() or path.is_symlink():
        continue
    with path.open('rb') as handle:
        magic = handle.read(4)
    if magic not in [b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf']:
        continue
    arch = subprocess.check_output(['lipo', '-archs', str(path)], text=True).strip()
    assert 'x86_64' in arch.split(), f'Not Intel-compatible: {path}: {arch}'
    count += 1
assert count > 20, f'Unexpected binary count: {count}'
for path in executables:
    assert path.is_file(), path
print(f'Architecture audit: {count} Mach-O files support x86_64', flush=True)
with tempfile.TemporaryDirectory(prefix='goteet-intel-smoke-') as directory:
    root = Path(directory)
    (root/'data').mkdir()
    (root/'data/settings.json').write_text(json.dumps({'auto_analysis':False,'google_enabled':False,'agent_observer_enabled':False,'activity_enabled':False}))
    with (root/'backend.log').open('w+') as log:
        process = subprocess.Popen([str(executables[1])], env={**os.environ, 'WORKMATE_HOME':directory}, stdout=log, stderr=log)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                runtime = root/'data/runtime.json'
                if runtime.exists():
                    config = json.loads(runtime.read_text())
                    try:
                        request = urllib.request.Request(config['url']+'/api/health', headers={'Authorization':'Bearer '+config['token']})
                        with urllib.request.urlopen(request, timeout=2) as response:
                            health = json.load(response)
                        assert health['ok']
                        print('Packaged API health:', health['ok'], 'version:', health['version'])
                        for endpoint in ['/api/tasks', '/api/projects', '/api/scheduler']:
                            request = urllib.request.Request(config['url']+endpoint, headers={'Authorization':'Bearer '+config['token']})
                            with urllib.request.urlopen(request, timeout=5) as response:
                                json.load(response)
                            print('HTTP 200:', endpoint)
                        break
                    except (OSError, ValueError):
                        pass
                time.sleep(1)
            else:
                raise RuntimeError('Packaged API did not become healthy')
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
