"""Read-only host inventory plus app-local skill enablement. Never expose MCP secrets."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tomllib
import engine

def enabled():return engine.read_json('agent_skills.json').get('enabled',[])

def skills():
    roots=[Path.home()/'.codex/skills',Path.home()/'.agents/skills'];seen=set();result=[];active=set(enabled())
    for root in roots:
        if not root.exists():continue
        for file in [*root.glob('*/SKILL.md'),*root.glob('.system/*/SKILL.md')]:
            try:
                real=file.resolve()
                if real in seen:continue
                seen.add(real);text=file.read_text()[:12000]
                name=re.search(r'^name:\s*[\'"]?([^\n\'"]+)',text,re.M)
                description=re.search(r'^description:\s*(.*?)(?=\n[a-z_]+:|\n---)',text,re.M|re.S)
                identifier=hashlib.sha256(str(real).encode()).hexdigest()[:16]
                result.append({'id':identifier,'name':name.group(1).strip() if name else file.parent.name,
                  'description':re.sub(r'\s+',' ',description.group(1)).strip(' \'"')[:500] if description else '',
                  'path':str(real),'enabled':identifier in active})
            except OSError:continue
    return sorted(result,key=lambda x:x['name'].lower())

def set_skill(value):
    identifier=value.get('id');state=value.get('enabled')
    if not isinstance(state,bool):raise ValueError('Skill enabled must be true or false')
    if identifier not in {s['id'] for s in skills()}:raise ValueError('Choose an installed skill')
    selected=set(enabled())
    if state:selected.add(identifier)
    else:selected.discard(identifier)
    path=engine.DATA/'agent_skills.json';path.write_text(json.dumps({'enabled':sorted(selected)}));path.chmod(0o600)
    return {'id':identifier,'enabled':state}

def inventory():
    records=[];errors=[]
    configs=[(Path.home()/'.codex/config.toml','Codex','toml'),(Path.home()/'.claude.json','Claude user','json'),(Path(__file__).parent/'.mcp.json','GOTEET project','json')]
    for file,source,kind in configs:
        if not file.exists():continue
        try:
            content=tomllib.loads(file.read_text()) if kind=='toml' else json.loads(file.read_text())
            for name,config in content.get('mcp_servers' if kind=='toml' else 'mcpServers',{}).items():
                if not isinstance(config,dict):continue
                records.append({'name':name,'source':source,'transport':'HTTP' if config.get('url') else 'stdio','command':Path(str(config.get('command',''))).name,'enabled':config.get('enabled',True)})
        except (OSError,ValueError):errors.append(source+' configuration could not be read')
    return {'agents':[{'name':name,'installed':bool(shutil.which(name)),'path':shutil.which(name) or ''} for name in ['codex','claude','ollama','gemini','aider','opencode']],
            'mcp':records,'skills':skills(),'errors':errors,'note':'MCP inventory shows registration only, not a live health probe. Skill toggles apply to GOTEET context and never modify original skill files or host MCP permissions.'}
