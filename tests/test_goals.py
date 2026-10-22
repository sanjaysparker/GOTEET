"""Goals, key results, milestones, deadlines (docs/API_V1.md#goals)."""
import datetime as dt
import pytest
from fastapi.testclient import TestClient
import api
import goals
import insights

def H(token=None):return {'Authorization':'Bearer '+(token or api.TOKEN)}

@pytest.fixture
def client(isolated):
    with TestClient(api.app) as c:yield c

@pytest.fixture
def member(client):return H(client.post('/api/team/invite',headers=H(),json={'name':'Ravi'}).json()['token'])

def D(n):return (goals.today()+dt.timedelta(days=n)).isoformat()
def post(client,path,**v):return client.post(path,headers=H(),json=v)
def goal(client,**v):
    r=post(client,'/api/goals',**{'title':'Ship v1'}|v);assert r.status_code==200,r.text;return r.json()
def kr(client,gid,**v):
    r=post(client,'/api/key-results',goal_id=gid,**{'title':'KR','kind':'manual','target':100}|v);assert r.status_code==200,r.text;return r.json()
def task(client,**v):
    r=post(client,'/api/tasks',**{'title':'T'}|v);assert r.status_code==200,r.text;return r.json()

def test_goal_crud_merge_and_validation(client):
    g=goal(client,description='d',owner='Sanju',start_date='2026-01-01',target_date='2026-12-31')
    assert g['status']=='Active' and g['progress']==0 and g['health']=='No plan' and g['key_results']==[] and g['milestones']==[]
    m=post(client,'/api/goals',id=g['id'],status='Paused').json()
    assert (m['status'],m['title'],m['owner'],m['target_date'])==('Paused','Ship v1','Sanju','2026-12-31') and m['created_at']==g['created_at']
    assert len(client.get('/api/goals',headers=H()).json())==1
    for bad in ({'title':''},{'title':'x'*301},{'title':5},{'title':'t','status':'Done'},{'title':'t','status':['Active']},{'title':'t','start_date':'2026-02-01','target_date':'2026-01-01'},
                {'title':'t','target_date':'31/12/2026'},{'title':'t','target_date':'20261231'},{'title':'t','owner':3},{'title':'t','description':{}},{'title':'t','start_date':5}):
        assert post(client,'/api/goals',**bad).status_code==400,bad
    assert client.post('/api/goals',headers=H(),json=['x']).status_code in (400,422)
    assert post(client,'/api/goals',title='t',project_id='nope').status_code==404

def test_key_result_rules_and_progress(client):
    g=goal(client)
    assert post(client,'/api/key-results',goal_id='missing',title='k',kind='manual',target=1).status_code==404
    for bad in ({'kind':'tasks'},{'kind':'manual'},{'kind':'manual','target':0},{'kind':'manual','target':'9'},{'kind':'x','target':1},{'kind':'manual','target':5,'current':True},{'kind':'manual','target':5,'due':'soon'},{'kind':5}):
        assert post(client,'/api/key-results',goal_id=g['id'],title='k',**bad).status_code==400,bad
    assert post(client,'/api/key-results',goal_id=g['id'],title='',kind='manual',target=1).status_code==400
    k=kr(client,g['id'],current=45,unit='%');assert (k['progress'],k['detail'])==(0.45,'45 / 100 %')
    assert kr(client,g['id'],id=k['id'],current=250)['progress']==1 and kr(client,g['id'],id=k['id'],current=-5)['progress']==0
    merged=post(client,'/api/key-results',id=k['id'],current=10).json();assert merged['title']=='KR' and merged['target']==100 and merged['progress']==0.1
    for n in range(3):task(client,project='Atlas',status='Done' if n==0 else 'Todo')
    t=kr(client,g['id'],kind='tasks',project_name='Atlas',target=0);assert (t['progress'],t['detail'])==(0.3333,'1/3 tasks')
    e=kr(client,g['id'],kind='tasks',project_name='Empty');assert (e['progress'],e['detail'])==(0,'No tasks yet')
    task(client,project='Atlas',status='Done');assert next(x for x in client.get('/api/goals',headers=H()).json()[0]['key_results'] if x['id']==t['id'])['detail']=='2/4 tasks'

