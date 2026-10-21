"""Work management: keys, relations, cycles, docs, saved views, inbox and automations (API v1).

Everything is local SQLite. Automations act only on local records, never send external messages,
and cannot recurse: a save caused by an automation does not trigger automations.
"""
import datetime as dt
import json
import re
import uuid
import engine
from collector import IST, now

RELATIONS=('blocks','relates','duplicates')
KINDS=('assigned','mention','status','blocked','automation','agent','chat','reminder','conflict')
TRIGGERS=('task_status','task_blocked_hours','task_created')
ACTIONS=('set_field','notify','add_label')
FIELDS=('status','priority','owner','cycle_id')
class NotFound(LookupError):'''Missing record: the API maps this (and only this) to 404.'''

VIEW_FILTERS=('status','priority','owner','project','label','cycle_id','query')

def migrate(c):
    seed='automations' not in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    c.executescript('''CREATE TABLE IF NOT EXISTS relations(id TEXT PRIMARY KEY,from_id TEXT NOT NULL,to_id TEXT NOT NULL,type TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(from_id,to_id,type));
      CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY,name TEXT NOT NULL,start TEXT NOT NULL,"end" TEXT NOT NULL,goal TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,project TEXT NOT NULL,linked_tasks TEXT NOT NULL,updated_at TEXT NOT NULL,author TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS views(id TEXT PRIMARY KEY,name TEXT NOT NULL,filters TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,detail TEXT NOT NULL,ref_type TEXT NOT NULL,ref_id TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0,snoozed_until TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS automations(id TEXT PRIMARY KEY,name TEXT NOT NULL,trigger TEXT NOT NULL,action TEXT NOT NULL,params TEXT NOT NULL,enabled INTEGER NOT NULL,runs INTEGER NOT NULL DEFAULT 0,last_run TEXT NOT NULL DEFAULT '',last_result TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS automation_fired(rule_id TEXT NOT NULL,task_id TEXT NOT NULL,marker TEXT NOT NULL,PRIMARY KEY(rule_id,task_id,marker));
      CREATE TABLE IF NOT EXISTS task_events(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,field TEXT NOT NULL,old TEXT NOT NULL,new TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS task_events_task ON task_events(task_id,field,created_at);''')
    if seed:
        for name,trigger,action,params in [('Notify me when a task is blocked','task_status','notify',{'to_status':'Blocked'}),
          ('Escalate tasks blocked for 24 hours','task_blocked_hours','set_field',{'hours':24,'field':'priority','value':'Urgent'}),
          ('Label new tasks for triage','task_created','add_label',{'project':'','label':'triage'})]:
            c.execute('INSERT INTO automations(id,name,trigger,action,params,enabled,created_at) VALUES(?,?,?,?,?,0,?)',(str(uuid.uuid4()),name,trigger,action,json.dumps(params),now()))

def audit(action,actor):
    with engine.connect() as c:c.execute('INSERT INTO audit VALUES(?,?,?,?)',(str(uuid.uuid4()),action,actor,now()))

def text(value,name,limit,required=False):
    if not isinstance(value,str):raise ValueError(name+' must be text')
    value=value.strip()
    if required and not value:raise ValueError('Enter '+name.lower())
    if len(value)>limit:raise ValueError(f'{name} exceeds {limit} characters')
    return value

def ident(value):
    value=value or str(uuid.uuid4())
    if not isinstance(value,str) or len(value)>200:raise ValueError('Invalid id')
    return value

def today():return dt.datetime.now(IST).date()

def moment(value):
    """ISO string -> aware datetime; naive values are Asia/Kolkata."""
    d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=IST)

# INBOX

def notify(kind,title,detail='',ref_type='',ref_id='',actor='system'):
    record={'id':str(uuid.uuid4()),'kind':kind,'title':str(title)[:300],'detail':str(detail)[:2000],'ref_type':ref_type,'ref_id':ref_id,'actor':str(actor)[:200],'created_at':now()}
    with engine.connect() as c:c.execute('INSERT INTO inbox(id,kind,title,detail,ref_type,ref_id,actor,created_at) VALUES(:id,:kind,:title,:detail,:ref_type,:ref_id,:actor,:created_at)',record)
    return record

