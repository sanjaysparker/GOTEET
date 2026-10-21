"""Work-management API v1 contract (docs/API_V1.md)."""
import datetime as dt
import pytest
from fastapi.testclient import TestClient
import api
import engine
import settings
import work

def H(token=None,**extra):return {'Authorization':'Bearer '+(token or api.TOKEN),**extra}

@pytest.fixture
def client(isolated):
    with TestClient(api.app) as c:yield c

@pytest.fixture
def member(client):return H(client.post('/api/team/invite',headers=H(),json={'name':'Ravi'}).json()['token'])

def task(client,**v):
    r=client.post('/api/tasks',headers=H(),json={'title':'Task',**v});assert r.status_code==200,r.text;return r.json()

def test_task_keys_new_columns_and_snapshot(client):
    client.post('/api/projects',headers=H(),json={'name':'Aigis GCS'})
    a=task(client,project='Aigis GCS',estimate=5,labels=['ui',' ui ','api']);b=task(client,project='Aigis GCS');g=task(client)
    assert (a['key'],b['key'],g['key'])==('AIG-1','AIG-2','GOT-1')
    assert a['labels']==['ui','api'] and a['estimate']==5 and a['cycle_id']=='' and a['parent_id']==''
    child=task(client,parent_id=a['id'])
    assert client.post('/api/tasks',headers=H(),json={'id':a['id'],'parent_id':child['id']}).status_code==400
    assert client.post('/api/tasks',headers=H(),json={'id':a['id'],'parent_id':'missing'}).status_code==400
    moved=client.post('/api/tasks',headers=H(),json={'id':a['id'],'project':'General'}).json()
    assert moved['key']=='AIG-1'
    snap=client.get('/api/snapshot',headers=H()).json()['tasks']
    assert {t['key'] for t in snap}=={'AIG-1','AIG-2','GOT-1','GOT-2'} and isinstance(snap[0]['labels'],list)
    assert isinstance(client.get('/api/tasks',headers=H()).json()[0]['labels'],list)

def test_deletes_are_owner_only_and_keep_project_tasks(client,member):
    p=client.post('/api/projects',headers=H(),json={'name':'Atlas'}).json()
    a=task(client,project='Atlas');b=task(client,project='Atlas',parent_id=a['id'])
    concept=client.post('/api/concepts',headers=H(),json={'title':'Idea','body':''}).json()
    rel=client.post('/api/relations',headers=H(),json={'from_id':a['id'],'to_id':b['id'],'type':'blocks'}).json()
    assert client.delete('/api/tasks/'+a['id'],headers=member).status_code==403
    assert client.delete('/api/projects/'+p['id'],headers=H()).status_code==200
    assert len(client.get('/api/tasks',headers=H()).json())==2 and client.get('/api/projects',headers=H()).json()==[]
    r=client.delete('/api/tasks/'+a['id'],headers=H()).json()
    assert r['relations_removed']==1 and client.get('/api/relations',headers=H()).json()==[]
    assert client.get('/api/tasks',headers=H()).json()[0]['parent_id']==''
    assert client.delete('/api/concepts/'+concept['id'],headers=H()).status_code==200
    assert client.delete('/api/concepts/'+concept['id'],headers=H()).status_code==404
    assert client.delete('/api/tasks/missing',headers=H()).status_code==404
    actions=[x['action'] for x in client.get('/api/audit',headers=H()).json()]
    assert {'task:delete:'+a['id'],'project:delete:'+p['id'],'concept:delete:'+concept['id']}<=set(actions)
    assert rel['type']=='blocks'

