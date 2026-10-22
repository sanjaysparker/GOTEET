"""Passive agent observer: parsing, privacy, signals, correlations, API (docs/API_V1.md#agent-observer). Never reads the real home."""
import datetime as dt
import json
import os
import subprocess
import pytest
from fastapi.testclient import TestClient
import agent_observer as obs
import api
import engine
import insights
import settings
from collector import IST

CLOCK=dt.datetime(2026,10,21,12,tzinfo=IST)
BASE=dt.datetime(2026,10,21,9,tzinfo=IST).timestamp()
PROMPT='ZEBRA prompt text sk-abcdefghijklmnop1234 and more'
SECRET_FILE='secret_file_name.py'
SECRET_CMD='rm -rf ZEBRA-CMD'

def H():return {'Authorization':'Bearer '+api.TOKEN}
def iso(t):return dt.datetime.fromtimestamp(BASE+t,dt.timezone.utc).isoformat().replace('+00:00','Z')
def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n'.join(json.dumps(r,separators=(',',':')) for r in rows)+'\n')
    os.utime(path,(CLOCK.timestamp(),CLOCK.timestamp()))
    return path

def cl(t,kind,cwd,content=None,**extra):
    return {'type':kind,'timestamp':iso(t),'sessionId':'s1','cwd':str(cwd),'gitBranch':'main','message':{'role':kind,'content':content if content is not None else []}}|extra
def use(i,name,**inputs):return {'type':'tool_use','id':i,'name':name,'input':inputs}
def res(i,error=False):return {'type':'tool_result','tool_use_id':i,'content':'ZEBRA output','is_error':error}

def claude_rows(cwd):
    return [cl(0,'user',cwd,PROMPT,origin={'kind':'human'}),
      cl(30,'assistant',cwd,[use('e1','Edit',file_path='/x/'+SECRET_FILE),use('e2','Edit',file_path='/x/b.py'),use('e3','Edit',file_path='/x/'+SECRET_FILE)]),
      cl(60,'user',cwd,[res('e1')]),
      cl(90,'assistant',cwd,[use('b1','Bash',command=SECRET_CMD)]),cl(120,'user',cwd,[res('b1',True)]),
      cl(150,'assistant',cwd,[use('b2','Bash',command=SECRET_CMD)]),cl(180,'user',cwd,[res('b2',True)]),
      cl(210,'assistant',cwd,[use('b3','Bash',command=SECRET_CMD)]),cl(240,'user',cwd,[res('b3',True)]),
      cl(840,'user',cwd,'sidechain prompt',isSidechain=True),
      cl(900,'user',cwd,'<system-reminder>ignore</system-reminder>'),
      cl(960,'user',cwd,'meta text',isMeta=True)]

def cx(t,kind,payload):return {'timestamp':iso(t),'type':kind,'payload':payload}
def item(t,**it):return cx(t,'event_msg',{'type':'item_completed','thread_id':'t','turn_id':'u','item':it})
def codex_rows(cwd,source='vscode'):
    cmd={'type':'CommandExecution','command':['bash','-lc',SECRET_CMD],'cwd':str(cwd),'status':'failed','exit_code':1,'stdout':'ZEBRA out'}
    return [cx(0,'session_meta',{'id':'c1','cwd':str(cwd),'originator':'Codex Desktop','source':source,'git':{'branch':'dev','commit_hash':'x'}}),
      cx(10,'turn_context',{'cwd':str(cwd),'turn_id':'u'}),
      item(20,type='UserMessage',content=[{'type':'text','text':PROMPT}]),
      item(40,**cmd),item(60,**cmd),item(80,**cmd),
      item(100,type='CommandExecution',command=['ls'],cwd=str(cwd),status='completed',exit_code=0),
      item(120,type='FileChange',changes={'/x/'+SECRET_FILE:{'type':'add','content':'ZEBRA'},'/x/b.py':{'type':'update'}},status='completed'),
      item(140,type='McpToolCall',server='s',tool='t',arguments={'a':1},status='failed',result=None),
      cx(160,'event_msg',{'type':'token_count','info':{}}),
      cx(1000,'event_msg',{'type':'task_complete'})]

