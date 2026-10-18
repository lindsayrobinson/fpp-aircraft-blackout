"""Run the public PHP endpoint against a temporary web root/private config."""
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import monitor as m
from public_export import public_snapshot
root=Path(__file__).resolve().parents[1]
php=os.environ.get('PHP_BIN','php')
with tempfile.TemporaryDirectory() as directory:
    tmp=Path(directory);doc=tmp/'www';shutil.copytree(root/'public-dashboard',doc)
    token='b'*64
    cfg=tmp/'aircraft-dashboard-config.php'
    cfg.write_text('<?php return '+"array('token'=>'"+token+"','data_file'=>__DIR__.'/data.json');")
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    proc=subprocess.Popen([php,'-n','-S',f'127.0.0.1:{port}','-t',str(doc)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{port}/api.php'
    def request(body=None,key=token,method=None,expected=200):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key}
        req=Request(url,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
        try:
            with urlopen(req,timeout=3) as response:
                assert response.status==expected
                assert response.headers['Cache-Control'].startswith('no-store')
                return json.load(response)
        except HTTPError as exc:
            assert exc.code==expected,(exc.code,exc.read())
    try:
        for _ in range(100):
            try:request();break
            except OSError:time.sleep(.03)
        assert request()['fresh'] is False
        c=copy.deepcopy(m.DEFAULT);c.update(latitude=-27.25,longitude=153.1)
        s=public_snapshot(dict(config=c,updated=time.time(),blocked=False,receiver_ok=True,reason='No tracked aircraft',aircraft=[]))
        request(s,key='bad',expected=401)
        assert request()['fresh'] is False
        s['config']={'secret':'must be discarded'}
        assert request(s)['ok']
        data=request();assert data['fresh'] and not data['snapshot']['blackout_requested']
        assert 'config' not in data['snapshot']
        assert request(method='DELETE',expected=405) is None
        old=copy.deepcopy(s);old['observed_at']-=40;request(old,expected=400)
        invalid=copy.deepcopy(s);invalid['zone']['radius_km']=-1;request(invalid,expected=400)
        older=copy.deepcopy(s);older['observed_at']-=1;request(older,expected=409)
        assert request()['snapshot']['observed_at']==s['observed_at']
        stored=json.loads((tmp/'data.json').read_text());stored['received_at']-=35;stored['snapshot']['observed_at']-=35;(tmp/'data.json').write_text(json.dumps(stored))
        data=request();assert data['fresh'] is False and data['snapshot'] is None
        s['observed_at']=time.time();s['monitor_fresh']=False;assert request(s)['ok'];assert request()['snapshot'] is None
        assert urlopen(f'http://127.0.0.1:{port}/index.html').status==200
        assert urlopen(f'http://127.0.0.1:{port}/dashboard.js').status==200
        print('Public PHP dashboard passed: authentication, allowlist, expiry, stale-monitor handling, out-of-order updates, invalid payloads, no-cache and page assets.')
    finally:proc.terminate();proc.wait(timeout=5)