def test_relations_both_directions_and_validation(client,member):
    a=task(client);b=task(client);c=task(client)
    r1=client.post('/api/relations',headers=member,json={'from_id':a['id'],'to_id':b['id'],'type':'blocks'}).json()
    again=client.post('/api/relations',headers=H(),json={'from_id':a['id'],'to_id':b['id'],'type':'blocks'}).json()
    assert again['id']==r1['id']
    client.post('/api/relations',headers=H(),json={'from_id':c['id'],'to_id':b['id'],'type':'relates'})
    assert len(client.get('/api/relations',params={'task_id':b['id']},headers=H()).json())==2
    assert client.get('/api/relations',params={'task_id':a['id']},headers=H()).json()==[{'id':r1['id'],'from_id':a['id'],'to_id':b['id'],'type':'blocks'}]
    for bad in [{'from_id':a['id'],'to_id':a['id'],'type':'blocks'},{'from_id':a['id'],'to_id':'nope','type':'blocks'},{'from_id':a['id'],'to_id':b['id'],'type':'parent'}]:
        assert client.post('/api/relations',headers=H(),json=bad).status_code==400
    assert client.delete('/api/relations/'+r1['id'],headers=member).status_code==403
    assert client.delete('/api/relations/'+r1['id'],headers=H()).status_code==200

def test_cycles_status_stats_history_and_delete(client,monkeypatch):
    today=work.today()
    active=client.post('/api/cycles',headers=H(),json={'name':'Sprint 1','start':str(today-dt.timedelta(days=2)),'end':str(today+dt.timedelta(days=5)),'goal':'Ship'}).json()
    upcoming=client.post('/api/cycles',headers=H(),json={'name':'Sprint 2','start':str(today+dt.timedelta(days=6)),'end':str(today+dt.timedelta(days=12))}).json()
    done=client.post('/api/cycles',headers=H(),json={'name':'Sprint 0','start':str(today-dt.timedelta(days=20)),'end':str(today-dt.timedelta(days=10))}).json()
    assert (active['status'],upcoming['status'],done['status'])==('active','upcoming','completed')
    assert client.post('/api/cycles',headers=H(),json={'name':'Bad','start':'2026-10-10','end':'2026-10-01'}).status_code==400
    assert client.post('/api/tasks',headers=H(),json={'title':'x','cycle_id':'nope'}).status_code==400
    a=task(client,cycle_id=active['id'],estimate=3);b=task(client,cycle_id=active['id'],estimate=5,status='Blocked')
    client.post('/api/tasks',headers=H(),json={'id':a['id'],'status':'Done'})
    cycle=next(c for c in client.get('/api/cycles',headers=H()).json() if c['id']==active['id'])
    s=cycle['stats']
    assert (s['issues'],s['done'],s['points'],s['done_points'],s['blocked'])==(2,1,8,3,1)
    assert [h['date'] for h in s['history']]==[str(today-dt.timedelta(days=i)) for i in (2,1,0)]
    assert s['history'][-1]=={'date':str(today),'scope':2,'done':1} and s['history'][0]['scope']==0
    renamed=client.post('/api/cycles',headers=H(),json={'id':active['id'],'goal':'Ship it'}).json()
    assert renamed['name']=='Sprint 1' and renamed['goal']=='Ship it'
    assert client.delete('/api/cycles/'+active['id'],headers=H()).json()['tasks_unset']==2
    assert all(t['cycle_id']=='' for t in client.get('/api/tasks',headers=H()).json())

def test_docs_merge_and_delete(client,member):
    a=task(client)
    d=client.post('/api/docs',headers=member,json={'title':'Spec','body':'# Hello','project':'Atlas','linked_tasks':[a['id']]}).json()
    assert d['author']=='Ravi'
    client.post('/api/docs',headers=H(),json={'id':d['id'],'title':'Spec v2'})
    got=client.get('/api/docs',headers=H()).json()[0]
    assert (got['title'],got['body'],got['project'],got['linked_tasks'])==('Spec v2','# Hello','Atlas',[a['id']])
    assert set(got)=={'id','title','body','project','linked_tasks','updated_at','author'}
    assert client.post('/api/docs',headers=H(),json={'title':'x','linked_tasks':['missing']}).status_code==400
    assert client.delete('/api/docs/'+d['id'],headers=H()).status_code==200 and client.get('/api/docs',headers=H()).json()==[]

