"""Read-only macOS Calendar and Reminders snapshot via JXA. Nothing is created, changed or deleted in either app."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from collector import DATA, IST, now
import settings

# Dates arrive as local-time strings with offset so all-day events keep their calendar day on any Mac timezone.
JXA_HELPERS='''
function p2(n){return String(n).padStart(2,'0')}
function loc(d){
  if(!d)return '';
  const off=-d.getTimezoneOffset(),a=Math.abs(off);
  return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate())+'T'+p2(d.getHours())+':'+p2(d.getMinutes())+':'+p2(d.getSeconds())+(off>=0?'+':'-')+p2(Math.floor(a/60))+':'+p2(a%60);
}
'''
CALENDAR_NAMES_JXA='''function run(){ return JSON.stringify(Application('Calendar').calendars.name()); }'''
EVENTS_JXA=JXA_HELPERS+'''
function run(argv){
  const start=new Date(argv[0]),end=new Date(argv[1]);
  const c=Application('Calendar').calendars.byName(argv[2]);
  const evs=c.events.whose({_and:[{startDate:{_lessThan:end}},{endDate:{_greaterThan:start}}]});
  const uid=evs.uid(),title=evs.summary(),st=evs.startDate(),en=evs.endDate(),allday=evs.alldayEvent(),where=evs.location();
  const events=[];
  for(let i=0;i<uid.length;i++)events.push({uid:uid[i]||'',title:title[i]||'',start:loc(st[i]),end:loc(en[i]),all_day:!!allday[i],calendar:argv[2],location:where[i]||''});
  return JSON.stringify({events:events});
}
'''
LISTS_JXA='''function run(){ return JSON.stringify(Application('Reminders').lists.name()); }'''
REMINDERS_JXA=JXA_HELPERS+'''
function run(argv){
  const start=new Date(argv[0]),end=new Date(argv[1]);
  const l=Application('Reminders').lists.byName(argv[2]);
  const rs=l.reminders.whose({_and:[{dueDate:{_greaterThan:start}},{dueDate:{_lessThan:end}}]});
  const id=rs.id(),title=rs.name(),body=rs.body(),due=rs.dueDate(),done=rs.completed(),pr=rs.priority();
  const reminders=[];
  for(let i=0;i<id.length;i++)reminders.push({id:id[i]||'',title:title[i]||'',body:body[i]||'',due:loc(due[i]),completed:!!done[i],list:argv[2],priority:pr[i]||0});
  return JSON.stringify({reminders:reminders});
}
'''

def _message(error):
    if isinstance(error,subprocess.TimeoutExpired):return f'timed out after {error.timeout:.0f} s; macOS may be waiting for permission or the collection is very large'
    return (str(error).strip() or error.__class__.__name__)[:300]

def _jxa(script,args):
    # Window and names go in as argv, never interpolated into the script text.
    result=subprocess.run(['osascript','-l','JavaScript','-e',script,*args],capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError((result.stderr or result.stdout).strip() or 'osascript failed')
    return json.loads(result.stdout)

def _moment(value,all_day=False):
    if not value:return ''
    if all_day:return dt.datetime.combine(dt.date.fromisoformat(value[:10]),dt.time(),IST).isoformat(timespec='seconds')
    return dt.datetime.fromisoformat(value).astimezone(IST).isoformat(timespec='seconds')

def fetch(days_back=7,days_ahead=30):
    settings.require('system_calendar_enabled')
    if sys.platform!='darwin':
        return {'captured_at':now(),'events':[],'reminders':[],'coverage':'Unsupported on this OS','errors':[],'ok_events':False,'ok_reminders':False}
    today=dt.datetime.now(IST).date()
    start=dt.datetime.combine(today-dt.timedelta(days=days_back),dt.time(),IST)
    end=dt.datetime.combine(today+dt.timedelta(days=days_ahead+1),dt.time(),IST)
    window=[start.isoformat(),end.isoformat()]
    errors=[];events=[];reminders=[];seen=set()
    # One osascript call per calendar and per list: a slow collection times out alone and the rest still arrive.
    names=[];ok_events=ok_reminders=False;read_cal=read_lists=0
    try:
        names=_jxa(CALENDAR_NAMES_JXA,[]);ok_events=True
    except Exception as error:errors.append('Calendar: '+_message(error))
    for name in names:
        try:
            for e in _jxa(EVENTS_JXA,[*window,name])['events']:
                if not e['uid'] or e['uid'] in seen:continue
                seen.add(e['uid'])
                events.append({'uid':e['uid'],'title':e['title'],'start':_moment(e['start'],e['all_day']),'end':_moment(e['end'],e['all_day']),'all_day':e['all_day'],'calendar':name,'location':e['location']})
            read_cal+=1
        except Exception as error:errors.append(f'Calendar {name}: {_message(error)}')
    ok_events=ok_events and (read_cal>0 or not names)
    lists=[]
    try:
        lists=_jxa(LISTS_JXA,[]);ok_reminders=True
    except Exception as error:errors.append('Reminders: '+_message(error))
    for name in lists:
        try:
            for r in _jxa(REMINDERS_JXA,[*window,name])['reminders']:
                if not r['id'] or not r['due']:continue
                reminders.append({'id':r['id'],'title':r['title'],'body':r['body'],'due':_moment(r['due']),'completed':r['completed'],'list':name,'priority':int(r['priority'])})
            read_lists+=1
        except Exception as error:errors.append(f'Reminders {name}: {_message(error)}')
    ok_reminders=ok_reminders and (read_lists>0 or not lists)
    parts=[f"Calendar: {len(events)} events across {read_cal} of {len(names)} calendars, {start:%d %b} to {end-dt.timedelta(days=1):%d %b %Y}" if ok_events else 'Calendar: not read',
      f"Reminders: {len(reminders)} dated reminders across {read_lists} of {len(lists)} lists" if ok_reminders else 'Reminders: not read']
    snapshot={'captured_at':now(),'events':events,'reminders':reminders,'coverage':'; '.join(parts)+'. Read-only: Calendar and Reminders were not modified.','errors':errors,'ok_events':ok_events,'ok_reminders':ok_reminders}
    _store(snapshot)
    return snapshot

def load():
    path=DATA/'system_calendar.json'
    return json.loads(path.read_text()) if path.exists() else {}

def _store(value):
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temporary=tempfile.mkstemp(dir=DATA,prefix='system-calendar-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w') as handle:handle.write(json.dumps(value,indent=2))
        os.chmod(temporary,0o600);os.replace(temporary,DATA/'system_calendar.json')
    except BaseException:
        if os.path.exists(temporary):os.unlink(temporary)
        raise