@pytest.fixture
def world(isolated,tmp_path,monkeypatch):
    home=tmp_path/'home';(home/'work'/'atlas'/'.git').mkdir(parents=True);(home/'work'/'beta'/'.git').mkdir(parents=True);(home/'tmp').mkdir()
    monkeypatch.setattr(obs,'HOME',home);monkeypatch.setattr(obs,'CLAUDE_ROOT',home/'.claude'/'projects')
    monkeypatch.setattr(obs,'CODEX_ROOTS',(home/'.codex'/'sessions',home/'.codex'/'archived_sessions'))
    monkeypatch.setattr(obs,'running',lambda mapper:([],0));monkeypatch.setattr(obs,'kick',lambda:None);obs.ROOTS.clear()
    return home

@pytest.fixture
def client(isolated):
    with TestClient(api.app) as c:yield c

def enable(**v):settings.save({'agent_observer_enabled':True}|v)
def mapper(world,**kw):return obs.Mapper(kw.get('overrides',[]),kw.get('saved',[]),world)
def parse(kind,path,world,titles=False):
    acc=obs.Acc(mapper(world),titles);(obs.parse_claude if kind=='claude' else obs.parse_codex)(path,acc)
    return acc,obs.record(acc,kind,path,path.stat(),'sig')

def dump_all():
    with engine.connect() as c:
        return json.dumps({t:[list(r) for r in c.execute(f'SELECT * FROM {t}')] for t in ('activity_sessions','activity_days','activity_state','activity_project_map')},default=str)

# DISABLED

def test_disabled_reads_nothing_and_reports_off(world,client,monkeypatch):
    def boom(*a,**k):raise AssertionError('source files were touched while disabled')
    monkeypatch.setattr(obs,'discover',boom);monkeypatch.setattr(obs,'parse_claude',boom);monkeypatch.setattr(obs,'parse_codex',boom)
    data=client.get('/api/activity/overview',headers=H()).json()
    assert data['enabled'] is False and data['coverage']==obs.OFF and data['sessions']==[] and data['totals']['minutes']==0
    assert client.post('/api/activity/scan',headers=H()).status_code==403
    with pytest.raises(PermissionError):obs.scan(CLOCK)
    obs.safe_scan()
    assert settings.get()['agent_observer_enabled'] is False and settings.get()['agent_observer_titles'] is False

def test_members_cannot_reach_the_observer(client):
    token=client.post('/api/team/invite',headers=H(),json={'name':'Ravi'}).json()['token']
    for method,path in (('get','/api/activity/overview'),('post','/api/activity/scan'),('get','/api/activity/map'),('delete','/api/activity/data')):
        assert getattr(client,method)(path,headers={'Authorization':'Bearer '+token}).status_code==403

# PARSING

def test_claude_active_minutes_turns_errors_and_file_counts(world):
    path=write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    acc,rec=parse('claude',path,world)
    # 0-240 s active, 240-840 s idle (excluded), 840-960 s active
    assert rec['active_minutes']==pytest.approx(6.0)
    assert rec['turns']==1 and rec['tool_calls']==6 and rec['tool_errors']==3
    assert rec['files_touched']==2 and rec['repeated_failures']==3 and rec['branch']=='main'
    assert json.loads(rec['projects'])==['atlas'] and rec['title']==''

def test_claude_huge_lines_are_not_parsed_but_still_count_time(world,monkeypatch):
    monkeypatch.setattr(obs,'BIG_LINE',200)
    rows=claude_rows(world/'work'/'atlas')
    rows[1]['message']['content'].append({'type':'text','text':'x'*500})
    acc,rec=parse('claude',write(world/'.claude'/'projects'/'p'/'s.jsonl',rows),world)
    assert rec['active_minutes']==pytest.approx(6.0) and rec['tool_calls']>=1

