import datetime as dt
from pathlib import Path
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
import api
import collector
import engine
import google_auth
import agent
import settings
import model_setup
import ui_control
import file_browser
import media_library

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    data=tmp_path/'data';data.mkdir()
    monkeypatch.setattr(engine,'DATA',data);monkeypatch.setattr(collector,'DATA',data)
    monkeypatch.setattr(engine,'STATE',tmp_path)
    monkeypatch.setattr(api,'DATA',data);monkeypatch.setattr(api,'STATE',tmp_path)
    monkeypatch.setattr(settings,'DATA',data)
    (data/'inventory.json').write_text(json.dumps({'github':[],'local':{'repos':[],'files':[]},'captured_at':'2026-10-21T09:00:00+05:30'}))
    (data/'workspace.json').write_text(json.dumps({'gmail':{'private':'owner mail'},'followups':[]}))
    return data

def headers(token=None):return {'Authorization':'Bearer '+(token or api.TOKEN)}

def test_media_preview_auth_range_and_path_boundary(workspace):
    file=(workspace/'frame.png').resolve();file.write_bytes(b'0123456789abcdef')
    inventory={'github':[],'local':{'repos':[],'files':[{'path':str(file),'name':file.name,'category':'Image','size':16}]}}
    (workspace/'inventory.json').write_text(json.dumps(inventory))
    with TestClient(api.app) as client:
        assert client.get('/api/media/info',params={'path':str(file)}).status_code==401
        assert client.get('/api/media/info',params={'path':'/etc/passwd'},headers=headers()).status_code==403
        assert client.get('/api/media/info',params={'path':str(file)},headers=headers()).json()['mime_type']=='image/png'
        result=client.get('/api/media/content',params={'path':str(file)},headers={**headers(),'Range':'bytes=4-8'})
        assert result.status_code==206 and result.content==b'45678'
        assert result.headers['content-range']=='bytes 4-8/16'
        linked=workspace/'link.png';linked.symlink_to(file)
        inventory['local']['files'].append({'path':str(linked),'name':'link.png'})
        (workspace/'inventory.json').write_text(json.dumps(inventory))
        assert client.get('/api/media/info',params={'path':str(linked)},headers=headers()).status_code==403
        settings.save({'media_preview_enabled':False})
        assert client.get('/api/media/content',params={'path':str(file)},headers=headers()).status_code==403

def test_ui_commands_are_bounded_and_acknowledged(workspace):
    ui_control.COMMANDS.clear();ui_control.STATE.clear()
    with TestClient(api.app) as client:
        assert client.post('/api/ui/command',headers=headers(),json={'action':'evaluate','value':'process.exit()'}).status_code==400
        assert client.post('/api/ui/command',headers=headers(),json={'action':'navigate','value':'Unknown'}).status_code==400
        result=client.post('/api/ui/command',headers=headers(),json={'action':'navigate','value':'Models'}).json()
        assert result['status']=='queued'
        assert client.get('/api/ui/pending',headers=headers()).json()[0]['id']==result['id']
        client.post('/api/ui/ack',headers=headers(),json={'id':result['id']})
        assert client.get('/api/ui/pending',headers=headers()).json()==[]
        client.post('/api/ui/state',headers=headers(),json={'route':'Models','query':'','media_path':''})
        assert client.get('/api/ui',headers=headers()).json()['connected']
        member=client.post('/api/team/invite',headers=headers(),json={'name':'Preview tester'}).json()
        assert client.get('/api/ui',headers=headers(member['token'])).status_code==403

def test_model_credentials_are_keychain_only_and_errors_redacted(workspace,monkeypatch):
    secrets={}
    monkeypatch.setattr(model_setup.keyring,'get_password',lambda service,name:secrets.get((service,name)))
    monkeypatch.setattr(model_setup.keyring,'set_password',lambda service,name,value:secrets.__setitem__((service,name),value))
    monkeypatch.setattr(model_setup.keyring,'delete_password',lambda service,name:secrets.pop((service,name),None))
    with TestClient(api.app) as client:
        result=client.post('/api/models/provider',headers=headers(),json={'provider':'nvidia','api_key':'test-fake-api-key','model':'example/model'})
        assert result.status_code==200 and 'test-fake-api-key' not in result.text
        assert model_setup.credentials('nvidia')['api_key']=='test-fake-api-key'
        assert not any('test-fake-api-key' in p.read_text(errors='ignore') for p in workspace.iterdir() if p.is_file())
        assert client.post('/api/models/provider',headers=headers(),json={'provider':'nvidia','model':'example/changed'}).status_code==200
        assert model_setup.credentials('nvidia')['api_key']=='test-fake-api-key'
        def fail(*args,**kwargs):raise __import__('httpx').ConnectError('private request details')
        monkeypatch.setattr(model_setup.httpx,'post',fail)
        with pytest.raises(ValueError,match='model request failed'):
            model_setup.chat('nvidia',[{'role':'user','content':'hello'}])
        assert client.post('/api/models/disconnect',headers=headers(),json={'provider':'nvidia'}).status_code==200
        assert not model_setup.credentials('nvidia')

