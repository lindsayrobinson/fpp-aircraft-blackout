import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('monitor', Path(__file__).resolve().parents[1]/'monitor.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def config():
    c=copy.deepcopy(m.DEFAULT)
    c.update(receiver_url='http://192.168.1.50:8080/data/aircraft.json', latitude=-27.25, longitude=153.1,
             clear_delay_s=2, channels=[dict(channel=101,value=0),dict(channel=102,value=8)])
    return c

def plane(lon=153.1, **extra):
    return dict(hex='abc123',lat=-27.25,lon=lon,seen_pos=0,**extra)

def feed(*aircraft, stamp=100):
    return dict(now=stamp, aircraft=list(aircraft))

class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.d=m.Detector(); self.c=config()
    def run_feed(self, data, t=0, wall=100):
        return self.d.evaluate(data,self.c,wall,t)[0]
    def test_radius_and_location(self):
        self.assertAlmostEqual(m.distance_km(0,0,0,1),111.195,places=2)
        self.assertTrue(self.run_feed(feed(plane())))
        self.assertTrue(self.run_feed(feed(plane(lon=154)),1))
        self.assertFalse(self.run_feed(feed(plane(lon=154)),3))
    def test_clear_hold_startup(self):
        self.assertTrue(self.run_feed(feed(),0))
        self.assertFalse(self.run_feed(feed(stamp=102),2,102))
    def test_configurable_distance(self):
        self.c['radius_km']=1
        self.run_feed(feed(plane(lon=153.15)),0)
        self.assertFalse(self.run_feed(feed(plane(lon=153.15)),2))
        self.c['radius_km']=15
        self.assertTrue(self.run_feed(feed(plane(lon=153.15)),3))
    def test_lost_track_remains_blocked(self):
        self.run_feed(feed(plane()))
        self.assertTrue(self.run_feed(feed(stamp=101),1,101))
        self.assertTrue(self.run_feed(feed(stamp=1100),1000,1100))
        self.assertTrue(self.d.fault_latched)
    def test_fault_ack_does_not_bypass_current_aircraft(self):
        self.d.fault(); self.d.acknowledge()
        self.assertTrue(self.run_feed(feed(plane())))
        self.assertTrue(self.d.fault_latched)
    def test_fault_ack_requires_fresh_clear_hold(self):
        self.d.fault(); self.d.acknowledge()
        self.assertTrue(self.run_feed(feed(),0))
        self.assertFalse(self.run_feed(feed(stamp=102),2,102))
    def test_unknown_position_blocks_even_with_ack(self):
        self.d.acknowledge()
        self.assertTrue(self.run_feed(feed({'hex':'abc'})))
    def test_unknown_position_is_visible_and_explains_disabled_ack(self):
        self.c['blackout_on_stale_positions']=False
        blocked,reason,rows=self.d.evaluate(feed({'hex':'abc'}),self.c,100,0)
        self.assertTrue(blocked)
        self.assertFalse(self.d.can_ack)
        self.assertIn('missing, invalid or stale',reason)
        self.assertIn('missing coordinates',self.d.acknowledge_reason)
        self.assertEqual(rows[0]['hex'],'abc')
        self.assertIsNone(rows[0]['distance_km'])
        self.assertTrue(rows[0]['blocking'])
        self.assertIn('No usable position',rows[0]['position_status'])
    def test_resolved_unknown_position_enables_ack_and_clear_delay(self):
        self.run_feed(feed({'hex':'abc'}))
        self.assertTrue(self.run_feed(feed(stamp=101),1,101))
        self.assertTrue(self.d.can_ack)
        self.assertIn('permits acknowledgement',self.d.acknowledge_reason)
        self.d.acknowledge()
        self.assertTrue(self.run_feed(feed(stamp=102),2,102))
        self.assertFalse(self.run_feed(feed(stamp=104),4,104))
    def test_ignored_stale_does_not_hide_positionless_aircraft(self):
        self.c['blackout_on_stale_positions']=False
        old=plane(lon=154);old['seen_pos']=20
        blocked,_,rows=self.d.evaluate(feed(old,{'hex':'unknown'}),self.c,100,0)
        self.assertTrue(blocked)
        self.assertFalse(self.d.can_ack)
        self.assertEqual(rows[0]['hex'],'unknown')
        self.assertTrue(rows[1]['stale_ignored'])
    def test_feed_fault_disables_ack_after_previous_recovery(self):
        self.d.fault();self.run_feed(feed())
        self.assertTrue(self.d.can_ack)
        self.d.fault()
        self.assertFalse(self.d.can_ack)
        self.assertIn('Receiver data must be valid',self.d.acknowledge_reason)
    def test_stale_feed_and_future_time_rejected(self):
        for stamp in [90,110,float('nan')]:
            with self.assertRaises(ValueError): self.run_feed(feed(stamp=stamp))
    def test_frozen_feed_rejected(self):
        self.run_feed(feed(),0)
        with self.assertRaises(ValueError): self.run_feed(feed(),5)
    def test_old_positions_block(self):
        a=plane();a['seen_pos']=9
        self.assertTrue(self.run_feed(feed(a)))
    def test_stale_option_disabled_allows_clear_after_hold(self):
        self.c['blackout_on_stale_positions']=False
        a=plane();a['seen_pos']=9
        self.assertTrue(self.run_feed(feed(a),0))
        self.assertFalse(self.run_feed(feed(a,stamp=102),2,102))
        self.assertFalse(self.d.fault_latched)
    def test_ignored_stale_row_is_labelled(self):
        self.c['blackout_on_stale_positions']=False
        a=plane();a['seen_pos']=9
        _,_,rows=self.d.evaluate(feed(a),self.c,100,0)
        self.assertTrue(rows[0]['stale_ignored'])
        self.assertFalse(rows[0]['fresh'])
    def test_stale_option_disabled_ignores_previous_inside_position(self):
        self.run_feed(feed(plane()),0)
        self.c['blackout_on_stale_positions']=False
        a=plane();a['seen_pos']=9
        self.assertTrue(self.run_feed(feed(a,stamp=101),1,101))
        self.assertFalse(self.run_feed(feed(a,stamp=103),3,103))
    def test_stale_option_disabled_still_blocks_missing_positions(self):
        self.c['blackout_on_stale_positions']=False
        self.assertTrue(self.run_feed(feed({'hex':'abc'})))
    def test_stale_option_disabled_still_blocks_fresh_aircraft(self):
        self.c['blackout_on_stale_positions']=False
        self.assertTrue(self.run_feed(feed(plane())))
    def test_stale_option_disabled_still_blocks_completely_lost_tracks(self):
        self.c['blackout_on_stale_positions']=False
        self.run_feed(feed(plane()))
        self.assertTrue(self.run_feed(feed(stamp=101),1,101))
        self.assertTrue(self.d.fault_latched)
    def test_stale_option_disabled_does_not_clear_existing_fault_latch(self):
        a=plane();a['seen_pos']=9
        self.run_feed(feed(a))
        self.c['blackout_on_stale_positions']=False
        self.assertTrue(self.run_feed(feed(a,stamp=101),1,101))
        self.assertTrue(self.d.can_ack)
        self.d.acknowledge()
        self.assertTrue(self.run_feed(feed(a,stamp=102),2,102))
        self.assertFalse(self.run_feed(feed(a,stamp=104),4,104))
    def test_reenabling_stale_option_blocks_again(self):
        self.c['blackout_on_stale_positions']=False
        a=plane();a['seen_pos']=9
        self.run_feed(feed(a))
        self.c['blackout_on_stale_positions']=True
        self.assertTrue(self.run_feed(feed(a,stamp=102),2,102))
    def test_all_aircraft_must_clear(self):
        b=plane();b['hex']='def456'
        self.run_feed(feed(plane(),b))
        self.assertTrue(self.run_feed(feed(plane(lon=154),b),1))
    def test_altitude_does_not_exclude_aircraft(self):
        self.assertTrue(self.run_feed(feed(plane(alt_baro=45000))))

class ConfigTests(unittest.TestCase):
    def test_defaults_and_valid_config(self):
        self.assertEqual(m.validate({})['radius_km'],15)
        self.assertFalse(m.validate({})['enforce'])
        self.assertEqual(m.validate(config())['latitude'],-27.25)
        self.assertTrue(m.validate({})['blackout_on_stale_positions'])
        old=config();old.pop('blackout_on_stale_positions')
        self.assertTrue(m.validate(old)['blackout_on_stale_positions'])
        self.assertFalse(m.validate({'blackout_on_stale_positions':False})['blackout_on_stale_positions'])
        with self.assertRaises(ValueError):m.validate({'blackout_on_stale_positions':'false'})
    def test_invalid_settings(self):
        for key,value in [('latitude',91),('longitude',181),('radius_km',0),('radius_km',float('nan')),('enforce','yes'),('channels',[{'channel':0,'value':0}]),('channels',[{'channel':1,'value':256}]),('receiver_url','http://8.8.8.8/data/aircraft.json'),('receiver_url','http://receiver.local/data/aircraft.json')]:
            c=config();c[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):m.validate(c)
    def test_duplicate_channels(self):
        c=config();c['channels']*=2
        with self.assertRaises(ValueError):m.validate(c)
    def test_enforcement_requires_configuration(self):
        with self.assertRaises(ValueError):m.validate({'enforce':True})
    def test_save_blocks_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=m.App(Path(tmp)/'config',Path(tmp)/'run')
            c=config();c['enforce']=True;a.save(c)
            self.assertEqual(json.loads(a.config_path.read_text()),m.validate(c))
            self.assertEqual((a.runtime/'snapshot').read_text().splitlines()[0].split()[3],'0')
            self.assertEqual(a.native_path.read_text(),(a.runtime/'snapshot').read_text())
            previous=a.native_path.stat().st_mtime_ns
            a.publish(True)
            self.assertEqual(previous,a.native_path.stat().st_mtime_ns)
            b=m.App(Path(tmp)/'config',Path(tmp)/'run')
            self.assertEqual((b.runtime/'snapshot').read_text().splitlines()[0].split()[3],'0')
    def test_manual_blackout_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=m.App(Path(tmp)/'config',Path(tmp)/'run');c=config();c['manual_blackout']=True;a.save(c)
            b=m.App(Path(tmp)/'config',Path(tmp)/'run')
            self.assertTrue(b.config['manual_blackout'])
    def test_network_failure_revokes_permit(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=m.App(Path(tmp)/'config',Path(tmp)/'run');a.save(config());a.publish(True)
            with patch.object(a.opener,'open',side_effect=OSError('Disconnected')):a.poll()
            self.assertTrue(a.status['blocked'])
            self.assertTrue(a.detector.fault_latched)
            self.assertEqual((a.runtime/'snapshot').read_text().splitlines()[0].split()[3],'0')

if __name__=='__main__':unittest.main()