def inbox(limit=300):
    evaluate_blocked()
    clock=dt.datetime.now(IST);items=[]
    with engine.connect() as c:rows=c.execute('SELECT * FROM inbox ORDER BY created_at DESC,rowid DESC LIMIT ?',(limit,)).fetchall()
    for r in rows:
        if r['snoozed_until'] and moment(r['snoozed_until'])>clock:continue
        items.append({k:r[k] for k in ('id','kind','title','detail','ref_type','ref_id','actor','created_at')}|{'read':bool(r['read'])})
    return items

def mark_read(ids):
    with engine.connect() as c:
        if ids=='all':c.execute('UPDATE inbox SET read=1')
        elif isinstance(ids,list) and all(isinstance(x,str) for x in ids):c.executemany('UPDATE inbox SET read=1 WHERE id=?',[(x,) for x in ids])
        else:raise ValueError("ids must be a list of inbox ids or 'all'")
    return {'read':ids if ids=='all' else len(ids)}

def snooze(value):
    item=value.get('id');until=value.get('until')
    if not isinstance(item,str) or not isinstance(until,str):raise ValueError('Snooze needs id and until')
    try:until=moment(until).isoformat()
    except ValueError:raise ValueError('until must be an ISO date-time')
    with engine.connect() as c:
        if not c.execute('UPDATE inbox SET snoozed_until=? WHERE id=?',(until,item)).rowcount:raise NotFound('Inbox item not found')
    return {'id':item,'until':until}

def mentions(body,channel,actor):
    import settings
    name=settings.get()['display_name'].strip()
    if name and re.search(r'(?<![\w@])@'+re.escape(name)+r'(?!\w)',body,re.I):
        notify('mention',f'{actor} mentioned you in #{channel}',body[:500],'channel',channel,actor)

# TASK HOOKS

def after_task_save(previous,task,actor,automated=False):
    """Record status/cycle/owner changes, raise inbox items, then run automations unless this save came from one."""
    changes=[(f,(previous or {}).get(f,''),task[f]) for f in ('status','owner','cycle_id') if previous is None or previous.get(f)!=task[f]]
    with engine.connect() as c:
        for field,old,new in changes:c.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),task['id'],field,str(old or ''),str(new or ''),str(actor)[:200],task['updated_at']))
    label=f"{task['key']} {task['title']}"
    # Calendar sync writes its own inbox items, so suppress these per-field notices for its saves.
    for field,old,new in ([] if actor=='calendar-sync' else changes):
        if field=='owner' and new and new!='Unassigned':notify('assigned',f'{label} assigned to {new}',f'Previously {old or "Unassigned"}' if previous else 'New task','task',task['id'],actor)
        if field=='status' and previous is not None:
            notify('blocked' if new=='Blocked' else 'status',f'{label} is {new}' if new=='Blocked' else f'{label} moved to {new}',f'{old} → {new}','task',task['id'],actor)
        if field=='status' and previous is None and new=='Blocked':notify('blocked',f'{label} is Blocked','Created as Blocked','task',task['id'],actor)
    if automated:return
    for rule in automations(enabled_only=True):
        p=rule['params']
        if rule['trigger']=='task_status' and previous is not None and previous.get('status')!=task['status'] and task['status']==p.get('to_status'):fire(rule,task)
        elif rule['trigger']=='task_created' and previous is None and (not p.get('project') or p['project']==task['project']):fire(rule,task)

def plan_action(rule,task):
    p=rule['params']
    if rule['action']=='set_field':return f"set {p['field']} of {task['key']} to {p['value'] or '(empty)'}"
    if rule['action']=='add_label':return f"add label {p['label']} to {task['key']}"
    return f"notify about {task['key']}"

