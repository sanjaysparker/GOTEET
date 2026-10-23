"""Freeze only application code and runtime dependencies, never private data."""
from pathlib import Path
import subprocess
import sys
import os
import platform
root=Path(__file__).resolve().parents[1]
backend='keyring.backends.macOS' if sys.platform=='darwin' else 'keyring.backends.Windows' if sys.platform=='win32' else 'keyring.backends.SecretService'
output=os.environ.get('GOTEET_PAYLOAD_DIR','payload')
work=os.environ.get('GOTEET_BUILD_DIR','build')
print('Freezing backend for', platform.machine(), 'into', output, flush=True)
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--name','goteet-api','--distpath',output,'--workpath',str(Path(work)/'pyinstaller'),'--specpath',work]
for name in ['faster_whisper','ctranslate2','tokenizers','onnxruntime']:args+=['--collect-all',name]
args+=['--hidden-import',backend,'api.py']
environment=dict(os.environ)
# Rosetta Python must use native developer tools when Apple's CLT contains only arm64.
if sys.platform=='darwin' and platform.machine()=='x86_64':
    native_arm=subprocess.run(['/usr/sbin/sysctl','-n','hw.optional.arm64'],capture_output=True,text=True)
    if native_arm.returncode==0 and native_arm.stdout.strip()=='1':
        wrappers=(root/work/'native-tools').resolve()
        wrappers.mkdir(parents=True,exist_ok=True)
        for tool in ['lipo','install_name_tool','codesign','otool','strip']:
            path=wrappers/tool
            path.write_text('#!/bin/sh\nexec /usr/bin/arch -arm64 /usr/bin/'+tool+' "$@"\n')
            path.chmod(0o755)
        environment['PATH']=str(wrappers)+os.pathsep+environment.get('PATH','')
subprocess.run(args,cwd=root,env=environment,check=True)
