"""Read-only, bounded inventory. No credential files or source bodies are indexed."""
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('WORKMATE_HOME', str(ROOT)))
DATA = STATE / 'data'
IST = ZoneInfo('Asia/Kolkata')
SKIP = {'.git', 'node_modules', 'Library', '.venv', 'venv', '__pycache__', 'build', 'dist', 'target', '.Trash', '.claude', '.codex', 'Pods', '.cache', 'browser-profile'}
MEDIA = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mov', '.mp4', '.m4v', '.mp3', '.wav', '.pdf', '.docx', '.xlsx', '.pptx', '.step', '.stp', '.iges', '.igs', '.brep', '.stl', '.glb', '.obj', '.blend'}

def now():
    return dt.datetime.now(IST).isoformat()

def run(args, cwd=None, env=None):
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=45)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:300] or 'Command failed')
    return p.stdout

def github(endpoint, env=None):
    return json.loads(run(['gh', 'api', endpoint], env=env))

def repo_detail(repo, env=None):
    name = repo['full_name']
    result = {k: repo.get(k) for k in ['full_name','description','html_url','pushed_at','private','fork','default_branch','archived']}
    result['errors'] = []
    def get(part, default):
        try:
            return github('repos/' + name + '/' + part, env=env)
        except Exception as e:
            result['errors'].append({'endpoint': part, 'error': str(e)})
            return default
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    commits=[]
    # Bound to 1000 commits per repo; record truncation explicitly.
    for page in range(1,11):
        batch = get('commits?per_page=100&page='+str(page)+'&since='+since, [])
        commits.extend(batch)
        if len(batch)<100:break
    result['commits_truncated'] = len(commits)==1000
    result['commits'] = [{'sha':x['sha'], 'message':x['commit']['message'].split('\n')[0], 'date':x['commit']['committer']['date'], 'author':x['commit']['author']['name'], 'url':x['html_url']} for x in commits]
    result['pulls'] = [{k:x.get(k) for k in ['number','title','state','html_url','updated_at','draft']} for x in get('pulls?state=open&per_page=100',[])]
    result['issues'] = [{k:x.get(k) for k in ['number','title','html_url','updated_at']} for x in get('issues?state=open&per_page=100',[]) if 'pull_request' not in x]
    result['runs'] = [{k:x.get(k) for k in ['name','status','conclusion','html_url','created_at','head_branch']} for x in get('actions/runs?per_page=10',{}).get('workflow_runs',[])]
    result['releases'] = [{k:x.get(k) for k in ['tag_name','name','published_at','html_url','prerelease']} for x in get('releases?per_page=5',[])]
    result['captured_at'] = now()
    return result

