"""Owner preferences and enforced application capabilities, separate from OS grants."""
import json
import os
import re
import tempfile
import threading
from zoneinfo import ZoneInfo
from collector import DATA
LOCK=threading.Lock()
THEMES={'noir','glacier','abyssal','cirrus','ember','phosphor','crimson','orchid','paper','graphite','midnight','light'}
DEFAULTS={'display_name':'Sanju','timezone':'Asia/Kolkata','start_view':'Today',
 'github_enabled':True,'local_index_enabled':True,'google_enabled':True,'voice_enabled':True,'agent_enabled':True,'attachments_enabled':True,'media_preview_enabled':True,'file_browser_enabled':True,'updates_repository':'',
 'role':'','organisation':'','location':'','website':'','bio':'','avatar_revision':'','activity_enabled':False,'theme':'noir','accent':'','density':'compact','reduce_motion':False,'auto_analysis':True,'analysis_provider':''}

def get():
    path=DATA/'settings.json'
    value=json.loads(path.read_text()) if path.exists() else {}
    return {**DEFAULTS,**value}

def save(value):
    if not isinstance(value,dict):raise ValueError('Settings must be an object')
    # One writer at a time: read-modify-write under a lock, unique temp file, atomic replace.
    with LOCK:
        current=get()
        for key,default in DEFAULTS.items():
            if key not in value:continue
            if isinstance(default,bool):
                if not isinstance(value[key],bool):raise ValueError('Permission values must be true or false')
            elif not isinstance(value[key],str) or len(value[key])>(1000 if key=='bio' else 200):raise ValueError('Invalid preference value')
            current[key]=value[key]
        if not current['display_name'].strip():raise ValueError('Enter a display name')
        if current['updates_repository'] and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',current['updates_repository']):raise ValueError('Use owner/repository for the update source')
        if current['accent'] and not re.fullmatch(r'#[0-9a-fA-F]{6}',current['accent']):raise ValueError('Use a six-digit hex accent colour')
        if current['theme'] not in THEMES:raise ValueError('Choose an available theme')
        if current['density'] not in {'compact','comfortable'}:raise ValueError('Choose compact or comfortable density')
        if current['website'] and not current['website'].startswith('https://'):raise ValueError('Use an HTTPS website address')
        try:ZoneInfo(current['timezone'])
        except Exception:raise ValueError('Choose a valid IANA timezone such as Asia/Kolkata')
        DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,temporary=tempfile.mkstemp(dir=DATA,prefix='settings-',suffix='.tmp')
        try:
            with os.fdopen(fd,'w') as handle:handle.write(json.dumps(current,indent=2))
            os.chmod(temporary,0o600);os.replace(temporary,DATA/'settings.json')
        except BaseException:
            if os.path.exists(temporary):os.unlink(temporary)
            raise
        return current

def require(capability):
    if not get().get(capability,False):raise PermissionError('This capability is disabled in Profile & settings → Permissions')
