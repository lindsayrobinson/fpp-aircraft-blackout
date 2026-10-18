import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor as m
from public_export import public_snapshot

class PublicExportTests(unittest.TestCase):
    def config(self):
        return {**copy.deepcopy(m.DEFAULT), 'receiver_url':'http://192.168.1.50/data/aircraft.json', 'latitude':-27.25,'longitude':153.1,'public_dashboard_url':'https://lightsonelizabeth.com/aircraft/api.php','public_dashboard_key':'a'*64}

    def test_defaults_validation_and_saved_preference(self):
        self.assertFalse(m.validate({})['public_dashboard_enabled'])
        for values in ({'public_dashboard_enabled':True}, {'public_dashboard_enabled':'true'}, {'public_dashboard_url':'http://lightsonelizabeth.com/aircraft/api.php'}, {'public_dashboard_url':'https://example.com/aircraft/api.php'}, {'public_dashboard_url':'https://lightsonelizabeth.com@evil.com/api.php'}, {'public_dashboard_url':'https://lightsonelizabeth.com/api.php?token=secret'}, {'public_dashboard_key':'short'}):
            with self.subTest(values=values),self.assertRaises(ValueError): m.validate(values)
        c=self.config();c['public_dashboard_enabled']=True
        with tempfile.TemporaryDirectory() as tmp:
            app=m.App(Path(tmp)/'cfg',Path(tmp)/'run');app.save(c)
            self.assertTrue(m.App(Path(tmp)/'cfg',Path(tmp)/'run').config['public_dashboard_enabled'])

    def test_projection_hides_secrets_and_raw_errors(self):
        s=dict(config=self.config(),updated=100,blocked=True,receiver_ok=False,reason='Receiver fault: private URL and credential',native={},aircraft=[])
        data=public_snapshot(s,100);wire=json.dumps(data)
        for secret in ('192.168.1.50', 'a'*64, 'channels', 'receiver_url', 'private URL'):self.assertNotIn(secret,wire)
        self.assertEqual(data['reason_code'],'receiver_fault')
        self.assertFalse(public_snapshot(s,104)['monitor_fresh'])
        self.assertFalse(public_snapshot(s,99)['monitor_fresh'])

    def test_plane_details_and_zone_counts_do_not_change_detection(self):
        c=self.config();d=m.Detector()
        planes=[dict(hex=f'{i:06x}',lat=-27.25,lon=153.1,seen_pos=0,alt_baro=10000,gs=250,track=90) for i in range(105)]
        blocked,reason,rows=d.evaluate(dict(now=100,aircraft=planes),c,100,0)
        self.assertTrue(blocked);self.assertEqual(len(rows),100)
        self.assertEqual(d.aircraft_counts,dict(received=105,inside=105))
        data=public_snapshot(dict(config=c,updated=100,blocked=blocked,reason=reason,receiver_ok=True,aircraft=rows,aircraft_counts=d.aircraft_counts),100)
        self.assertEqual(data['inside_zone_count'],105)
        self.assertEqual(data['aircraft'][0]['altitude_ft'],10000)
        self.assertEqual(data['aircraft'][0]['latitude'],-27.25)
        self.assertTrue(data['aircraft'][0]['inside_zone'])

    def test_worker_disabled_and_failed_upload_cannot_change_local_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=m.App(Path(tmp)/'cfg',Path(tmp)/'run');c=self.config();app.save(c)
            with patch.object(app.public_publisher.opener,'open') as upload:
                app.public_publisher.once();upload.assert_not_called()
            c['public_dashboard_enabled']=True;app.save(c)
            before=(app.runtime/'snapshot').read_text()
            with patch.object(app.public_publisher.opener,'open',side_effect=OSError('secret internal error')):
                app.public_publisher.once()
            self.assertEqual(before,(app.runtime/'snapshot').read_text())
            self.assertNotIn('secret',app.public_publisher.snapshot()['result'])

    def test_upload_is_projection_not_config_and_uses_bearer_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=m.App(Path(tmp)/'cfg',Path(tmp)/'run');c=self.config();c['public_dashboard_enabled']=True;app.save(c)
            class Response:
                status=200
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self,*a):return b'{"ok":true}'
            with patch.object(app.public_publisher.opener,'open',return_value=Response()) as upload:
                app.public_publisher.once()
            request=upload.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'),'Bearer '+c['public_dashboard_key'])
            self.assertNotIn('public_dashboard_key',request.data.decode())
            self.assertEqual(app.public_publisher.snapshot()['result'],'Published')

if __name__=='__main__':unittest.main()
