"""Local, opt-in foreground application timing. No titles, URLs, keys or screenshots."""
import datetime as dt
import time
import uuid
from zoneinfo import ZoneInfo
import engine
import settings

def database():
    c=engine.connect()
    c.execute('CREATE TABLE IF NOT EXISTS app_activity(id TEXT PRIMARY KEY,at REAL NOT NULL,app TEXT NOT NULL,bundle TEXT NOT NULL,seconds REAL NOT NULL)')
    c.commit();return c

def record(value):
    if not settings.get().get('activity_enabled'):return {'recorded':False}
    name=str(value.get('app','')).strip()[:150];bundle=str(value.get('bundle',''))[:200]
    seconds=float(value.get('seconds',0))
    if not name or not 0<seconds<=30:raise ValueError('Invalid activity sample')
    with database() as c:
        c.execute('INSERT INTO app_activity VALUES(?,?,?,?,?)',(str(uuid.uuid4()),time.time(),name,bundle,seconds))
        c.execute('DELETE FROM app_activity WHERE at<?',(time.time()-30*86400,))
    return {'recorded':True}

def summary(days=7):
    days=max(1,min(30,int(days)));zone=ZoneInfo(settings.get().get('timezone','Asia/Kolkata'));today=dt.datetime.now(zone).date()
    start=dt.datetime.combine(today-dt.timedelta(days=days-1),dt.time(),zone).timestamp()
    with database() as c:rows=c.execute('SELECT at,app,bundle,seconds FROM app_activity WHERE at>=? ORDER BY at',(start,)).fetchall()
    apps={};daily={str(today-dt.timedelta(days=i)):0 for i in reversed(range(days))}
    for r in rows:
        day=str(dt.datetime.fromtimestamp(r['at'],zone).date());daily[day]=daily.get(day,0)+r['seconds']
        key=r['bundle'] or r['app'];entry=apps.setdefault(key,{'name':r['app'],'bundle':r['bundle'],'seconds':0,'browser':any(x in key.lower() for x in ['chrome','safari','firefox','edge','brave','arc','browser'])});entry['seconds']+=r['seconds']
    return {'enabled':settings.get().get('activity_enabled',False),'apps':sorted(apps.values(),key=lambda a:a['seconds'],reverse=True),'daily':[{'date':k,'seconds':v} for k,v in daily.items()],'total_seconds':sum(daily.values()),'sample_count':len(rows),'timezone':str(zone),'coverage':'Estimated foreground time sampled every 15 seconds while GOTEET runs. Idle ≥60 seconds and sleep gaps excluded. Browser totals are app-level only. No tab titles, URLs, keystrokes or screenshots collected. History retained for 30 days.'}

def clear():
    with database() as c:c.execute('DELETE FROM app_activity')
    return {'cleared':True}
