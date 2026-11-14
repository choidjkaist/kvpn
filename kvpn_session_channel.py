"""Owner-only, memory-only gateway session channel for bounded diagnostics.

Started only with --inspect-session. Cookie never enters argv/files/logs. The
channel ends after 20 minutes and offers GET only; it cannot extend/log out.
"""
import json, os, socket, stat, subprocess, sys, time, urllib.request, urllib.parse, posixpath
from pathlib import Path

BASE='https://kvpn.kaist.ac.kr'
DIRECTORY=Path.home()/'Library/Application Support/kvpn'
SOCKET=DIRECTORY/'session-v3.sock'

class SameOrigin(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if (urllib.parse.urlsplit(newurl).scheme,urllib.parse.urlsplit(newurl).netloc)!=('https','kvpn.kaist.ac.kr'):
            raise ValueError('Cross-origin redirect refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def request(path, method="GET", data=None):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(25);s.connect(str(SOCKET))
        s.sendall(json.dumps({'path':path,'method':method,'data':data}).encode()+b'\n');s.shutdown(socket.SHUT_WR)
        data=b''
        while True:
            block=s.recv(65536)
            if not block:break
            data+=block
            if len(data)>24000000:raise ValueError('Oversized response')
        return json.loads(data)

def start(cookie):
    if SOCKET.exists():
        raise ValueError('Existing diagnostic session channel; wait for it to expire before another inspection login')
    p=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--serve'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    p.communicate(json.dumps({'cookie':cookie}).encode(),timeout=5)
    if p.returncode:raise ValueError('Session channel did not start')

def serve(cookie):
    fd=os.open(DIRECTORY,os.O_RDONLY|os.O_NOFOLLOW); st=os.fstat(fd);os.close(fd)
    if st.st_uid!=os.getuid() or st.st_mode&0o077:raise ValueError('Unsafe channel directory')
    opener=urllib.request.build_opener(SameOrigin())
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    sock.bind(str(SOCKET));os.chmod(SOCKET,0o600);sock.listen(1);sock.settimeout(10)
    try:
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            try: conn,_=sock.accept()
            except socket.timeout:continue
            with conn:
                conn.settimeout(5)
                try:
                    import runpy
                    message=json.loads(conn.recv(8192))
                    handler=runpy.run_path(str(Path(__file__).resolve()),run_name='kvpn_session_handler')
                    value=handler['fetch'](cookie,message)
                except Exception as error:value={'error':type(error).__name__}
                conn.sendall(json.dumps(value).encode())
    finally:
        sock.close();SOCKET.unlink(missing_ok=True)


def fetch(cookie,message):
    opener=urllib.request.build_opener(SameOrigin())
    path=message['path']
    method=message.get('method','GET')
    parsed=urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith('/'):
        raise ValueError('Path outside diagnostic scope')
    action = method != 'GET' or any(x in path.lower() for x in ('logout','logoff','signout','extend','delete'))
    if action:
        policy_path=DIRECTORY/'verified-extension-request.json'
        with policy_path.open() as f:policy=json.load(f)
        if (path,method)!=(policy.get('path'),policy.get('method')):
            raise ValueError('Unverified action refused')
    if method not in ('GET','POST'):raise ValueError('Method refused')
    payload=urllib.parse.urlencode(message.get('data') or {}).encode() if method=='POST' else None
    req=urllib.request.Request(BASE+path,data=payload,method=method,headers={'Cookie':'DSID='+cookie})
    with opener.open(req,timeout=15) as response:
        body=response.read(16000000).decode('utf-8','replace')
        value={'url':response.url,'body':body,'status':response.status}
    return value

if __name__=='__main__' and sys.argv[1:]==['--serve']:
    payload=json.load(sys.stdin)
    if os.fork():sys.exit(0)
    os.setsid()
    if os.fork():os._exit(0)
    serve(payload['cookie'])
