"""Measured system state, without command lines, secrets or device serials."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import psutil
from collector import now

def snapshot():
    memory=psutil.virtual_memory();disk=shutil.disk_usage(Path.home())
    chip=platform.processor() or platform.machine()
    if platform.system()=='Darwin':
        try:chip=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True,timeout=3).strip()
        except Exception:pass
    tools=[]
    for name in ['git','gh','codex','claude','ollama','node','npm','python3','docker','ffmpeg','gcloud']:
        location=shutil.which(name)
        tools.append({'name':name,'available':bool(location),'path':location or ''})
    battery=psutil.sensors_battery()
    return {'captured_at':now(),'os':platform.system(),'os_version':platform.mac_ver()[0] if platform.system()=='Darwin' else platform.release(),
      'architecture':platform.machine(),'processor':chip,'logical_cores':psutil.cpu_count(),'physical_cores':psutil.cpu_count(logical=False),
      'cpu_percent':psutil.cpu_percent(interval=0.15),'memory':{'total':memory.total,'available':memory.available,'percent':memory.percent},
      'disk':{'total':disk.total,'used':disk.used,'free':disk.free,'percent':disk.used/disk.total*100},
      'battery':{'percent':battery.percent,'plugged_in':battery.power_plugged} if battery else None,
      'cli_tools':tools,'process_count':len(psutil.pids()),
      'coverage':'OS, CPU, memory, home-volume storage, battery and CLI availability. No process command lines, credentials, private browser databases or device serials are collected.'}
