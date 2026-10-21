"""Read-only Gmail reader. Bodies are fetched on demand, never persisted."""
import base64
import re
from html.parser import HTMLParser
from urllib.parse import quote
import httpx
import google_auth
import settings

SENSITIVE=re.compile(r'verif|sign.in|secure link|token|password|otp|one.time|security code|payroll|salary|payslip|identity',re.I)

class PlainHTML(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','head'}:self.hidden+=1
        if tag in {'br','p','div','li','tr','h1','h2','h3'} and not self.hidden:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','head'}:self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def body_text(payload):
    plain=[];html=[];attachments=[];total=0;nodes=0
    def walk(part,depth=0):
        nonlocal total,nodes
        nodes+=1
        if depth>20 or nodes>1000:raise ValueError('Message structure exceeds reader limits.')
        if part.get('filename'):
            attachments.append({'name':part['filename'],'size':part.get('body',{}).get('size',0),'type':part.get('mimeType','')});return
        mime=part.get('mimeType','');data=part.get('body',{}).get('data','')
        if data and mime in {'text/plain','text/html'}:
            if len(data)>1500000:raise ValueError('Message body exceeds the 1 MB reader limit. Open it in Gmail.')
            total+=len(data)
            if total>1500000:raise ValueError('Message body exceeds reader limits.')
            value=base64.urlsafe_b64decode(data+'='*(-len(data)%4)).decode('utf-8',errors='replace')
            (plain if mime=='text/plain' else html).append(value)
        for child in part.get('parts',[])[:100]:walk(child,depth+1)
    walk(payload)
    text='\n\n'.join(plain)
    if not text:
        parser=PlainHTML();parser.feed('\n'.join(html));text=''.join(parser.parts)
    return text[:200000],attachments,len(text)>200000

def summary(d,account):
    h={v['name'].lower():v['value'] for v in d.get('payload',{}).get('headers',[])}
    return {'id':d['id'],'subject':h.get('subject','(No subject)'),'from':h.get('from',''),'to':h.get('to',''),'date':h.get('date',''),'unread':'UNREAD' in d.get('labelIds',[]),'url':'https://mail.google.com/mail/u/?authuser='+quote(account)+'#all/'+d['id']}

def read(query='',folder='INBOX',page='',message_id=''):
    settings.require('google_enabled')
    status=google_auth.status()
    if not status.get('connected') or not status.get('sources',{}).get('gmail'):raise ValueError('Connect Gmail read access in Connections first.')
    if len(query)>500 or len(page)>4096:raise ValueError('Search or page token is too long.')
    if folder not in {'INBOX','SENT','STARRED','ALL'}:raise ValueError('Unknown mail folder')
    if message_id and not re.fullmatch(r'[a-fA-F0-9]{1,64}',message_id):raise ValueError('Invalid Gmail message ID')
    account=status.get('profile',{}).get('email','')
    with httpx.Client(headers={'Authorization':'Bearer '+google_auth.access_token()},timeout=30) as client:
        def get(path,params=None):
            r=client.get('https://gmail.googleapis.com/gmail/v1/users/me/'+path,params=params)
            if r.status_code!=200:raise ValueError('Gmail could not load this request. Check your connection and permissions.')
            return r.json()
        if message_id:
            # Check subject before requesting the full body.
            metadata=get('messages/'+message_id,{'format':'metadata','metadataHeaders':['Subject']})
            subject=summary(metadata,account)['subject']
            if SENSITIVE.search(subject):raise ValueError('Authentication, identity and payroll messages are excluded from this reader. Open them directly in Gmail.')
            value=get('messages/'+message_id,{'format':'full'})
            text,attachments,truncated=body_text(value.get('payload',{}))
            return {**summary(value,account),'text':text,'attachments':attachments,'truncated':truncated,'account':account}
        params={'maxResults':30,'q':query,'includeSpamTrash':'false'}
        if folder!='ALL':params['labelIds']=folder
        if page:params['pageToken']=page
        result=get('messages',params)
        import concurrent.futures
        def item(row):
            value=get('messages/'+row['id'],{'format':'metadata','metadataHeaders':['Subject','From','To','Date']})
            data=summary(value,account)
            return data if not SENSITIVE.search(data['subject']) else None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:items=[i for i in pool.map(item,result.get('messages',[])) if i]
        return {'messages':items,'next':result.get('nextPageToken',''),'account':account,'excluded':len(result.get('messages',[]))-len(items)}
