"""On-demand filesystem browsing. No full-disk indexing or background writes."""
import os
from pathlib import Path
import settings
import media_library

def checked(path):
    settings.require('file_browser_enabled')
    if not isinstance(path,str) or not path or '\x00' in path:raise ValueError('Enter a folder or file path')
    file=Path(path).expanduser().absolute()
    if not file.exists() and not file.is_symlink():raise ValueError('This path is no longer available')
    return file

def info(path,action='read'):
    file=checked(path);resolved=file.resolve()
    if action not in {'read','copy','trash','share'}:raise ValueError('Unsupported file action')
    if action=='trash':
        home=Path.home().resolve()
        protected=[home,Path('/'),Path(__file__).resolve().parent]
        if resolved in protected or not resolved.is_relative_to(home) or resolved.is_relative_to(Path(__file__).resolve().parent):
            raise PermissionError('System locations, your home folder and GOTEET itself cannot be moved to Trash here')
        for folder in [home/'Library',home/'.ssh',home/'.gnupg',home/'.codex',home/'.claude',home/'.config',home/'.local']:
            if resolved==folder or resolved.is_relative_to(folder):raise PermissionError('Manage application data and credentials through their own tools')
    stat=file.lstat()
    return {'path':str(file),'name':file.name or str(file),'kind':'Folder' if file.is_dir() else 'File','is_symlink':file.is_symlink(),
            'size':stat.st_size,'modified':stat.st_mtime,'previewable':file.suffix.lower() in media_library.FORMATS and file.is_file()}

def listing(path='',hidden=False,query='',offset=0,sort='name'):
    root=checked(path or str(Path.home())).resolve()
    if not root.is_dir():raise ValueError('Choose a folder to browse')
    rows=[];errors=0;scanned=0
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                scanned+=1
                if scanned>20000:break
                if (entry.name.startswith('.') and not hidden) or query.lower() not in entry.name.lower():continue
                try:rows.append(info(entry.path))
                except (OSError,ValueError,PermissionError):errors+=1
    except PermissionError:raise PermissionError('macOS denied access to this folder. Choose another folder or manage GOTEET access in System Settings.')
    if sort not in {'name','size','modified'}:sort='name'
    rows.sort(key=lambda r:(r['kind']!='Folder',r['name'].lower()) if sort=='name' else (-r[sort],r['name'].lower()))
    offset=max(0,min(20000,offset))
    return {'path':str(root),'parent':str(root.parent),'items':rows[offset:offset+200],'total':len(rows),'offset':offset,
            'truncated':scanned>20000,'unreadable':errors,'home':str(Path.home()),'roots':[{'name':'Home','path':str(Path.home())},
            *[{'name':name,'path':str(Path.home()/name)} for name in ['Desktop','Documents','Downloads','Pictures','Movies']],{'name':'System','path':str(Path('/'))}]}

def preview(path):
    file=checked(path).resolve()
    if not file.is_file():raise ValueError('Choose a regular media file')
    media_library.EXPLICIT_PREVIEWS.add(str(file))
    try:return media_library.info(str(file))
    except Exception:
        media_library.EXPLICIT_PREVIEWS.discard(str(file));raise
