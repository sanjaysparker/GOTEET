"""Regression tests for the backend defects in docs/concepts/BUG_AUDIT.md."""
import json
import sqlite3
import threading
import pytest
from fastapi.testclient import TestClient
import api
import engine
import google_auth
import media_library
import mcp_server
import operations
import settings

def H(token=None,**extra):return {'Authorization':'Bearer '+(token or api.TOKEN),**extra}

FULL={'title':'Ship','project':'GOTEET','owner':'Asha','priority':'High','due':'2026-11-02','start_date':'2026-10-25',
  'description':'Outcome','checklist':[{'text':'Check','done':False}],'source_url':'https://example.test/1','estimate':3,'labels':['ui']}

def test_partial_task_update_keeps_every_omitted_field(isolated):
    task=engine.save_task(FULL)
    updated=engine.save_task({'id':task['id'],'status':'Done'})
    for k,v in FULL.items():assert updated[k]==v,k
    assert updated['status']=='Done' and updated['key']==task['key'] and updated['created_at']==task['created_at']
    with TestClient(api.app) as client:
        r=client.post('/api/tasks',headers=H(),json={'id':task['id'],'title':'Ship v2'}).json()
        assert r['owner']=='Asha' and r['due']=='2026-11-02' and r['checklist']==FULL['checklist'] and r['status']=='Done'

def test_mcp_task_and_project_tools_send_only_supplied_fields(monkeypatch):
    sent=[]
    monkeypatch.setattr(mcp_server,'call',lambda method,path,value=None:sent.append(value) or value)
    mcp_server.workmate_save_task(id='t1',status='Done')
    mcp_server.workmate_save_project(id='p1',status='Active')
    assert sent==[{'id':'t1','status':'Done'},{'id':'p1','status':'Active'}]

def test_partial_project_update_keeps_dates_and_description(isolated):
    p=operations.save_project({'name':'Atlas','description':'Long brief','status':'Active','start_date':'2026-10-01','target_date':'2026-12-01'})
    updated=operations.save_project({'id':p['id'],'status':'At risk'})
    assert (updated['description'],updated['start_date'],updated['target_date'],updated['name'])==('Long brief','2026-10-01','2026-12-01','Atlas')
    with pytest.raises(ValueError,match='on or after'):operations.save_project({'id':p['id'],'start_date':'2027-01-01'})
    with pytest.raises(ValueError,match='must be text'):operations.save_project({'id':p['id'],'status':5})

def test_task_type_guards_and_new_status_priority_sets(isolated):
    for bad in [{'status':1},{'due':20261021},{'priority':['High']},{'start_date':True},{'title':7},{'estimate':'3'},{'labels':'ui'}]:
        with pytest.raises(ValueError):engine.save_task({'title':'Typed',**bad})
    for status in engine.STATUSES:assert engine.save_task({'title':'S','status':status})['status']==status
    for priority in engine.PRIORITIES:assert engine.save_task({'title':'P','priority':priority})['priority']==priority
    with TestClient(api.app) as client:
        assert client.post('/api/tasks',headers=H(),json={'title':'X','status':{'a':1}}).status_code==400
        assert client.post('/api/tasks',headers=H(),json={'title':'X','due':'21/10/2026'}).status_code==400

def test_settings_concurrent_saves_lose_nothing_and_bad_timezone_is_400(isolated):
    errors=[]
    def save(i):
        try:settings.save({'bio':'b'+str(i)} if i%2 else {'role':'r'+str(i)})
        except Exception as e:errors.append(e)
    threads=[threading.Thread(target=save,args=(i,)) for i in range(40)]
    [t.start() for t in threads];[t.join() for t in threads]
    assert errors==[]
    assert not list(isolated.glob('*.tmp'))
    assert json.loads((isolated/'settings.json').read_text())['display_name']=='Local user'
    with TestClient(api.app) as client:
        r=client.post('/api/settings',headers=H(),json={'timezone':'Mars/Olympus'})
        assert r.status_code==400 and 'timezone' in r.json()['detail']
        assert client.post('/api/settings',headers=H(),json={'theme':'phosphor','accent':''}).json()['theme']=='phosphor'
    assert settings.get()['auto_analysis'] is False and settings.get()['analysis_provider']==''

