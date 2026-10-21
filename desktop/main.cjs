const {app,BrowserWindow,ipcMain,shell,session,dialog,systemPreferences,protocol,clipboard,ShareMenu,powerMonitor}=require('electron');
const {spawn,execFile}=require('node:child_process');
const {promisify}=require('node:util');
const execFileAsync=promisify(execFile);
const fs=require('node:fs');
const path=require('node:path');
app.setName('GOTEET');
let backend,windowRef,runtime,closing=false;
const integratedBrowser=require('./browser.cjs').createBrowser(()=>windowRef);
ipcMain.handle('browser',async(event,action,value)=>{if(!trusted(event))throw Error('Untrusted caller');return integratedBrowser.command(action,value);});
const repo=path.resolve(__dirname,'..');
const state=process.env.WORKMATE_HOME||path.join(app.getPath('userData'),'workspace');
const runtimePath=path.join(state,'data','runtime.json');
const environment={...process.env,WORKMATE_HOME:state,PATH:[process.env.PATH,'/opt/homebrew/bin','/usr/local/bin',path.join(app.getPath('home'),'.local/bin'),'/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS'].filter(Boolean).join(path.delimiter)};
protocol.registerSchemesAsPrivileged([{scheme:'goteet-media',privileges:{standard:true,secure:true,supportFetchAPI:true,stream:true,corsEnabled:true}}]);
const cdpPort=process.env.GOTEET_CDP_PORT;
if(cdpPort){
 if(!/^\d+$/.test(cdpPort)||Number(cdpPort)<1024||Number(cdpPort)>65535)throw new Error('GOTEET_CDP_PORT must be between 1024 and 65535');
 app.commandLine.appendSwitch('remote-debugging-address','127.0.0.1');
 app.commandLine.appendSwitch('remote-debugging-port',cdpPort);
}
if(!app.requestSingleInstanceLock())app.quit();
function openAccount(url){if(url!=='goteet://account'&&url!=='goteet://account/')return;windowRef?.show();windowRef?.focus();if(runtime)apiRequest('POST','/api/ui/command',{action:'navigate',value:'Connections'}).catch(()=>{});}
app.on('second-instance',(_event,argv)=>{windowRef?.show();windowRef?.focus();for(const url of argv)openAccount(url);});
app.on('open-url',(event,url)=>{event.preventDefault();openAccount(url);});
function delay(ms){return new Promise(resolve=>setTimeout(resolve,ms));}
async function startBackend(){
 if(process.env.WORKMATE_SERVER_URL&&process.env.WORKMATE_SERVER_TOKEN){
  const url=new URL(process.env.WORKMATE_SERVER_URL);
  if(url.protocol!=='https:'&&!(url.protocol==='http:'&&url.hostname==='127.0.0.1'))throw new Error('Team servers must use HTTPS.');
  runtime={url:url.toString().replace(/\/$/,''),token:process.env.WORKMATE_SERVER_TOKEN};
  const response=await fetch(runtime.url+'/api/tasks',{headers:{Authorization:'Bearer '+runtime.token}});
  if(!response.ok)throw new Error('The team server rejected this pairing credential.');return;
 }
 fs.mkdirSync(path.join(state,'data'),{recursive:true,mode:0o700});
 const seed=app.isPackaged?path.join(process.resourcesPath,'payload','seed'):path.join(repo,'data');
 for(const name of ['inventory.json','workspace.json','opensource.json']){
  const target=path.join(state,'data',name);
  if(!fs.existsSync(target)&&fs.existsSync(path.join(seed,name)))fs.copyFileSync(path.join(seed,name),target);
 }
 const command=app.isPackaged?path.join(process.resourcesPath,'payload','workmate-api',process.platform==='win32'?'workmate-api.exe':'workmate-api'):path.join(repo,'.venv312',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 backend=spawn(command,app.isPackaged?[]:[path.join(repo,'api.py')],{env:environment,stdio:['ignore','pipe','pipe'],windowsHide:true});
 const log=fs.createWriteStream(path.join(state,'backend.log'),{flags:'a',mode:0o600});
 backend.stdout.pipe(log);backend.stderr.pipe(log);
 let exited=false;backend.on('exit',()=>{exited=true;if(!closing)dialog.showErrorBox('GOTEET engine stopped','Close and reopen the app. Details are in the local backend.log file.');});
 for(let attempt=0;attempt<180;attempt++){
  if(exited)throw new Error('The local engine could not start. See '+path.join(state,'backend.log'));
  try{const value=JSON.parse(fs.readFileSync(runtimePath,'utf8'));
   if(value.pid===backend.pid){const response=await fetch(value.url+'/api/health');const health=await response.json();if(health.instance===value.instance){runtime=value;return;}}
  }catch{}
  await delay(350);
 }
 throw new Error('The local engine did not become ready in time.');
}
function trusted(event){return event.sender===windowRef?.webContents;}
async function apiRequest(method,route,value){
 if(!/^\/api\/[a-zA-Z0-9_/-]+(?:\?[^#\s]*)?$/.test(route)||!['GET','POST'].includes(method))throw new Error('Unsupported API request');
 const response=await fetch(runtime.url+route,{method,headers:{'Authorization':'Bearer '+runtime.token,'Content-Type':'application/json'},body:method==='POST'?JSON.stringify(value||{}):undefined});
 let result;try{result=await response.json();}catch{throw new Error('The local service returned an unexpected response (HTTP '+response.status+'). Please retry or restart GOTEET.');}if(!response.ok)throw new Error(result.detail||'The request failed');return result;
}
ipcMain.handle('api',async(event,method,route,value)=>{if(!trusted(event))throw new Error('Untrusted caller');return apiRequest(method,route,value);});
ipcMain.handle('preview',async(event,file)=>{
 if(!trusted(event)||typeof file!=='string')throw new Error('Invalid preview');
 const info=await apiRequest('GET','/api/media/info?path='+encodeURIComponent(file));
 return {...info,url:'goteet-media://library/content?path='+encodeURIComponent(file)};
});
ipcMain.handle('browse-preview',async(event,file)=>{
 if(!trusted(event)||typeof file!=='string')throw new Error('Invalid preview');
 const info=await apiRequest('POST','/api/files/preview',{path:file});
 return {...info,url:'goteet-media://library/content?path='+encodeURIComponent(info.path)};
});
ipcMain.handle('profile-photo',async(event)=>{
 if(!trusted(event))throw new Error('Untrusted caller');
 const choice=await dialog.showOpenDialog(windowRef,{title:'Choose a profile photo',properties:['openFile'],filters:[{name:'Profile photo',extensions:['png','jpg','jpeg','webp']}]});
 if(choice.canceled)return null;
 const file=choice.filePaths[0];if(fs.statSync(file).size>12000000)throw new Error('Choose a profile photo under 12 MB');
 const form=new FormData();form.append('file',new Blob([fs.readFileSync(file)]),path.basename(file));
 const response=await fetch(runtime.url+'/api/profile/photo',{method:'POST',headers:{Authorization:'Bearer '+runtime.token},body:form});
 const value=await response.json();if(!response.ok)throw new Error(value.detail);return value;
});
ipcMain.handle('file-action',async(event,action,file)=>{
 if(!trusted(event)||!['copy-path','reveal','copy','trash','share'].includes(action))throw new Error('Unsupported file action');
 if(process.env.WORKMATE_SERVER_URL)throw new Error('Use Files on the workspace owner’s computer for native file actions');
 const inspect=()=>apiRequest('GET','/api/files/info?path='+encodeURIComponent(file)+'&action='+encodeURIComponent(['copy','trash','share'].includes(action)?action:'read'));
 const info=await inspect();
 if(action==='copy-path'){clipboard.writeText(info.path);return {message:'Path copied'};}
 if(action==='reveal'){shell.showItemInFolder(info.path);return {message:'Shown in Finder'};}
 if(action==='share'){
  if(process.platform!=='darwin'){clipboard.writeText(info.path);return {message:'Path copied. Native sharing is available on macOS.'};}
  new ShareMenu({filePaths:[info.path]}).popup({browserWindow:windowRef});return {message:'Choose a destination in the system share menu'};
 }
 if(action==='copy'){
  if(info.kind!=='File'||info.is_symlink)throw new Error('Copy a regular file; folder and symlink copying are not supported yet');
  const choice=await dialog.showSaveDialog(windowRef,{title:'Copy file to…',defaultPath:info.name,buttonLabel:'Copy file'});
  if(choice.canceled)return {message:'Copy cancelled'};
  await inspect();
  try{await fs.promises.copyFile(info.path,choice.filePath,fs.constants.COPYFILE_EXCL);}
  catch(error){if(error.code==='EEXIST')throw new Error('A file already exists at that destination. Choose a different name.');throw error;}
  return {message:'File copied',destination:choice.filePath};
 }
 const choice=await dialog.showMessageBox(windowRef,{type:'question',message:'Move “'+info.name+'” to Trash?',detail:info.path+'\nYou can restore it from the system Trash.',buttons:['Cancel','Move to Trash'],defaultId:0,cancelId:0});
 if(choice.response!==1)return {message:'Trash cancelled'};
 await inspect();await shell.trashItem(info.path);return {message:'Moved to Trash'};
});
ipcMain.handle('copy-text',async(event,value)=>{if(!trusted(event)||typeof value!=='string'||value.length>100000)throw new Error('Invalid clipboard text');clipboard.writeText(value);});
ipcMain.handle('agent-access',async(event)=>{
 if(!trusted(event))throw new Error('Untrusted caller');
 const executable=app.isPackaged?path.join(process.resourcesPath,'payload','workmate-api',process.platform==='win32'?'workmate-api.exe':'workmate-api'):path.join(repo,'.venv312',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 return {mcpConfig:{mcpServers:{goteet:{command:executable,args:app.isPackaged?['--mcp']:[path.join(repo,'mcp_server.py')]}}},cli:{command:executable,args:app.isPackaged?['--cli']:[path.join(repo,'workmate_client.py')]}};
});
ipcMain.handle('developer-status',async(event)=>{if(!trusted(event))return;return {cdp:!!cdpPort,url:cdpPort?'http://127.0.0.1:'+cdpPort:null};});
ipcMain.handle('check-updates',async(event)=>{
 if(!trusted(event))throw new Error('Untrusted caller');
 const config=await apiRequest('GET','/api/settings');
 const repository=config.updates_repository||'';
 if(!repository)return {configured:false,current:app.getVersion()};
 if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository))throw new Error('Enter an owner/repository update source');
 const response=await fetch('https://api.github.com/repos/'+repository+'/releases/latest',{headers:{Accept:'application/vnd.github+json','User-Agent':'GOTEET/'+app.getVersion()},signal:AbortSignal.timeout(15000)});
 if(response.status===404)return {configured:true,current:app.getVersion(),message:'No published public release found for this repository.'};
 if(!response.ok)throw new Error('GitHub update check failed ('+response.status+'). Try again later.');
 const release=await response.json();const latest=String(release.tag_name||'').replace(/^v/,'');
 const parse=v=>/^\d+\.\d+\.\d+$/.test(v)?v.split('.').map(Number):null;
 const current=parse(app.getVersion()),next=parse(latest);
 const available=!!(current&&next&&next.some((n,i)=>n>current[i]&&next.slice(0,i).every((p,j)=>p===current[j])));
 const url=new URL(release.html_url);
 if(url.protocol!=='https:'||url.host!=='github.com'||!url.pathname.startsWith('/'+repository+'/releases/'))throw new Error('Invalid release destination');
 return {configured:true,current:app.getVersion(),latest,available,url:url.href,published_at:release.published_at,message:available?'An update is available. Download the installer from the release page.':'You are on the latest published version.'};
});
ipcMain.handle('audio',async(event,bytes)=>{
 if(!trusted(event)||!Array.isArray(bytes)||bytes.length>15000000)throw new Error('Invalid audio');
 const form=new FormData();form.append('audio',new Blob([Uint8Array.from(bytes)],{type:'audio/webm'}),'recording.webm');
 const r=await fetch(runtime.url+'/api/voice/transcribe',{method:'POST',headers:{Authorization:'Bearer '+runtime.token},body:form});
 const d=await r.json();if(!r.ok)throw new Error(d.detail);return d;
});
ipcMain.handle('external',async(event,url)=>{
 if(!trusted(event))throw Error('Untrusted caller');
 const parsed=new URL(url);
 if(parsed.protocol!=='https:'||parsed.username||parsed.password)throw Error('Use an HTTPS link');
 // Google's installed-app consent must run in the system browser.
 if(parsed.hostname==='accounts.google.com'){await shell.openExternal(parsed.href);return;}
 await integratedBrowser.open(parsed.href);
});
ipcMain.handle('reveal',async(event,file)=>{
 if(!trusted(event))return;
 const snap=await apiRequest('GET','/api/snapshot');
 if(!snap.inventory?.local?.files?.some(f=>f.path===file))throw new Error('Choose a file from the indexed media library');
 shell.showItemInFolder(file);
});
ipcMain.handle('export',async(event,report)=>{
 if(!trusted(event))return;
 const choice=await dialog.showSaveDialog(windowRef,{defaultPath:`GOTEET-${report.kind}.md`,filters:[{name:'Markdown report',extensions:['md']}]});
 if(!choice.canceled&&choice.filePath){fs.writeFileSync(choice.filePath,String(report.content));return true;}return false;
});
ipcMain.handle('oauth-file',async(event)=>{
 if(!trusted(event))return;
 const result=await dialog.showOpenDialog(windowRef,{properties:['openFile'],filters:[{name:'Google Desktop OAuth client',extensions:['json']}]});
 if(result.canceled)return null;
 const file=result.filePaths[0];if(fs.statSync(file).size>100000)throw new Error('Choose the small OAuth client JSON file');
 const value=JSON.parse(fs.readFileSync(file,'utf8'));return apiRequest('POST','/api/google/configure',value);
});
ipcMain.handle('attach',async(event,type,id)=>{
 if(!trusted(event))return;
 const selected=await dialog.showOpenDialog(windowRef,{title:'Attach a file to this shared work item',properties:['openFile']});
 if(selected.canceled)return null;
 const file=selected.filePaths[0];if(fs.statSync(file).size>25000000)throw new Error('Keep attachments under 25 MB');
 const form=new FormData();form.append('file',new Blob([fs.readFileSync(file)]),path.basename(file));
 const r=await fetch(runtime.url+'/api/attachments/upload?target_type='+encodeURIComponent(type)+'&target_id='+encodeURIComponent(id),{method:'POST',headers:{Authorization:'Bearer '+runtime.token},body:form});
 const result=await r.json();if(!r.ok)throw new Error(result.detail);return result;
});
ipcMain.handle('download-attachment',async(event,item)=>{
 if(!trusted(event)||!/^[-a-f0-9]{36}$/.test(item.id))throw new Error('Invalid attachment');
 const r=await fetch(runtime.url+'/api/attachments/download?id='+item.id,{headers:{Authorization:'Bearer '+runtime.token}});
 if(!r.ok)throw new Error('Attachment download failed');
 const folder=path.join(app.getPath('userData'),'attachment-downloads',item.id);fs.mkdirSync(folder,{recursive:true,mode:0o700});
 const file=path.join(folder,path.basename(String(item.name)).replace(/[\\/]/g,'_'));
 fs.writeFileSync(file,Buffer.from(await r.arrayBuffer()),{mode:0o600});shell.showItemInFolder(file);
});
app.whenReady().then(async()=>{
 app.setAccessibilitySupportEnabled(true);
 app.setAsDefaultProtocolClient('goteet');
 app.setAboutPanelOptions({applicationName:'GOTEET',applicationVersion:app.getVersion(),copyright:'Made by SPARKER',iconPath:path.join(__dirname,'assets/icon.png')});
 if(app.dock)app.dock.setIcon(path.join(__dirname,'assets/icon.png'));
 try{
  await startBackend();
  protocol.handle('goteet-media',async request=>{
   const url=new URL(request.url);
   if(url.hostname==='profile'&&url.pathname==='/avatar')return fetch(runtime.url+'/api/profile/photo',{headers:{Authorization:'Bearer '+runtime.token}});
   if(url.hostname!=='library'||!['/content','/thumbnail'].includes(url.pathname)||!url.searchParams.get('path'))return new Response('Invalid media request',{status:400});
   const headers={Authorization:'Bearer '+runtime.token};
   if(request.headers.has('Range'))headers.Range=request.headers.get('Range');
   try{const response=await fetch(runtime.url+'/api/media'+url.pathname+'?path='+encodeURIComponent(url.searchParams.get('path')),{headers});const output=new Headers(response.headers);output.set('Access-Control-Allow-Origin','*');return new Response(response.body,{status:response.status,headers:output});}
   catch{return new Response('Media is unavailable',{status:503});}
  });
  session.defaultSession.setPermissionCheckHandler((_webContents,permission)=>permission==='media');
  session.defaultSession.setPermissionRequestHandler(async(webContents,permission,callback)=>{
   if(webContents!==windowRef?.webContents||permission!=='media'){callback(false);return;}
   const granted=process.platform==='darwin'?await systemPreferences.askForMediaAccess('microphone'):true;callback(granted);
  });
  windowRef=new BrowserWindow({width:1450,height:940,minWidth:980,minHeight:680,title:'GOTEET',backgroundColor:'#17191d',titleBarStyle:process.platform==='darwin'?'hiddenInset':'default',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:false}});
  windowRef.webContents.setWindowOpenHandler(({url})=>{if(url.startsWith('https://'))integratedBrowser.open(url).catch(()=>{});return {action:'deny'};});
  windowRef.webContents.on('will-navigate',(event)=>event.preventDefault());
  await windowRef.loadFile(path.join(repo,'dist/index.html'));
  if(process.env.WORKMATE_SCREENSHOT)await windowRef.webContents.capturePage().then(image=>fs.writeFileSync(process.env.WORKMATE_SCREENSHOT,image.toPNG()));
 }catch(error){dialog.showErrorBox('GOTEET could not open',error.message);app.quit();}
});
app.on('before-quit',()=>{closing=true;integratedBrowser.close();backend?.kill();});
app.on('window-all-closed',()=>app.quit());

// Application names only. Never read browser tabs, window titles or typed content.
let activityTimer,activityBusy=false,activityLast=Date.now();
app.whenReady().then(()=>{
 activityTimer=setInterval(async()=>{
  const current=Date.now(),elapsed=(current-activityLast)/1000;activityLast=current;
  if(activityBusy||!runtime||process.platform!=='darwin'||elapsed>30||powerMonitor.getSystemIdleTime()>=60)return;
  activityBusy=true;
  try{
   const preferences=await apiRequest('GET','/api/settings');if(!preferences.activity_enabled)return;
   const front=(await execFileAsync('/usr/bin/lsappinfo',['front'],{timeout:2000})).stdout.trim();
   if(!/^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/i.test(front))return;
   const info=(await execFileAsync('/usr/bin/lsappinfo',['info','-only','name','-only','bundleid',front],{timeout:2000,maxBuffer:16000})).stdout;
   const name=info.match(/^"([^"]+)"/m)?.[1],bundle=info.match(/bundleID="([^"]+)"/)?.[1]||'';
   if(name&&!['loginwindow','ScreenSaverEngine'].includes(name))await apiRequest('POST','/api/activity/sample',{app:name,bundle,seconds:elapsed});
  }catch{}finally{activityBusy=false;}
 },15000);
});
app.on('before-quit',()=>clearInterval(activityTimer));