def test_saved_views(client):
    v=client.post('/api/views',headers=H(),json={'name':'My blocked','filters':{'status':'Blocked','owner':'Sanju'}}).json()
    assert client.get('/api/views',headers=H()).json()[0]['filters']=={'status':'Blocked','owner':'Sanju'}
    assert client.post('/api/views',headers=H(),json={'id':v['id'],'name':'Renamed'}).json()['filters']['status']=='Blocked'
    assert client.post('/api/views',headers=H(),json={'name':'Bad','filters':{'sql':'1'}}).status_code==400
    assert client.delete('/api/views/'+v['id'],headers=H()).status_code==200 and client.get('/api/views',headers=H()).json()==[]

def test_inbox_events_read_and_snooze(client,member):
    settings.save({'display_name':'Sanju'})
    t=task(client,owner='Asha')
    client.post('/api/tasks',headers=H(),json={'id':t['id'],'status':'In review'})
    client.post('/api/tasks',headers=H(),json={'id':t['id'],'status':'Blocked'})
    client.post('/api/chat',headers=member,json={'body':'hey @sanju can you look','channel':'general'})
    client.post('/api/chat',headers=member,json={'body':'mail me at x@sanjupal.dev','channel':'general'})
    items=client.get('/api/inbox',headers=H()).json()
    assert [i['kind'] for i in items]==['mention','blocked','status','assigned']
    assert set(items[0])=={'id','kind','title','detail','ref_type','ref_id','actor','created_at','read'} and items[0]['actor']=='Ravi'
    assert items[1]['ref_type']=='task' and items[1]['ref_id']==t['id'] and not items[1]['read']
    client.post('/api/inbox/read',headers=H(),json={'ids':[items[0]['id']]})
    assert client.get('/api/inbox',headers=H()).json()[0]['read'] is True
    client.post('/api/inbox/read',headers=H(),json={'ids':'all'})
    assert all(i['read'] for i in client.get('/api/inbox',headers=H()).json())
    later=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=2)).isoformat()
    assert client.post('/api/inbox/snooze',headers=H(),json={'id':items[1]['id'],'until':later}).status_code==200
    assert items[1]['id'] not in [i['id'] for i in client.get('/api/inbox',headers=H()).json()]
    client.post('/api/inbox/snooze',headers=H(),json={'id':items[1]['id'],'until':'2020-01-01T00:00:00'})
    assert items[1]['id'] in [i['id'] for i in client.get('/api/inbox',headers=H()).json()]
    assert client.post('/api/inbox/snooze',headers=H(),json={'id':'missing','until':later}).status_code==404
    assert client.post('/api/inbox/read',headers=H(),json={'ids':'some'}).status_code==400

def rule(client,**v):
    r=client.post('/api/automations',headers=H(),json={'enabled':True,**v});assert r.status_code==200,r.text;return r.json()

def test_automations_seeded_crud_toggle_and_permissions(client,member):
    seeded=client.get('/api/automations',headers=H()).json()
    assert len(seeded)==3 and not any(r['enabled'] for r in seeded)
    assert {r['trigger'] for r in seeded}=={'task_status','task_blocked_hours','task_created'}
    assert set(seeded[0])=={'id','name','trigger','action','params','enabled','runs','last_run','last_result'}
    assert client.post('/api/automations',headers=member,json={'name':'x','trigger':'task_created','action':'notify','params':{}}).status_code==403
    for bad in [{'trigger':'cron'},{'action':'email'},{'trigger':'task_status','params':{'to_status':'Gone'}},{'params':{'field':'title','value':'x'}},{'trigger':'task_blocked_hours','params':{'hours':-1}}]:
        assert client.post('/api/automations',headers=H(),json={'name':'Bad','trigger':'task_created','action':'set_field','params':{'field':'priority','value':'High'},**bad}).status_code==400,bad
    toggled=client.post('/api/automations/'+seeded[0]['id']+'/toggle',headers=H()).json()
    assert toggled['enabled'] is True
    assert client.post('/api/automations/'+seeded[0]['id']+'/toggle',headers=member).status_code==403
    assert client.delete('/api/automations/'+seeded[0]['id'],headers=H()).status_code==200
    assert client.post('/api/automations/missing/toggle',headers=H()).status_code==404
    assert len(client.get('/api/automations',headers=member).json())==2