def account_workspace(data):
    preview=data/'drive-previews';preview.mkdir();cached=preview/'cached.pdf';cached.write_bytes(b'%PDF')
    media_library.CLOUD_PREVIEWS[str(cached)]='sub-a'
    (data/'workspace.json').write_text(json.dumps({'account':'a@example.test','gmail':{'emails':[{'subject':'A mail'}]},'drive':{'files':[1]},'calendar':{},'contacts':{},
      'google_tasks':{},'followups':[{'title':'A'}],'captured_at':'x','plane':{'status':'kept'}}))
    google_auth.DRIVE_SETUP.update(state='ready',message='Drive is ready')
    return cached

def assert_purged(data,cached):
    value=json.loads((data/'workspace.json').read_text())
    assert value=={'plane':{'status':'kept'}}
    assert google_auth.DRIVE_SETUP['state']=='idle' and media_library.CLOUD_PREVIEWS=={} and not cached.exists()

def test_google_logout_purges_account_snapshot(isolated,monkeypatch):
    cached=account_workspace(isolated)
    monkeypatch.setattr(google_auth,'read_secret',lambda name:{'access_token':'t'} if name=='google-tokens' else None)
    monkeypatch.setattr(google_auth.httpx,'post',lambda *a,**k:None)
    monkeypatch.setattr(google_auth.keyring,'delete_password',lambda *a:None)
    google_auth.disconnect()
    assert_purged(isolated,cached)

def test_google_sign_in_as_different_account_purges_previous_snapshot(isolated,monkeypatch):
    import httpx,time
    cached=account_workspace(isolated);saved={}
    secrets={'google-client':{'client_id':'c.apps.googleusercontent.com','client_secret':''},'google-tokens':{'profile':{'sub':'sub-a','email':'a@example.test'}}}
    monkeypatch.setattr(google_auth,'read_secret',lambda name:secrets.get(name))
    monkeypatch.setattr(google_auth,'save_secret',lambda name,value:saved.__setitem__(name,value))
    def handler(request):
        if request.url.path=='/token':return httpx.Response(200,json={'access_token':'new','expires_in':3600})
        return httpx.Response(200,json={'sub':'sub-b','email':'b@example.test'})
    original=httpx.Client
    monkeypatch.setattr(google_auth.httpx,'Client',lambda **k:original(transport=httpx.MockTransport(handler),**k))
    google_auth.PENDING['switch']={'verifier':'v','redirect':'http://127.0.0.1/cb','created':time.monotonic(),'scope':'openid','sources':[]}
    assert google_auth.finish('code','switch')['sub']=='sub-b'
    assert_purged(isolated,cached)
    assert saved['google-tokens']['profile']['email']=='b@example.test'

def test_same_account_sign_in_keeps_snapshot(isolated,monkeypatch):
    import httpx,time
    (isolated/'workspace.json').write_text(json.dumps({'account':'a@example.test','gmail':{'emails':[1]}}))
    secrets={'google-client':{'client_id':'c.apps.googleusercontent.com','client_secret':''},'google-tokens':{'profile':{'sub':'sub-a'},'refresh_token':'r'}}
    monkeypatch.setattr(google_auth,'read_secret',lambda name:secrets.get(name))
    monkeypatch.setattr(google_auth,'save_secret',lambda *a:None)
    original=httpx.Client
    monkeypatch.setattr(google_auth.httpx,'Client',lambda **k:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'access_token':'n','sub':'sub-a','email':'a@example.test'})),**k))
    google_auth.PENDING['same']={'verifier':'v','redirect':'r','created':time.monotonic(),'scope':'openid','sources':[]}
    google_auth.finish('code','same')
    assert json.loads((isolated/'workspace.json').read_text())['gmail']=={'emails':[1]}

