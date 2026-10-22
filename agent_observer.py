"""Passive, opt-in observer of the owner's own machine: Claude Code and Codex session logs, running agents and git.

Metadata only. Source logs are opened read-only and streamed; nothing but aggregated numbers and mapped project names is persisted or returned.
Never stored: message text (except an optional redacted 100-char title), tool inputs/outputs, commands, file names, paths, tokens.
Everything is gated by settings.agent_observer_enabled; when it is off no file under ~/.claude or ~/.codex is touched.
"""
import bisect
import concurrent.futures
import datetime as dt
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
import engine
import settings
from collector import IST, now

CLAUDE_ROOT=Path.home()/'.claude'/'projects'
CODEX_ROOTS=(Path.home()/'.codex'/'sessions',Path.home()/'.codex'/'archived_sessions')
HOME=Path.home()
LOOKBACK_DAYS=14;RETAIN_DAYS=60;BUDGET_S=20;PARSE_SHARE=0.6;IDLE_S=300;BIG_LINE=512*1024;SCAN_EVERY=300;FRESH_S=1800;GIT_TIMEOUT=10
SCHEMA=4
LOG=logging.getLogger('goteet.observer')
LOCK=threading.Lock()
OFF='Off. Enable in Settings → Permissions.'
EDIT_TOOLS={'Edit','Write','NotebookEdit','MultiEdit'}
NOISE=('<system-reminder>','<command-name>','<command-message>','<local-command','<task-notification','Caveat:','[Request interrupted')
ROOTS={}  # session id -> git roots seen at parse time; RAM only, never persisted
STATE_RUN={'thread':None,'last':0.0}

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS activity_sessions(id TEXT PRIMARY KEY,tool TEXT NOT NULL,mtime REAL NOT NULL,size INTEGER NOT NULL,sig TEXT NOT NULL,started REAL NOT NULL,ended REAL NOT NULL,active_minutes REAL NOT NULL,turns INTEGER NOT NULL,tool_calls INTEGER NOT NULL,tool_errors INTEGER NOT NULL,files_touched INTEGER NOT NULL,repeated_failures INTEGER NOT NULL,branch TEXT NOT NULL,title TEXT NOT NULL,projects TEXT NOT NULL,blocks TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS activity_sessions_ended ON activity_sessions(ended);
      CREATE TABLE IF NOT EXISTS activity_days(date TEXT NOT NULL,project TEXT NOT NULL,tool TEXT NOT NULL,minutes REAL NOT NULL,sessions INTEGER NOT NULL,commits INTEGER NOT NULL,PRIMARY KEY(date,project,tool));
      CREATE TABLE IF NOT EXISTS activity_project_map(pattern TEXT NOT NULL,project TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS activity_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')

# REDACTION AND HASHING

SECRET=[re.compile(p) for p in (r'sk-[A-Za-z0-9_\-]{6,}',r'gh[pousr]_[A-Za-z0-9]{6,}',r'xox[a-z]?-[A-Za-z0-9\-]{6,}',r'AKIA[0-9A-Z]{8,}',r'[A-Za-z0-9+/_\-]{24,}={0,2}',r'(?:~|/)[\w.\-]+(?:/[\w.\-]+)+')]
KEYWORD=re.compile(r'(?i)\b(password|passwd|token|secret)\b.*')

def redact(value,limit=100):
    value=re.sub(r'\s+',' ',str(value)[:600]).strip()
    for pattern in SECRET:value=pattern.sub('…',value)
    return KEYWORD.sub(lambda m:m.group(1)+' …',value)[:limit].strip()

def h(value):return hashlib.blake2b(json.dumps(value,sort_keys=True,default=str).encode(),digest_size=8).hexdigest()
def norm(value):return re.sub(r'[-_\s]','',str(value)).lower()
def day_of(t):return dt.datetime.fromtimestamp(t,IST).date().isoformat()

def ts(value):
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (AttributeError,ValueError):return None

# PROJECT MAPPING: override > saved project > repo root > scratch/home > last folder

class Mapper:
    def __init__(self,overrides,saved,home):
        self.overrides=[(p.rstrip('/') or '/',n) for p,n in overrides];self.saved={norm(n):n for n in saved};self.home=str(home);self.memo={}
    def root(self,cwd):
        path=Path(cwd)
        for q in (path,*path.parents):
            if str(q) in (self.home,'/'):return ''
            marker=q/'.git'
            if marker.is_dir():return q.name
            if marker.is_file():
                try:link=marker.read_text(errors='replace').split('gitdir:',1)[1].strip()
                except (OSError,IndexError):return q.name
                # A LINKED WORKTREE BELONGS TO ITS MAIN CHECKOUT, NOT ITS OWN FOLDER NAME
                return Path(link.split('/.git/worktrees/')[0]).name if '/.git/worktrees/' in link else q.name
        return ''
    def __call__(self,cwd):
        if cwd not in self.memo:self.memo[cwd]=self.resolve(cwd)
        return self.memo[cwd]
    def resolve(self,cwd):
        if not cwd:return 'Unknown'
        clean=cwd.rstrip('/') or '/'
        for pattern,name in self.overrides:
            if clean==pattern or clean.startswith(pattern+'/') or pattern in clean:return name
        root=self.root(clean);parts=[x for x in clean.split('/') if x]
        for candidate in [root,*reversed(parts)]:
            if candidate and norm(candidate) in self.saved:return self.saved[norm(candidate)]
        if root:return root
        if 'Application Support/Claude' in clean or any(x=='scratch' or x.startswith('scratch-') for x in parts):return 'Scratch'
        if clean==self.home:return 'Home'
        return parts[-1] if parts else 'Unknown'

# STREAMING PARSERS

def lines(path):
    with open(path,'rb') as handle:
        yield from handle

class Acc:
    """Per-file accumulator. Only counters, hashes and per-project time blocks leave it."""
    def __init__(self,mapper,titles):
        self.mapper=mapper;self.titles=titles;self.cwd='';self.last=None;self.first=None;self.end=None
        self.blocks={};self.seen=set();self.turns=self.calls=self.errors=0;self.files=set();self.fail=None;self.streak=self.worst=0
        self.branch='';self.title='';self.custom='';self.fallback=0;self.roots=set()
    def event(self,t,cwd=''):
        if cwd:
            if cwd!=self.cwd:self.roots.add(cwd)
            self.cwd=cwd
        project=self.mapper(self.cwd);self.seen.add(project)
        self.first=t if self.first is None else min(self.first,t);self.end=t if self.end is None else max(self.end,t)
        if self.last is not None and 0<t-self.last<=IDLE_S:
            run=self.blocks.setdefault(project,[])
            if run and abs(run[-1][1]-self.last)<1e-6:run[-1][1]=t
            else:run.append([self.last,t])
        if self.last is None or t>self.last:self.last=t
    def turn(self,text):
        self.turns+=1
        if self.titles and not self.title:self.title=text
    def result(self,error,key):
        if error:
            self.errors+=1;self.streak=self.streak+1 if key==self.fail else 1;self.fail=key;self.worst=max(self.worst,self.streak)
        else:self.fail=None;self.streak=0

def tail_field(raw,name):
    found=re.findall(rb'"'+name+rb'":"([^"]*)"',raw[-1500:])
    return found[-1].decode('utf8','replace') if found else ''

def claude_big(raw,acc):
    """HUGE LINES (e.g. API request blobs) ARE NOT PARSED: TIME AND COUNTS COME FROM CHEAP BYTE SCANS."""
    # USER LINES CARRY THEIR TYPE BEFORE THE MESSAGE, ASSISTANT LINES AFTER IT
    found=re.search(rb'"type":"(user|assistant|system)"',raw[:400]) or (re.findall(rb'"type":"(user|assistant|system)"',raw[-1500:]) or [None])[-1]
    if not found:return
    t=ts(tail_field(raw,b'timestamp'))
    if t is None:return
    acc.event(t,tail_field(raw,b'cwd'))
    acc.calls+=raw.count(b'"type":"tool_use"');acc.errors+=raw.count(b'"is_error":true')

def real_prompt(d,content):
    """The text of a genuine human prompt, or None for tool results, hooks, reminders and notifications."""
    if d.get('isMeta'):return None
    origin=d.get('origin')
    if isinstance(origin,dict) and origin.get('kind') not in (None,'human'):return None
    if isinstance(content,str):text=content
    elif isinstance(content,list):
        parts=[x.get('text','') for x in content if isinstance(x,dict) and x.get('type')=='text']
        if not parts and not any(isinstance(x,dict) and x.get('type')=='image' for x in content):return None
        text=' '.join(parts)
    else:return None
    return None if text.lstrip().startswith(NOISE) else text

def parse_claude(path,acc):
    uses={}
    for raw in lines(path):
        if len(raw)>BIG_LINE:claude_big(raw,acc);continue
        try:d=json.loads(raw)
        except ValueError:continue
        kind=d.get('type')
        if kind=='custom-title' and isinstance(d.get('customTitle'),str):acc.custom=d['customTitle']
        if kind not in ('user','assistant','system'):continue
        t=ts(d.get('timestamp'))
        if t is None:continue
        acc.event(t,d.get('cwd') or '')
        if d.get('gitBranch'):acc.branch=str(d['gitBranch'])[:100]
        message=d.get('message');content=message.get('content') if isinstance(message,dict) else None
        if kind=='assistant' and isinstance(content,list):
            for item in content:
                if not isinstance(item,dict) or item.get('type')!='tool_use':continue
                name=str(item.get('name',''));inputs=item.get('input');uses[item.get('id')]=(name,h(inputs));acc.calls+=1
                if name in EDIT_TOOLS and isinstance(inputs,dict):
                    target=inputs.get('file_path') or inputs.get('notebook_path')
                    if target:acc.files.add(h(target))
        elif kind=='user':
            if isinstance(content,list):
                for item in content:
                    if isinstance(item,dict) and item.get('type')=='tool_result':acc.result(bool(item.get('is_error')),uses.get(item.get('tool_use_id'),('?','')))
            if not d.get('isSidechain'):
                text=real_prompt(d,content)
                if text is not None:acc.turn(text)
    if acc.custom and acc.titles:acc.title=acc.custom

def codex_big(raw,acc):
    head=raw[:20000];found=re.search(rb'"timestamp":"([^"]+)"',head[:300])
    t=ts(found.group(1).decode()) if found else None
    if t is None:return
    acc.event(t)
    if b'"type":"CommandExecution"' in head[:2500]:
        acc.calls+=1
        if b'"status":"failed"' in head:acc.errors+=1

def parse_codex(path,acc):
    sub=False;item_turns=legacy_turns=item_tools=0;first_text=''
    for raw in lines(path):
        if len(raw)>BIG_LINE:codex_big(raw,acc);continue
        try:d=json.loads(raw)
        except ValueError:continue
        t=ts(d.get('timestamp'))
        payload=d.get('payload');payload=payload if isinstance(payload,dict) else {}
        kind=d.get('type');sub_kind=payload.get('type');cwd=''
        if kind=='session_meta':
            cwd=payload.get('cwd') or '';source=payload.get('source');sub=isinstance(source,dict) and 'subagent' in source
            git=payload.get('git');acc.branch=str(git.get('branch',''))[:100] if isinstance(git,dict) else acc.branch
        elif kind=='turn_context':cwd=payload.get('cwd') or ''
        if t is None:continue
        acc.event(t,cwd if isinstance(cwd,str) else '')
        if kind=='response_item' and sub_kind in ('function_call','custom_tool_call'):acc.fallback+=1
        elif kind=='event_msg' and sub_kind=='user_message':
            legacy_turns+=1;first_text=first_text or str(payload.get('message',''))
        elif kind=='event_msg' and sub_kind=='item_completed':
            item=payload.get('item');item=item if isinstance(item,dict) else {};name=item.get('type')
            if name=='UserMessage':
                item_turns+=1
                if not first_text:
                    parts=item.get('content');first_text=' '.join(str(x.get('text','')) for x in parts if isinstance(x,dict)) if isinstance(parts,list) else ''
            elif name=='CommandExecution':
                item_tools+=1;acc.calls+=1;acc.result(item.get('status')=='failed' and item.get('exit_code') not in (130,143),('cmd',h(item.get('command'))))
            elif name=='FileChange':
                item_tools+=1;acc.calls+=1;changes=item.get('changes');changes=changes if isinstance(changes,dict) else {}
                for target in changes:acc.files.add(h(target))
                acc.result(item.get('status')=='failed',('file',h(sorted(changes))))
            elif name=='McpToolCall':
                result=item.get('result');failed=item.get('status')=='failed' or (isinstance(result,dict) and result.get('isError') is True)
                item_tools+=1;acc.calls+=1;acc.result(failed,('mcp',item.get('server'),item.get('tool'),h(item.get('arguments'))))
    # OLDER ROLLOUTS HAVE NO ITEM EVENTS: FALL BACK TO RAW CALL COUNTS (ERRORS UNAVAILABLE, REPORTED AS 0)
    if not item_tools:acc.calls=max(acc.calls,acc.fallback)
    acc.turns=0 if sub else (item_turns or legacy_turns)
    if acc.titles and not sub:acc.title=first_text

def record(acc,tool,path,stat,sig):
    minutes={p:sum(e-s for s,e in b)/60 for p,b in acc.blocks.items()}
    return {'id':tool+':'+hashlib.sha1(str(path).encode()).hexdigest()[:16],'tool':tool,'mtime':stat.st_mtime,'size':stat.st_size,'sig':sig,
      'started':acc.first or 0,'ended':acc.end or 0,'active_minutes':round(sum(minutes.values()),3),'turns':acc.turns,'tool_calls':acc.calls,'tool_errors':acc.errors,
      'files_touched':len(acc.files),'repeated_failures':acc.worst,'branch':acc.branch,'title':redact(acc.title) if acc.titles else '',
      'projects':json.dumps(sorted(acc.seen)),'blocks':json.dumps({p:[[round(s,1),round(e,1)] for s,e in b] for p,b in acc.blocks.items()})}

def discover(since):
    found=[];skipped=0
    def add(tool,path):
        try:stat=path.stat()
        except OSError:return
        if stat.st_mtime>=since:found.append((tool,path,stat))
    if CLAUDE_ROOT.is_dir():
        for path in CLAUDE_ROOT.glob('*/*.jsonl'):add('claude',path)
    for root in CODEX_ROOTS:
        if root.is_dir():
            for path in root.rglob('*.jsonl'):add('codex',path)
            for path in root.rglob('*.jsonl.zst'):
                try:skipped+=path.stat().st_mtime>=since
                except OSError:pass
    found.sort(key=lambda x:-x[2].st_mtime)
    return found,skipped

# RUNNING AGENTS

AGENT_BINARIES={'claude':'claude','codex':'codex','aider':'aider','cursor-agent':'cursor-agent','gemini':'gemini'}
SCRIPT_HINTS=(('claude','claude-code'),('claude','@anthropic-ai/claude'),('codex','/codex'),('aider','aider'),('gemini','gemini-cli'),('gemini','@google/gemini'),('cursor-agent','cursor-agent'))

def classify(name,exe,args):
    base=os.path.basename(exe or '') or name or ''
    if base in AGENT_BINARIES:return AGENT_BINARIES[base]
    if base in ('node','bun','deno') or base.startswith('python'):
        script=' '.join(args[1:4]).lower()
        for tool,hint in SCRIPT_HINTS:
            if hint in script:return tool
    return ''

def running(mapper):
    """Agent processes (tool, pid, project, start, CPU) and an MCP server count. Command lines are inspected in memory only."""
    import psutil
    out=[];mcp=0;me=os.getpid()
    for proc in psutil.process_iter(['pid','name','exe','cmdline','create_time','cpu_times','cwd']):
        try:
            info=proc.info;args=info.get('cmdline') or [];tool=classify(info.get('name'),info.get('exe'),args)
            if tool and info['pid']!=me:
                cpu=info.get('cpu_times');cwd=info.get('cwd') or ''
                out.append({'tool':tool,'pid':info['pid'],'project':mapper(cwd) if cwd not in ('','/') else '','cwd':'','started':dt.datetime.fromtimestamp(info['create_time'],IST).isoformat(),'cpu_seconds':round((cpu.user+cpu.system) if cpu else 0,1)})
            elif info['pid']!=me and (info.get('name') or '').lower().startswith(('node','bun','deno','npx','uv','python')) and any('mcp' in a.lower() for a in args[1:5]):mcp+=1
        except (psutil.Error,OSError,KeyError,TypeError,AttributeError):continue
    return sorted(out,key=lambda x:(x['tool'],x['pid'])),mcp

# GIT (READ ONLY: log, rev-parse, status; no fetch, no writes; optional locks off)

def git(repo,*args):
    try:
        done=subprocess.run(['git','-C',repo,*args],capture_output=True,text=True,timeout=GIT_TIMEOUT,env={**os.environ,'GIT_OPTIONAL_LOCKS':'0','GIT_TERMINAL_PROMPT':'0'})
    except (subprocess.TimeoutExpired,OSError):return None
    return done.stdout if done.returncode==0 else None

def classify_subject(subject):
    """Subjects are used only to classify; they are discarded immediately."""
    if re.match(r'(?i)revert\b',subject):return 'revert'
    if re.match(r'(?i)(fix|bugfix|hotfix)(\([^)]*\))?!?(:|\s)',subject):return 'fix'
    if re.match(r'(?i)feat(ure)?(\([^)]*\))?!?:',subject):return 'feat'
    return 'other'

def repo_facts(path,since,clock):
    email=(git(path,'config','user.email') or '').strip()
    log=git(path,'log','--all','--no-merges','--since='+since,'--format=%H%x09%at%x09%s',*(['--author='+email] if email else []))
    if log is None:return None
    commits=[]
    for row in log.splitlines():
        parts=row.split('\t',2)
        if len(parts)==3 and parts[1].isdigit():commits.append((parts[0],int(parts[1]),classify_subject(parts[2])))
    unpushed=[]
    if git(path,'rev-parse','--abbrev-ref','@{u}') is not None:
        unpushed=[int(x) for x in (git(path,'log','@{u}..HEAD','--format=%at') or '').split() if x.isdigit()]
    oldest=None;dirty=0
    status=git(path,'status','--porcelain','-z','--untracked-files=no')
    if status:
        for entry in status.split('\0')[:300]:
            if len(entry)>3:
                dirty+=1
                try:m=os.stat(os.path.join(path,entry[3:])).st_mtime
                except OSError:continue
                oldest=m if oldest is None else min(oldest,m)
    return {'commits':commits,'unpushed':len(unpushed),'unpushed_age_days':round((clock.timestamp()-min(unpushed))/86400,2) if unpushed else 0.0,
      'dirty_files':dirty,'dirty_age_days':round((clock.timestamp()-oldest)/86400,2) if oldest else 0.0}

def inventory_repos(since_day):
    out=[]
    for r in engine.read_json('inventory.json').get('local',{}).get('repos',[]):
        try:last=str(r.get('last_commit','')).split()[1]
        except IndexError:last=''
        if r.get('path') and os.path.isdir(r['path']) and (r.get('tracked_changes') or last>=since_day):out.append(r['path'])
    return out

def gather_git(paths,mapper,since_dt,clock,deadline):
    """One facts dict per mapped project; commits deduplicated by SHA across worktrees and forks."""
    since=since_dt.isoformat();seen=set();per={};errors=[];done=0;repos=sorted(set(paths))
    def work(path):
        if time.monotonic()>deadline:return path,'late'
        return path,repo_facts(path,since,clock)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(work,repos))
    for path,facts in results:
        if facts=='late':errors.append('git budget exhausted');continue
        if facts is None:continue
        done+=1;project=mapper(path);entry=per.setdefault(project,{'commits':[],'dirty_age_days':0.0,'dirty_files':0,'unpushed':0,'unpushed_age_days':0.0,'repos':0})
        entry['repos']+=1
        for sha,t,cls in facts['commits']:
            if sha not in seen:seen.add(sha);entry['commits'].append((t,cls))
        entry['dirty_files']+=facts['dirty_files'];entry['dirty_age_days']=max(entry['dirty_age_days'],facts['dirty_age_days'])
        entry['unpushed']+=facts['unpushed'];entry['unpushed_age_days']=max(entry['unpushed_age_days'],facts['unpushed_age_days'])
    return per,done,len(repos),sorted(set(errors))

def ci_facts(mapper):
    """Latest default-branch CI conclusion and failure days per project, from the collector's GitHub snapshot."""
    inventory=engine.read_json('inventory.json');local={r.get('name'):r.get('path') for r in inventory.get('local',{}).get('repos',[]) if r.get('path')};out={}
    for r in inventory.get('github',[]):
        name=str(r.get('full_name','')).split('/')[-1];runs=r.get('runs') or []
        if not name or not runs:continue
        project=mapper(local[name]) if name in local else name
        entry=out.setdefault(project,{'latest':'','failure_days':[]})
        entry['latest']='failure' if entry['latest']=='failure' or runs[0].get('conclusion')=='failure' else str(runs[0].get('conclusion') or '')
        entry['failure_days']=sorted(set(entry['failure_days'])|{str(x.get('created_at',''))[:10] for x in runs if x.get('conclusion')=='failure'})
    return out

# AGGREGATION

def merge(intervals,gap=1.0):
    out=[]
    for s,e in sorted(intervals):
        if out and s<=out[-1][1]+gap:out[-1][1]=max(out[-1][1],e)
        else:out.append([s,e])
    return out

def split_days(s,e):
    while s<e:
        cursor=dt.datetime.fromtimestamp(s,IST);nxt=(cursor.replace(hour=0,minute=0,second=0,microsecond=0)+dt.timedelta(days=1)).timestamp()
        end=min(e,nxt);yield cursor.date().isoformat(),end-s;s=end

def hours_of(intervals):
    keys=set()
    for s,e in intervals:
        cursor=dt.datetime.fromtimestamp(s,IST).replace(minute=0,second=0,microsecond=0)
        while cursor.timestamp()<=e:keys.add(cursor.strftime('%Y-%m-%dT%H'));cursor+=dt.timedelta(hours=1)
    return keys

def git_blocks(times):
    """Commits closer than 45 minutes form one block worth its span plus 15 minutes: an estimate, not a measurement."""
    out=[];times=sorted(times)
    for t in times:
        if out and t-out[-1][1]<45*60:out[-1][1]=t
        else:out.append([t,t])
    return [(a,b,(b-a)/60+15) for a,b in out]

def build(records,git_data,days):
    """Per-day rows and per-project activity sets from session records and git facts, restricted to the window."""
    window=set(days);per={};sessions={}
    for r in records:
        for project,iv in r['blocks'].items():
            per.setdefault((project,r['tool']),[]).extend(iv)
            for d in {d for s,e in iv for d,_ in split_days(s,e)}&window:
                for tool in (r['tool'],'agent'):sessions.setdefault((d,project,tool),set()).add(r['id'])
    rows={};activity={}
    def row(d,p,t):return rows.setdefault((d,p,t),{'date':d,'project':p,'tool':t,'minutes':0.0,'sessions':0,'commits':0})
    for project in {p for p,_ in per}:
        union=merge([iv for (p,_),v in per.items() if p==project for iv in v])
        for tool,intervals in [(t,merge(v)) for (p,t),v in per.items() if p==project]+[('agent',union)]:
            for s,e in intervals:
                for d,sec in split_days(s,e):
                    if d in window:row(d,project,tool)['minutes']+=sec/60
        activity[project]={'blocks':merge(union,IDLE_S),'days':set()}
    for (d,p,t),ids in sessions.items():row(d,p,t)['sessions']=len(ids)
    for project,facts in git_data.items():
        commits=[c for c in facts['commits'] if day_of(c[0]) in window]
        for t,_ in commits:row(day_of(t),project,'git')['commits']+=1
        for start,_,minutes in git_blocks([c[0] for c in commits]):row(day_of(start),project,'git')['minutes']+=minutes
        entry=activity.setdefault(project,{'blocks':[],'days':set()});entry['commits']=[c[0] for c in commits]
    for project,entry in activity.items():
        entry.setdefault('commits',[])
        entry['blocks']=merge(entry['blocks']+[[t,t] for t in entry['commits']],IDLE_S)
        entry['hours']=hours_of(entry['blocks']);entry['days']={d for s,e in entry['blocks'] for d,_ in split_days(s,e+1)}&window
        entry['last']=max([e for _,e in entry['blocks']],default=0)
    rows={k:v|{'minutes':round(v['minutes'],2)} for k,v in rows.items() if v['minutes']>0 or v['commits']}
    return rows,activity

# SIGNALS

def mistakes(sessions,git_data,ci,last_active,clock):
    """Deterministic rework and risk signals. Each carries counts as evidence and a concrete suggestion; no text from logs is used."""
    out=[];by={}
    def add(kind,severity,project,title,detail,suggestion,evidence):
        out.append({'id':f'{kind}:{project}','severity':severity,'kind':kind,'project':project,'title':title,'detail':detail,'suggestion':suggestion,'evidence':evidence})
    for s in sessions:by.setdefault(s['project'],[]).append(s)
    for project,items in sorted(by.items()):
        bad=[s for s in items if s['tool_calls']>=10 and s['tool_errors']/s['tool_calls']>=0.30]
        if bad:
            worst=max(s['tool_errors']/s['tool_calls'] for s in bad);calls=max(s['tool_calls'] for s in bad)
            add('session_error_rate','critical' if worst>=0.6 and calls>=30 else 'warn',project,f"{project}: {len(bad)} agent session{'s' if len(bad)>1 else ''} with a high tool error rate",f"Worst session: {round(worst*100)}% of tool calls failed.",'Check the environment or give the agent a smaller, better-specified step.',
              [f"{day_of(s['started'])}: {s['tool_errors']} of {s['tool_calls']} tool calls failed" for s in sorted(bad,key=lambda s:-s['started'])[:5]])
        loops=[s for s in items if s['repeated_failures']>=3]
        if loops:
            worst=max(s['repeated_failures'] for s in loops)
            add('repeated_failures','critical' if worst>=6 else 'warn',project,f"{project}: the same tool call failed {worst} times in a row",f"{len(loops)} session(s) retried an identical failing call.",'Stop the retry loop: read the error, change the approach or fix the environment.',
              [f"{day_of(s['started'])}: {s['repeated_failures']} identical failures in a row" for s in sorted(loops,key=lambda s:-s['started'])[:5]])
        thrash={}
        for s in items:
            if s['files_touched']>=10:thrash.setdefault(day_of(s['started']),[]).append(s)
        days=sorted(d for d,v in thrash.items() if len(v)>=3)
        if days:add('file_thrash','warn',project,f"{project}: {len(days)} day(s) of repeated large edit sessions",'Three or more sessions on one day each changed 10+ files.','Settle the design first, then edit once; check for conflicting instructions between agents.',
          [f"{d}: {len(thrash[d])} sessions, {min(s['files_touched'] for s in thrash[d])}+ files each" for d in days[:5]])
        long=[s for s in items if s['active_minutes']>=90 and project in git_data and not any(s['started']<=c[0]<=s['ended']+300 for c in git_data[project]['commits'])]
        if long:add('long_session_no_commit','warn' if max(s['active_minutes'] for s in long)>=180 else 'info',project,f"{project}: {len(long)} long session(s) without a commit",f"Longest {round(max(s['active_minutes'] for s in long))} active minutes with no commit in that window.",'Commit working increments so progress is recoverable and reviewable.',
          [f"{day_of(s['started'])}: {round(s['active_minutes'])} active min, no commit" for s in long[:5]])
    for project,facts in sorted(git_data.items()):
        commits=sorted(facts['commits']);reverts=[c for c in commits if c[1]=='revert']
        if reverts:add('reverts','critical' if len(reverts)>=3 else 'warn',project,f"{project}: {len(reverts)} revert commit{'s' if len(reverts)>1 else ''}",'Reverts mark work that had to be undone.','Review what was shipped without enough checking and add a test or review step.',[f"{day_of(t)}: revert commit" for t,_ in reverts[:5]])
        feats=[t for t,c in commits if c=='feat'];rework={}
        for t,c in commits:
            if c=='fix' and any(0<t-f<=7200 for f in feats):rework.setdefault(day_of(t),[]).append(t)
        days=sorted(d for d,v in rework.items() if len(v)>=2)
        if days:add('rework_after_feature','warn',project,f"{project}: fixes right after features on {len(days)} day(s)",'Two or more fix commits landed within 2 hours of a feature commit on the same day.','Test before committing features; consider smaller, verified commits.',[f"{d}: {len(rework[d])} fix commits within 2 h of a feature" for d in days[:5]])
        if facts['dirty_files'] and facts['dirty_age_days']>3:add('stale_dirty_tree','warn' if facts['dirty_age_days']>=7 else 'info',project,f"{project}: uncommitted changes {facts['dirty_age_days']:.0f} days old",f"{facts['dirty_files']} tracked file(s) modified and not committed.",'Commit, stash or discard them so work is not lost.',[f"oldest uncommitted change {facts['dirty_age_days']:.1f} d old",f"{facts['dirty_files']} modified tracked files"])
        if facts['unpushed']>=3 and facts['unpushed_age_days']>1:add('unpushed_work','warn',project,f"{project}: {facts['unpushed']} unpushed commits",f"Oldest unpushed commit is {facts['unpushed_age_days']:.1f} days old.",'Push so the work is backed up and visible to CI.',[f"{facts['unpushed']} commits ahead of upstream",f"oldest {facts['unpushed_age_days']:.1f} d"])
    for project,c in sorted(ci.items()):
        if c['latest']=='failure' and clock.timestamp()-last_active.get(project,0)<=86400:add('ci_failing_after_work','critical',project,f"{project}: CI is failing after recent work",'Activity in the last 24 h and the latest sampled CI run failed.','Open the failing run, fix or revert before piling on more changes.',['latest sampled CI run: failure','activity within 24 h'])
    order={'critical':0,'warn':1,'info':2}
    return sorted(out,key=lambda m:(order[m['severity']],m['kind'],m['project']))

def correlate(activity,ci,span,days):
    """Pairwise project coupling. score = 0.30*days_shared + 0.20*min(1,hours_overlap/8) + 0.25*min(1,handoffs/6) + 0.15*min(1,same_session/2) + 0.10*min(1,shared_ci/2).
    Kept when score >= 0.15 and at least 2 evidence points (shared days + overlapping hours + handoffs + spanning sessions + shared CI days)."""
    names=sorted(p for p,v in activity.items() if v['days'] and p not in ('Scratch','Home','Unknown'));out=[]
    for i,a in enumerate(names):
        for b in names[i+1:]:
            A,B=activity[a],activity[b];union=A['days']|B['days'];shared=A['days']&B['days']
            jaccard=len(shared)/len(union) if union else 0;hours=len(A['hours']&B['hours'])
            def hand(x,y):
                starts=[s for s,_ in y['blocks']];n=0
                for _,end in x['blocks']:
                    k=bisect.bisect_right(starts,end)
                    if k<len(starts) and starts[k]-end<=1800:n+=1
                return n
            handoffs=hand(A,B)+hand(B,A);same=span.get(tuple(sorted((a,b))),0)
            ci_days=len(set(ci.get(a,{}).get('failure_days',[]))&set(ci.get(b,{}).get('failure_days',[]))&set(days))
            points=len(shared)+hours+handoffs+same+ci_days
            score=0.30*jaccard+0.20*min(1,hours/8)+0.25*min(1,handoffs/6)+0.15*min(1,same/2)+0.10*min(1,ci_days/2)
            if score<0.15 or points<2:continue
            bits=[f"both active on {len(shared)} of {len(union)} days"]
            if handoffs:bits.append(f"{handoffs} handoffs")
            if hours:bits.append(f"{hours} overlapping hours")
            if same:bits.append(f"{same} session{'s' if same>1 else ''} spanning both")
            if ci_days:bits.append(f"CI failed on both on {ci_days} day{'s' if ci_days>1 else ''}")
            out.append({'a':a,'b':b,'score':round(score,2),'days_shared':round(jaccard,2),'hours_overlap':hours,'handoffs':handoffs,'shared_ci_failures':ci_days,'same_session':same,'evidence':'; '.join(bits)})
    return sorted(out,key=lambda c:(-c['score'],c['a'],c['b']))[:30]

def suggestions(totals,corr,sessions,saved,task_update,deadlines,last_active,clock):
    """Derived advice only; nothing here changes a task. totals: project -> {minutes,commits} for the last 7 days."""
    out=[];week=clock.timestamp()-7*86400
    for project,t in sorted(totals.items()):
        if project in saved and (t['minutes']>=60 or t['commits']>=2) and task_update.get(project,0)<week:
            out.append({'id':'unlogged:'+project,'project':project,'title':f"{project}: {t['minutes']/60:.1f} h agent time, {t['commits']} commits, no task updated → update tasks or log work",'detail':'Agent sessions and commits exist for this project but no task in it changed in the last 7 days.','reason':'Session logs and git over the last 7 days against task update times; measured activity, not completion.'})
    for c in corr:
        if c['score']>=0.5:out.append({'id':f"together:{c['a']}|{c['b']}",'project':c['a'],'title':f"{c['a']} and {c['b']} move together (score {c['score']:.2f}): link them or plan together",'detail':c['evidence'],'reason':'Pairwise coupling of active days, overlapping hours, handoffs and shared sessions.'})
    today=clock.astimezone(IST).date();seen=set()
    for d in sorted(deadlines,key=lambda d:d['days']):
        p=d.get('project')
        if not p or p in seen or not 0<=d['days']<=7:continue
        idle=(today-dt.datetime.fromtimestamp(last_active[p],IST).date()).days if last_active.get(p) else None
        if idle is None or idle>=5:
            gap=f'{idle} days' if idle is not None else f'{LOOKBACK_DAYS}+ days';due='today' if d['days']==0 else f"in {d['days']} days"
            seen.add(p);out.append({'id':'idle_deadline:'+p,'project':p,'title':f"No activity on {p} for {gap} but a deadline is {due}",'detail':f"{d['type']} due {d['due']}.",'reason':'No session or commit activity seen against a deadline within 7 days.'})
    long={}
    for s in sessions:
        if s['active_minutes']>=180:long.setdefault(s['project'],[]).append(s)
    for project,items in sorted(long.items()):out.append({'id':'split:'+project,'project':project,'title':f"{project}: split long sessions ({len(items)} over 3 h of active time)",'detail':f"Longest {round(max(s['active_minutes'] for s in items))} active minutes.",'reason':'Long single sessions accumulate context and are harder to review.'})
    return out[:30]

# SCAN

def settings_inputs(c):
    overrides=[(r['pattern'],r['project']) for r in c.execute('SELECT pattern,project FROM activity_project_map ORDER BY rowid')]
    saved=[r['name'] for r in c.execute('SELECT name FROM projects')]
    return overrides,saved

def load_records(c,since):
    out=[]
    for r in c.execute('SELECT * FROM activity_sessions WHERE ended>=? ORDER BY ended DESC',(since,)):
        blocks=json.loads(r['blocks']);minutes={p:sum(e-s for s,e in v) for p,v in blocks.items()};projects=json.loads(r['projects'])
        primary=max(minutes,key=minutes.get) if minutes else (projects[0] if projects else 'Unknown')
        out.append({k:r[k] for k in r.keys() if k not in ('blocks','projects','mtime','size','sig')}|{'blocks':blocks,'projects':projects,'project':primary})
    return out

def set_state(c,key,value):c.execute('INSERT INTO activity_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

def get_state(key='scan'):
    with engine.connect() as c:row=c.execute('SELECT value FROM activity_state WHERE key=?',(key,)).fetchone()
    return json.loads(row['value']) if row else None

def scan(clock=None,budget=BUDGET_S):
    settings.require('agent_observer_enabled')
    with LOCK:return _scan(clock or dt.datetime.now(IST),budget)

def _scan(clock,budget):
    t0=time.monotonic();clock=clock.astimezone(IST);since=clock-dt.timedelta(days=LOOKBACK_DAYS);errors=[];prefs=settings.get();titles=bool(prefs['agent_observer_titles'])
    days=[(clock.date()-dt.timedelta(days=i)).isoformat() for i in range(LOOKBACK_DAYS)]
    with engine.connect() as c:overrides,saved=settings_inputs(c)
    mapper=Mapper(overrides,saved,HOME)
    sig=hashlib.sha1(json.dumps([SCHEMA,overrides,sorted(saved),titles,str(HOME)]).encode()).hexdigest()[:16]
    files,skipped=discover(since.timestamp());parsed=cached=failed=0;seen_ids=set();partial=False
    with engine.connect() as c:
        known={r['id']:(r['mtime'],r['size'],r['sig']) for r in c.execute('SELECT id,mtime,size,sig FROM activity_sessions')}
        for tool,path,stat in files:
            sid=tool+':'+hashlib.sha1(str(path).encode()).hexdigest()[:16];seen_ids.add(sid)
            if known.get(sid)==(stat.st_mtime,stat.st_size,sig):cached+=1;continue
            if time.monotonic()-t0>budget*PARSE_SHARE:partial=True;continue
            acc=Acc(mapper,titles)
            try:(parse_claude if tool=='claude' else parse_codex)(path,acc)
            except OSError:failed+=1;continue
            if acc.first is None:continue
            rec=record(acc,tool,path,stat,sig);ROOTS[sid]=set(acc.roots);parsed+=1
            c.execute('INSERT OR REPLACE INTO activity_sessions VALUES(:id,:tool,:mtime,:size,:sig,:started,:ended,:active_minutes,:turns,:tool_calls,:tool_errors,:files_touched,:repeated_failures,:branch,:title,:projects,:blocks)',rec)
        if not partial:
            for sid in set(known)-seen_ids:c.execute('DELETE FROM activity_sessions WHERE id=?',(sid,))
        c.execute('DELETE FROM activity_sessions WHERE ended<?',((clock-dt.timedelta(days=RETAIN_DAYS)).timestamp(),))
        records=load_records(c,since.timestamp())
    if partial:errors.append(f'Time budget reached after {parsed} new files; remaining files are parsed on the next scan.')
    if failed:errors.append(f'{failed} session file(s) could not be read.')
    roots=set(inventory_repos(since.date().isoformat()))|{p for r in records for p in ROOTS.get(r['id'],())}
    roots={p for p in roots if os.path.isdir(p)}
    git_data,repos_done,repos_total,git_errors=gather_git(roots,mapper,since,clock,t0+budget);errors+=git_errors
    ci=ci_facts(mapper);rows,activity=build(records,git_data,days)
    last_active={p:v['last'] for p,v in activity.items() if v['last']}
    span={}
    for r in records:
        names=sorted(set(r['projects'])-{'Unknown'})
        for i,a in enumerate(names):
            for b in names[i+1:]:
                if r['blocks'].get(a) and r['blocks'].get(b):span[(a,b)]=span.get((a,b),0)+1
    window_records=[r for r in records if r['ended']>=since.timestamp()]
    found=mistakes(window_records,git_data,ci,last_active,clock);corr=correlate(activity,ci,span,days)
    week=set(days[:7]);totals={}
    for (d,p,t),v in rows.items():
        if d in week:
            e=totals.setdefault(p,{'minutes':0.0,'commits':0})
            if t=='agent':e['minutes']+=v['minutes']
            if t=='git':e['commits']+=v['commits']
    with engine.connect() as c:
        task_update={r['project']:dt.datetime.fromisoformat(r['u']).timestamp() for r in c.execute("SELECT project,max(updated_at) u FROM tasks GROUP BY project") if r['u']}
    import goals
    advice=suggestions(totals,corr,window_records,set(saved),task_update,goals.deadlines(clock.date())['this_week'],last_active,clock)
    now_list,mcp=running(mapper)
    unlogged=[{'project':a['project'],'minutes':round(totals[a['project']]['minutes']),'commits':totals[a['project']]['commits']} for a in advice if a['id'].startswith('unlogged:')]
    tools={t:sum(1 for r in records if r['tool']==t) for t in ('claude','codex')}
    coverage=(f"Parsed {parsed} and reused {cached} session files from the last {LOOKBACK_DAYS} days (Claude {tools['claude']}, Codex {tools['codex']}); {repos_done} of {repos_total} git repositories read; "
      f"minutes are estimates from session logs (gaps over 5 min excluded)."+(f" {skipped} compressed archived Codex session(s) not read." if skipped else '')+(' Partial: time budget reached.' if partial else ''))
    blob={'captured_at':clock.isoformat(),'coverage':coverage,'errors':errors,'now':now_list,'mcp_servers':mcp,'mistakes':found,'correlations':corr,'suggestions':advice,'unlogged':unlogged,
      'last_active':{p:day_of(t) for p,t in last_active.items()},'duration_s':round(time.monotonic()-t0,2),'parsed':{'claude':tools['claude'],'codex':tools['codex'],'new':parsed,'cached':cached}}
    with engine.connect() as c:
        c.execute('DELETE FROM activity_days WHERE date>=?',(days[-1],))
        c.execute('DELETE FROM activity_days WHERE date<?',((clock.date()-dt.timedelta(days=RETAIN_DAYS)).isoformat(),))
        c.executemany('INSERT INTO activity_days VALUES(:date,:project,:tool,:minutes,:sessions,:commits)',list(rows.values()))
        set_state(c,'scan',blob)
    notify_critical(found,clock)
    STATE_RUN['last']=time.monotonic()
    return overview()

def notify_critical(found,clock):
    import work
    week=clock.strftime('%G-W%V')
    for m in found:
        if m['severity']!='critical':continue
        key=f"{m['id']}@{week}"
        with engine.connect() as c:seen=c.execute("SELECT 1 FROM inbox WHERE ref_type='activity' AND ref_id=?",(key,)).fetchone()
        if not seen:work.notify('agent',m['title'],m['detail']+' '+m['suggestion'],'activity',key,'activity-observer')

# READ MODEL

def empty(enabled,coverage):
    return {'enabled':enabled,'captured_at':'','coverage':coverage,'errors':[],'now':[],'mcp_servers':0,'sessions':[],'daily':[],'projects':[],'correlations':[],'mistakes':[],'suggestions':[],'totals':{'minutes':0,'sessions':0,'commits':0,'projects':0}}

def overview(days=LOOKBACK_DAYS,clock=None):
    prefs=settings.get()
    if not prefs['agent_observer_enabled']:return empty(False,OFF)
    clock=(clock or dt.datetime.now(IST)).astimezone(IST);days=max(1,min(int(days),RETAIN_DAYS));start=(clock.date()-dt.timedelta(days=days-1)).isoformat();blob=get_state() or {}
    result=empty(True,blob.get('coverage','No scan yet. Use Scan now.'))
    since=dt.datetime.combine(dt.date.fromisoformat(start),dt.time(),IST).timestamp()
    with engine.connect() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM activity_days WHERE date>=? ORDER BY date',(start,))]
        records=load_records(c,since)
    for key in ('captured_at','errors','now','mcp_servers','mistakes','correlations','suggestions'):result[key]=blob.get(key,result[key])
    def state(ended):
        age=clock.timestamp()-ended
        return 'active' if age<=600 else 'recent' if age<=10800 else 'done'
    result['sessions']=[{'id':r['id'],'tool':r['tool'],'project':r['project'],'branch':r['branch'],'started':dt.datetime.fromtimestamp(r['started'],IST).isoformat(),'ended':dt.datetime.fromtimestamp(r['ended'],IST).isoformat(),
      'active_minutes':round(r['active_minutes'],1),'turns':r['turns'],'tool_calls':r['tool_calls'],'tool_errors':r['tool_errors'],'files_touched':r['files_touched'],'title':r['title'] if prefs['agent_observer_titles'] else '','state':state(r['ended'])} for r in records[:60]]
    daily={};projects={}
    for r in rows:
        p=projects.setdefault(r['project'],{'name':r['project'],'minutes':0.0,'sessions':0,'commits':0,'last_active':blob.get('last_active',{}).get(r['project'],''),'tools':{'claude':0.0,'codex':0.0,'git':0},'git_estimate_minutes':0.0})
        if r['tool']=='agent':
            d=daily.setdefault(r['date'],{'date':r['date'],'total':0.0,'projects':{}});d['total']=round(d['total']+r['minutes'],1);d['projects'][r['project']]=round(r['minutes'],1);p['minutes']+=r['minutes']
        elif r['tool']in('claude','codex'):p['tools'][r['tool']]=round(p['tools'][r['tool']]+r['minutes'],1)
        elif r['tool']=='git':p['commits']+=r['commits'];p['tools']['git']+=r['commits'];p['git_estimate_minutes']=round(p['git_estimate_minutes']+r['minutes'],1)
    for r in records:
        for name in r['blocks']:
            if name in projects:projects[name]['sessions']+=1
    result['daily']=list(daily.values())
    result['projects']=sorted(({**p,'minutes':round(p['minutes'],1)} for p in projects.values() if p['minutes']>0 or p['commits']),key=lambda p:(-p['minutes'],p['name']))
    result['totals']={'minutes':round(sum(d['total'] for d in daily.values()),1),'sessions':len(records),'commits':sum(p['commits'] for p in projects.values()),'projects':len(result['projects'])}
    return result

def fresh(clock=None):
    """The latest scan if the observer is on and the scan is under 30 minutes old, else None."""
    if not settings.get()['agent_observer_enabled']:return None
    blob=get_state()
    if not blob or not blob.get('captured_at'):return None
    try:age=((clock or dt.datetime.now(IST)).astimezone(IST)-dt.datetime.fromisoformat(blob['captured_at'])).total_seconds()
    except ValueError:return None
    return blob if 0<=age<FRESH_S else None

def compact(clock=None):
    """Small, name-only summary for the AI brief: project minutes, top mistakes, correlations, suggestions."""
    blob=fresh(clock)
    if not blob:return None
    data=overview(7,clock)
    return {'window_days':7,'projects':[{'project':p['name'],'agent_minutes':round(p['minutes']),'sessions':p['sessions'],'commits':p['commits'],'claude_min':round(p['tools']['claude']),'codex_min':round(p['tools']['codex'])} for p in data['projects'][:8]],
      'mistakes':[{k:m[k] for k in ('severity','kind','project','title','detail')} for m in data['mistakes'][:5]],'correlations':[{k:c[k] for k in ('a','b','score','evidence')} for c in data['correlations'][:3]],
      'suggestions':[{'project':s['project'],'title':s['title']} for s in data['suggestions'][:5]],'note':'Minutes are estimates from session logs; no prompts or file names are included.'}

def report_lines(start,end):
    """Deterministic markdown for daily/weekly reports; empty when the observer is off or there is no data in the window."""
    if not settings.get()['agent_observer_enabled']:return []
    first,last=start.astimezone(IST).date().isoformat(),end.astimezone(IST).date().isoformat()
    with engine.connect() as c:rows=[dict(r) for r in c.execute('SELECT * FROM activity_days WHERE date>=? AND date<=?',(first,last))]
    if not rows:return []
    per={}
    for r in rows:
        p=per.setdefault(r['project'],{'claude':0.0,'codex':0.0,'agent':0.0,'git':0.0,'commits':0,'sessions':0})
        p[r['tool']]+=r['minutes'];p['commits']+=r['commits'];p['sessions']+=r['sessions'] if r['tool']=='agent' else 0
    blob=get_state() or {}
    lines=['','## Activity','Observed passively from local Claude Code and Codex session logs and git. Minutes are estimates (gaps over 5 minutes excluded); commit counts measure activity, not completion.','']
    for name,p in sorted(per.items(),key=lambda x:(-x[1]['agent'],x[0])):
        lines.append(f"- {name}: {p['agent']:.0f} min agent time (Claude {p['claude']:.0f}, Codex {p['codex']:.0f}), {p['sessions']} sessions, {p['commits']} commits, ~{p['git']:.0f} min git estimate.")
    if blob.get('mistakes'):
        lines+=['','Rework and risk signals:']+[f"- [{m['severity']}] {m['title']}. {m['suggestion']}" for m in blob['mistakes'][:3]]
    if blob.get('correlations'):
        lines+=['','Projects that move together:']+[f"- {c['a']} and {c['b']} (score {c['score']:.2f}): {c['evidence']}." for c in blob['correlations'][:3]]
    lines+=['',f"Activity coverage: {blob.get('coverage','not scanned')}"]
    return lines

# MAP, WIPE, BACKGROUND

def get_map():
    with engine.connect() as c:return [{'pattern':r['pattern'],'project':r['project']} for r in c.execute('SELECT pattern,project FROM activity_project_map ORDER BY rowid')]

def set_map(value):
    if not isinstance(value,list) or len(value)>200:raise ValueError('Mapping must be a list of at most 200 rules')
    clean=[]
    for item in value:
        if not isinstance(item,dict) or not isinstance(item.get('pattern'),str) or not isinstance(item.get('project'),str):raise ValueError('Each rule needs a text pattern and project')
        pattern,project=item['pattern'].strip(),item['project'].strip()
        if not 1<=len(pattern)<=300 or not 1<=len(project)<=100:raise ValueError('Pattern must be 1-300 characters and project 1-100')
        clean.append((pattern,project))
    with engine.connect() as c:
        c.execute('DELETE FROM activity_project_map');c.executemany('INSERT INTO activity_project_map VALUES(?,?)',clean)
    return get_map()

def wipe():
    ROOTS.clear()
    with engine.connect() as c:
        counts={t:c.execute(f'DELETE FROM {t}').rowcount for t in ('activity_sessions','activity_days','activity_state')}
    return {'deleted':counts}

def safe_scan():
    try:
        if settings.get()['agent_observer_enabled']:scan()
    except Exception as error:LOG.warning('Agent observer scan failed: %s',type(error).__name__)

def kick():
    threading.Thread(target=safe_scan,name='agent-observer-kick',daemon=True).start()

def loop():
    while True:
        time.sleep(30)
        try:
            if settings.get()['agent_observer_enabled'] and time.monotonic()-STATE_RUN['last']>=SCAN_EVERY:safe_scan();STATE_RUN['last']=time.monotonic()
        except Exception as error:LOG.warning('Agent observer loop failed: %s',type(error).__name__)

def start():
    thread=STATE_RUN['thread']
    if thread and thread.is_alive():return
    STATE_RUN['thread']=threading.Thread(target=loop,name='agent-observer',daemon=True);STATE_RUN['thread'].start()
