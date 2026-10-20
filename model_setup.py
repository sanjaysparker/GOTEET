"""Model accounts in OS keyring; bounded local downloads; no credentials in snapshots."""
import json
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import httpx
import keyring

SERVICE='in.droneos.goteet.models'
PROVIDERS={
 'openai':{'name':'OpenAI','base':'https://api.openai.com/v1','site':'https://platform.openai.com/api-keys'},
 'anthropic':{'name':'Anthropic','base':'https://api.anthropic.com/v1','site':'https://console.anthropic.com/settings/keys'},
 'nvidia':{'name':'NVIDIA NIM','base':'https://integrate.api.nvidia.com/v1','site':'https://build.nvidia.com'},
 'openrouter':{'name':'OpenRouter','base':'https://openrouter.ai/api/v1','site':'https://openrouter.ai/keys'},
 'gemini':{'name':'Google Gemini','base':'https://generativelanguage.googleapis.com/v1beta/openai','site':'https://aistudio.google.com/api-keys'}}
JOBS={};LOCK=threading.Lock();LOGIN_PROCESSES={}

def credentials(provider):
    if provider not in PROVIDERS:raise ValueError('Choose a supported model provider')
    value=keyring.get_password(SERVICE,provider)
    return json.loads(value) if value else {}

def save(value):
    provider=value.get('provider');current=credentials(provider)
    model=str(value.get('model','')).strip();key=str(value.get('api_key','')).strip()
    if not model or len(model)>200:raise ValueError('Enter the provider model ID')
    if key:
        if len(key)>4096 or any(c.isspace() for c in key):raise ValueError('Enter a valid API key without spaces')
        current['api_key']=key
    if not current.get('api_key'):raise ValueError('Enter an API key')
    current['model']=model
    keyring.set_password(SERVICE,provider,json.dumps(current));return {'saved':True,'provider':provider,'model':model}

def disconnect(provider):
    if credentials(provider):keyring.delete_password(SERVICE,provider)
    return {'disconnected':True}

def status():
    accounts=[]
    for identifier,metadata in PROVIDERS.items():
        try:
            config=credentials(identifier)
            accounts.append({'id':identifier,**metadata,'configured':bool(config.get('api_key')),'model':config.get('model','')})
        except Exception:accounts.append({'id':identifier,**metadata,'configured':False,'model':'','error':'OS credential store unavailable'})
    local=[];online=False
    try:
        r=httpx.get('http://127.0.0.1:11434/api/tags',timeout=2);r.raise_for_status();online=True
        local=[{'name':m['name'],'size':m.get('size',0),'details':m.get('details',{})} for m in r.json().get('models',[])]
    except httpx.HTTPError:pass
    cli={}
    for name,command in [('codex',['codex','login','status']),('claude',['claude','auth','status'])]:
        installed=bool(shutil.which(name));logged_in=False
        if installed:
            try:logged_in=subprocess.run(command,capture_output=True,timeout=8).returncode==0
            except (subprocess.SubprocessError,OSError):pass
        cli[name]={'installed':installed,'logged_in':logged_in,'login_running':bool(LOGIN_PROCESSES.get(name) and LOGIN_PROCESSES[name].poll() is None)}
    with LOCK:jobs=[dict(j) for j in JOBS.values()]
    return {'providers':accounts,'cli':cli,'ollama':{'installed':bool(shutil.which('ollama')),'online':online,'models':local},'downloads':jobs}

def login(provider):
    if provider not in {'codex','claude'}:raise ValueError('Choose Codex or Claude login')
    if not shutil.which(provider):raise ValueError('Install the official '+provider+' CLI first')
    process=LOGIN_PROCESSES.get(provider)
    if process and process.poll() is None:return {'started':True}
    command=['codex','login'] if provider=='codex' else ['claude','auth','login']
    LOGIN_PROCESSES[provider]=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return {'started':True,'message':'Complete sign-in in your browser, then refresh login status.'}

