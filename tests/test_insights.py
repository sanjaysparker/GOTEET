"""Deterministic insights and owner-only analysis routes."""
import datetime as dt
import subprocess
from fastapi.testclient import TestClient
import api
import insights
import settings
from collector import IST

def H(token=None):return {'Authorization':'Bearer '+(token or api.TOKEN)}

CLOCK=dt.datetime(2026,10,21,10,tzinfo=IST)

def snap():
    t=lambda **v:{'id':v.get('id','x'),'key':v.get('key',''),'title':'T','project':'Atlas','owner':'Asha','status':'Todo','priority':'Normal','due':'','updated_at':'2026-10-21T09:00:00+05:30',**v}
    return {'generated_at':'now','tasks':[t(id='o',key='ATL-1',due='2026-10-18',priority='High'),t(id='b',key='ATL-2',status='Blocked',updated_at='2026-10-17T09:00:00+05:30'),
        t(id='d',key='ATL-3',status='Done'),t(id='d2',key='ATL-4',status='Todo')],
      'projects':[{'id':'p','name':'Atlas','status':'Active','start_date':'2026-10-01','target_date':'2026-10-20'}],
      'inventory':{'github':[]},'workspace':{'followups':[{'id':'f1','title':'Reply to vendor','project':'Atlas','priority':'High','detail':'Quote'}]}}

def test_analyse_flags_overdue_blocked_project_and_untracked_followup():
    result=insights.analyse(snap(),CLOCK)
    by={f['kind']:f for f in result['findings']}
    assert by['overdue']['severity']=='critical' and '3 d overdue' in by['overdue']['title']
    assert by['blocked']['severity']=='critical' and 'blocked 4 d' in by['blocked']['title']
    assert by['project_health']['title']=='Atlas off track' and result['projects'][0]['health']=='Off track'
    assert by['untracked_followup']['severity']=='warn'
    assert result['today']=='2026-10-21' and result['totals']=={'open':3,'done':1,'blocked':1,'projects':1}
    assert result['score']<100

def test_analyse_quiet_workspace_has_no_findings():
    result=insights.analyse({'tasks':[],'projects':[],'inventory':{},'workspace':{}},CLOCK)
    assert result['findings']==[] and result['score']==100

def test_insights_routes_owner_only_gate_and_inbox(isolated,monkeypatch):
    import agent
    monkeypatch.setattr(agent,'plan',lambda q,p,m:{'id':'plan-1','plan':{'summary':'Unblock ATL-2','steps':[]}})
    with TestClient(api.app) as client:
        member=H(client.post('/api/team/invite',headers=H(),json={'name':'Ravi'}).json()['token'])
        assert client.get('/api/insights',headers=member).status_code==403
        assert client.get('/api/insights',headers=H()).json()['score']==100
        run=client.post('/api/insights/run',headers=H(),json={'provider':'codex','focus':'blockers'}).json()
        assert run['plan']['id']=='plan-1' and run['analysis']['summary']=='Unblock ATL-2'
        assert client.get('/api/insights/history',headers=H()).json()[0]['plan_id']=='plan-1'
        item=next(i for i in client.get('/api/inbox',headers=H()).json() if i['kind']=='agent')
        assert item['title']=='AI analysis ready' and item['ref_id']=='plan-1'
        def missing(*a):raise FileNotFoundError('codex')
        monkeypatch.setattr(agent,'plan',missing)
        r=client.post('/api/insights/run',headers=H(),json={});assert r.status_code==400 and 'not installed' in r.json()['detail']
        def slow(*a):raise subprocess.TimeoutExpired('codex',150)
        monkeypatch.setattr(agent,'plan',slow)
        assert 'timed out' in client.post('/api/insights/run',headers=H(),json={}).json()['detail']
        settings.save({'agent_enabled':False})
        assert client.post('/api/insights/run',headers=H(),json={}).status_code==403