def test_codex_parsing_against_real_schema(world):
    path=write(world/'.codex'/'sessions'/'2026'/'10'/'21'/'rollout-x.jsonl',codex_rows(world/'work'/'beta'))
    acc,rec=parse('codex',path,world)
    # 3 failing commands + 1 ok + 1 file change + 1 failing MCP call; errors 3+1; identical failing command streak 3
    assert rec['tool_calls']==6 and rec['tool_errors']==4 and rec['files_touched']==2 and rec['repeated_failures']==3
    assert rec['turns']==1 and rec['branch']=='dev' and json.loads(rec['projects'])==['beta']
    # 0-160 s active, then a 840 s idle gap
    assert rec['active_minutes']==pytest.approx(160/60,abs=0.01)

def test_codex_subagent_has_no_turns_and_old_rollouts_fall_back(world):
    rows=codex_rows(world/'work'/'beta',source={'subagent':{'thread_spawn':{}}})
    assert parse('codex',write(world/'.codex'/'sessions'/'a.jsonl',rows),world)[1]['turns']==0
    old=[cx(0,'session_meta',{'cwd':str(world/'work'/'beta'),'source':'vscode'}),cx(10,'event_msg',{'type':'user_message','message':'hi'}),
      cx(20,'response_item',{'type':'function_call','name':'exec'}),cx(30,'response_item',{'type':'custom_tool_call','name':'exec'})]
    rec=parse('codex',write(world/'.codex'/'sessions'/'b.jsonl',old),world)[1]
    assert rec['turns']==1 and rec['tool_calls']==2 and rec['tool_errors']==0

def test_cache_skips_unchanged_files(world,monkeypatch):
    enable();path=write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    calls=[];original=obs.parse_claude
    monkeypatch.setattr(obs,'parse_claude',lambda p,a:(calls.append(1),original(p,a))[1])
    obs.scan(CLOCK);obs.scan(CLOCK);assert len(calls)==1
    with open(path,'a') as f:f.write(json.dumps(cl(1000,'user',world/'work'/'atlas','another prompt'))+'\n')
    os.utime(path,(CLOCK.timestamp()+5,CLOCK.timestamp()+5))
    obs.scan(CLOCK);assert len(calls)==2

# MAPPING

def test_project_mapping_order(world):
    atlas=world/'work'/'atlas'/'src';atlas.mkdir()
    assert mapper(world)(str(atlas))=='atlas'                                                        # repo root
    assert mapper(world,saved=['ATLAS'])(str(atlas))=='ATLAS'                                        # saved project beats repo root (case/-_ insensitive)
    assert mapper(world,saved=['Be-ta'])(str(world/'work'/'beta'))=='Be-ta'
    assert mapper(world,saved=['ATLAS'],overrides=[('work/atlas','Custom')])(str(atlas))=='Custom'  # override beats saved project
    assert mapper(world,overrides=[(str(world/'work'),'Work')])(str(atlas))=='Work'                  # prefix override
    scratch=world/'Library'/'Application Support'/'Claude'/'scratch-workspaces'/'w'/'scratch-2026'
    scratch.mkdir(parents=True)
    assert mapper(world)(str(scratch))=='Scratch' and mapper(world)(str(world))=='Home' and mapper(world)('')=='Unknown'
    assert mapper(world)(str(world/'tmp'))=='tmp'

def test_linked_worktree_maps_to_its_main_checkout(world):
    tree=world/'work'/'atlas-wt';tree.mkdir();(tree/'.git').write_text(f"gitdir: {world/'work'/'atlas'}/.git/worktrees/atlas-wt\n")
    assert mapper(world)(str(tree))=='atlas'

# REDACTION AND PRIVACY