def test_agent_plan_respects_agent_permission(isolated,monkeypatch):
    import agent
    monkeypatch.setattr(agent,'plan',lambda *a:{'id':'p1','plan':{'summary':'Do it','steps':[]}})
    with TestClient(api.app) as client:
        assert client.post('/api/agent/plan',headers=H(),json={'question':'x'}).status_code==200
        assert any(i['kind']=='agent' and i['ref_id']=='p1' for i in client.get('/api/inbox',headers=H()).json())
        settings.save({'agent_enabled':False})
        assert client.post('/api/agent/plan',headers=H(),json={'question':'x'}).status_code==403

def test_project_channel_attachments_and_bad_names(isolated):
    with TestClient(api.app) as client:
        project=client.post('/api/projects',headers=H(),json={'name':'Atlas'}).json()
        up=lambda target,name='a.txt':client.post('/api/attachments/upload?target_type=channel&target_id='+target,headers=H(),files={'file':(name,b'x','text/plain')})
        assert up('project-'+project['id']).status_code==200
        assert up('project-unknown').status_code==400
        assert up('random').status_code==400
        for name in ['..','.','/']:assert up('general',name).status_code==400,name

def test_actor_header_is_honoured_for_owner_only(isolated):
    with TestClient(api.app) as client:
        client.post('/api/tasks',headers=H(**{'X-GOTEET-Actor':'cli/mcp'}),json={'title':'From agent'})
        member=client.post('/api/team/invite',headers=H(),json={'name':'Ravi'}).json()['token']
        client.post('/api/tasks',headers=H(member,**{'X-GOTEET-Actor':'Sanju'}),json={'title':'From member'})
        actors=[a['actor'] for a in client.get('/api/audit',headers=H()).json() if a['action'].startswith('task:')]
        assert 'cli/mcp' in actors and 'Ravi' in actors and 'Sanju' not in actors

def test_team_uses_display_name(isolated):
    settings.save({'display_name':'Sanjay'})
    with TestClient(api.app) as client:assert client.get('/api/team',headers=H()).json()[0]['name']=='Sanjay'

def test_engine_wal_single_migration_and_closed_connections(isolated,monkeypatch):
    calls=[]
    original=engine.migrate
    monkeypatch.setattr(engine,'migrate',lambda c:calls.append(1) or original(c))
    for _ in range(5):
        with engine.connect() as c:c.execute('SELECT 1')
    assert calls==[1]
    with engine.connect() as c:assert c.execute('PRAGMA journal_mode').fetchone()[0]=='wal';assert c.execute('PRAGMA busy_timeout').fetchone()[0]==5000
    with pytest.raises(sqlite3.ProgrammingError):c.execute('SELECT 1')

def test_legacy_database_migrates_additively(isolated):
    raw=sqlite3.connect(isolated/'workmate.sqlite3')
    raw.executescript('''CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,project TEXT NOT NULL,owner TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,due TEXT NOT NULL,source_url TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL,start_date TEXT NOT NULL,target_date TEXT NOT NULL,updated_at TEXT NOT NULL);
      INSERT INTO projects VALUES('p','aigis-gcs','kept','Active','','','2026-10-01');
      INSERT INTO tasks VALUES('a','Old one','aigis-gcs','Sanju','Todo','High','','','2026-10-01T00:00:00+05:30','2026-10-01T00:00:00+05:30');
      INSERT INTO tasks VALUES('b','Old two','General','Sanju','Done','Low','','','2026-10-02T00:00:00+05:30','2026-10-02T00:00:00+05:30');
      INSERT INTO tasks VALUES('c','Old three','aigis-gcs','Sanju','Todo','Normal','','','2026-10-03T00:00:00+05:30','2026-10-03T00:00:00+05:30');''')
    raw.commit();raw.close()
    tasks={t['id']:t for t in engine.snapshot()['tasks']}
    assert (tasks['a']['key'],tasks['c']['key'],tasks['b']['key'])==('AIG-1','AIG-2','GOT-1')
    assert tasks['a']['title']=='Old one' and tasks['a']['priority']=='High' and tasks['a']['labels']==[] and tasks['a']['estimate']==0
    assert engine.snapshot()['projects'][0]['description']=='kept'
    assert engine.save_task({'title':'New','project':'aigis-gcs'})['key']=='AIG-3'
