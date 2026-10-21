"""Read-only bounded Drive downloads/exports into a private local preview cache."""
import hashlib
import re
import tempfile
from pathlib import Path
import httpx
import google_auth
import media_library
import settings
from collector import DATA
READ_SCOPE='https://www.googleapis.com/auth/drive.readonly'

def preview(file_id):
    settings.require('google_enabled');settings.require('media_preview_enabled')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',file_id):raise ValueError('Invalid Drive file ID')
    token=google_auth.read_secret('google-tokens') or {}
    if READ_SCOPE not in token.get('scope','').split():raise ValueError('To view Drive contents, expand Optional Google data imports, select Drive and connect Google again. Approve read access to file contents.')
    with httpx.Client(headers={'Authorization':'Bearer '+google_auth.access_token()},timeout=60) as client:
        base='https://www.googleapis.com/drive/v3/files/'+file_id
        r=client.get(base,params={'fields':'id,name,mimeType,size,modifiedTime','supportsAllDrives':'true'})
        if r.status_code!=200:raise ValueError('Drive file unavailable or access denied.')
        meta=r.json();mime=meta['mimeType'];ext=Path(meta['name']).suffix.lower()
        if mime in {'application/vnd.google-apps.document','application/vnd.google-apps.spreadsheet','application/vnd.google-apps.presentation'}:
            url=base+'/export';params={'mimeType':'application/pdf'};ext='.pdf'
        elif mime=='application/vnd.google-apps.folder':raise ValueError('Choose a file rather than a Drive folder.')
        else:
            if ext not in media_library.FORMATS:raise ValueError('This Drive format is not supported in the viewer yet.')
            url=base;params={'alt':'media','supportsAllDrives':'true'}
        if int(meta.get('size',0))>50*1024*1024:raise ValueError('Drive preview limit is 50 MB. Open this file in Drive.')
        cache=DATA/'drive-previews';cache.mkdir(parents=True,exist_ok=True);cache.chmod(0o700)
        key=hashlib.sha256((str(token.get('profile',{}).get('sub',''))+file_id+meta.get('modifiedTime','')).encode()).hexdigest()
        safe=re.sub(r'[^\w .()-]','_',Path(meta['name']).stem)[:80]
        target=cache/(key[:20]+'-'+safe+ext)
        if not target.exists():
            temp=None
            try:
                with tempfile.NamedTemporaryFile(dir=cache,delete=False) as out:
                    temp=Path(out.name);total=0
                    with client.stream('GET',url,params=params) as response:
                        if response.status_code!=200:raise ValueError('Drive could not export/download this file. Check permissions or export size.')
                        for chunk in response.iter_bytes():
                            total+=len(chunk)
                            if total>50*1024*1024:raise ValueError('Drive preview limit is 50 MB.')
                            out.write(chunk)
                temp.replace(target);target.chmod(0o600)
            finally:
                if temp and temp.exists():temp.unlink()
        media_library.CLOUD_PREVIEWS[str(target)]=token.get('profile',{}).get('sub')
        # Keep at most 500 MB of previously opened previews. Originals are untouched.
        files=sorted(cache.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
        used=target.stat().st_size
        for old in files:
            if old==target:continue
            used+=old.stat().st_size
            if used>500*1024*1024:
                old.unlink(missing_ok=True);media_library.CLOUD_PREVIEWS.pop(str(old),None)
        return {'path':str(target),'name':meta['name'],'exported':url.endswith('/export')}

FOLDER='application/vnd.google-apps.folder'
def listing(parent='root',query='',page='',order='name',kind='all'):
    settings.require('google_enabled')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',parent):raise ValueError('Invalid Drive folder')
    if len(query)>200 or len(page)>4096:raise ValueError('Search or pagination value too long')
    orders={'name':'folder,name_natural','modified':'folder,modifiedTime desc','size':'folder,quotaBytesUsed desc'}
    types={'all':'','image':"mimeType contains 'image/'",'video':"mimeType contains 'video/'",'pdf':"mimeType = 'application/pdf'",'document':"(mimeType contains 'document' or mimeType contains 'spreadsheet' or mimeType contains 'presentation')"}
    if order not in orders or kind not in types:raise ValueError('Invalid Drive filter')
    conditions=['trashed = false']
    if parent=='shared':conditions.append('sharedWithMe = true')
    elif parent!='recent':conditions.append("'"+parent+"' in parents")
    if query:conditions.append("name contains '"+query.replace('\\','\\\\').replace("'","\\'")+"'")
    if types[kind]:conditions.append(types[kind])
    params={'q':' and '.join(conditions),'pageSize':40,'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,size,modifiedTime,hasThumbnail,parents,webViewLink)','orderBy':orders[order],'includeItemsFromAllDrives':'true','supportsAllDrives':'true'}
    if page:params['pageToken']=page
    with httpx.Client(headers={'Authorization':'Bearer '+google_auth.access_token()},timeout=30) as client:
        r=client.get('https://www.googleapis.com/drive/v3/files',params=params)
        if r.status_code!=200:raise ValueError('Drive folders could not load. Check Google sign-in and Drive permissions.')
        value=r.json()
    return {'files':value.get('files',[]),'next':value.get('nextPageToken',''),'incomplete':value.get('incompleteSearch',False)}

def thumbnail(file_id):
    """Proxy only Google's signed thumbnail URL; credentials never go to its host."""
    settings.require('google_enabled');settings.require('media_preview_enabled')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',file_id):raise ValueError('Invalid Drive file ID')
    from urllib.parse import urlparse
    import base64,io
    from PIL import Image
    with httpx.Client(timeout=20) as client:
        r=client.get('https://www.googleapis.com/drive/v3/files/'+file_id,params={'fields':'thumbnailLink','supportsAllDrives':'true'},headers={'Authorization':'Bearer '+google_auth.access_token()})
        if r.status_code!=200:return {'url':''}
        url=r.json().get('thumbnailLink','');parsed=urlparse(url)
        if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.googleusercontent.com'):return {'url':''}
        data=bytearray()
        with client.stream('GET',url) as response:
            if response.status_code!=200:return {'url':''}
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>2*1024*1024:return {'url':''}
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height>16000000:return {'url':''}
            im.thumbnail((320,220));out=io.BytesIO();im.convert('RGB').save(out,format='JPEG',quality=75)
        return {'url':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()}
