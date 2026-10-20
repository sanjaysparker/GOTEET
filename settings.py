"""Owner preferences and enforced application capabilities, separate from OS grants."""
import json
from collector import DATA
DEFAULTS={'display_name':'Sanju','timezone':'Asia/Kolkata','start_view':'Today',
 'github_enabled':True,'local_index_enabled':True,'google_enabled':True,'voice_enabled':True,'agent_enabled':True,'attachments_enabled':True,'media_preview_enabled':True,'file_browser_enabled':True,'updates_repository':'',
 'role':'','organisation':'','location':'','website':'','bio':'','avatar_revision':'','accent':'#ffab65','density':'compact','reduce_motion':False}

def get():
    path=DATA/'settings.json'
    value=json.loads(path.read_text()) if path.exists() else {}
    return {**DEFAULTS,**value}

def save(value):
    current=get()
    for key,default in DEFAULTS.items():
        if key not in value:continue
        if isinstance(default,bool):
            if not isinstance(value[key],bool):raise ValueError('Permission values must be true or false')
        elif not isinstance(value[key],str) or len(value[key])>(1000 if key=='bio' else 200):raise ValueError('Invalid preference value')
        current[key]=value[key]
    if not current['display_name'].strip():raise ValueError('Enter a display name')
    import re
    if current['updates_repository'] and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',current['updates_repository']):raise ValueError('Use owner/repository for the update source')
    if current['accent'] not in {'#ffab65','#8cdbb1','#8fb9ff','#c2b3ff'}:raise ValueError('Choose an available accent colour')
    if current['density'] not in {'compact','comfortable'}:raise ValueError('Choose compact or comfortable density')
    if current['website'] and not current['website'].startswith('https://'):raise ValueError('Use an HTTPS website address')
    from zoneinfo import ZoneInfo
    ZoneInfo(current['timezone'])
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=DATA/'settings.json';temporary=DATA/'settings.tmp';temporary.write_text(json.dumps(current,indent=2));temporary.chmod(0o600);temporary.replace(path)
    return current

def require(capability):
    if not get().get(capability,False):raise PermissionError('This capability is disabled in Profile & settings → Permissions')