def local_inventory():
    home=Path.home()
    roots=[home/x for x in ['Desktop','Documents','Downloads','Pictures','Movies','Music','code','JETRAY - TAILSITTER'] if (home/x).exists()]
    # Explicit project roots in home, without crawling account/config directories.
    roots += [p for p in home.iterdir() if p.is_dir() and not p.is_symlink() and (p/'.git').exists()]
    repos=[]; files=[]; errors=[]; seen=set(); visited=0; truncated=False
    for base in roots:
        def walk_error(error):errors.append(str(error))
        for path,dirs,names in os.walk(base,followlinks=False,onerror=walk_error):
            p=Path(path)
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith('.') and not (p/d).is_symlink() and 'backup' not in d.lower()]
            if p.name.endswith(('.app','.photoslibrary')): dirs[:]=[]; continue
            if len(p.relative_to(base).parts)>5: dirs[:]=[];truncated=True;continue
            if (p/'.git').exists() and str(p) not in seen:
                seen.add(str(p))
                try:
                    status=run(['git','status','--porcelain','--untracked-files=no'],cwd=p)
                    # git status is read-only at worktree level; avoids expensive source scans.
                    remote=run(['git','config','--get','remote.origin.url'],cwd=p).strip()
                    if '@' in remote and '://' in remote: remote='[credential-bearing remote redacted]'
                    repos.append({'path':str(p),'name':p.name,'branch':run(['git','branch','--show-current'],cwd=p).strip(),'tracked_changes':len(status.splitlines()),'remote':remote,'last_commit':run(['git','log','-1','--format=%h %cs %s'],cwd=p).strip()})
                except Exception as e:errors.append({'path':str(p),'error':str(e)})
            for name in names:
                visited+=1
                f=p/name
                if visited>100000:truncated=True;break
                if f.suffix.lower() not in MEDIA or f.is_symlink():continue
                try:
                    stat=f.stat()
                    files.append({'name':name,'path':str(f),'extension':f.suffix.lower(),'size':stat.st_size,'modified':dt.datetime.fromtimestamp(stat.st_mtime,IST).isoformat(),'category': 'Video' if f.suffix.lower() in {'.mov','.mp4','.m4v'} else 'Image' if f.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif'} else 'Audio' if f.suffix.lower() in {'.mp3','.wav'} else '3D' if f.suffix.lower() in {'.step', '.stp', '.iges', '.igs', '.brep', '.stl','.glb','.obj','.blend'} else 'Document'})
                except OSError as e:errors.append(str(e))
            if visited>100000:break
        if visited>100000:break
    return {'repos':repos,'files':sorted(files,key=lambda f:f['modified'],reverse=True),'roots':[str(x) for x in roots],'visited_files':visited,'depth_limit':5,'file_limit':100000,'truncated':truncated,'errors':errors,'captured_at':now(),'coverage':'Metadata only; selected work folders, max depth 5. Hidden folders, credentials, app bundles, symlinks and backups excluded.'}

def collect():
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    errors=[]; sources={}; accounts=[]
    import settings
    preferences=settings.get()
    previous=json.loads((DATA/'inventory.json').read_text()) if (DATA/'inventory.json').exists() else {}
    configured_accounts=[]
    if preferences['github_enabled']:
        try:
            auth=json.loads(run(['gh','auth','status','--json','hosts']))
            configured_accounts=[x['login'] for x in auth.get('hosts',{}).get('github.com',[]) if x.get('login')]
        except Exception as e:errors.append({'source':'github','error':str(e)})
    # Read existing gh authentication in memory. Never write or print tokens.
    for account in configured_accounts:
        try:
            token=run(['gh','auth','token','--user',account]).strip()
            env=dict(os.environ,GH_TOKEN=token)
            pages=json.loads(run(['gh','api','--paginate','--slurp','user/repos?per_page=100&sort=pushed'],env=env))
            accounts.append(account)
            for page in pages:
                for repo in page:sources.setdefault(repo['full_name'],(repo,env))
        except Exception as e:errors.append({'source':'github','account':account,'error':str(e)})
    repos=list(sources.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        detailed=list(pool.map(lambda pair:repo_detail(*pair),repos))
    value={'github':detailed if preferences['github_enabled'] else previous.get('github',[]),
      'local':local_inventory() if preferences['local_index_enabled'] else previous.get('local',{}),
      'captured_at':now(),'errors':errors,'github_accounts':accounts,'disabled_sources':[name for name,key in [('github','github_enabled'),('local','local_index_enabled')] if not preferences[key]]}
    # Never replace a valid prior GitHub snapshot with a failed empty collection.
    if not repos and errors and (DATA/'inventory.json').exists():
        previous=json.loads((DATA/'inventory.json').read_text())
        value['github']=previous.get('github',[])
        value['github_stale']=True
        value['github_previous_capture']=previous.get('captured_at')
    temporary=DATA/'inventory.tmp'
    temporary.write_text(json.dumps(value,indent=2))
    temporary.replace(DATA/'inventory.json')
    print(json.dumps({'github_repos':len(value['github']),'local_repos':len(value['local']['repos']),'media_files':len(value['local']['files']),'errors':errors,'captured_at':value['captured_at']}))
    return value

if __name__=='__main__':collect()
