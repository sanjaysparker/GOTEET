const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('workmate',{
 browser:(action,value)=>ipcRenderer.invoke('browser',action,value),
 onBrowser:callback=>{const listener=(_event,value)=>callback(value);ipcRenderer.on('browser-state',listener);return()=>ipcRenderer.removeListener('browser-state',listener);},
 copyText:value=>ipcRenderer.invoke('copy-text',value),
 agentAccess:()=>ipcRenderer.invoke('agent-access'),
 profilePhoto:()=>ipcRenderer.invoke('profile-photo'),
 request:(method,route,value)=>ipcRenderer.invoke('api',method,route,value),
 transcribe:bytes=>ipcRenderer.invoke('audio',bytes),
 external:url=>ipcRenderer.invoke('external',url),
 reveal:file=>ipcRenderer.invoke('reveal',file),
 preview:file=>ipcRenderer.invoke('preview',file),
 developerStatus:()=>ipcRenderer.invoke('developer-status'),
 checkUpdates:()=>ipcRenderer.invoke('check-updates'),
 browsePreview:file=>ipcRenderer.invoke('browse-preview',file),
 fileAction:(action,file)=>ipcRenderer.invoke('file-action',action,file),
 exportReport:report=>ipcRenderer.invoke('export',report),
 importOAuth:()=>ipcRenderer.invoke('oauth-file'),
 attach:(type,id)=>ipcRenderer.invoke('attach',type,id),
 downloadAttachment:item=>ipcRenderer.invoke('download-attachment',item)
});
