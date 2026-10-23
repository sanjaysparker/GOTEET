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
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--name','workmate-api','--distpath',output,'--workpath',str(Path(work)/'pyinstaller'),'--specpath',work]
for name in ['faster_whisper','ctranslate2','tokenizers','onnxruntime']:args+=['--collect-all',name]
args+=['--hidden-import',backend,'api.py']
subprocess.run(args,cwd=root,check=True)