def test_model_download_rejects_shell_and_remote_urls():
    for name in ['$(whoami)','https://evil.example/model','../../secret','qwen; rm file']:
        with pytest.raises(ValueError):model_setup.pull(name)

def test_file_browser_read_selection_and_protected_trash(workspace):
    file=(workspace/'local-photo.png').resolve()
    from PIL import Image
    Image.new('RGB',(800,400),(255,171,101)).save(file)
    listing=file_browser.listing(str(workspace),query='photo')
    assert listing['total']==1 and listing['items'][0]['previewable']
    assert file_browser.preview(str(file))['mime_type']=='image/png'
    assert media_library.thumbnail(str(file)).startswith(b'\x89PNG')
    with pytest.raises(PermissionError):file_browser.info(str(Path.home()),'trash')
    with pytest.raises(PermissionError):file_browser.info('/','trash')
    settings.save({'file_browser_enabled':False})
    with pytest.raises(PermissionError):file_browser.listing(str(workspace))
    with pytest.raises(PermissionError):media_library.info(str(file))

def test_agent_ui_action_is_not_done_before_desktop_ack(workspace):
    ui_control.COMMANDS.clear()
    step={k:'' for k in agent.Step.model_fields}
    step.update(action='navigate',reason='Open the requested page',title='Files')
    plan={'summary':'Open Files','steps':[step]}
    with agent.storage() as c:c.execute('INSERT INTO agent_plans VALUES(?,?,?,?,?,?)',('ui-proof','Open Files',json.dumps(plan),'[]','proposed','2026-10-21'))
    result=agent.execute('ui-proof')
    assert result['status']=='pending' and result['results'][0]['status']=='queued'
    assert agent.execute('ui-proof')['status']=='pending' and len(ui_control.COMMANDS)==1
    ui_control.acknowledge({'id':result['results'][0]['command_id']})
    assert agent.reconcile('ui-proof')['status']=='applied'

def test_agent_download_waits_for_ollama_completion(workspace,monkeypatch):
    job={'id':'download-proof','status':'downloading'}
    monkeypatch.setattr(model_setup,'pull',lambda name:job)
    monkeypatch.setitem(model_setup.JOBS,'download-proof',job)
    step={k:'' for k in agent.Step.model_fields};step.update(action='download_model',reason='Requested download',title='example:model')
    with agent.storage() as c:c.execute('INSERT INTO agent_plans VALUES(?,?,?,?,?,?)',('download-plan','Download requested model',json.dumps({'summary':'Download','steps':[step]}),'[]','proposed','2026-10-21'))
    assert agent.execute('download-plan')['status']=='pending'
    assert agent.reconcile('download-plan')['status']=='pending'
    job['status']='done'
    assert agent.reconcile('download-plan')['status']=='applied'

def test_profile_photo_is_normalized_and_owner_only(workspace):
    from PIL import Image
    import io
    source=io.BytesIO();Image.new('RGB',(600,300),(140,219,177)).save(source,format='JPEG')
    with TestClient(api.app) as client:
        member=client.post('/api/team/invite',headers=headers(),json={'name':'Profile test member'}).json()
        result=client.post('/api/profile/photo',headers=headers(),files={'file':('profile.jpg',source.getvalue(),'image/jpeg')})
        assert result.status_code==200 and result.json()['avatar_revision']
        with Image.open(workspace/'profile.png') as normalized:assert normalized.size==(256,256) and normalized.format=='PNG'
        assert client.get('/api/profile/photo',headers=headers()).status_code==200
        assert client.get('/api/profile/photo',headers=headers(member['token'])).status_code==403
        assert client.post('/api/profile/photo',headers=headers(),files={'file':('fake.png',b'<script>bad</script>','image/png')}).status_code==400
        result=client.post('/api/settings',headers=headers(),json={'role':'Founder','organisation':'Example team','accent':'#8cdbb1','density':'comfortable','reduce_motion':True})
        assert result.status_code==200 and result.json()['role']=='Founder'
        assert client.post('/api/settings',headers=headers(),json={'accent':'arbitrary'}).status_code==400