def test_redaction_of_secrets_and_length():
    text='deploy with sk-abcdefghijklmnop and ghp_abcdefghijkl and xoxb-123456-abcdef AKIAABCDEFGHIJKL key QUJDREVGR0hJSkxNTk9QUVJTVFVWV1hZWg== from /Users/me/project/file.py then password hunter2 here'
    out=obs.redact(text)
    for leaked in ('sk-abc','ghp_abc','xoxb-','AKIAABC','QUJDREVG','/Users/me','hunter2'):assert leaked not in out
    assert obs.redact('login password hunter2')=='login password …'
    assert len(obs.redact('word '*100))<=100

def test_titles_are_off_by_default_and_redacted_when_on(world,client):
    enable();write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'));data=obs.scan(CLOCK)
    assert data['sessions'][0]['title']=='' and 'ZEBRA' not in json.dumps(data) and 'ZEBRA' not in dump_all()
    enable(agent_observer_titles=True);data=obs.scan(CLOCK);title=data['sessions'][0]['title']
    assert title.startswith('ZEBRA prompt text') and 'sk-abc' not in title and len(title)<=100
    enable(agent_observer_titles=False);assert obs.overview()['sessions'][0]['title']==''

def test_no_text_paths_or_names_leak_into_overview_or_database(world):
    enable();write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    write(world/'.codex'/'sessions'/'2026'/'10'/'21'/'rollout-x.jsonl',codex_rows(world/'work'/'beta'))
    data=obs.scan(CLOCK);blob=json.dumps(data)+dump_all()
    for leaked in ('ZEBRA',SECRET_FILE,SECRET_CMD,str(world),'/Users','/private','.jsonl','sk-abc'):assert leaked not in blob,leaked
    assert data['now']==[] and all('cwd' not in s for s in data['sessions'])
    assert {s['tool'] for s in data['sessions']}=={'claude','codex'}

def test_scan_numbers_daily_and_projects(world):
    enable();write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    write(world/'.codex'/'sessions'/'2026'/'10'/'21'/'rollout-x.jsonl',codex_rows(world/'work'/'atlas'))
    data=obs.scan(CLOCK)
    atlas=next(p for p in data['projects'] if p['name']=='atlas')
    assert atlas['tools']['claude']==pytest.approx(6.0,abs=0.1) and atlas['tools']['codex']==pytest.approx(2.7,abs=0.1) and atlas['sessions']==2
    # overlapping time of both tools is counted once in the agent total
    assert 6.0<=atlas['minutes']<=8.7 and data['daily'][0]['date']=='2026-10-21' and data['totals']['sessions']==2
    assert data['coverage'].startswith('Parsed 2') and 'estimates' in data['coverage']
    assert {s['state'] for s in data['sessions']}=={'done'}

# SIGNALS

def S(project='P',start=BASE,**v):
    return {'project':project,'started':start,'ended':start+600,'active_minutes':10,'tool_calls':20,'tool_errors':0,'files_touched':0,'repeated_failures':0,'id':str(v)}|v
def G(**v):return {'commits':[],'dirty_age_days':0.0,'dirty_files':0,'unpushed':0,'unpushed_age_days':0.0}|v
def kinds(found):return {m['kind']:m for m in found}

def test_session_error_rate_and_repeated_failures():
    found=kinds(obs.mistakes([S(tool_calls=10,tool_errors=3),S(tool_calls=9,tool_errors=9,id='short'),S(repeated_failures=3,id='loop')],{},{},{},CLOCK))
    assert found['session_error_rate']['severity']=='warn' and '3 of 10' in found['session_error_rate']['evidence'][0] and found['session_error_rate']['suggestion']
    assert 'short' not in json.dumps(found['session_error_rate']['evidence']) and found['repeated_failures']['severity']=='warn'
    assert kinds(obs.mistakes([S(tool_calls=40,tool_errors=30)],{},{},{},CLOCK))['session_error_rate']['severity']=='critical'
    assert kinds(obs.mistakes([S(repeated_failures=7)],{},{},{},CLOCK))['repeated_failures']['severity']=='critical'
    assert not obs.mistakes([S(tool_calls=10,tool_errors=2),S(repeated_failures=2,id='b')],{},{},{},CLOCK)

