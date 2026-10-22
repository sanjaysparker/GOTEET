"""Goals, key results, milestones and the unified deadlines view (API v1).

Progress and health are deterministic and recomputed from saved tasks on every read; nothing is cached or inferred by a model.
"""
import datetime as dt
import math
import re
import uuid
import engine
import work
from work import NotFound, text, ident, audit
from collector import now

STATUSES=('Active','Achieved','Paused','Dropped')
KINDS=('tasks','manual')
ORDER={s:i for i,s in enumerate(STATUSES)}
DATE=re.compile(r'\d{4}-\d{2}-\d{2}$')

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',owner TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Active',start_date TEXT NOT NULL DEFAULT '',target_date TEXT NOT NULL DEFAULT '',project_id TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS key_results(id TEXT PRIMARY KEY,goal_id TEXT NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,project_name TEXT NOT NULL DEFAULT '',target REAL NOT NULL DEFAULT 0,current REAL NOT NULL DEFAULT 0,unit TEXT NOT NULL DEFAULT '',due TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS milestones(id TEXT PRIMARY KEY,goal_id TEXT NOT NULL DEFAULT '',project_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,due TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS key_results_goal ON key_results(goal_id);
      CREATE INDEX IF NOT EXISTS milestones_goal ON milestones(goal_id);''')

def today():return work.today()

def date_(value,name,required=False):
    value=text(value,name,10,required)
    if value and not DATE.match(value):raise ValueError(f'{name} must use YYYY-MM-DD')
    try:dt.date.fromisoformat(value) if value else None
    except ValueError as e:raise ValueError(f'{name} must use YYYY-MM-DD') from e
    return value

def number(value,name):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError(name+' must be a number')
    return float(value)

def clamp(x):return max(0.0,min(1.0,x))

def fmt(x):return str(int(x)) if float(x).is_integer() else str(round(x,2))

def kr_view(r,counts):
    if r['kind']=='tasks':
        total,done=counts.get(r['project_name'],(0,0))
        progress=done/total if total else 0.0;detail=f'{done}/{total} tasks' if total else 'No tasks yet'
    else:
        progress=clamp(r['current']/r['target']) if r['target']>0 else 0.0
        detail=f"{fmt(r['current'])} / {fmt(r['target'])}"+(' '+r['unit'] if r['unit'] else '')
    return {k:r[k] for k in ('id','goal_id','title','kind','project_name','target','current','unit','due')}|{'progress':round(progress,4),'detail':detail,'_raw':progress}

def health(status,progress,krs,milestones,start,target,on):
    """Returns (health, elapsed). Achieved wins, then No plan, then schedule slippage against progress."""
    elapsed=None
    if start and target:
        s=dt.date.fromisoformat(start);t=dt.date.fromisoformat(target)
        elapsed=clamp((on-s).days/(t-s).days) if t>s else (1.0 if on>=t else 0.0)
    if status=='Achieved' or progress>=1:return 'Achieved',elapsed
    if not krs and not milestones:return 'No plan',elapsed
    if (target and dt.date.fromisoformat(target)<on) or (elapsed is not None and elapsed-progress>0.30):return 'Off track',elapsed
    if elapsed is not None and elapsed-progress>0.12:return 'At risk',elapsed
    return 'On track',elapsed

def goals(on=None):
    on=on or today()
    with engine.connect() as c:
        rows=c.execute('SELECT * FROM goals').fetchall()
        counts={r['project']:(r['n'],r['d'] or 0) for r in c.execute("SELECT project,COUNT(*) n,SUM(status='Done') d FROM tasks GROUP BY project")}
        krs={};mss={}
        for r in c.execute('SELECT * FROM key_results ORDER BY updated_at,rowid'):krs.setdefault(r['goal_id'],[]).append(kr_view(r,counts))
        for r in c.execute('SELECT * FROM milestones ORDER BY due,rowid'):mss.setdefault(r['goal_id'],[]).append({k:r[k] for k in ('id','goal_id','project_id','title','due')}|{'done':bool(r['done'])})
    result=[]
    for g in rows:
        k=krs.get(g['id'],[]);m=mss.get(g['id'],[])
        raw=sum(x['_raw'] for x in k)/len(k) if k else (sum(x['done'] for x in m)/len(m) if m else 0.0)
        state,elapsed=health(g['status'],raw,k,m,g['start_date'],g['target_date'],on)
        days_left=(dt.date.fromisoformat(g['target_date'])-on).days if g['target_date'] else None
        result.append({k_:g[k_] for k_ in ('id','title','description','owner','status','start_date','target_date','project_id')}|{'progress':round(raw,4),'health':state,
          'elapsed':None if elapsed is None else round(elapsed,4),'days_left':days_left,'key_results':[{a:b for a,b in x.items() if a!='_raw'} for x in k],'milestones':m,
          'created_at':g['created_at'],'updated_at':g['updated_at']})
    result.sort(key=lambda g:(ORDER[g['status']],g['target_date'] or '9999-99-99',g['title']))
    return result

def get_goal(identifier,on=None):
    return next(g for g in goals(on) if g['id']==identifier)

def exists(c,table,identifier,label):
    if not c.execute('SELECT 1 FROM '+table+' WHERE id=?',(identifier,)).fetchone():raise NotFound(label+' not found')

def save_goal(value,actor='desktop'):
    if not isinstance(value,dict):raise ValueError('Goal must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM goals WHERE id=?',(identifier,)).fetchone()
    v={**(dict(row) if row else {'title':'','description':'','owner':'','status':'Active','start_date':'','target_date':'','project_id':''}),
       **{k:value[k] for k in ('title','description','owner','status','start_date','target_date','project_id') if k in value and value[k] is not None}}
    title=text(v['title'],'Title',300,True);description=text(v['description'],'Description',5000);owner=text(v['owner'],'Owner',200)
    if not isinstance(v['status'],str) or v['status'] not in STATUSES:raise ValueError('Status must be one of '+', '.join(STATUSES))
    start=date_(v['start_date'],'start_date');target=date_(v['target_date'],'target_date');project=text(v['project_id'],'project_id',200)
    if start and target and target<start:raise ValueError('Target date must be on or after the start date')
    stamp=now()
    with engine.connect() as c:
        if project:exists(c,'projects',project,'Project')
        c.execute('''INSERT INTO goals VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,description=excluded.description,owner=excluded.owner,status=excluded.status,
          start_date=excluded.start_date,target_date=excluded.target_date,project_id=excluded.project_id,updated_at=excluded.updated_at''',(identifier,title,description,owner,v['status'],start,target,project,row['created_at'] if row else stamp,stamp))
    if v['status']=='Achieved' and (not row or row['status']!='Achieved'):work.notify('status','Goal achieved: '+title,'Status set to Achieved','goal',identifier,actor)
    return get_goal(identifier)

def delete_goal(identifier,actor):
    with engine.connect() as c:
        if not c.execute('DELETE FROM goals WHERE id=?',(identifier,)).rowcount:raise NotFound('Goal not found')
        krs=c.execute('DELETE FROM key_results WHERE goal_id=?',(identifier,)).rowcount;ms=c.execute('DELETE FROM milestones WHERE goal_id=?',(identifier,)).rowcount
    return {'deleted':identifier,'key_results_removed':krs,'milestones_removed':ms}

def save_key_result(value):
    if not isinstance(value,dict):raise ValueError('Key result must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM key_results WHERE id=?',(identifier,)).fetchone()
    v={**(dict(row) if row else {'goal_id':'','title':'','kind':'','project_name':'','target':0,'current':0,'unit':'','due':''}),
       **{k:value[k] for k in ('goal_id','title','kind','project_name','target','current','unit','due') if k in value and value[k] is not None}}
    goal_id=text(v['goal_id'],'goal_id',200,True);title=text(v['title'],'Title',300,True)
    if not isinstance(v['kind'],str) or v['kind'] not in KINDS:raise ValueError('Kind must be one of '+', '.join(KINDS))
    project_name=text(v['project_name'],'project_name',200);unit=text(v['unit'],'Unit',50);due=date_(v['due'],'due')
    target=number(v['target'],'target');current=number(v['current'],'current')
    if v['kind']=='tasks' and not project_name:raise ValueError('Tasks key results need a project_name')
    if v['kind']=='manual' and target<=0:raise ValueError('Manual key results need a target above 0')
    with engine.connect() as c:
        exists(c,'goals',goal_id,'Goal')
        c.execute('''INSERT INTO key_results VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET goal_id=excluded.goal_id,title=excluded.title,kind=excluded.kind,project_name=excluded.project_name,
          target=excluded.target,current=excluded.current,unit=excluded.unit,due=excluded.due,updated_at=excluded.updated_at''',(identifier,goal_id,title,v['kind'],project_name,target,current,unit,due,now()))
    return next(k for k in get_goal(goal_id)['key_results'] if k['id']==identifier)

def save_milestone(value,actor='desktop'):
    if not isinstance(value,dict):raise ValueError('Milestone must be an object')
    identifier=ident(value.get('id'))
    with engine.connect() as c:row=c.execute('SELECT * FROM milestones WHERE id=?',(identifier,)).fetchone()
    v={**(dict(row) if row else {'goal_id':'','project_id':'','title':'','due':'','done':False}),**{k:value[k] for k in ('goal_id','project_id','title','due','done') if k in value and value[k] is not None}}
    goal_id=text(v['goal_id'],'goal_id',200);project=text(v['project_id'],'project_id',200);title=text(v['title'],'Title',300,True);due=date_(v['due'],'due',True)
    if type(v['done']) not in (bool,int) or v['done'] not in (0,1):raise ValueError('done must be true or false')
    done=bool(v['done'])
    with engine.connect() as c:
        if goal_id:exists(c,'goals',goal_id,'Goal')
        if project:exists(c,'projects',project,'Project')
        c.execute('''INSERT INTO milestones VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET goal_id=excluded.goal_id,project_id=excluded.project_id,title=excluded.title,due=excluded.due,done=excluded.done,updated_at=excluded.updated_at''',
          (identifier,goal_id,project,title,due,int(done),now()))
    if bool(row['done'] if row else False)!=done:audit(f"milestone:{'done' if done else 'reopen'}:{identifier}",actor)
    return {'id':identifier,'goal_id':goal_id,'project_id':project,'title':title,'due':due,'done':done}

def delete_row(table,identifier,label):
    assert table in {'key_results','milestones'}
    with engine.connect() as c:
        if not c.execute('DELETE FROM '+table+' WHERE id=?',(identifier,)).rowcount:raise NotFound(label+' not found')
    return {'deleted':identifier}

def deadlines(on=None,limit=60):
    on=on or today();items=[]
    def add(kind,ref,title,due,status,goal_id='',project=''):
        try:days=(dt.date.fromisoformat(str(due)[:10])-on).days
        except ValueError:return
        items.append({'type':kind,'id':f'{kind}:{ref}','title':title,'due':str(due)[:10],'days':days,'status':status,'ref_id':ref,'goal_id':goal_id,'project':project})
    with engine.connect() as c:
        names={r['id']:r['name'] for r in c.execute('SELECT id,name FROM projects')}
        for t in c.execute("SELECT id,title,project,status,due FROM tasks WHERE due!='' AND status!='Done'"):add('task',t['id'],t['title'],t['due'],t['status'],'',t['project'])
        for m in c.execute('SELECT * FROM milestones WHERE done=0'):add('milestone',m['id'],m['title'],m['due'],'Open',m['goal_id'],names.get(m['project_id'],''))
        for p in c.execute("SELECT id,name,status,target_date FROM projects WHERE target_date!='' AND status!='Done'"):add('project',p['id'],p['name'],p['target_date'],p['status'],'',p['name'])
    for g in goals(on):
        if g['status']=='Active' and g['target_date']:add('goal',g['id'],g['title'],g['target_date'],g['status'],g['id'],names.get(g['project_id'],''))
        for k in g['key_results']:
            if k['due'] and k['progress']<1:add('kr',k['id'],k['title'],k['due'],'Open',g['id'],k['project_name'])
    items=sorted(items,key=lambda i:(i['days'],i['type'],i['title']))[:limit]
    return {'overdue':[i for i in items if i['days']<0],'this_week':[i for i in items if 0<=i['days']<=7],'later':[i for i in items if i['days']>7]}

def open_milestones_overdue(on=None):
    on=on or today()
    with engine.connect() as c:return [dict(r) for r in c.execute("SELECT id,title,due FROM milestones WHERE done=0 AND due<? ORDER BY due",(on.isoformat(),))]
