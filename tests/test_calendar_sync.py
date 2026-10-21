"""System Calendar and Reminders sync: stubbed fetch only (osascript is never called here)."""
import datetime as dt
import stat
import pytest
from fastapi.testclient import TestClient
import api
import autosync
import calendar_sync
import engine
import insights
import settings
import work
from collector import IST

REAL_FETCH=calendar_sync.fetch
CLOCK=dt.datetime(2026,10,21,9,0,tzinfo=IST)

def H():return {'Authorization':'Bearer '+api.TOKEN}

def event(uid='E1',start='2026-10-22T10:00:00+05:30',end='2026-10-22T10:30:00+05:30',title='Design review',all_day=False,location='Room 4'):
    return {'uid':uid,'title':title,'start':start,'end':end,'all_day':all_day,'calendar':'Work','location':location}

def reminder(rid='R1',due='2026-10-22T18:00:00+05:30',title='Send invoice',completed=False):
    return {'id':rid,'title':title,'body':'','due':due,'completed':completed,'list':'Admin','priority':1}

@pytest.fixture
def cal(isolated,monkeypatch):
    monkeypatch.setattr(calendar_sync,'DATA',isolated)
    state={'calls':0,'events':[],'reminders':[],'ok_events':True,'ok_reminders':True,'errors':[]}
    def fake_fetch(days_back=7,days_ahead=30):
        state['calls']+=1
        value={'captured_at':'2026-10-21T09:00:00+05:30','events':[dict(e) for e in state['events']],'reminders':[dict(r) for r in state['reminders']],
          'coverage':'test','errors':list(state['errors']),'ok_events':state['ok_events'],'ok_reminders':state['ok_reminders']}
        calendar_sync._store(value)
        return value
    monkeypatch.setattr(calendar_sync,'fetch',fake_fetch)
    settings.save({'system_calendar_enabled':True,'calendar_autotasks':True})
    return state

@pytest.fixture
def client(cal):
    with TestClient(api.app) as c:yield c

def linked_task(source_key):
    with engine.connect() as c:
        row=c.execute('SELECT task_id FROM calendar_links WHERE source_key=?',(source_key,)).fetchone()
        if not row:return None
        task=c.execute('SELECT * FROM tasks WHERE id=?',(row['task_id'],)).fetchone()
        detail=c.execute('SELECT * FROM task_details WHERE id=?',(row['task_id'],)).fetchone()
        return dict(task)|{'start_date':detail['start_date'],'description':detail['description']}

def inbox_kind(kind):return [i for i in work.inbox() if i['kind']==kind]

def test_disabled_never_fetches_and_gate_raises(cal):
    settings.save({'system_calendar_enabled':False})
    assert 'skipped' in autosync.sync() and cal['calls']==0
    with pytest.raises(PermissionError):REAL_FETCH()

def test_event_creates_linked_task_with_due_and_audit(cal):
    cal['events']=[event()]
    result=autosync.sync()
    assert (result['created'],result['updated'],result['conflicts']) == (1,0,0) and result['captured_at']
    task=linked_task('event:E1')
    assert task['title']=='Design review' and task['due']=='2026-10-22' and task['start_date']=='2026-10-22'
    assert task['status']=='Todo' and task['priority']=='Normal' and task['owner']=='Unassigned' and task['project']=='General'
    assert 'calendar' in task['labels'] and 'Room 4' in task['description']
    with engine.connect() as c:assert c.execute("SELECT count(*) FROM audit WHERE actor='calendar-sync' AND action LIKE 'calendar:create:%'").fetchone()[0]==1

def test_second_run_without_source_change_creates_nothing(cal):
    cal['events']=[event()];cal['reminders']=[reminder()]
    autosync.sync()
    result=autosync.sync()
    assert {k:result[k] for k in ('created','updated','completed','conflicts')}=={'created':0,'updated':0,'completed':0,'conflicts':0}
    with engine.connect() as c:assert c.execute('SELECT count(*) FROM tasks').fetchone()[0]==2

def test_source_moved_and_task_untouched_is_updated(cal):
    cal['events']=[event()];autosync.sync()
    cal['events']=[event(start='2026-10-23T10:00:00+05:30',end='2026-10-23T10:30:00+05:30')]
    result=autosync.sync()
    assert result['updated']==1
    task=linked_task('event:E1');assert task['due']=='2026-10-23' and task['start_date']=='2026-10-23'

def test_source_moved_but_task_edited_locally_raises_conflict_without_overwrite(cal):
    cal['events']=[event()];autosync.sync()
    engine.save_task({'id':linked_task('event:E1')['id'],'due':'2026-10-25'},actor='desktop')
    cal['events']=[event(start='2026-10-24T10:00:00+05:30',end='2026-10-24T10:30:00+05:30')]
    result=autosync.sync()
    assert result['conflicts']==1 and result['updated']==0
    assert linked_task('event:E1')['due']=='2026-10-25'
    assert len(inbox_kind('conflict'))==1
    assert autosync.sync()['conflicts']==0 and len(inbox_kind('conflict'))==1

def test_completed_reminder_closes_task_once_and_respects_reopen(cal):
    cal['reminders']=[reminder()];autosync.sync()
    task_id=linked_task('reminder:R1')['id']
    cal['reminders']=[reminder(completed=True)]
    assert autosync.sync()['completed']==1
    assert linked_task('reminder:R1')['status']=='Done'
    engine.save_task({'id':task_id,'status':'Todo'},actor='desktop')
    assert autosync.sync()['completed']==0 and linked_task('reminder:R1')['status']=='Todo'

