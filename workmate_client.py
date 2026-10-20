"""Live client used by CLI and MCP. The desktop owns the API process."""
import argparse
import json
import os
from pathlib import Path
import sys
import httpx

def runtime():
    url=os.environ.get('WORKMATE_SERVER_URL')
    token=os.environ.get('WORKMATE_SERVER_TOKEN')
    if url and token:
        if not (url.startswith('https://') or url.startswith('http://127.0.0.1:')):raise ValueError('Remote team connections require HTTPS')
        return {'url':url.rstrip('/'),'token':token}
    roots=[]
    if os.environ.get('WORKMATE_HOME'):roots.append(Path(os.environ['WORKMATE_HOME']))
    if sys.platform=='darwin':roots.append(Path.home()/'Library/Application Support/GOTEET/workspace')
    elif os.name=='nt':roots.append(Path(os.environ.get('APPDATA',Path.home()))/'GOTEET/workspace')
    else:roots.append(Path.home()/'.config/GOTEET/workspace')
    roots.append(Path(__file__).resolve().parent)
    for root in roots:
        p=root/'data/runtime.json'
        if p.exists():return json.loads(p.read_text())
    raise ValueError('Open GOTEET first. No running local API was found.')

def call(method,path,value=None):
    config=runtime()
    r=httpx.request(method,config['url']+path,headers={'Authorization':'Bearer '+config['token'],'X-GOTEET-Actor':'cli/mcp'},json=value,timeout=180)
    if r.is_error:raise ValueError(r.json().get('detail','GOTEET API request failed'))
    return r.json()

def main():
    parser=argparse.ArgumentParser(description='Control the live GOTEET app')
    parser.add_argument('command',choices=['status','tasks','task','projects','project','concepts','concept','chat','send','report','sync','media','ui','navigate','preview','search','draft','models','launch'])
    parser.add_argument('--channel',default='general');parser.add_argument('--kind',default='daily',choices=['daily','weekly'])
    parser.add_argument('--value',default='',help='View name, indexed media path, search or assistant draft')
    parser.add_argument('--cdp',type=int,help='Optional loopback CDP port when launching the desktop')
    a=parser.parse_args()
    quote=__import__('urllib.parse',fromlist=['quote']).quote
    routes={'status':'/api/health','tasks':'/api/tasks','projects':'/api/projects','concepts':'/api/concepts','chat':'/api/chat?channel='+quote(a.channel),'media':'/api/media?query='+quote(a.value),'ui':'/api/ui','models':'/api/models'}
    try:
        if a.command=='launch':
            import subprocess
            environment=dict(os.environ)
            if a.cdp:
                if not 1024<=a.cdp<=65535:raise ValueError('CDP port must be 1024–65535')
                environment['GOTEET_CDP_PORT']=str(a.cdp)
            if sys.platform=='darwin':command=['/Applications/GOTEET.app/Contents/MacOS/GOTEET']
            else:raise ValueError('Launch the packaged GOTEET executable with GOTEET_CDP_PORT set on this OS')
            subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            result={'launched':True,'cdp_requested':a.cdp,'note':'Quit an existing instance first to change CDP mode.'}
        elif a.command in {'navigate','preview','search','draft'}:
            action={'navigate':'navigate','preview':'open_media','search':'search','draft':'draft_assistant'}[a.command]
            result=call('POST','/api/ui/command',{'action':action,'value':a.value})
        elif a.command in routes:result=call('GET',routes[a.command])
        elif a.command in {'task','project','concept','send'}:
            path={'task':'/api/tasks','project':'/api/projects','concept':'/api/concepts','send':'/api/chat'}[a.command]
            result=call('POST',path,json.load(sys.stdin))
        elif a.command=='report':result=call('POST','/api/reports',{'kind':a.kind})
        else:result=call('POST','/api/sync',{})
        print(json.dumps(result,indent=2))
    except Exception as e:print(json.dumps({'error':str(e)}));sys.exit(1)

if __name__=='__main__':main()
