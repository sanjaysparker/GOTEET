"""Installed-app OAuth: system browser, PKCE/state, OS credential storage."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode, quote, urlparse
import threading
import re
import httpx
import keyring
from collector import DATA, now

SERVICE='in.droneos.workmate'
PENDING={}
SYNC_LOCK=threading.Lock()
SCOPES={
 'gmail':'https://www.googleapis.com/auth/gmail.readonly',
 'drive':'https://www.googleapis.com/auth/drive.metadata.readonly',
 'calendar':'https://www.googleapis.com/auth/calendar.readonly',
 'contacts':'https://www.googleapis.com/auth/contacts.readonly',
 'google_tasks':'https://www.googleapis.com/auth/tasks.readonly'}
LABELS={'gmail':'Gmail','drive':'Drive','calendar':'Calendar','contacts':'Contacts','google_tasks':'Google Tasks'}


def read_secret(name):
    value=keyring.get_password(SERVICE,name)
    return json.loads(value) if value else None

def save_secret(name,value):keyring.set_password(SERVICE,name,json.dumps(value))

def configure(value):
    value=value.get('installed',value)
    client=str(value.get('client_id','')).strip()
    if not client.endswith('.apps.googleusercontent.com'):raise ValueError('Use the client ID from a Google Desktop app OAuth client')
    save_secret('google-client',{'client_id':client,'client_secret':value.get('client_secret',''),'project_id':str(value.get('project_id',''))[:200]})
    return {'configured':True}

def status():
    try:
        token=read_secret('google-tokens')
        config=read_secret('google-client') or {}
        granted=set((token or {}).get('scope','').split())
        return {'configured':bool(config),'connected':bool(token),'profile':token.get('profile') if token else None,
          'project_id':config.get('project_id',''),'sources':{name:scope in granted for name,scope in SCOPES.items()}}
    except Exception:
        return {'configured':False,'connected':False,'error':'OS credential store unavailable. Configure a supported keyring before signing in.'}

def start(redirect, workspace=False, sources=None):
    config=read_secret('google-client')
    if not config:raise ValueError('Create a Google Desktop OAuth client and add its client ID in Connections first')
    verifier=secrets.token_urlsafe(64)
    state=secrets.token_urlsafe(32)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    selected=sources if sources is not None else (['gmail','drive','calendar'] if workspace else [])
    if not isinstance(selected,list) or any(name not in SCOPES for name in selected):raise ValueError('Choose supported Google sources')
    scope=' '.join(['openid','email','profile']+[SCOPES[name] for name in dict.fromkeys(selected)])
    PENDING[state]={'verifier':verifier,'redirect':redirect,'created':time.monotonic(),'scope':scope}
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':config['client_id'],'redirect_uri':redirect,
      'response_type':'code','scope':scope,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent','include_granted_scopes':'true'})}

def finish(code,state):
    pending=PENDING.pop(state,None)
    if not pending or time.monotonic()-pending['created']>600:raise ValueError('Login state is invalid or expired. Start sign-in again.')
    config=read_secret('google-client')
    with httpx.Client(timeout=30) as client:
        response=client.post('https://oauth2.googleapis.com/token',data={**{k:config[k] for k in ['client_id','client_secret']},'code':code,'code_verifier':pending['verifier'],
          'redirect_uri':pending['redirect'],'grant_type':'authorization_code'})
        if response.status_code!=200:raise ValueError('Google could not complete sign-in. Check the Desktop OAuth client configuration.')
        token=response.json()
        profile=client.get('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+token['access_token']})
        profile.raise_for_status()
        token['profile']=profile.json()
        previous=read_secret('google-tokens') or {}
        if previous.get('profile',{}).get('sub')==token['profile'].get('sub') and not token.get('refresh_token') and previous.get('refresh_token'):
            token['refresh_token']=previous['refresh_token']
        token.setdefault('scope',pending['scope'])
        token['expires_at']=time.time()+token.get('expires_in',3600)
        save_secret('google-tokens',token)
    return token['profile']

def access_token():
    token=read_secret('google-tokens')
    if not token:raise ValueError('Sign in to Google first')
    if token.get('expires_at',0)<time.time()+60:
        config=read_secret('google-client')
        if not token.get('refresh_token'):raise ValueError('Google session expired. Sign in again.')
        r=httpx.post('https://oauth2.googleapis.com/token',data={**{k:config[k] for k in ['client_id','client_secret']},'refresh_token':token['refresh_token'],'grant_type':'refresh_token'},timeout=30)
        if r.status_code!=200:raise ValueError('Google session could not refresh. Sign in again.')
        token.update(r.json());token['expires_at']=time.time()+token.get('expires_in',3600);save_secret('google-tokens',token)
    return token['access_token']

def disconnect():
    token=read_secret('google-tokens')
    if token:
        try:httpx.post('https://oauth2.googleapis.com/revoke',data={'token':token.get('refresh_token') or token['access_token']},timeout=15)
        except httpx.HTTPError:pass
        keyring.delete_password(SERVICE,'google-tokens')
    return {'connected':False}

def import_profile():
    """Apply Google name and validated photo locally only on the user's explicit action."""
    import settings
    import io
    import uuid
    from PIL import Image, ImageOps
    token=read_secret('google-tokens')
    if not token:raise ValueError('Sign in to Google first')
    profile=token.get('profile',{});changes={};warnings=[]
    if profile.get('name'):changes['display_name']=str(profile['name'])[:200]
    picture=profile.get('picture','');host=urlparse(picture).hostname or ''
    if picture and urlparse(picture).scheme=='https' and (host=='googleusercontent.com' or host.endswith('.googleusercontent.com')):
        try:
            with httpx.stream('GET',picture,timeout=15,follow_redirects=False) as response:
                response.raise_for_status();payload=bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload)>12_000_000:raise ValueError('Photo exceeds size limit')
            with Image.open(io.BytesIO(payload)) as image:
                if image.width*image.height>20_000_000:raise ValueError('Photo exceeds pixel limit')
                photo=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'),(256,256))
                DATA.mkdir(parents=True,exist_ok=True);photo.save(DATA/'profile.png',format='PNG');(DATA/'profile.png').chmod(0o600)
            changes['avatar_revision']=str(uuid.uuid4())
        except Exception:warnings.append('Google name imported; photo unavailable. You can choose a local photo.')
    return {'settings':settings.save(changes),'warnings':warnings}