def test_git_based_signals():
    t=BASE;commits=[(t,'feat'),(t+1800,'fix'),(t+3000,'fix'),(t+90000,'fix'),(t+95000,'revert')]
    found=kinds(obs.mistakes([],{'P':G(commits=commits,dirty_files=4,dirty_age_days=5.0,unpushed=3,unpushed_age_days=1.5)},{},{},CLOCK))
    assert found['reverts']['evidence'] and found['rework_after_feature']['evidence']==['2026-10-21: 2 fix commits within 2 h of a feature']
    assert found['stale_dirty_tree']['severity']=='info' and found['unpushed_work']['severity']=='warn'
    assert kinds(obs.mistakes([],{'P':G(dirty_files=1,dirty_age_days=8.0)},{},{},CLOCK))['stale_dirty_tree']['severity']=='warn'
    assert kinds(obs.mistakes([],{'P':G(commits=[(t,'revert')]*3)},{},{},CLOCK))['reverts']['severity']=='critical'
    assert not obs.mistakes([],{'P':G(dirty_files=1,dirty_age_days=2.0,unpushed=2,unpushed_age_days=3.0,commits=[(t,'feat'),(t+60,'fix')])},{},{},CLOCK)

def test_long_session_thrash_and_ci_signals():
    long=S(active_minutes=95,started=BASE,tool_calls=5)
    assert 'long_session_no_commit' in kinds(obs.mistakes([long],{'P':G()},{},{},CLOCK))
    assert 'long_session_no_commit' not in kinds(obs.mistakes([long],{'P':G(commits=[(BASE+300,'other')])},{},{},CLOCK))
    assert 'long_session_no_commit' not in kinds(obs.mistakes([long],{},{},{},CLOCK))
    three=[S(files_touched=10,started=BASE+i*1000,id=str(i)) for i in range(3)]
    assert 'file_thrash' in kinds(obs.mistakes(three,{},{},{},CLOCK)) and 'file_thrash' not in kinds(obs.mistakes(three[:2],{},{},{},CLOCK))
    assert 'file_thrash' not in kinds(obs.mistakes([S(files_touched=9,started=BASE+i,id=str(i)) for i in range(3)],{},{},{},CLOCK))
    ci={'P':{'latest':'failure','failure_days':['2026-10-21']}}
    assert kinds(obs.mistakes([],{},ci,{'P':CLOCK.timestamp()-3600},CLOCK))['ci_failing_after_work']['severity']=='critical'
    assert not obs.mistakes([],{},ci,{'P':CLOCK.timestamp()-90000},CLOCK) and not obs.mistakes([],{},{'P':{'latest':'success','failure_days':[]}},{'P':CLOCK.timestamp()},CLOCK)

# CORRELATIONS

def act(days,blocks,hours=None):
    return {'days':set(days),'blocks':blocks,'hours':set(hours or [])}

def test_correlations_from_synthetic_days():
    a=act(['d1','d2','d3','d4','d5'],[[0,600],[7200,7800],[20000,20600]],['h1','h2','h3'])
    b=act(['d1','d2','d3','d9'],[[1000,1500],[8000,8400],[21000,21400]],['h2','h3','h8'])
    c=act(['d7'],[[900000,900100]],['h9'])
    out=obs.correlate({'A':a,'B':b,'C':c,'Scratch':a},{},{('A','B'):1},['d%d'%i for i in range(1,10)])
    assert [(x['a'],x['b']) for x in out]==[('A','B')]
    x=out[0];assert x['handoffs']==3 and x['hours_overlap']==2 and x['same_session']==1 and x['days_shared']==pytest.approx(3/6)
    assert x['evidence'].startswith('both active on 3 of 6 days; 3 handoffs') and 0.15<=x['score']<=1
    # a single coincidence is not enough evidence
    assert obs.correlate({'A':act(['d1'],[[0,10]],['h1']),'B':act(['d2'],[[100000,100010]],['h2'])},{},{},['d1','d2'])==[]

