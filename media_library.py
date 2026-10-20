"""Owner-only previews of explicitly indexed local media, never arbitrary files."""
from pathlib import Path
import engine
import settings
import io
from functools import lru_cache
EXPLICIT_PREVIEWS=set()

FORMATS={
 '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp',
 '.gif':'image/gif','.bmp':'image/bmp','.avif':'image/avif',
 '.mp4':'video/mp4','.m4v':'video/mp4','.webm':'video/webm','.mov':'video/quicktime',
 '.mp3':'audio/mpeg','.wav':'audio/wav','.ogg':'audio/ogg','.m4a':'audio/mp4',
 '.flac':'audio/flac','.aac':'audio/aac', '.pdf':'application/pdf',
 '.txt':'text/plain','.md':'text/plain','.csv':'text/plain','.log':'text/plain',
 '.stl':'model/stl','.obj':'model/obj','.glb':'model/gltf-binary',
 '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
 '.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
 '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}

def indexed(path):
    settings.require('media_preview_enabled')
    record=next((f for f in engine.read_json('inventory.json').get('local',{}).get('files',[]) if f.get('path')==path),None)
    if not record:
        if path not in EXPLICIT_PREVIEWS:raise PermissionError('Choose a file from the media library or Files panel')
        settings.require('file_browser_enabled')
    file=Path(path)
    if not file.is_absolute() or not file.is_file():raise ValueError('This file is no longer available. Refresh your library.')
    if file.is_symlink() or any(p.is_symlink() for p in file.parents) or file.resolve()!=file:
        raise PermissionError('Symlink previews are not allowed. Refresh your library.')
    mime=FORMATS.get(file.suffix.lower())
    if not mime:raise ValueError('This format cannot be previewed yet. Use Reveal to open it in its own app.')
    return file,mime

def info(path):
    file,mime=indexed(path)
    result={'path':path,'name':file.name,'size':file.stat().st_size,'mime_type':mime,'kind':mime.split('/')[0]}
    if mime=='text/plain':
        with file.open('rb') as handle:content=handle.read(200001)
        result.update(text=content[:200000].decode('utf-8',errors='replace'),truncated=len(content)>200000)
    if file.suffix.lower() in {'.docx','.pptx','.xlsx'}:
        import zipfile
        import xml.etree.ElementTree as ET
        parts=[];used=0
        with zipfile.ZipFile(file) as archive:
            for name in archive.namelist():
                if name=='word/document.xml' or name.startswith('ppt/slides/slide') and name.endswith('.xml') or name=='xl/sharedStrings.xml' or name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                    info=archive.getinfo(name);used+=info.file_size
                    if info.file_size>2000000 or used>4000000:raise ValueError('This document is too large for the text preview. Use its desktop editor.')
                    root=ET.fromstring(archive.read(name));lines=[]
                    for element in root.iter():
                        tag=element.tag.rsplit('}',1)[-1]
                        if tag in {'t','v'} and element.text:lines.append(element.text)
                        if tag in {'p','row'} and lines:parts.append(' '.join(lines));lines=[]
                    if lines:parts.append(' '.join(lines))
        result.update(kind='document',text='\n\n'.join(parts)[:200000],truncated=sum(len(p) for p in parts)>200000,
                      note='Text preview; original document formatting is preserved in the source file. Spreadsheet shared strings and cell values are shown in source order.')
    return result

def search(query='',kind='',limit=100):
    settings.require('media_preview_enabled')
    rows=engine.read_json('inventory.json').get('local',{}).get('files',[])
    return [f for f in rows if query.lower() in (f.get('name','')+' '+f.get('path','')).lower()
            and (not kind or f.get('category','').lower()==kind.lower())][:max(1,min(200,limit))]

@lru_cache(maxsize=128)
def _thumbnail(path,modified,size):
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=40000000
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source);image.thumbnail((256,192));image=image.convert('RGBA')
        output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()

def thumbnail(path):
    file,mime=indexed(path)
    if not mime.startswith('image/'):raise ValueError('No image thumbnail is available for this format')
    stat=file.stat()
    try:return _thumbnail(str(file),stat.st_mtime_ns,stat.st_size)
    except Exception:raise ValueError('This image cannot be thumbnailed')