def test_tasks_validate_and_update_without_duplicate(workspace):
    with pytest.raises(ValueError):engine.save_task({'title':' '})
    t=engine.save_task({'title':'Review release','owner':'Sanju','status':'Todo'})
    engine.save_task({**t,'status':'Done'})
    assert len(engine.snapshot()['tasks'])==1
    assert engine.snapshot()['tasks'][0]['status']=='Done'

def test_report_ist_window_deduplicates_forks_and_excludes_future(workspace):
    commits=[{'sha':'same','date':'2026-10-20T23:00:00Z','url':'https://example.com/a','message':'One change','author':'A'},
      {'sha':'future','date':'2026-10-22T23:00:00Z','url':'https://example.com/b','message':'Future','author':'A'}]
    repos=[{'full_name':name,'html_url':'https://example.com','commits':commits,'pulls':[],'issues':[],'runs':[]} for name in ['a/main','b/fork']]
    (workspace/'inventory.json').write_text(json.dumps({'github':repos,'local':{'repos':[],'files':[]}}))
    record=engine.report('daily',dt.datetime(2026,10,21,9,tzinfo=collector.IST))
    assert '1 distinct commits observed' in record['content']
    assert 'Future' not in record['content']

def test_api_rejects_missing_or_wrong_credential(workspace):
    with TestClient(api.app) as client:
        assert client.get('/api/snapshot').status_code==401
        assert client.get('/api/tasks',headers=headers('wrong')).status_code==401
        assert client.get('/api/health').status_code==200

def test_member_chat_identity_and_personal_data_boundary(workspace):
    with TestClient(api.app) as client:
        invite=client.post('/api/team/invite',headers=headers(),json={'name':'Test colleague'}).json()
        member=headers(invite['token'])
        sent=client.post('/api/chat',headers=member,json={'body':'Hello','author_name':'Spoofed owner','channel':'development'})
        assert sent.status_code==200
        assert sent.json()['author_name']=='Test colleague'
        assert client.get('/api/chat?channel=development',headers=headers()).json()[0]['body']=='Hello'
        shared=client.get('/api/snapshot',headers=member).json()
        assert shared['workspace']=={} and shared['reports']==[] and shared['conversations']==[]
        assert client.get('/api/connections',headers=member).status_code==403
        assert client.post('/api/google/sync',headers=member,json={}).status_code==403
        assert client.post('/api/team/invite',headers=member,json={'name':'Other'}).status_code==403
        client.post('/api/team/revoke',headers=headers(),json={'id':invite['id']})
        assert client.get('/api/chat',headers=member).status_code==401

def test_timeline_dates_rejected_if_reversed(workspace):
    with TestClient(api.app) as client:
        response=client.post('/api/projects',headers=headers(),json={'name':'Project','start_date':'2026-10-25','target_date':'2026-10-21'})
        assert response.status_code==400
        assert client.post('/api/projects',headers=headers(),json={'name':'Project','status':'Active','start_date':'2026-10-21'}).status_code==200

def test_concept_update_keeps_one_live_record(workspace):
    with TestClient(api.app) as client:
        value=client.post('/api/concepts',headers=headers(),json={'title':'Idea','body':'First'}).json()
        client.post('/api/concepts',headers=headers(),json={**value,'body':'Revised'})
        result=client.get('/api/concepts',headers=headers()).json()
        assert len(result)==1 and result[0]['body']=='Revised'

def test_browser_origin_is_checked(workspace):
    with TestClient(api.app) as client:
        assert client.get('/api/tasks',headers={**headers(),'Origin':'https://untrusted.example'}).status_code==403

def test_google_oauth_requires_state_and_uses_pkce(monkeypatch):
    monkeypatch.setattr(google_auth,'read_secret',lambda _: {'client_id':'unit.apps.googleusercontent.com','client_secret':''})
    from urllib.parse import urlparse,parse_qs
    value=google_auth.start('http://127.0.0.1:12345/api/google/callback')
    query=parse_qs(urlparse(value['url']).query)
    assert query['code_challenge_method']==['S256']
    pending=google_auth.PENDING.pop(query['state'][0])
    assert len(pending['verifier'])>=43
    with pytest.raises(ValueError):google_auth.finish('invalid','not-a-real-state')

def test_media_tag_cannot_reference_arbitrary_files(workspace):
    with TestClient(api.app) as client:
        assert client.post('/api/media/tag',headers=headers(),json={'path':'/private/secrets','collection':'work'}).status_code==400