def test_goal_progress_mean_and_milestone_fallback(client):
    g=goal(client);assert post(client,'/api/milestones',goal_id=g['id'],title='m1',due=D(5)).json()['done'] is False
    a=post(client,'/api/milestones',goal_id=g['id'],title='m2',due=D(6),done=True).json()
    assert client.get('/api/goals',headers=H()).json()[0]['progress']==0.5
    kr(client,g['id'],current=100);kr(client,g['id'],current=50,title='b')
    assert client.get('/api/goals',headers=H()).json()[0]['progress']==0.75  # KRs override milestones
    assert a['done']

def test_health_matrix_with_injected_clock(isolated):
    import engine
    on=dt.date(2026,6,1)
    def make(i,status='Active',start='2026-01-01',target='2026-12-31',progress=None,plan=True):
        with engine.connect() as c:
            c.execute("INSERT INTO goals VALUES(?,?,?,?,?,?,?,?,?,?)",(i,i,'','',status,start,target,'','x','x'))
            if plan:c.execute("INSERT INTO key_results VALUES(?,?,?,?,?,?,?,?,?,?)",(i+'k',i,'k','manual','',100,0 if progress is None else progress,'','','x'))
    elapsed=(on-dt.date(2026,1,1)).days/(dt.date(2026,12,31)-dt.date(2026,1,1)).days*100  # about 41.7
    make('ontrack',progress=round(elapsed));make('risk',progress=round(elapsed-20));make('off',progress=round(elapsed-40))
    make('late',target='2026-05-01',start='',progress=50);make('done',status='Achieved',progress=10);make('full',progress=100);make('noplan',plan=False);make('nodates',start='',target='',progress=0)
    h={g['id']:g for g in goals.goals(on)}
    assert {k:v['health'] for k,v in h.items()}=={'ontrack':'On track','risk':'At risk','off':'Off track','late':'Off track','done':'Achieved','full':'Achieved','noplan':'No plan','nodates':'On track'}
    assert h['nodates']['elapsed'] is None and h['nodates']['days_left'] is None and h['ontrack']['days_left']==213 and 0.41<h['ontrack']['elapsed']<0.42
    assert [g['status'] for g in goals.goals(on)]==sorted((g['status'] for g in goals.goals(on)),key=goals.ORDER.get)

def test_sort_active_first_by_target(client):
    a=goal(client,target_date=D(30));b=goal(client,target_date=D(10));c=goal(client);d=goal(client,target_date=D(1),status='Achieved')
    assert [g['id'] for g in client.get('/api/goals',headers=H()).json()]==[b['id'],a['id'],c['id'],d['id']]

def test_milestone_validation_audit_and_links(client):
    g=goal(client);p=post(client,'/api/projects',name='Atlas').json()
    assert post(client,'/api/milestones',title='m').status_code==400
    assert post(client,'/api/milestones',title='m',due='tomorrow').status_code==400
    assert post(client,'/api/milestones',title='m',due=D(1),goal_id='nope').status_code==404
    assert post(client,'/api/milestones',title='m',due=D(1),project_id='nope').status_code==404
    assert post(client,'/api/milestones',title='m',due=D(1),done='yes').status_code==400
    m=post(client,'/api/milestones',title='m',due=D(1),goal_id=g['id'],project_id=p['id']).json()
    post(client,'/api/milestones',id=m['id'],done=True);post(client,'/api/milestones',id=m['id'],title='renamed')
    r=post(client,'/api/milestones',id=m['id'],done=False).json();assert r['title']=='renamed' and r['due']==D(1)
    acts=[x['action'] for x in client.get('/api/audit',headers=H()).json()]
    assert acts.count('milestone:done:'+m['id'])==1 and acts.count('milestone:reopen:'+m['id'])==1

