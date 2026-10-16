"""Integration check: real receiver HTTP, monitor process and authenticated panel API."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

class Receiver(BaseHTTPRequestHandler):
    aircraft=[]
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200);self.end_headers()
        self.wfile.write(json.dumps({'now':time.time(),'aircraft':self.aircraft}).encode())

rx=ThreadingHTTPServer(('127.0.0.1',0),Receiver)
threading.Thread(target=rx.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); cfg=root/'config'; run=root/'run'
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    p=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'monitor.py'),
                        '--config-dir',str(cfg),'--runtime-dir',str(run),'--host','127.0.0.1','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        base=f'http://127.0.0.1:{port}'
        for _ in range(100):
            if (cfg/'aircraft-blackout.key').exists():
                try:
                    urlopen(base,timeout=.1)
                except HTTPError as e:
                    if e.code==401: break
                except OSError: pass
            time.sleep(.05)
        else:raise AssertionError('Monitor failed to start')
        token=base64.b64encode(('admin:'+(cfg/'aircraft-blackout.key').read_text()).encode()).decode()
        def api(path, body=None, csrf=True):
            headers={'Authorization':'Basic '+token}
            if body is not None:
                headers.update({'Content-Type':'application/json'})
                if csrf: headers['X-Blackout-UI']='1'
            request=Request(base+'/api/'+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
            with urlopen(request,timeout=3) as r:return json.load(r)
        def wait_for(test, description):
            for _ in range(80):
                s=api('status')
                if test(s): return s
                time.sleep(.1)
            raise AssertionError(description+': '+str(s))
        c=api('status')['config']
        c.update(receiver_url=f'http://127.0.0.1:{rx.server_port}/data/aircraft.json',latitude=-27.25,longitude=153.1,clear_delay_s=1,enforce=True,channels=[{'channel':101,'value':0}])
        try:api('config',c,csrf=False);raise AssertionError('Cross-site write accepted')
        except HTTPError as e:assert e.code==400
        api('config',c)
        s=wait_for(lambda s:s.get('can_acknowledge',False) or not s['blocked'],'Receiver recovery')
        if s['blocked']:api('acknowledge',{})
        wait_for(lambda s:not s['blocked'],'Clear hold failed')
        assert (run/'snapshot').read_text().split()[3]=='1'
        Receiver.aircraft=[dict(hex='abc123',lat=-27.25,lon=153.1,seen_pos=0)]
        wait_for(lambda s:s['blocked'] and 'Aircraft inside' in s['reason'],'Aircraft did not trigger')
        Receiver.aircraft=[]
        wait_for(lambda s:s.get('fault_latched',False),'Lost track not latched')
        api('acknowledge',{})
        wait_for(lambda s:not s['blocked'],'Acknowledgement/clear hold failed')
        api('manual',{'blackout':True})
        wait_for(lambda s:s['reason']=='Manual blackout','Manual command failed')
        assert (run/'snapshot').read_text().split()[3]=='0'
        assert json.loads((cfg/'aircraft-blackout.json').read_text())['manual_blackout']
        print('HTTP integration passed: authentication, write protection, settings, receiver, clear hold, aircraft blackout, lost-track latch, acknowledgement and manual blackout.')
    finally:
        p.terminate();p.wait(timeout=5)
        rx.shutdown()