def start_ollama():
    if not shutil.which('ollama'):raise ValueError('Install Ollama from ollama.com first')
    try:
        httpx.get('http://127.0.0.1:11434/api/tags',timeout=2).raise_for_status()
        return {'running':True}
    except httpx.HTTPError:
        subprocess.Popen(['ollama','serve'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'starting':True}

def pull(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}',name) or '..' in name or name.startswith(('http:','https:')):
        raise ValueError('Use an Ollama model name or hf.co/owner/GGUF-repository:quantization')
    with LOCK:
        for job in JOBS.values():
            if job['status'] in {'queued','downloading'}:
                if job['name']==name:return dict(job)
                raise ValueError('A model download is already running. Wait for it to finish.')
        job={'id':str(uuid.uuid4()),'name':name,'status':'queued','detail':'Connecting to Ollama','completed':0,'total':0}
        JOBS[job['id']]=job
    def download():
        try:
            with httpx.stream('POST','http://127.0.0.1:11434/api/pull',json={'model':name,'stream':True},timeout=httpx.Timeout(30,read=600)) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:continue
                    value=json.loads(line)
                    if value.get('error'):raise ValueError('Ollama rejected the model. Check the model ID, availability and license.')
                    with LOCK:job.update(status='done' if value.get('status')=='success' else 'downloading',detail=value.get('status','Downloading'),completed=value.get('completed',0),total=value.get('total',0))
            if job['status']!='done':raise ValueError('The download ended before Ollama confirmed success. Retry from Models.')
        except Exception as error:
            with LOCK:job.update(status='failed',detail=str(error) if isinstance(error,ValueError) else 'Could not download. Start Ollama, check the model name and network, then retry.')
    threading.Thread(target=download,daemon=True,name='goteet-model-download').start()
    return dict(job)

def remote_models(provider):
    config=credentials(provider)
    if not config.get('api_key'):raise ValueError('Save this provider API key first')
    headers={'Authorization':'Bearer '+config['api_key']}
    if provider=='anthropic':headers={'x-api-key':config['api_key'],'anthropic-version':'2023-06-01'}
    try:
        r=httpx.get(PROVIDERS[provider]['base']+'/models',headers=headers,timeout=20);r.raise_for_status()
        return {'models':[m['id'] for m in r.json().get('data',[]) if isinstance(m.get('id'),str)]}
    except httpx.HTTPError:raise ValueError('Provider verification failed. Check your key, account access and network.')

def claude_text(prompt,schema=None):
    args=['claude','-p','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--disable-slash-commands','--no-session-persistence','--setting-sources','','--output-format','json']
    if schema:args+=['--json-schema',json.dumps(schema)]
    with tempfile.TemporaryDirectory(prefix='goteet-claude-') as directory:
        result=subprocess.run(args,input=prompt,text=True,capture_output=True,timeout=180,cwd=directory)
    if result.returncode:raise ValueError('Claude could not answer. Check Claude login, usage and model access in Models.')
    value=json.loads(result.stdout)
    if value.get('is_error'):raise ValueError('Claude did not complete this request. Check its account status.')
    if schema:return json.dumps(value.get('structured_output',{}))
    return str(value.get('result',''))

def chat(provider,messages,schema=None):
    config=credentials(provider)
    if not config.get('api_key') or not config.get('model'):raise ValueError('Configure this provider in Models first')
    if schema:messages=[*messages,{'role':'user','content':'Return ONLY JSON matching this schema, no markdown: '+json.dumps(schema)}]
    headers={'Authorization':'Bearer '+config['api_key']};payload={'model':config['model'],'messages':messages,'stream':False,'max_tokens':4096}
    endpoint='/chat/completions'
    if provider=='anthropic':
        headers={'x-api-key':config['api_key'],'anthropic-version':'2023-06-01'};endpoint='/messages'
        payload={'model':config['model'],'max_tokens':4096,'system':'\n'.join(m['content'] for m in messages if m['role']=='system'),
                 'messages':[m for m in messages if m['role']!='system']}
        if not payload['messages']:payload['messages']=[{'role':'user','content':'Respond to the system request.'}]
    try:
        response=httpx.post(PROVIDERS[provider]['base']+endpoint,headers=headers,json=payload,timeout=180);response.raise_for_status();value=response.json()
        if provider=='anthropic':return '\n'.join(c.get('text','') for c in value.get('content',[]) if c.get('type')=='text')
        return value['choices'][0]['message']['content']
    except (httpx.HTTPError,KeyError,IndexError):raise ValueError('The model request failed. Check the provider key, model ID, quota and account access in Models.')
