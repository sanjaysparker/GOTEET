"""Domain mutations shared by the human API and approved agent steps."""
import datetime as dt
import uuid
import engine
from collector import now

PROJECT_FIELDS=('name','description','status','start_date','target_date')

def save_project(value):
    """Create, or merge only the supplied keys over the stored project."""
    if not isinstance(value,dict):raise ValueError('Project must be an object')
    identifier=value.get('id') or str(uuid.uuid4())
    if not isinstance(identifier,str) or len(identifier)>200:raise ValueError('Invalid project id')
    with engine.connect() as c:
        row=c.execute('SELECT * FROM projects WHERE id=?',(identifier,)).fetchone()
        base=dict(row) if row else {'name':'','description':'','status':'Planned','start_date':'','target_date':''}
        v={**base,**{k:value[k] for k in PROJECT_FIELDS if k in value and value[k] is not None}}
        for k in PROJECT_FIELDS:
            if not isinstance(v[k],str):raise ValueError('Project '+k.replace('_',' ')+' must be text')
        name=v['name'].strip()
        if not name or len(name)>300:raise ValueError('Enter a project name of 1–300 characters')
        if v['status'] not in {'Planned','Active','At risk','Paused','Done'}:raise ValueError('Invalid project status')
        start=v['start_date'];target=v['target_date']
        for date in [start,target]:
            if date:
                try:dt.date.fromisoformat(date)
                except ValueError:raise ValueError('Project dates must use YYYY-MM-DD')
        if start and target and start>target:raise ValueError('Target date must be on or after the start date')
        record={'id':identifier,'name':name,'description':v['description'][:10000],'status':v['status'],'start_date':start,'target_date':target,'updated_at':now()}
        c.execute('''INSERT INTO projects VALUES(:id,:name,:description,:status,:start_date,:target_date,:updated_at)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,status=excluded.status,start_date=excluded.start_date,target_date=excluded.target_date,updated_at=excluded.updated_at''',record)
    return record

def save_concept(value):
    title=str(value.get('title','')).strip()
    if not title or len(title)>500:raise ValueError('Enter a concept title of 1–500 characters')
    status=value.get('status','Idea')
    if status not in {'Idea','Exploring','Approved','Parked'}:raise ValueError('Invalid concept status')
    record={'id':value.get('id') or str(uuid.uuid4()),'title':title,'body':str(value.get('body',''))[:50000],
      'project':str(value.get('project','General'))[:200],'status':status,'updated_at':now()}
    with engine.connect() as c:c.execute('''INSERT INTO concepts VALUES(:id,:title,:body,:project,:status,:updated_at)
      ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,project=excluded.project,status=excluded.status,updated_at=excluded.updated_at''',record)
    return record