def test_shared_ci_failures_count_toward_score():
    a=act(['d1'],[[0,10]]);b=act(['d1'],[[100000,100010]])
    ci={'A':{'latest':'','failure_days':['d1','d2']},'B':{'latest':'','failure_days':['d1','d2']}}
    out=obs.correlate({'A':a,'B':b},ci,{},['d1','d2'])
    assert out and out[0]['shared_ci_failures']==2 and 'CI failed on both' in out[0]['evidence']

# SUGGESTIONS

def test_suggestions_are_derived_and_never_touch_tasks():
    corr=[{'a':'X','b':'Y','score':0.72,'evidence':'both active on 5 of 9 days'}]
    totals={'Atlas':{'minutes':186,'commits':4},'Quiet':{'minutes':20,'commits':0},'Unsaved':{'minutes':500,'commits':9}}
    deadlines=[{'project':'Idle','days':3,'due':'2026-10-24','type':'goal'},{'project':'Atlas','days':1,'due':'2026-10-22','type':'task'}]
    out=obs.suggestions(totals,corr,[S('Atlas',active_minutes=200)],{'Atlas','Quiet','Idle'},{'Atlas':BASE-30*86400},deadlines,{'Idle':CLOCK.timestamp()-9*86400,'Atlas':CLOCK.timestamp()-3600},CLOCK)
    titles=[s['title'] for s in out]
    assert 'Atlas: 3.1 h agent time, 4 commits, no task updated → update tasks or log work' in titles
    assert any('X and Y move together (score 0.72)' in t for t in titles) and any(t.startswith('No activity on Idle for 9 days') for t in titles)
    assert any('split long sessions' in t for t in titles) and not any('Unsaved' in t or 'Quiet' in t for t in titles) and not any('No activity on Atlas' in t for t in titles)
    assert all(set(s)=={'id','project','title','detail','reason'} for s in out)
    assert not [s for s in obs.suggestions({'Atlas':{'minutes':186,'commits':4}},[],[],{'Atlas'},{'Atlas':CLOCK.timestamp()-3600},[],{},CLOCK) if s['id'].startswith('unlogged')]

# GIT

def run_git(repo,*args,when=None):
    env={**os.environ,'GIT_AUTHOR_NAME':'T','GIT_AUTHOR_EMAIL':'t@example.com','GIT_COMMITTER_NAME':'T','GIT_COMMITTER_EMAIL':'t@example.com','GIT_CONFIG_GLOBAL':'/dev/null'}
    if when:env['GIT_AUTHOR_DATE']=env['GIT_COMMITTER_DATE']=when
    subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,env=env)