def test_deadlines_grouping_and_exclusions(client):
    g=goal(client,target_date=D(3));goal(client,target_date=D(2),status='Achieved');goal(client,target_date=D(2),status='Paused');goal(client,target_date=D(2),status='Dropped')
    kr(client,g['id'],due=D(-1),current=10);kr(client,g['id'],due=D(1),current=100,title='full')
    post(client,'/api/milestones',goal_id=g['id'],title='late ms',due=D(-3));post(client,'/api/milestones',title='done ms',due=D(-3),done=True)
    task(client,title='over',due=D(-2),project='Atlas',status='Todo');task(client,title='finished',due=D(-2),status='Done');task(client,title='later',due=D(20));task(client)
    post(client,'/api/projects',name='Open',target_date=D(10));post(client,'/api/projects',name='Shipped',target_date=D(1),status='Done')
    d=client.get('/api/deadlines',headers=H()).json()
    titles=lambda k:[i['title'] for i in d[k]]
    assert titles('overdue')==['late ms','over','KR']
    assert set(titles('this_week'))=={ 'Ship v1' } and d['this_week'][0]['type']=='goal' and d['this_week'][0]['days']==3
    assert set(titles('later'))=={'Open','later'}
    allit=[i for k in d for i in d[k]]
    assert all(set(i)=={'type','id','title','due','days','status','ref_id','goal_id','project'} for i in allit)
    assert next(i for i in allit if i['title']=='late ms')['goal_id']==g['id'] and next(i for i in allit if i['title']=='over')['project']=='Atlas'
    assert [i['days'] for i in d['overdue']]==sorted(i['days'] for i in d['overdue'])

def test_deadlines_cap(client):
    for n in range(70):task(client,due=D(n))
    d=client.get('/api/deadlines',headers=H()).json();assert sum(map(len,d.values()))==60

def test_delete_cascades_and_audit(client):
    g=goal(client);k=kr(client,g['id']);m=post(client,'/api/milestones',goal_id=g['id'],title='m',due=D(1)).json();other=post(client,'/api/milestones',title='free',due=D(1)).json()
    r=client.delete('/api/goals/'+g['id'],headers=H()).json();assert (r['key_results_removed'],r['milestones_removed'])==(1,1)
    assert client.get('/api/goals',headers=H()).json()==[]
    assert client.delete('/api/key-results/'+k['id'],headers=H()).status_code==404 and client.delete('/api/milestones/'+m['id'],headers=H()).status_code==404
    assert client.delete('/api/milestones/'+other['id'],headers=H()).status_code==200 and client.delete('/api/goals/'+g['id'],headers=H()).status_code==404
    assert 'goal:delete:'+g['id'] in [x['action'] for x in client.get('/api/audit',headers=H()).json()]

def test_owner_only_writes_member_reads(client,member):
    g=goal(client);k=kr(client,g['id']);m=post(client,'/api/milestones',goal_id=g['id'],title='m',due=D(1)).json()
    for path in ('/api/goals','/api/key-results','/api/milestones'):assert client.post(path,headers=member,json={'title':'x'}).status_code==403
    for path in ('/api/goals/'+g['id'],'/api/key-results/'+k['id'],'/api/milestones/'+m['id']):assert client.delete(path,headers=member).status_code==403
    assert client.get('/api/goals',headers=member).status_code==200 and client.get('/api/deadlines',headers=member).status_code==200
    assert len(client.get('/api/goals',headers=H()).json())==1

def test_achieved_creates_inbox_item_once(client):
    g=goal(client);post(client,'/api/goals',id=g['id'],status='Achieved');post(client,'/api/goals',id=g['id'],title='Ship v1.1')
    items=[i for i in client.get('/api/inbox',headers=H()).json() if i['title'].startswith('Goal achieved')]
    assert len(items)==1 and items[0]['kind']=='status' and items[0]['title']=='Goal achieved: Ship v1'

def test_insights_findings(isolated,client):
    off=goal(client,start_date=D(-100),target_date=D(-1));kr(client,off['id'],current=10)
    near=goal(client,title='Near',start_date=D(-50),target_date=D(5));kr(client,near['id'],current=60)
    risk=goal(client,title='Risky',start_date=D(-50),target_date=D(50));kr(client,risk['id'],current=30)
    ok=goal(client,title='OK',start_date=D(-50),target_date=D(50));kr(client,ok['id'],current=50)
    post(client,'/api/milestones',goal_id=ok['id'],title='slipped',due=D(-4))
    r=client.get('/api/insights',headers=H()).json()
    by={(f['kind'],f['evidence'][0]['id']):f for f in r['findings']}
    assert by[('goal_health',off['id'])]['severity']=='critical' and by[('goal_health',risk['id'])]['severity']=='warn'
    assert ('goal_health',ok['id']) not in by and by[('goal_deadline',near['id'])]['severity']=='warn' and ('goal_deadline',off['id']) not in by
    ms=[f for f in r['findings'] if f['kind']=='milestone_overdue'];assert len(ms)==1 and ms[0]['evidence'][0]['type']=='milestone'
    assert {g['id'] for g in r['goals']}=={off['id'],near['id'],risk['id'],ok['id']}