def test_task_due_reminder_fires_once(cal):
    engine.save_task({'title':'File return','project':'General','due':'2026-10-21'},actor='desktop')
    first=autosync.due_reminders(CLOCK);second=autosync.due_reminders(CLOCK)
    assert len(first)==1 and first[0]['kind']=='task' and first[0]['id'] and first[0]['id']==second[0]['id']
    assert first[0]['title']=='File return' and first[0]['when']=='2026-10-21'
    assert len(inbox_kind('reminder'))==1

def test_event_reminder_within_lead_fires_once_and_ack_marks_read(client,cal):
    cal['events']=[event(start='2026-10-21T09:10:00+05:30',end='2026-10-21T09:40:00+05:30')];autosync.sync()
    due=autosync.due_reminders(CLOCK)
    assert len(due)==1 and due[0]['kind']=='event' and due[0]['lead_minutes']==15 and due[0]['title']=='Design review'
    assert autosync.due_reminders(CLOCK)[0]['id']==due[0]['id']
    assert client.get('/api/reminders/due',headers=H()).status_code==200
    items=inbox_kind('reminder');assert len(items)==1 and items[0]['read'] is False and items[0]['title']=='Starts in 10 min: Design review'
    assert client.post('/api/reminders/ack',headers=H(),json={'id':due[0]['id']}).json()=={'ok':True}
    assert inbox_kind('reminder')[0]['read'] is True

def test_notifications_off_returns_items_without_inbox(cal):
    settings.save({'calendar_notifications':False})
    engine.save_task({'title':'Quiet task','project':'General','due':'2026-10-21'},actor='desktop')
    items=autosync.due_reminders(CLOCK)
    assert len(items)==1 and items[0]['id']=='' and inbox_kind('reminder')==[]

def test_partial_failure_stores_events_and_lists_reminder_error(isolated,monkeypatch):
    monkeypatch.setattr(calendar_sync,'DATA',isolated);settings.save({'system_calendar_enabled':True})
    monkeypatch.setattr(calendar_sync.sys,'platform','darwin')
    def fake_jxa(script,args):
        if script is calendar_sync.CALENDAR_NAMES_JXA:return ['Work']
        if script is calendar_sync.EVENTS_JXA:return {'events':[{'uid':'E9','title':'Standup','start':'2026-10-22T09:00:00+05:30','end':'2026-10-22T09:15:00+05:30','all_day':False,'calendar':'Work','location':''}]}
        if script is calendar_sync.LISTS_JXA:return ['Admin']
        raise RuntimeError('Reminders got an error: Not authorized to send Apple events (-1743)')
    monkeypatch.setattr(calendar_sync,'_jxa',fake_jxa)
    snap=REAL_FETCH()
    assert snap['ok_events'] and not snap['ok_reminders'] and len(snap['events'])==1 and snap['reminders']==[]
    assert any('-1743' in e for e in snap['errors']) and 'Calendar 1 of 1' not in snap['coverage']
    stored=calendar_sync.load();assert stored['events'][0]['uid']=='E9'
    assert stat.S_IMODE((isolated/'system_calendar.json').stat().st_mode)==0o600

def test_unsupported_platform_returns_no_items(isolated,monkeypatch):
    monkeypatch.setattr(calendar_sync,'DATA',isolated);settings.save({'system_calendar_enabled':True})
    monkeypatch.setattr(calendar_sync.sys,'platform','linux')
    snap=REAL_FETCH();assert snap['coverage']=='Unsupported on this OS' and snap['events']==[] and snap['reminders']==[]

def test_calendar_findings_back_to_back_overload_crunch_and_no_focus(cal):
    at=lambda h,m:f'2026-10-21T{h:02d}:{m:02d}:00+05:30'
    events=[event('A',at(9,0),at(9,50)),event('B',at(9,55),at(10,40)),event('C',at(11,0),at(11,30)),event('D',at(12,0),at(12,30)),
      event('E',at(13,0),at(13,30)),event('F',at(14,0),at(17,50))]
    snap={'generated_at':'now','tasks':[{'id':'t','key':'GOT-1','title':'Ship','project':'General','owner':'Unassigned','status':'Todo','priority':'Normal','due':'2026-10-21','updated_at':'2026-10-21T08:00:00+05:30'}],
      'projects':[],'inventory':{'github':[]},'workspace':{},'calendar':{'captured_at':'2026-10-21T08:00:00+05:30','events':events,'reminders':[]}}
    kinds={f['kind'] for f in insights.analyse(snap,CLOCK)['findings']}
    assert {'calendar_backtoback','calendar_overload','calendar_no_focus','calendar_deadline_crunch'}<=kinds
    found=[f for f in insights.analyse(snap,CLOCK)['findings'] if f['kind']=='calendar_overload'][0]
    assert found['evidence'][0]['type']=='calendar_day' and found['evidence'][0]['id']=='2026-10-21'
    snap['calendar']['captured_at']='2026-10-19T08:00:00+05:30'
    assert not any(f['kind'].startswith('calendar_') for f in insights.analyse(snap,CLOCK)['findings'])

def test_reminder_lead_setting_validation():
    assert settings.save({'reminder_lead_minutes':30})['reminder_lead_minutes']==30
    for bad in ['x',2000,-1,True,15.5]:
        with pytest.raises(ValueError):settings.save({'reminder_lead_minutes':bad})
    assert settings.get()['reminder_lead_minutes']==30

def test_routes_status_and_sync_counts(client,cal):
    cal['events']=[event()];body=client.post('/api/calendar/sync',headers=H()).json()
    assert set(body)>={'created','updated','completed','conflicts','skipped','captured_at','errors'} and body['created']==1
    status=client.get('/api/calendar/system',headers=H()).json()
    assert status['enabled'] is True and status['events'][0]['uid']=='E1' and status['captured_at']
    assert set(status)>={'enabled','captured_at','coverage','errors','events','reminders'}
