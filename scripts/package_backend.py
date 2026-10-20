"""Freeze only application code and runtime dependencies, never private data."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
backend='keyring.backends.macOS' if sys.platform=='darwin' else 'keyring.backends.Windows' if sys.platform=='win32' else 'keyring.backends.SecretService'
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--name','workmate-api','--distpath','payload','--workpath','build/pyinstaller','--specpath','build']
for name in ['faster_whisper','ctranslate2','tokenizers','onnxruntime']:args+=['--collect-all',name]
args+=['--hidden-import',backend,'api.py']
subprocess.run(args,cwd=root,check=True)