def test_git_facts_from_a_throwaway_repo(tmp_path,monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL','/dev/null')
    repo=tmp_path/'repo';repo.mkdir();run_git(repo,'init','-b','main');run_git(repo,'config','user.email','t@example.com')
    def commit(name,subject,minutes):
        (repo/name).write_text(subject);run_git(repo,'add','.');run_git(repo,'commit','-m',subject,when=(CLOCK-dt.timedelta(minutes=minutes)).isoformat())
    commit('a','feat: add thing',200);commit('b','fix: repair thing',170);commit('c','Revert "feat: add thing"',60);commit('d','chore: tidy',30)
    (repo/'a').write_text('dirty');old=CLOCK.timestamp()-5*86400;os.utime(repo/'a',(old,old))
    facts=obs.repo_facts(str(repo),(CLOCK-dt.timedelta(days=14)).isoformat(),CLOCK)
    assert sorted(c[2] for c in facts['commits'])==['feat','fix','other','revert'] and len({c[0] for c in facts['commits']})==4
    assert facts['dirty_files']==1 and facts['dirty_age_days']==pytest.approx(5.0,abs=0.05) and facts['unpushed']==0
    assert 'thing' not in json.dumps(facts)
    # the signals fire on that real data: one revert, a fix 30 min after a feature (only one, so no rework finding)
    found=kinds(obs.mistakes([],{'repo':facts|{'commits':[(t,c) for _,t,c in facts['commits']]}},{},{},CLOCK))
    assert 'reverts' in found and 'stale_dirty_tree' in found and 'rework_after_feature' not in found
    assert obs.repo_facts(str(tmp_path/'missing'),'2026-01-01',CLOCK) is None

def test_git_classification_and_time_blocks():
    assert [obs.classify_subject(s) for s in ('Revert "x"','fix: a','fix(api): b','Fix typo','feat(ui): c','feature: d','refactor','fixture')]==['revert','fix','fix','fix','feat','feat','other','other']
    blocks=obs.git_blocks([0,600,1200,10000,10100])
    assert [(a,b,round(m)) for a,b,m in blocks]==[(0,1200,35),(10000,10100,17)]

def test_scan_reads_git_for_inventory_repos(world,isolated):
    repo=world/'work'/'atlas'
    for part in ('.git',):
        import shutil;shutil.rmtree(repo/part)
    run_git(repo,'init','-b','main');run_git(repo,'config','user.email','t@example.com')
    (repo/'f').write_text('1');run_git(repo,'add','.');run_git(repo,'commit','-m','feat: one',when=(CLOCK-dt.timedelta(hours=2)).isoformat())
    (isolated/'inventory.json').write_text(json.dumps({'github':[],'local':{'repos':[{'path':str(repo),'name':'atlas','tracked_changes':0,'last_commit':'abc 2026-10-21 feat'}]},'captured_at':'x'}))
    enable();data=obs.scan(CLOCK);atlas=next(p for p in data['projects'] if p['name']=='atlas')
    assert atlas['commits']==1 and atlas['git_estimate_minutes']==15 and atlas['tools']['git']==1
    assert 'one' not in json.dumps(data) and 'one' not in dump_all()

# API, WIPE, MAP, NOTIFY

def test_enable_scan_map_and_wipe_through_the_api(world,client):
    client.post('/api/settings',headers=H(),json={'agent_observer_enabled':True})
    write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    data=client.post('/api/activity/scan',headers=H()).json()
    assert data['enabled'] and data['totals']['sessions']>=1
    assert client.get('/api/activity/overview?days=7',headers=H()).json()['projects']
    assert client.post('/api/activity/map',headers=H(),json=[{'pattern':'work/atlas','project':'Renamed'}]).json()==[{'pattern':'work/atlas','project':'Renamed'}]
    assert client.get('/api/activity/map',headers=H()).json()[0]['project']=='Renamed'
    assert client.post('/api/activity/map',headers=H(),json=[{'pattern':'','project':'x'}]).status_code==400
    assert client.post('/api/activity/map',headers=H(),json=[{'pattern':'x','project':'y'*101}]).status_code==400
    assert client.post('/api/activity/map',headers=H(),json=[{'pattern':'x'}]).status_code==400
    assert {p['name'] for p in client.post('/api/activity/scan',headers=H()).json()['projects']}=={'Renamed'}
    wiped=client.delete('/api/activity/data',headers=H()).json()['deleted']
    assert wiped['activity_sessions']>=1 and wiped['activity_days']>=1
    after=client.get('/api/activity/overview',headers=H()).json()
    assert after['sessions']==[] and after['daily']==[] and after['projects']==[]
    with engine.connect() as c:assert all(c.execute(f'SELECT count(*) FROM {t}').fetchone()[0]==0 for t in ('activity_sessions','activity_days','activity_state'))
    assert any(a['action']=='activity:wipe' for a in client.get('/api/audit',headers=H()).json())

def test_source_logs_are_never_modified(world):
    enable();paths=[write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas')),write(world/'.codex'/'sessions'/'r.jsonl',codex_rows(world/'work'/'beta'))]
    before=[(p.read_bytes(),p.stat().st_mtime) for p in paths];obs.scan(CLOCK);obs.wipe()
    assert [(p.read_bytes(),p.stat().st_mtime) for p in paths]==before

def test_new_critical_mistake_creates_one_inbox_item(world):
    enable();rows=[]
    for i in range(3):rows+=[cl(i*600,'assistant',world/'work'/'atlas',[use(f'x{i}{j}','Bash',command='c') for j in range(35)]),cl(i*600+30,'user',world/'work'/'atlas',[res(f'x{i}{j}',j<28) for j in range(35)])]
    write(world/'.claude'/'projects'/'p'/'s.jsonl',rows);obs.scan(CLOCK);obs.scan(CLOCK)
    with engine.connect() as c:items=c.execute("SELECT kind,ref_id,detail FROM inbox WHERE ref_type='activity'").fetchall()
    assert len(items)>=1 and len({i['ref_id'] for i in items})==len(items) and all(i['kind']=='agent' for i in items)

# INSIGHTS AND REPORTS

def blob(captured=CLOCK):
    return {'captured_at':captured.isoformat(),'coverage':'Parsed 3 session files','errors':[],'now':[],'mcp_servers':0,'suggestions':[],'correlations':[{'a':'Atlas','b':'Beta','score':0.7,'evidence':'both active on 5 of 9 days','days_shared':0.5,'hours_overlap':3,'handoffs':4,'same_session':0,'shared_ci_failures':0}],
      'mistakes':[{'id':'reverts:Atlas','severity':'critical','kind':'reverts','project':'Atlas','title':'Atlas: 3 revert commits','detail':'Reverts mark work that had to be undone.','suggestion':'Add a test.','evidence':['x']}],
      'unlogged':[{'project':'Atlas','minutes':186,'commits':4}],'last_active':{}}

def store(value):
    with engine.connect() as c:obs.set_state(c,'scan',value)

def test_analyse_adds_activity_findings_only_when_fresh_and_enabled(isolated):
    from tests.test_insights import snap
    store(blob());base=insights.analyse(snap(),CLOCK)
    assert not [f for f in base['findings'] if f['kind'].startswith('activity_') or f['kind']=='project_unlogged_work']
    enable();found={f['kind']:f for f in insights.analyse(snap(),CLOCK)['findings']}
    assert found['activity_reverts']['severity']=='critical' and found['activity_reverts']['evidence']==[{'type':'project','id':'Atlas','label':'Atlas'}]
    assert 'project_unlogged_work' in found and found['overdue']
    first,second=insights.analyse(snap(),CLOCK),insights.analyse(snap(),CLOCK)
    assert first['findings']==second['findings']
    stale=insights.analyse(snap(),CLOCK+dt.timedelta(minutes=31))
    assert not [f for f in stale['findings'] if f['kind'].startswith('activity_')]

def test_report_has_activity_section_only_when_enabled_with_data(world):
    write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'))
    enable();obs.scan(CLOCK);report=engine.report('daily',CLOCK+dt.timedelta(hours=1))['content']
    assert '## Activity' in report and '- atlas:' in report and 'estimates' in report and 'ZEBRA' not in report
    settings.save({'agent_observer_enabled':False})
    assert '## Activity' not in engine.report('daily',CLOCK+dt.timedelta(hours=1))['content']
    enable();obs.wipe();assert '## Activity' not in engine.report('daily',CLOCK+dt.timedelta(hours=1))['content']

def test_compact_brief_is_name_only(world):
    enable();write(world/'.claude'/'projects'/'p'/'s.jsonl',claude_rows(world/'work'/'atlas'));obs.scan(dt.datetime.now(IST))
    brief=obs.compact();assert brief and brief['projects'][0]['project']=='atlas' and 'ZEBRA' not in json.dumps(brief)
