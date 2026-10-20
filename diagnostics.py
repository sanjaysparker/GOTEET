"""Measured health and bounded storage review. Findings never trigger cleanup."""
import os
import time
from pathlib import Path
import psutil
import system_info
from collector import now

def scan_folder(root,budget=5000):
    root=Path(root);total=0;files=0;errors=0;large=[];old=0;truncated=False;started=time.monotonic()
    if not root.exists():return {'path':str(root),'available':False,'bytes':0,'files':0,'errors':0,'truncated':False,'large_files':[],'old_bytes':0}
    def error(_):
        nonlocal errors
        errors+=1
    for parent,dirs,names in os.walk(root,followlinks=False,onerror=error):
        if time.monotonic()-started>3:truncated=True;break
        depth=len(Path(parent).relative_to(root).parts)
        dirs[:]=[d for d in dirs if not Path(parent,d).is_symlink() and d not in {'.git','node_modules','.venv','venv'}]
        if depth>=4:
            if dirs:truncated=True
            dirs[:]=[]
        for name in names:
            file=Path(parent,name)
            if file.is_symlink():continue
            try:
                stat=file.stat();files+=1;total+=stat.st_size
                if time.time()-stat.st_mtime>90*86400:old+=stat.st_size
                if stat.st_size>=20*1024*1024:large.append({'name':name,'path':str(file),'size':stat.st_size,'modified':stat.st_mtime})
            except OSError:errors+=1
            if files>=budget or time.monotonic()-started>3:truncated=True;break
        if files>=budget or time.monotonic()-started>3:break
    return {'path':str(root),'available':True,'bytes':total,'files':files,'errors':errors,'truncated':truncated,'old_bytes':old,'large_files':sorted(large,key=lambda r:-r['size'])[:15]}

def health():
    processes=[]
    for process in psutil.process_iter(['pid','name','memory_info']):
        try:
            memory=process.info['memory_info']
            if memory:processes.append({'pid':process.info['pid'],'name':process.info['name'],'rss':memory.rss})
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    metrics=system_info.snapshot();memory=psutil.virtual_memory();swap=psutil.swap_memory();cpu=psutil.cpu_percent(interval=.4)
    home=Path.home();folders=[scan_folder(home/'Downloads'),scan_folder(home/'Library/Caches'),scan_folder(home/'.Trash')]
    disk=psutil.disk_usage(home);free_percent=100*disk.free/disk.total
    findings=[]
    if free_percent<10:findings.append({'level':'high','title':'Storage is running low','evidence':f'{free_percent:.1f}% free on your home volume.','next':'Review large Downloads files and caches before installing more models.'})
    else:findings.append({'level':'ok','title':'Storage has working headroom','evidence':f'{free_percent:.1f}% free on your home volume.','next':'Review the largest files if you want more room. No deletion is required by this reading alone.'})
    if memory.available/memory.total<.1:findings.append({'level':'high','title':'Available RAM is low','evidence':f'{memory.available/2**30:.2f} GB available of {memory.total/2**30:.1f} GB; swap in use {swap.used/2**30:.2f} GB.','next':'Review the top memory users. Close work you have saved or choose a smaller local model.'})
    else:findings.append({'level':'ok','title':'RAM availability is within this check’s threshold','evidence':f'{memory.available/2**30:.2f} GB available; swap {swap.used/2**30:.2f} GB.','next':'One reading does not prove there is no memory pressure. Compare during the slowdown.'})
    if cpu>85:findings.append({'level':'high','title':'CPU is busy during this sample','evidence':f'{cpu:.1f}% utilization over 0.4 seconds.','next':'Recheck during the issue and review active builds, model inference and background jobs.'})
    return {'captured_at':now(),'metrics':metrics,'cpu_sample':cpu,'swap':{'used':swap.used,'total':swap.total},'available_memory':memory.available,
            'top_memory':sorted(processes,key=lambda r:-r['rss'])[:12],'storage_reviews':folders,'findings':findings,
            'coverage':'Read-only sample; Downloads, user caches and Trash scanned to depth 4, at most 5,000 files or 3 seconds per folder. Allocated/compressed disk usage may differ. Skipped folders and denied access are reported. Large/old/cache does not mean disposable.'}