def fire(rule,task):
    """Apply one rule to one task synchronously. Saves are marked automated so they cannot re-trigger rules."""
    p=rule['params'];result=plan_action(rule,task)
    try:
        if rule['action']=='set_field':
            if task.get(p['field'])!=p['value']:engine.save_task({'id':task['id'],p['field']:p['value']},actor='automation',automated=True)
        elif rule['action']=='add_label':
            if p['label'] not in task['labels']:engine.save_task({'id':task['id'],'labels':task['labels']+[p['label']]},actor='automation',automated=True)
        notify('automation',f"{rule['name']}: {task['key']} {task['title']}",p.get('message','') or result,'task',task['id'],'automation')
    except Exception as error:result='failed: '+str(error)[:300]
    with engine.connect() as c:c.execute('UPDATE automations SET runs=runs+1,last_run=?,last_result=? WHERE id=?',(now(),result,rule['id']))
    audit(f"automation:{rule['id']}:task:{task['id']}",'automation')
    return result

def blocked_since(c,task):
    row=c.execute("SELECT created_at FROM task_events WHERE task_id=? AND field='status' AND new='Blocked' ORDER BY created_at DESC,rowid DESC LIMIT 1",(task['id'],)).fetchone()
    return row['created_at'] if row else task['updated_at']

def blocked_candidates(rule):
    clock=dt.datetime.now(IST);hours=rule['params']['hours'];found=[]
    with engine.connect() as c:
        for t in c.execute("SELECT * FROM tasks WHERE status='Blocked'").fetchall():
            since=blocked_since(c,t)
            if clock-moment(since)>=dt.timedelta(hours=hours):
                done=bool(c.execute('SELECT 1 FROM automation_fired WHERE rule_id=? AND task_id=? AND marker=?',(rule['id'],t['id'],since)).fetchone())
                found.append((engine.decode_task(t),since,done))
    return found

def evaluate_blocked():
    """Idempotent: each rule fires once per task per blocked episode (keyed by the time it became Blocked)."""
    for rule in automations(enabled_only=True):
        if rule['trigger']!='task_blocked_hours':continue
        for task,since,done in blocked_candidates(rule):
            if done:continue
            with engine.connect() as c:
                if not c.execute('INSERT OR IGNORE INTO automation_fired VALUES(?,?,?)',(rule['id'],task['id'],since)).rowcount:continue
            fire(rule,task)

# AUTOMATIONS

def automation_row(r):return {k:r[k] for k in ('id','name','trigger','action','last_run','last_result')}|{'params':json.loads(r['params']),'enabled':bool(r['enabled']),'runs':r['runs']}

def automations(enabled_only=False):
    with engine.connect() as c:return [automation_row(r) for r in c.execute('SELECT * FROM automations'+(' WHERE enabled=1' if enabled_only else '')+' ORDER BY created_at,rowid')]

def get_automation(identifier):
    with engine.connect() as c:row=c.execute('SELECT * FROM automations WHERE id=?',(identifier,)).fetchone()
    if not row:raise NotFound('Automation not found')
    return automation_row(row)

def save_automation(value):
    if not isinstance(value,dict):raise ValueError('Automation must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM automations WHERE id=?',(identifier,)).fetchone()
    base=automation_row(row) if row else {'name':'','trigger':'','action':'','params':{},'enabled':True}
    v={**base,**{k:value[k] for k in ('name','trigger','action','params','enabled') if k in value and value[k] is not None}}
    name=text(v['name'],'Name',200,True)
    if v['trigger'] not in TRIGGERS:raise ValueError('Trigger must be one of '+', '.join(TRIGGERS))
    if v['action'] not in ACTIONS:raise ValueError('Action must be one of '+', '.join(ACTIONS))
    if type(v['enabled']) is not bool:raise ValueError('enabled must be true or false')
    p=v['params']
    if not isinstance(p,dict):raise ValueError('params must be an object')
    p=dict(p)
    if v['trigger']=='task_status' and p.get('to_status') not in engine.STATUSES:raise ValueError('params.to_status must be a task status')
    if v['trigger']=='task_blocked_hours':
        if type(p.get('hours')) not in (int,float) or not 0<p['hours']<=8760:raise ValueError('params.hours must be a number 0–8760')
    if v['trigger']=='task_created':p['project']=text(p.get('project',''),'params.project',200)
    if v['action']=='set_field':
        if p.get('field') not in FIELDS:raise ValueError('params.field must be one of '+', '.join(FIELDS))
        value_=p.get('value')
        if not isinstance(value_,str):raise ValueError('params.value must be text')
        if p['field']=='status' and value_ not in engine.STATUSES:raise ValueError('params.value must be a task status')
        if p['field']=='priority' and value_ not in engine.PRIORITIES:raise ValueError('params.value must be a priority')
        if p['field']=='owner' and not value_.strip():raise ValueError('params.value must name an owner')
        if p['field']=='cycle_id' and value_:
            with engine.connect() as c:
                if not c.execute('SELECT id FROM cycles WHERE id=?',(value_,)).fetchone():raise ValueError('Unknown cycle')
    if v['action']=='add_label':p['label']=text(p.get('label',''),'params.label',50,True)
    if v['action']=='notify' and 'message' in p:p['message']=text(p['message'],'params.message',500)
    with engine.connect() as c:c.execute('''INSERT INTO automations(id,name,trigger,action,params,enabled,created_at) VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name,trigger=excluded.trigger,action=excluded.action,params=excluded.params,enabled=excluded.enabled''',
      (identifier,name,v['trigger'],v['action'],json.dumps(p),int(v['enabled']),now()))
    return get_automation(identifier)

