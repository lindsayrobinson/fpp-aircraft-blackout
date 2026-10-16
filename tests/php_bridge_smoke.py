"""Exercise the integrated FPP page/bridge against the real Python monitor.

Requires PHP CLI (set PHP_BIN if it is not on PATH). A small wrapper simulates
FPP's plugin.php include and configDirectory without requiring a live FPP host.
"""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
php = os.environ.get('PHP_BIN', 'php')

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

with tempfile.TemporaryDirectory() as temporary:
    tmp = Path(temporary)
    cfg = tmp/'config'
    doc = tmp/'www'
    doc.mkdir()
    entry = json.dumps(str(root/'index.php'))
    config_dir = json.dumps(str(cfg))
    (doc/'plugin.php').write_text('<?php $settings = array("configDirectory" => '+config_dir+'); if (!isset($_GET["nopage"])) { echo "<!doctype html><html><head><title>FPP</title></head><body><nav>FPP menu</nav>"; } include '+entry+'; if (!isset($_GET["nopage"])) { echo "</body></html>"; }')
    port = free_port()
    url = f'http://127.0.0.1:{port}/plugin.php?plugin=fpp-aircraft-blackout&page=index.php'
    monitor = subprocess.Popen([sys.executable, str(root/'monitor.py'), '--config-dir', str(cfg), '--runtime-dir', str(tmp/'runtime')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    server = subprocess.Popen([php, '-n', '-d', 'output_buffering=4096', '-S', f'127.0.0.1:{port}', '-t', str(doc)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if monitor.poll() is not None:
                    raise AssertionError('Monitor process exited during startup')
                # The key is written before the HTTP listener starts. Wait for
                # the listener, not merely for the page to find that key.
                try:
                    urlopen('http://127.0.0.1:32380/api/status', timeout=1)
                except HTTPError as error:
                    if error.code != 401:
                        raise
                html = urlopen(url, timeout=1).read().decode()
                if '__BLACKOUT_CONFIG__' not in html and 'const ui=' in html: break
            except OSError: pass
            time.sleep(.05)
        else: raise AssertionError('Integrated page did not start')
        ui = json.loads(re.search(r'const ui=(\{.*?\});', html).group(1))
        key = (cfg/'aircraft-blackout.key').read_text().strip()
        assert key not in html, 'Internal monitor credential leaked into the page'
        assert 'FPP menu' in html and 'ab-radius_km' in html and 'ab-latitude' in html
        assert html.lower().count('<!doctype') == 1, 'Nested standalone page in FPP'
        assert '127.0.0.1:32380' not in html, 'Browser directly accesses backend'
        endpoint = f'http://127.0.0.1:{port}/'+ui['endpoint']
        def api(action, body=None, token=ui['token']):
            headers={'X-Aircraft-Token': token}
            if body is not None: headers['Content-Type']='application/json'
            req=Request(endpoint+action,data=None if body is None else json.dumps(body).encode(),headers=headers)
            with urlopen(req,timeout=4) as r: return json.load(r)
        def denied(action,body=None,token=ui['token'],code=403):
            try: api(action,body,token);raise AssertionError('Unsafe request allowed')
            except HTTPError as e: assert e.code==code, (e.code, e.read())
        s=api('status')
        c=s['config']
        c.update(latitude=-27.25,longitude=153.1,radius_km=20,blackout_on_stale_positions=False,ignore_aircraft_without_position=True,channels=[{'channel':8,'value':0}])
        assert api('config',c)['ok']
        s=api('status')
        assert s['config']['radius_km']==20
        assert s['config']['blackout_on_stale_positions'] is False
        assert 'ab-blackout_on_stale_positions' in html
        assert s['config']['ignore_aircraft_without_position'] is True
        assert 'ab-ignore_aircraft_without_position' in html
        assert json.loads((cfg/'aircraft-blackout.json').read_text())['ignore_aircraft_without_position'] is True
        assert json.loads((cfg/'aircraft-blackout.json').read_text())['latitude']==-27.25
        assert api('manual',{'blackout':True})['ok']
        assert api('status')['config']['manual_blackout']
        assert api('manual',{'blackout':False})['ok']
        denied('status',token='')
        denied('config',c,token='tampered')
        denied('status',{},code=405)
        denied('unknown',code=404)
        denied('acknowledge',{},code=400) # Receiver is unconfigured; cannot bypass fault.
        denied('config',{**c,'radius_km':-1},code=400)
        # Expired signed token must be rejected even though it has a correct HMAC.
        import hashlib,hmac
        stamp=str(int(time.time())-7201);nonce='a'*32;payload=stamp+':'+nonce
        old=payload+':'+hmac.new(key.encode(),payload.encode(),hashlib.sha256).hexdigest()
        denied('status',token=old)
        monitor.terminate();monitor.wait(timeout=5)
        denied('status',code=502)
        print('FPP PHP integration passed: embedded controls, no key disclosure, status, persisted location/radius/channels, manual controls, validation, token protection, method restrictions and unavailable-monitor errors.')
    finally:
        for p in (monitor,server):
            if p.poll() is None: p.terminate();p.wait(timeout=5)