def test_automations_run_on_save_without_recursion(client):
    for r in client.get('/api/automations',headers=H()).json():client.delete('/api/automations/'+r['id'],headers=H())
    label=rule(client,name='Triage',trigger='task_created',action='add_label',params={'project':'','label':'triage'})
    urgent=rule(client,name='Blocked is urgent',trigger='task_status',action='set_field',params={'to_status':'Blocked','field':'priority','value':'Urgent'})
    # Would loop forever if automation saves triggered automations: Done -> Blocked -> Done ...
    rule(client,name='Ping-pong A',trigger='task_status',action='set_field',params={'to_status':'In review','field':'status','value':'Done'})
    rule(client,name='Ping-pong B',trigger='task_status',action='set_field',params={'to_status':'Done','field':'status','value':'In review'})
    t=task(client)
    assert client.get('/api/tasks',headers=H()).json()[0]['labels']==['triage']
    client.post('/api/tasks',headers=H(),json={'id':t['id'],'status':'Blocked'})
    assert client.get('/api/tasks',headers=H()).json()[0]['priority']=='Urgent'
    client.post('/api/tasks',headers=H(),json={'id':t['id'],'status':'In review'})
    assert client.get('/api/tasks',headers=H()).json()[0]['status']=='Done'
    rules={r['name']:r for r in client.get('/api/automations',headers=H()).json()}
    assert rules['Triage']['runs']==1 and rules['Ping-pong A']['runs']==1 and rules['Ping-pong B']['runs']==0
    assert rules['Blocked is urgent']['last_result'].startswith('set priority')
    audit=client.get('/api/audit',headers=H()).json()
    assert any(a['actor']=='automation' and a['action'].startswith('automation:'+label['id']) for a in audit)
    assert sum(i['kind']=='automation' for i in client.get('/api/inbox',headers=H()).json())==3
    assert urgent['enabled']

def test_automation_dry_run_changes_nothing(client):
    t=task(client,status='Blocked')
    r=rule(client,name='Unblock',trigger='task_status',action='set_field',params={'to_status':'Blocked','field':'owner','value':'Asha'},enabled=False)
    result=client.post('/api/automations/'+r['id']+'/run',headers=H()).json()
    assert result['dry_run'] and result['matches'][0]['task_id']==t['id'] and 'owner' in result['matches'][0]['would']
    assert client.get('/api/tasks',headers=H()).json()[0]['owner']=='Unassigned'
    assert client.get('/api/automations',headers=H()).json()[-1]['runs']==0
    assert client.post('/api/automations/missing/run',headers=H()).status_code==404

def test_blocked_hours_rule_is_idempotent(client):
    t=task(client,status='Blocked')
    r=rule(client,name='Stale block',trigger='task_blocked_hours',action='set_field',params={'hours':24,'field':'priority','value':'Urgent'})
    dry=client.post('/api/automations/'+r['id']+'/run',headers=H()).json()
    assert dry['matches']==[]
    old=(dt.datetime.now(engine.IST)-dt.timedelta(hours=30)).isoformat()
    with engine.connect() as c:c.execute("UPDATE task_events SET created_at=? WHERE task_id=? AND field='status'",(old,t['id']))
    assert client.post('/api/automations/'+r['id']+'/run',headers=H()).json()['matches'][0]['already_applied'] is False
    client.get('/api/inbox',headers=H());client.get('/api/snapshot',headers=H());client.get('/api/inbox',headers=H())
    assert client.get('/api/tasks',headers=H()).json()[0]['priority']=='Urgent'
    assert next(x for x in client.get('/api/automations',headers=H()).json() if x['id']==r['id'])['runs']==1
    assert client.post('/api/automations/'+r['id']+'/run',headers=H()).json()['matches'][0]['already_applied'] is True