def toggle_automation(identifier):
    rule=get_automation(identifier)
    with engine.connect() as c:c.execute('UPDATE automations SET enabled=? WHERE id=?',(int(not rule['enabled']),identifier))
    return get_automation(identifier)

def dry_run(identifier):
    """What the rule WOULD do against current tasks. Changes nothing (not even run counters)."""
    rule=get_automation(identifier);p=rule['params'];matches=[]
    if rule['trigger']=='task_blocked_hours':
        for task,since,done in blocked_candidates(rule):matches.append({'task_id':task['id'],'key':task['key'],'title':task['title'],'would':plan_action(rule,task),'already_applied':done})
    else:
        with engine.connect() as c:
            if rule['trigger']=='task_status':rows=c.execute('SELECT * FROM tasks WHERE status=? ORDER BY updated_at DESC LIMIT 50',(p['to_status'],)).fetchall()
            else:rows=c.execute('SELECT * FROM tasks'+(' WHERE project=?' if p.get('project') else '')+' ORDER BY created_at DESC LIMIT 50',((p['project'],) if p.get('project') else ())).fetchall()
        for r in rows:
            task=engine.decode_task(r);matches.append({'task_id':task['id'],'key':task['key'],'title':task['title'],'would':plan_action(rule,task),'already_applied':False})
    note={'task_status':'Runs when a task moves into this status; listed tasks are already there.','task_created':'Runs when a matching task is created; listed tasks show the rule applied to recent ones.',
      'task_blocked_hours':'Runs on inbox/snapshot reads for tasks blocked longer than the threshold; already_applied marks this blocked episode as handled.'}[rule['trigger']]
    return {'automation':rule,'dry_run':True,'matches':matches,'note':note}

# RELATIONS

def relations(task_id=''):
    with engine.connect() as c:
        rows=c.execute('SELECT id,from_id,to_id,type FROM relations WHERE from_id=? OR to_id=? ORDER BY created_at',(task_id,task_id)) if task_id else c.execute('SELECT id,from_id,to_id,type FROM relations ORDER BY created_at')
        return [dict(r) for r in rows]

def save_relation(value):
    a=value.get('from_id');b=value.get('to_id');kind=value.get('type')
    if kind not in RELATIONS:raise ValueError('type must be one of '+', '.join(RELATIONS))
    if not isinstance(a,str) or not isinstance(b,str):raise ValueError('from_id and to_id are required')
    if a==b:raise ValueError('A task cannot relate to itself')
    with engine.connect() as c:
        if sum(1 for x in (a,b) if c.execute('SELECT 1 FROM tasks WHERE id=?',(x,)).fetchone())!=2:raise ValueError('Unknown task id')
        existing=c.execute('SELECT id,from_id,to_id,type FROM relations WHERE from_id=? AND to_id=? AND type=?',(a,b,kind)).fetchone()
        if existing:return dict(existing)
        record={'id':str(uuid.uuid4()),'from_id':a,'to_id':b,'type':kind}
        c.execute('INSERT INTO relations VALUES(?,?,?,?,?)',(*record.values(),now()))
    return record

