"""Maps Calendar events and dated Reminders onto GOTEET tasks, and raises due-time reminders. Source apps stay read-only."""
import datetime as dt
import threading
import calendar_sync
import engine
import settings
import work
from collector import IST, now

ACTOR='calendar-sync'
LOCK=threading.Lock();REMIND_LOCK=threading.Lock()

def ensure(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS calendar_links(source_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, kind TEXT NOT NULL, synced_due TEXT NOT NULL, synced_title TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS reminder_log(key TEXT PRIMARY KEY, fired_at TEXT NOT NULL);''')
    # Additive columns: the start time drives due-time reminders; inbox_id lets the due list point at its notification.
    if 'synced_start' not in {r[1] for r in c.execute('PRAGMA table_info(calendar_links)')}:c.execute("ALTER TABLE calendar_links ADD COLUMN synced_start TEXT NOT NULL DEFAULT ''")
    if 'inbox_id' not in {r[1] for r in c.execute('PRAGMA table_info(reminder_log)')}:c.execute("ALTER TABLE reminder_log ADD COLUMN inbox_id TEXT NOT NULL DEFAULT ''")
    c.commit()

def _db(fn):
    """Each step opens its own short connection: task saves run on separate connections and must not wait on ours."""
    with engine.connect() as c:
        ensure(c);return fn(c)

def sync(clock=None):
    if not settings.get()['system_calendar_enabled']:return {'skipped':'System Calendar sync is disabled in Permissions'}
    if not LOCK.acquire(blocking=False):return {'skipped':'A calendar sync is already running'}
    try:return _sync()
    finally:LOCK.release()

def _sync():
    snap=calendar_sync.fetch()
    state={'created':0,'updated':0,'completed':0,'conflicts':0,'skipped':0,'errors':list(snap.get('errors',[]))}
    if settings.get()['calendar_autotasks']:
        if snap.get('ok_events'):
            for e in snap['events']:_process('event',e,state)
        if snap.get('ok_reminders'):
            for r in snap['reminders']:_process('reminder',r,state)
    # Absence from a snapshot never changes a task: deleted source items are left alone.
    return {k:state[k] for k in ('created','updated','completed','conflicts','skipped')}|{'captured_at':snap.get('captured_at',''),'errors':state['errors']}

def _shape(kind,item):
    if kind=='event':
        place=item.get('location','');cal=item.get('calendar','')
        return {'key':'event:'+item['uid'],'title':item['title'].strip() or '(No title)','when':item['start'],'day':item['start'][:10],'start_date':item['start'][:10],'label':'calendar','group':cal,
          'description':' · '.join(x for x in [place,'Calendar: '+cal if cal else ''] if x)}
    return {'key':'reminder:'+item['id'],'title':item['title'].strip() or '(No title)','when':item['due'],'day':item['due'][:10],'start_date':'','label':'reminder','group':item.get('list',''),
      'description':'Reminders list: '+item['list'] if item.get('list') else ''}

def _link(key):
    return _db(lambda c:c.execute('SELECT * FROM calendar_links WHERE source_key=?',(key,)).fetchone())

def _task(task_id):
    return _db(lambda c:c.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone())

def _put_link(s,kind,task_id):
    def write(c):c.execute('''INSERT INTO calendar_links(source_key,task_id,kind,synced_due,synced_title,updated_at,synced_start) VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(source_key) DO UPDATE SET task_id=excluded.task_id,kind=excluded.kind,synced_due=excluded.synced_due,synced_title=excluded.synced_title,updated_at=excluded.updated_at,synced_start=excluded.synced_start''',
      (s['key'],task_id,kind,s['day'],s['title'],now(),s['when']));c.commit()
    _db(write)

def _logged(key):return _db(lambda c:c.execute('SELECT 1 FROM reminder_log WHERE key=?',(key,)).fetchone()) is not None

def _log(key,inbox_id=''):
    def write(c):c.execute('INSERT OR IGNORE INTO reminder_log(key,fired_at,inbox_id) VALUES(?,?,?)',(key,now(),inbox_id));c.commit()
    _db(write)

def _project(name):
    return bool(name) and _db(lambda c:c.execute('SELECT 1 FROM projects WHERE name=?',(name,)).fetchone()) is not None

def _process(kind,item,state):
    s=_shape(kind,item)
    if not s['key'].split(':',1)[1] or not s['when'] or not s['day']:state['skipped']+=1;return
    link=_link(s['key'])
    if kind=='reminder' and item['completed']:
        # One-way: a completed Apple reminder closes its task once; a later reopen by the user is respected.
        if not link or _logged('done:'+s['key']):state['skipped']+=1;return
        task=_task(link['task_id'])
        if not task or task['status']=='Done':state['skipped']+=1;return
        engine.save_task({'id':task['id'],'status':'Done'},actor=ACTOR,automated=True)
        _log('done:'+s['key'])
        work.audit('calendar:complete:'+task['id'],ACTOR)
        work.notify('automation',f"Completed in Reminders: {task['title']}",s['title'],'task',task['id'],ACTOR)
        state['completed']+=1;return
    if not link:
        if kind=='reminder' and item['completed']:state['skipped']+=1;return
        _create(kind,s,state);return
    task=_task(link['task_id'])
    if not task:state['skipped']+=1;return
    _update(kind,s,link,task,state)

def _create(kind,s,state):
    project=s['group'] if _project(s['group']) else 'General'
    try:task=engine.save_task({'title':s['title'],'project':project,'status':'Todo','priority':'Normal','owner':'Unassigned','due':s['day'],'start_date':s['start_date'],'labels':[s['label']],'description':s['description']},actor=ACTOR)
    except ValueError as error:state['skipped']+=1;state['errors'].append(f"{s['key']}: {error}");return
    _put_link(s,kind,task['id'])
    work.audit('calendar:create:'+task['id'],ACTOR)
    work.notify('automation',f"Created from {s['label']}: {task['key']} {s['title']}",s['when'],'task',task['id'],ACTOR)
    state['created']+=1

def _update(kind,s,link,task,state):
    day_moved=s['day']!=link['synced_due'];title_moved=s['title']!=link['synced_title']
    if not day_moved and not title_moved and s['when']==link['synced_start']:return
    if not day_moved and not title_moved:
        # Same day, new time: refresh the baseline so due-time reminders follow the source.
        _put_link(s,kind,task['id']);return
    changes={};conflicts=[]
    if day_moved:
        if task['due']==link['synced_due']:
            changes['due']=s['day']
            if kind=='event':changes['start_date']=s['start_date']
        else:conflicts.append('date')
    if title_moved:
        if task['title']==link['synced_title']:changes['title']=s['title']
        else:conflicts.append('title')
    if conflicts:
        work.notify('conflict',f"Source moved, task edited locally: {task['key']} {task['title']}",f"Source now {s['day']} / {s['title']}; {' and '.join(conflicts)} left as edited in GOTEET.",'task',task['id'],ACTOR)
        _put_link(s,kind,task['id']);state['conflicts']+=1;return
    if changes:
        engine.save_task({'id':task['id'],**changes},actor=ACTOR)
        work.audit('calendar:update:'+task['id'],ACTOR)
        work.notify('automation',f"Updated from {s['label']}: {task['key']} {s['title']}",f"{'due '+s['day'] if day_moved else ''}{'; ' if day_moved and title_moved else ''}{'title changed' if title_moved else ''}".strip(),'task',task['id'],ACTOR)
        state['updated']+=1
    _put_link(s,kind,task['id'])

# DUE REMINDERS

def _fire(key,title,detail,task_id,notify_on):
    """Once per key: the first call creates the inbox item; later calls return the same inbox id."""
    row=_db(lambda c:c.execute('SELECT inbox_id FROM reminder_log WHERE key=?',(key,)).fetchone())
    if row:return row['inbox_id']
    if not notify_on:return ''
    record=work.notify('reminder',title,detail,'task',task_id,ACTOR)
    _log(key,record['id'])
    return record['id']

def due_reminders(clock=None,lead=None):
    prefs=settings.get()
    if not prefs['system_calendar_enabled']:return []
    lead=prefs['reminder_lead_minutes'] if lead is None else lead
    at=(clock or dt.datetime.now(IST)).astimezone(IST);today=at.date().isoformat();horizon=at+dt.timedelta(minutes=lead)
    rows=_db(lambda c:c.execute("SELECT t.id,t.title,t.due,l.kind AS link_kind,l.synced_start FROM tasks t LEFT JOIN calendar_links l ON l.task_id=t.id WHERE t.status!='Done'").fetchall())
    items=[]
    with REMIND_LOCK:
        for r in rows:
            linked=bool(r['synced_start'])
            if linked:
                moment=work.moment(r['synced_start'])
                if not at<=moment<=horizon:continue
                minutes=max(0,round((moment-at).total_seconds()/60))
                key=f"task:{r['id']}:{r['synced_start']}";when=r['synced_start']
                kind='event' if r['link_kind']=='event' else 'task'
                title=(f"Starts in {minutes} min: " if minutes else 'Starts now: ')+r['title']
            else:
                if r['due']!=today:continue
                key=f"task:{r['id']}:{r['due']}";when=r['due'];kind='task'
                title='Due today: '+r['title']
            inbox_id=_fire(key,title,f"{'Calendar event' if kind=='event' else 'Task'} · {when}",r['id'],prefs['calendar_notifications'])
            items.append({'key':key,'task_id':r['id'],'title':r['title'],'when':when,'lead_minutes':lead,'kind':kind,'id':inbox_id})
    return items
