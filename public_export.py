"""Opt-in, read-only public projection. Website requests never reach FPP."""
import copy
import json
import math
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

PUBLIC_DEFAULTS = dict(public_dashboard_enabled=False, public_dashboard_url='', public_dashboard_key='')

def validate_public_settings(c):
    if type(c['public_dashboard_enabled']) is not bool:
        raise ValueError('public_dashboard_enabled must be true or false')
    url, key = c['public_dashboard_url'], c['public_dashboard_key']
    if not isinstance(url, str) or not isinstance(key, str):
        raise ValueError('Dashboard URL and upload key must be text')
    if url:
        u = urlsplit(url)
        if (u.scheme != 'https' or u.hostname not in ('lightsonelizabeth.com', 'www.lightsonelizabeth.com', 'linrob.net', 'www.linrob.net')
                or u.port not in (None, 443) or u.username or u.password or u.query or u.fragment
                or not u.path.endswith('/api.php')):
            raise ValueError('Use the final HTTPS /aircraft/api.php URL on lightsonelizabeth.com or linrob.net (www is also allowed); redirects are not followed')
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', key):
        raise ValueError('Upload key must contain 32–128 letters, digits, underscores or hyphens')
    if c['public_dashboard_enabled'] and (not url or not key or c['latitude'] is None or c['longitude'] is None):
        raise ValueError('Set dashboard URL, upload key and display coordinates before publishing')

def finite(value, low, high):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None

def public_snapshot(s, now=None):
    """Allowlist only; never include raw receiver errors, local URLs or secrets."""
    now = time.time() if now is None else now
    c = s['config']
    observed = s.get('updated', now)
    monitor_fresh = 'updated' in s and 0 <= now-observed < 3
    aircraft = []
    for a in s.get('aircraft', [])[:100]:
        lat, lon = finite(a.get('latitude'), -90, 90), finite(a.get('longitude'), -180, 180)
        aircraft.append(dict(hex=str(a['hex'])[:24], flight=str(a.get('flight', ''))[:32],
                             latitude=lat, longitude=lon,
                             distance_km=finite(a.get('distance_km'), 0, 21000),
                             position_age_s=finite(a.get('position_age_s'), 0, 1e9),
                             altitude_ft=finite(a.get('altitude_ft'), -2000, 100000),
                             speed_kt=finite(a.get('speed_kt'), 0, 2000),
                             track_deg=finite(a.get('track_deg'), 0, 360),
                             fresh=bool(a.get('fresh')), inside_zone=bool(a.get('inside_zone')),
                             blocking=bool(a.get('blocking')),
                             ignored=bool(a.get('stale_ignored') or a.get('position_ignored'))))
    reason = s.get('reason', '')
    if reason == 'Manual blackout': reason_code = 'manual'
    elif not s.get('receiver_ok', False): reason_code = 'receiver_fault'
    elif reason.startswith('Aircraft inside'): reason_code = 'aircraft_inside'
    elif s.get('fault_latched'): reason_code = 'position_fault'
    elif reason.startswith('Clear hold:'): reason_code = 'clear_delay'
    else: reason_code = 'clear'
    return dict(schema=1, observed_at=observed, monitor_fresh=monitor_fresh,
                zone=dict(latitude=c['latitude'], longitude=c['longitude'], radius_km=c['radius_km']),
                enforcement_enabled=c['enforce'], blackout_requested=bool(s.get('blocked', True)),
                receiver_ok=bool(s.get('receiver_ok')), native_hook_fresh=bool(s.get('native', {}).get('heartbeat_fresh')),
                reason_code=reason_code, aircraft_count=s.get('aircraft_counts', {}).get('received', len(aircraft)),
                inside_zone_count=s.get('aircraft_counts', {}).get('inside', sum(a['fresh'] and a['inside_zone'] for a in aircraft)), aircraft=aircraft)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirect refused')

class PublicPublisher:
    """Separate worker: slow website/TLS/DNS cannot delay DMX permission renewal."""
    def __init__(self, app):
        self.app = app
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.status = dict(last_success=None, result='Disabled')
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.thread = None

    def snapshot(self):
        with self.lock: return copy.deepcopy(self.status)

    def once(self):
        s = self.app.snapshot()
        c = s['config']
        if not c['public_dashboard_enabled']:
            with self.lock: self.status['result'] = 'Disabled'
            return
        try:
            body = json.dumps(public_snapshot(s), allow_nan=False).encode()
            req = Request(c['public_dashboard_url'], data=body, method='POST', headers={
                'Authorization': 'Bearer '+c['public_dashboard_key'], 'Content-Type': 'application/json',
                'User-Agent': 'LightsOnElizabeth-AircraftDashboard/1.0'})
            with self.opener.open(req, timeout=3) as response:
                if response.status != 200 or json.loads(response.read(4096)).get('ok') is not True:
                    raise ValueError('Upload rejected')
            with self.lock: self.status = dict(last_success=time.time(), result='Published')
        except Exception:
            # URLs, credentials and server error bodies must not leak into logs or public status.
            with self.lock: self.status['result'] = 'Upload failed; check website URL, key and hosting'

    def start(self):
        def run():
            while not self.stop.is_set():
                self.once()
                self.stop.wait(10)
        self.thread = threading.Thread(target=run, daemon=True, name='aircraft-public-upload')
        self.thread.start()
