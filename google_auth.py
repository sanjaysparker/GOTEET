"""Installed-app OAuth: system browser, PKCE/state, OS credential storage."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode
import httpx
import keyring
from collector import DATA, now

SERVICE='in.droneos.workmate'
PENDING={}

def read_secret(name):
    value=keyring.get_password(SERVICE,name)
    return json.loads(value) if value else None

def save_secret(name,value):keyring.set_password(SERVICE,name,json.dumps(value))

def configure(value):
    value=value.get('installed',value)
    client=str(value.get('client_id','')).strip()
    if not client.endswith('.apps.googleusercontent.com'):raise ValueError('Use the client ID from a Google Desktop app OAuth client')
    save_secret('google-client',{'client_id':client,'client_secret':value.get('client_secret','')})
    return {'configured':True}

def status():
    try:
        token=read_secret('google-tokens')
        return {'configured':bool(read_secret('google-client')),'connected':bool(token),'profile':token.get('profile') if token else None}
    except Exception:
        return {'configured':False,'connected':False,'error':'OS credential store unavailable. Configure a supported keyring before signing in.'}

def start(redirect, workspace=False):
    config=read_secret('google-client')
    if not config:raise ValueError('Create a Google Desktop OAuth client and add its client ID in Connections first')
    verifier=secrets.token_urlsafe(64)
    state=secrets.token_urlsafe(32)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    PENDING[state]={'verifier':verifier,'redirect':redirect,'created':time.monotonic()}
    scope='openid email profile'
    if workspace:scope+=' https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/calendar.readonly'
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':config['client_id'],'redirect_uri':redirect,
      'response_type':'code','scope':scope,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent'})}

def finish(code,state):
    pending=PENDING.pop(state,None)
    if not pending or time.monotonic()-pending['created']>600:raise ValueError('Login state is invalid or expired. Start sign-in again.')
    config=read_secret('google-client')
    with httpx.Client(timeout=30) as client:
        response=client.post('https://oauth2.googleapis.com/token',data={**config,'code':code,'code_verifier':pending['verifier'],
          'redirect_uri':pending['redirect'],'grant_type':'authorization_code'})
        if response.status_code!=200:raise ValueError('Google could not complete sign-in. Check the Desktop OAuth client configuration.')
        token=response.json()
        profile=client.get('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+token['access_token']})
        profile.raise_for_status()
        token['profile']=profile.json();token['expires_at']=time.time()+token.get('expires_in',3600)
        save_secret('google-tokens',token)
    return token['profile']

def access_token():
    token=read_secret('google-tokens')
    if not token:raise ValueError('Sign in to Google first')
    if token.get('expires_at',0)<time.time()+60:
        config=read_secret('google-client')
        if not token.get('refresh_token'):raise ValueError('Google session expired. Sign in again.')
        r=httpx.post('https://oauth2.googleapis.com/token',data={**config,'refresh_token':token['refresh_token'],'grant_type':'refresh_token'},timeout=30)
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

def sync():
    from engine import read_json
    import concurrent.futures
    import datetime as dt
    headers={'Authorization':'Bearer '+access_token()}
    workspace=read_json('workspace.json');errors=[]
    with httpx.Client(headers=headers,timeout=30) as client:
        def get(url,params=None):
            r=client.get(url,params=params)
            if r.status_code!=200:raise ValueError('Google API access failed. Reconnect with Workspace access and enable the Gmail, Drive and Calendar APIs.')
            return r.json()
        try:
            ids=get('https://gmail.googleapis.com/gmail/v1/users/me/messages',{'maxResults':35,'q':'newer_than:14d -category:promotions -category:social -subject:verification -subject:password -subject:token'})
            def message(item):
                d=get('https://gmail.googleapis.com/gmail/v1/users/me/messages/'+item['id'],{'format':'metadata'})
                h={x['name'].lower():x['value'] for x in d.get('payload',{}).get('headers',[])}
                if any(w in h.get('subject','').lower() for w in ['verification','verify','sign-in','secure link','token','password']):return None
                return {'id':d['id'],'thread_id':d.get('threadId'),'subject':h.get('subject',''),'from':h.get('from',''),'snippet':d.get('snippet',''),'date':dt.datetime.fromtimestamp(int(d['internalDate'])/1000,dt.timezone.utc).isoformat(),'url':'https://mail.google.com/mail/u/0/#all/'+d['id']}
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:emails=[m for m in pool.map(message,ids.get('messages',[])) if m]
            workspace['gmail']={'emails':emails,'coverage':'First 35 matching messages; authentication messages excluded','captured_at':now(),'mode':'direct OAuth'}
        except Exception as e:errors.append({'source':'gmail','error':str(e)})
        try:
            files=get('https://www.googleapis.com/drive/v3/files',{'pageSize':100,'orderBy':'modifiedTime desc','q':'trashed = false','fields':'files(id,name,mimeType,modifiedTime,webViewLink,size)'})
            workspace['drive']={'files':[{'id':f['id'],'title':f['name'],'mime_type':f['mimeType'],'updated_at':f['modifiedTime'],'url':f.get('webViewLink',''),'size':f.get('size')} for f in files.get('files',[])],'coverage':'First 100 recent Drive metadata records','captured_at':now(),'mode':'direct OAuth'}
        except Exception as e:errors.append({'source':'drive','error':str(e)})
        try:
            today=dt.datetime.now(dt.timezone.utc)
            events=get('https://www.googleapis.com/calendar/v3/calendars/primary/events',{'timeMin':today.isoformat(),'timeMax':(today+dt.timedelta(days=7)).isoformat(),'maxResults':100,'singleEvents':'true','orderBy':'startTime'})
            workspace['calendar']={'events':events.get('items',[]),'coverage':'Primary calendar, upcoming seven days, first 100 events','captured_at':now(),'mode':'direct OAuth'}
        except Exception as e:errors.append({'source':'calendar','error':str(e)})
    workspace['last_refresh_attempt']=now();workspace['refresh_errors']=errors
    if not errors:workspace['captured_at']=now()
    workspace['integration_note']='Direct Google OAuth API refresh; each source has its own capture time. Errors retain prior source snapshots.'
    temp=DATA/'workspace.tmp';temp.write_text(json.dumps(workspace,indent=2));temp.replace(DATA/'workspace.json')
    return {'errors':errors,'captured_at':now()}