# CYCLES

def cycle_status(start,end,on=None):
    on=on or today()
    return 'upcoming' if on<dt.date.fromisoformat(start) else 'completed' if on>dt.date.fromisoformat(end) else 'active'

def value_at(events,current,created,day):
    """Field value at end of `day` from recorded events; falls back to the current value for tasks without history."""
    if created[:10]>day:return None
    past=[e for e in events if e['created_at'][:10]<=day]
    if past:return past[-1]['new']
    return events[0]['old'] if events else current

def cycles():
    on=today()
    with engine.connect() as c:
        rows=c.execute('SELECT * FROM cycles ORDER BY start,name').fetchall()
        tasks=[dict(t) for t in c.execute('SELECT id,status,estimate,cycle_id,created_at FROM tasks')]
        events={}
        for e in c.execute("SELECT task_id,field,old,new,created_at FROM task_events WHERE field IN ('status','cycle_id') ORDER BY created_at,rowid"):events.setdefault((e['task_id'],e['field']),[]).append(dict(e))
    result=[]
    for r in rows:
        mine=[t for t in tasks if t['cycle_id']==r['id']]
        start=dt.date.fromisoformat(r['start']);end=dt.date.fromisoformat(r['end']);history=[]
        touched=[t for t in tasks if t['cycle_id']==r['id'] or any(r['id'] in (e['old'],e['new']) for e in events.get((t['id'],'cycle_id'),[]))]
        day=start
        while day<=min(on,end):
            d=day.isoformat();scope=done=0
            for t in touched:
                if value_at(events.get((t['id'],'cycle_id'),[]),t['cycle_id'],t['created_at'],d)!=r['id']:continue
                scope+=1;done+=value_at(events.get((t['id'],'status'),[]),t['status'],t['created_at'],d)=='Done'
            history.append({'date':d,'scope':scope,'done':done});day+=dt.timedelta(days=1)
        result.append({'id':r['id'],'name':r['name'],'start':r['start'],'end':r['end'],'status':cycle_status(r['start'],r['end'],on),'goal':r['goal'],
          'stats':{'issues':len(mine),'done':sum(t['status']=='Done' for t in mine),'points':sum(t['estimate'] for t in mine),
            'done_points':sum(t['estimate'] for t in mine if t['status']=='Done'),'blocked':sum(t['status']=='Blocked' for t in mine),'history':history}})
    return result

def save_cycle(value):
    if not isinstance(value,dict):raise ValueError('Cycle must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM cycles WHERE id=?',(identifier,)).fetchone()
    v={**(dict(row) if row else {'name':'','start':'','end':'','goal':''}),**{k:value[k] for k in ('name','start','end','goal') if k in value and value[k] is not None}}
    name=text(v['name'],'Name',200,True);goal=text(v['goal'],'Goal',2000)
    for k in ('start','end'):
        try:dt.date.fromisoformat(text(v[k],k.title(),10,True))
        except ValueError as e:raise ValueError(f'{k} must use YYYY-MM-DD') from e
    if v['start']>v['end']:raise ValueError('Cycle end must be on or after its start')
    with engine.connect() as c:c.execute('''INSERT INTO cycles VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,start=excluded.start,"end"=excluded."end",goal=excluded.goal,updated_at=excluded.updated_at''',
      (identifier,name,v['start'],v['end'],goal,now()))
    return next(x for x in cycles() if x['id']==identifier)

def delete_cycle(identifier,actor):
    with engine.connect() as c:
        if not c.execute('DELETE FROM cycles WHERE id=?',(identifier,)).rowcount:raise NotFound('Cycle not found')
        affected=[r['id'] for r in c.execute('SELECT id FROM tasks WHERE cycle_id=?',(identifier,))]
        c.execute("UPDATE tasks SET cycle_id='',updated_at=? WHERE cycle_id=?",(now(),identifier))
        for t in affected:c.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),t,'cycle_id',identifier,'',str(actor),now()))
    return {'deleted':identifier,'tasks_unset':len(affected)}

# DOCS