def test_failed_github_refresh_keeps_prior_snapshot(workspace,monkeypatch):
    original={'github':[{'full_name':'keep/repo'}],'captured_at':'previous'}
    (workspace/'inventory.json').write_text(json.dumps(original))
    def fail(*a,**k):raise RuntimeError('offline')
    monkeypatch.setattr(collector,'run',fail)
    monkeypatch.setattr(collector,'local_inventory',lambda:{'repos':[],'files':[]})
    result=collector.collect()
    assert result['github']==original['github']
    assert result['github_stale'] is True

def test_approved_agent_plan_applies_once_and_reports_results(workspace):
    step={k:'' for k in agent.Step.model_fields}
    step.update(action='create_task',reason='User requested this task',title='Review release',project='GOTEET',owner='Sanju',status='Todo',priority='Normal')
    plan={'summary':'Create requested task','steps':[step]}
    with agent.storage() as c:c.execute('INSERT INTO agent_plans VALUES(?,?,?,?,?,?)',('proof','Create task',json.dumps(plan),'[]','proposed','2026-10-21'))
    assert engine.snapshot()['tasks']==[]
    first=agent.execute('proof');second=agent.execute('proof')
    assert first['status']==second['status']=='applied'
    assert len(engine.snapshot()['tasks'])==1
    assert first['results'][0]['record_id']==second['results'][0]['record_id']

def test_agent_rejects_unsupported_operations_and_keeps_partial_truth(workspace):
    with pytest.raises(Exception):agent.Step.model_validate({'action':'run_shell'})
    step={k:'' for k in agent.Step.model_fields}
    step.update(action='create_task',reason='Invalid status test',title='Review',status='Invented')
    plan={'summary':'Invalid task','steps':[step]}
    with agent.storage() as c:c.execute('INSERT INTO agent_plans VALUES(?,?,?,?,?,?)',('invalid','Create task',json.dumps(plan),'[]','proposed','2026-10-21'))
    result=agent.execute('invalid')
    assert result['status']=='partial' and result['results'][0]['status']=='failed'
    assert engine.snapshot()['tasks']==[]

def test_voice_decoder_accepts_real_wav_input(tmp_path):
    import wave,struct,math
    from faster_whisper.audio import decode_audio
    sample=tmp_path/'sample.wav'
    with wave.open(str(sample),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000)
        out.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*i/16000))) for i in range(1600)))
    audio=decode_audio(str(sample))
    assert len(audio)==1600

def test_permissions_are_enforced_and_profile_is_saved(workspace):
    with TestClient(api.app) as client:
        result=client.post('/api/settings',headers=headers(),json={'display_name':'Workspace owner','agent_enabled':False,'voice_enabled':False,'attachments_enabled':False,'google_enabled':False})
        assert result.status_code==200
        assert client.get('/api/snapshot',headers=headers()).json()['identity']['name']=='Workspace owner'
        assert client.post('/api/agent/execute',headers=headers(),json={'id':'anything'}).status_code==403
        assert client.post('/api/google/start',headers=headers(),json={}).status_code==403
        assert client.post('/api/voice/transcribe',headers=headers(),files={'audio':('x.webm',b'audio','audio/webm')}).status_code==403
        assert client.post('/api/attachments/upload?target_type=channel&target_id=general',headers=headers(),files={'file':('x.txt',b'hello','text/plain')}).status_code==403

def test_attachment_roundtrip_preserves_original_bytes(workspace):
    with TestClient(api.app) as client:
        created=client.post('/api/attachments/upload?target_type=channel&target_id=general',headers=headers(),files={'file':('../../note.txt',b'timeline evidence','text/plain')})
        assert created.status_code==200
        item=created.json()
        assert item['name']=='note.txt'
        assert item['sha256']==hashlib.sha256(b'timeline evidence').hexdigest()
        downloaded=client.get('/api/attachments/download?id='+item['id'],headers=headers())
        assert downloaded.content==b'timeline evidence'
        assert client.get('/api/attachments/download?id=../../secret',headers=headers()).status_code==404

def test_google_selected_scopes_are_readonly(monkeypatch):
    from urllib.parse import urlparse,parse_qs
    monkeypatch.setattr(google_auth,'read_secret',lambda _: {'client_id':'unit.apps.googleusercontent.com','client_secret':''})
    result=google_auth.start('http://127.0.0.1:12345/api/google/callback',sources=['contacts','google_tasks'])
    query=parse_qs(urlparse(result['url']).query)
    assert google_auth.SCOPES['contacts'] in query['scope'][0]
    assert google_auth.SCOPES['google_tasks'] in query['scope'][0]
    assert google_auth.SCOPES['gmail'] not in query['scope'][0]
    assert query['include_granted_scopes']==['true']
    with pytest.raises(ValueError):google_auth.start('http://127.0.0.1:12345/api/google/callback',sources=['gmail.modify'])

