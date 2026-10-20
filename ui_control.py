"""Bounded, authenticated UI commands; no script evaluation or external actions."""
import threading
import time
import uuid
from collections import deque

ROUTES={'Today','Projects','Tasks','Timeline','Team chat','Concepts','Media','Files','Reports','Connections','Models','Agents','System','Settings'}
LOCK=threading.Lock()
COMMANDS=deque(maxlen=100)
STATE={}

def enqueue(value):
    action=value.get('action');argument=value.get('value','')
    if action not in {'navigate','search','open_media','close_media','draft_assistant','file_action','browse_files','system_health','select_model'}:raise ValueError('Unsupported UI action')
    if not isinstance(argument,str) or len(argument)>4000:raise ValueError('Invalid UI argument')
    if action=='navigate' and argument not in ROUTES:raise ValueError('Choose a workspace view')
    command={'id':str(uuid.uuid4()),'action':action,'value':argument,'status':'queued','created':time.time()}
    with LOCK:COMMANDS.append(command)
    return dict(command)

def pending():
    with LOCK:return [dict(c) for c in COMMANDS if c['status']=='queued' and time.time()-c['created']<60]

def command_status(identifier):
    with LOCK:
        command=next((dict(c) for c in COMMANDS if c['id']==identifier),None)
    if not command:return {'status':'failed','error':'Desktop command expired; review and retry'}
    if command['status']=='queued' and time.time()-command['created']>=60:return {**command,'status':'failed','error':'Desktop did not respond within 60 seconds'}
    return command

def acknowledge(value):
    with LOCK:
        for command in COMMANDS:
            if command['id']==value.get('id'):
                command.update(status='failed' if value.get('error') else 'applied',error=str(value.get('error',''))[:500])
                return dict(command)
    raise ValueError('UI command expired or not found')

def state(value=None):
    with LOCK:
        if value is not None:
            STATE.update({k:value[k] for k in ['route','query','media_path','file_location'] if isinstance(value.get(k),str)})
            STATE['updated_at']=time.time()
        return {**STATE,'connected':bool(STATE.get('updated_at') and time.time()-STATE['updated_at']<10),
                'commands':[dict(c) for c in COMMANDS][-10:]}