def docs():
    with engine.connect() as c:
        ids={r[0] for r in c.execute('SELECT id FROM tasks')}
        return [dict(r)|{'linked_tasks':[t for t in json.loads(r['linked_tasks']) if t in ids]} for r in c.execute('SELECT * FROM docs ORDER BY updated_at DESC')]

def save_doc(value,author):
    if not isinstance(value,dict):raise ValueError('Doc must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:
        row=c.execute('SELECT * FROM docs WHERE id=?',(identifier,)).fetchone()
        base=dict(row)|{'linked_tasks':json.loads(row['linked_tasks'])} if row else {'title':'','body':'','project':'','linked_tasks':[]}
        v={**base,**{k:value[k] for k in ('title','body','project','linked_tasks') if k in value and value[k] is not None}}
        title=text(v['title'],'Title',500,True);body=v['body']
        if not isinstance(body,str) or len(body)>200000:raise ValueError('Body must be text of at most 200000 characters')
        project=text(v['project'],'Project',200);linked=v['linked_tasks']
        if not isinstance(linked,list) or len(linked)>200 or any(not isinstance(x,str) for x in linked):raise ValueError('linked_tasks must be a list of task ids')
        linked=list(dict.fromkeys(linked))
        if any(not c.execute('SELECT 1 FROM tasks WHERE id=?',(x,)).fetchone() for x in linked):raise ValueError('Unknown task id in linked_tasks')
        record={'id':identifier,'title':title,'body':body,'project':project,'linked_tasks':linked,'updated_at':now(),'author':str(author)[:200]}
        c.execute('INSERT INTO docs VALUES(:id,:title,:body,:project,:lt,:updated_at,:author) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,project=excluded.project,linked_tasks=excluded.linked_tasks,updated_at=excluded.updated_at,author=excluded.author',
          record|{'lt':json.dumps(linked)})
    return record

# SAVED VIEWS

def views():
    with engine.connect() as c:return [dict(r)|{'filters':json.loads(r['filters'])} for r in c.execute('SELECT * FROM views ORDER BY name')]

def save_view(value):
    if not isinstance(value,dict):raise ValueError('View must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM views WHERE id=?',(identifier,)).fetchone()
    base={'name':row['name'],'filters':json.loads(row['filters'])} if row else {'name':'','filters':{}}
    v={**base,**{k:value[k] for k in ('name','filters') if k in value and value[k] is not None}}
    name=text(v['name'],'Name',200,True);filters=v['filters']
    if not isinstance(filters,dict) or any(k not in VIEW_FILTERS for k in filters):raise ValueError('filters may contain only '+', '.join(VIEW_FILTERS))
    if any(not isinstance(x,str) or len(x)>500 for x in filters.values()):raise ValueError('Filter values must be text')
    record={'id':identifier,'name':name,'filters':filters,'updated_at':now()}
    with engine.connect() as c:c.execute('INSERT INTO views VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,filters=excluded.filters,updated_at=excluded.updated_at',(identifier,name,json.dumps(filters),record['updated_at']))
    return record

# DELETES

def delete(table,identifier):
    assert table in {'docs','views','automations','relations','projects','concepts'}
    with engine.connect() as c:
        if not c.execute('DELETE FROM '+table+' WHERE id=?',(identifier,)).rowcount:raise NotFound('Not found')
        if table=='automations':c.execute('DELETE FROM automation_fired WHERE rule_id=?',(identifier,))
    return {'deleted':identifier}

def delete_task(identifier):
    """Removes the task, its details and relations; children lose their parent. Projects/docs are untouched."""
    with engine.connect() as c:
        if not c.execute('DELETE FROM tasks WHERE id=?',(identifier,)).rowcount:raise NotFound('Task not found')
        c.execute('DELETE FROM task_details WHERE id=?',(identifier,))
        removed=c.execute('DELETE FROM relations WHERE from_id=? OR to_id=?',(identifier,identifier)).rowcount
        c.execute("UPDATE tasks SET parent_id='' WHERE parent_id=?",(identifier,))
        c.execute('DELETE FROM automation_fired WHERE task_id=?',(identifier,))
    return {'deleted':identifier,'relations_removed':removed}