def test_google_import_partial_failure_retains_snapshot_and_filters_mail(workspace,monkeypatch):
    import httpx
    monkeypatch.setattr(google_auth,'DATA',workspace)
    token={'access_token':'fake','scope':' '.join(google_auth.SCOPES.values()),'profile':{'email':'owner@example.test'}}
    monkeypatch.setattr(google_auth,'access_token',lambda:'fake')
    monkeypatch.setattr(google_auth,'read_secret',lambda _:token)
    (workspace/'workspace.json').write_text(json.dumps({'account':'owner@example.test','drive':{'files':[{'title':'Retained file'}],'captured_at':'previous'}}))
    original=httpx.Client
    def handler(request):
        path=request.url.path
        if path.endswith('/messages'):return httpx.Response(200,json={'messages':[{'id':'auth'},{'id':'work'}]})
        if '/messages/' in path:
            return httpx.Response(200,json={'id':path.rsplit('/',1)[-1],'internalDate':'1792534972000','snippet':'never persist body or snippet','payload':{'headers':[{'name':'Subject','value':'Your verification code' if path.endswith('/auth') else 'Project review'}]}})
        if '/drive/' in path:return httpx.Response(403,json={})
        if path.endswith('/connections'):return httpx.Response(200,json={'connections':[{'resourceName':'people/1','names':[{'displayName':'Test Person'}],'emailAddresses':[{'value':'person@example.test'}]}]})
        if path.endswith('/users/@me/lists'):return httpx.Response(200,json={'items':[{'id':'list1','title':'Work'}]})
        if path.endswith('/lists/list1/tasks'):return httpx.Response(200,json={'items':[{'id':'task1','title':'Review project','status':'needsAction'}]})
        return httpx.Response(200,json={'items':[]})
    monkeypatch.setattr(google_auth.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    result=google_auth.sync(['gmail','drive','contacts','google_tasks'])
    assert result['results']['gmail']['count']==1
    assert result['results']['contacts']['count']==1 and result['results']['google_tasks']['count']==1
    assert result['errors'][0]['source']=='drive'
    data=json.loads((workspace/'workspace.json').read_text())
    assert data['drive']['captured_at']=='previous'
    assert 'snippet' not in data['gmail']['emails'][0]
    assert data['google_tasks']['tasks'][0]['list_title']=='Work'
    assert engine.snapshot()['tasks']==[]
    assert not (workspace/'workspace.json').stat().st_mode & 0o077

def test_google_missing_scope_and_account_switch_do_not_mix_data(workspace,monkeypatch):
    monkeypatch.setattr(google_auth,'DATA',workspace)
    monkeypatch.setattr(google_auth,'access_token',lambda:'fake')
    monkeypatch.setattr(google_auth,'read_secret',lambda _:{'scope':'openid email profile','profile':{'email':'new@example.test'}})
    (workspace/'workspace.json').write_text(json.dumps({'account':'old@example.test','gmail':{'emails':[{'subject':'Old account'}]},'followups':[{'title':'Old'}],'plane':{'status':'offline'}}))
    result=google_auth.sync(['gmail'])
    assert 'permission not granted' in result['errors'][0]['error']
    value=json.loads((workspace/'workspace.json').read_text())
    assert 'gmail' not in value and 'followups' not in value
    assert value['plane']['status']=='offline' and value['account']=='new@example.test'


def test_google_basic_login_does_not_request_data_and_logout_cancels_pending(monkeypatch):
    import google_auth
    from urllib.parse import urlparse, parse_qs
    monkeypatch.setattr(google_auth,'read_secret',lambda name: {'client_id':'test.apps.googleusercontent.com','client_secret':''} if name=='google-client' else None)
    query=parse_qs(urlparse(google_auth.start('http://127.0.0.1/callback',sources=[])['url']).query)
    assert query['scope']==['openid email profile']
    assert query['prompt']==['select_account']
    assert query['include_granted_scopes']==['false']
    assert google_auth.PENDING
    google_auth.disconnect()
    assert not google_auth.PENDING


def test_google_completion_page_escapes_identity():
    import google_auth
    page=google_auth.completion_page({'name':'<script>alert(1)</script>','email':'a&b@example.test'})
    assert '<script>alert' not in page
    assert 'a&amp;b@example.test' in page
    assert 'goteet://account' in page
    assert 'Sign-in cancelled.' in google_auth.completion_page(cancelled=True)