def sync(sources=None):
    if not SYNC_LOCK.acquire(blocking=False):raise ValueError('Google import is already running')
    try:return _sync(sources)
    finally:SYNC_LOCK.release()

def _sync(sources=None):
    from engine import read_json
    import concurrent.futures
    import datetime as dt
    selected=sources if sources is not None else list(SCOPES)
    if not isinstance(selected,list) or any(name not in SCOPES for name in selected):raise ValueError('Choose supported Google sources')
    selected=list(dict.fromkeys(selected));headers={'Authorization':'Bearer '+access_token()}
    granted=set((read_secret('google-tokens') or {}).get('scope','').split())
    workspace=read_json('workspace.json');errors=[];results={}
    account=(read_secret('google-tokens') or {}).get('profile',{}).get('email','')
    # Avoid mixing two Google accounts' personal snapshots after account switching.
    if workspace.get('account') and account and workspace['account']!=account:
        for key in [*SCOPES,'followups','daily_refresh','captured_at']:workspace.pop(key,None)
    if account:workspace['account']=account
    with httpx.Client(headers=headers,timeout=30) as client:
        def get(url,params=None):
            r=client.get(url,params=params)
            if r.status_code==401:raise ValueError('Session expired. Sign in again.')
            if r.status_code==403:raise ValueError('Access denied. Enable this Google API and reconnect with its read permission; check Workspace administrator restrictions.')
            if r.status_code==429:raise ValueError('Google rate limit reached. Retry later.')
            if r.status_code!=200:raise ValueError('Google request failed (HTTP '+str(r.status_code)+'). Retry later.')
            return r.json()
        def pages(url,params,key,limit):
            rows=[];token=None
            for _ in range(10):
                value=get(url,{**params,**({'pageToken':token} if token else {})});rows.extend(value.get(key,[]));token=value.get('nextPageToken')
                if not token or len(rows)>=limit:break
            return rows[:limit],bool(token or len(rows)>limit)
        def fetch(name):
            if SCOPES[name] not in granted:raise ValueError('Read permission not granted. Select this source and connect Google again.')
            if name=='gmail':
                ids,truncated=pages('https://gmail.googleapis.com/gmail/v1/users/me/messages',{'maxResults':100,'q':'newer_than:30d -category:promotions -category:social -subject:(verification OR password OR token OR OTP OR login OR payroll OR salary OR payslip OR identity)'},'messages',100)
                def message(item):
                    d=get('https://gmail.googleapis.com/gmail/v1/users/me/messages/'+quote(item['id'],safe=''),{'format':'metadata','metadataHeaders':['Subject','From','Date']})
                    h={x['name'].lower():x['value'] for x in d.get('payload',{}).get('headers',[])}
                    if re.search(r'verif|sign.in|secure link|token|password|otp|one.time|security code|payroll|salary|payslip|identity',h.get('subject',''),re.I):return None
                    return {'id':d['id'],'thread_id':d.get('threadId'),'subject':h.get('subject',''),'from':h.get('from',''),'date':dt.datetime.fromtimestamp(int(d['internalDate'])/1000,dt.timezone.utc).isoformat(),'url':'https://mail.google.com/mail/u/?authuser='+quote(account)+'#all/'+d['id']}
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:items=[m for m in pool.map(message,ids) if m]
                return {'emails':items,'coverage':'Last 30 days; up to 100 messages; headers only; authentication/identity/payroll subjects excluded','truncated':truncated},len(items)
            if name=='drive':
                items,truncated=pages('https://www.googleapis.com/drive/v3/files',{'pageSize':100,'orderBy':'modifiedTime desc','q':'trashed = false','fields':'nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,size,parents)','includeItemsFromAllDrives':'true','supportsAllDrives':'true'},'files',500)
                return {'files':[{'id':f['id'],'title':f['name'],'mime_type':f['mimeType'],'updated_at':f.get('modifiedTime'),'url':f.get('webViewLink',''),'size':f.get('size'),'parents':f.get('parents',[])} for f in items],'coverage':'Up to 500 recent accessible Drive files/folders; metadata only, including shared-drive items','truncated':truncated},len(items)
            if name=='calendar':
                today=dt.datetime.now(dt.timezone.utc)
                items,truncated=pages('https://www.googleapis.com/calendar/v3/calendars/primary/events',{'timeMin':today.isoformat(),'timeMax':(today+dt.timedelta(days=30)).isoformat(),'maxResults':100,'singleEvents':'true','orderBy':'startTime','fields':'nextPageToken,items(id,summary,start,end,htmlLink,status,location)'},'items',500)
                return {'events':items,'coverage':'Primary calendar, next 30 days, up to 500 events','truncated':truncated},len(items)
            if name=='contacts':
                items,truncated=pages('https://people.googleapis.com/v1/people/me/connections',{'pageSize':100,'personFields':'names,emailAddresses,organizations','sortOrder':'LAST_MODIFIED_DESCENDING'},'connections',500)
                contacts=[{'id':v.get('resourceName'),'name':next((n.get('displayName','') for n in v.get('names',[])),''),'emails':[e['value'] for e in v.get('emailAddresses',[])],'organisations':[o.get('name','') for o in v.get('organizations',[])]} for v in items]
                return {'contacts':contacts,'coverage':'Up to 500 saved contacts: names, email addresses and organisations','truncated':truncated},len(contacts)
            lists,truncated=pages('https://tasks.googleapis.com/tasks/v1/users/@me/lists',{'maxResults':100},'items',100)
            tasks=[]
            for tasklist in lists[:20]:
                items,more=pages('https://tasks.googleapis.com/tasks/v1/lists/'+quote(tasklist['id'],safe='')+'/tasks',{'maxResults':100,'showCompleted':'true','showHidden':'false','fields':'nextPageToken,items(id,title,status,due,completed,updated,webViewLink)'},'items',100)
                truncated=truncated or more
                tasks.extend([{**t,'list_id':tasklist['id'],'list_title':tasklist['title']} for t in items])
            return {'tasks':tasks,'lists':[{'id':v['id'],'title':v['title']} for v in lists[:20]],'coverage':'First 20 Google task lists, up to 100 tasks each; imported read-only, not assigned to local teammates','truncated':truncated or len(lists)>20},len(tasks)
        for name in selected:
            try:
                value,count=fetch(name);workspace[name]={**value,'captured_at':now(),'mode':'direct OAuth'}
                results[name]={'count':count,'captured_at':workspace[name]['captured_at'],'truncated':value['truncated']}
            except Exception as error:
                detail=str(error) if isinstance(error,ValueError) else 'Google source could not be read. Retry or check connection.'
                errors.append({'source':name,'error':detail})
    workspace['last_refresh_attempt']=now();workspace['refresh_errors']=errors
    if not errors and selected:workspace['captured_at']=now()
    workspace['integration_note']='Direct Google OAuth import; each source retains its own capture time. Failed imports retain previous same-account data.'
    DATA.mkdir(parents=True,exist_ok=True);temp=DATA/'workspace.tmp';temp.write_text(json.dumps(workspace,indent=2));temp.chmod(0o600);temp.replace(DATA/'workspace.json')
    return {'errors':errors,'results':results,'captured_at':now()}
