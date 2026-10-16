#!/usr/bin/env python3
"""Local ADS-B monitor and settings UI. Standard library only; Linux/FPP."""
import argparse
import base64
import copy
import hmac
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

MAX_CHANNEL = 8192 * 1024
DEFAULT = dict(receiver_url='', latitude=None, longitude=None, radius_km=15.0,
               clear_delay_s=60.0, max_feed_age_s=5.0, max_position_age_s=5.0,
               blackout_on_stale_positions=True, ignore_aircraft_without_position=False,
               enforce=False, manual_blackout=False, channels=[])
LOG = logging.getLogger('aircraft-blackout')


def boottime_ms():
    return int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000)


def atomic_write(path, data, mode=0o640):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w') as f:
        os.fchmod(f.fileno(), mode)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name}: enter a number between {low} and {high}')
    return float(value)


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT):
        raise ValueError('Invalid settings fields')
    c = copy.deepcopy(DEFAULT)
    c.update(raw)
    for name in ('enforce', 'manual_blackout', 'blackout_on_stale_positions', 'ignore_aircraft_without_position'):
        if type(c[name]) is not bool:
            raise ValueError(f'{name} must be true or false')
    u = urlsplit(c['receiver_url'])
    # Literal private IP only: avoids DNS changes, proxies and inadvertent cloud feeds.
    if c['receiver_url']:
        try:
            ip = ipaddress.ip_address(u.hostname)
            port = u.port
        except ValueError as e:
            raise ValueError('Receiver URL must use a local IP address') from e
        if u.scheme != 'http' or not (ip.is_private and not ip.is_unspecified and not ip.is_multicast) or u.username or u.password or u.fragment:
            raise ValueError('Use an http:// URL with a private/local receiver IP, without credentials')
    for name, lo, hi in [('latitude', -90, 90), ('longitude', -180, 180)]:
        if c[name] is not None:
            c[name] = number(c[name], name, lo, hi)
    for name, lo, hi in [('radius_km', .1, 300), ('clear_delay_s', 1, 3600),
                         ('max_feed_age_s', 1, 10), ('max_position_age_s', 1, 30)]:
        c[name] = number(c[name], name, lo, hi)
    if not isinstance(c['channels'], list) or len(c['channels']) > 1024:
        raise ValueError('Enter at most 1024 blackout channel overrides')
    seen = set()
    for row in c['channels']:
        if not isinstance(row, dict) or set(row) != {'channel', 'value'}:
            raise ValueError('Each override needs channel and value')
        ch, val = row['channel'], row['value']
        if type(ch) is not int or not 1 <= ch <= MAX_CHANNEL or ch in seen:
            raise ValueError('Channels must be unique FPP absolute channel numbers (1–8388608)')
        if type(val) is not int or not 0 <= val <= 255:
            raise ValueError('Blackout values must be integers 0–255')
        seen.add(ch)
    if c['enforce'] and (not c['channels'] or not c['receiver_url'] or c['latitude'] is None or c['longitude'] is None):
        raise ValueError('Set receiver URL, display coordinates and blackout channels before enabling enforcement')
    return c


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    x = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, x))))


class Detector:
    """Latch unknown/stale nearby tracks until positively seen outside the zone."""
    def __init__(self):
        self.hazards = set()
        self.clear_since = None
        self.fault_latched = False
        self.fault_generation = 0
        self.pending_ack = None
        self.last_feed_now = None
        self.last_feed_advance = None
        self.latest_blocked = True
        self.can_ack = False
        self.acknowledge_reason = 'Waiting for valid receiver data before acknowledgement is available'

    def fault(self):
        if not self.fault_latched:
            self.fault_generation += 1
        self.fault_latched = True
        self.clear_since = None
        self.latest_blocked = True
        self.can_ack = False
        self.acknowledge_reason = 'Receiver data must be valid and aircraft positions resolved before acknowledgement is available'

    def acknowledge(self):
        # Does not clear an actively detected hazard; faults after this request need a new acknowledgement.
        self.pending_ack = self.fault_generation

    def evaluate(self, feed, c, wall, mono):
        if not isinstance(feed, dict) or not isinstance(feed.get('aircraft'), list):
            raise ValueError('Missing aircraft list')
        stamp = number(feed.get('now'), 'feed timestamp', 0, 1e12)
        if stamp > wall + 2 or wall - stamp > c['max_feed_age_s']:
            raise ValueError('Receiver feed timestamp is stale or ahead of this FPP clock')
        if self.last_feed_now is not None and stamp < self.last_feed_now:
            raise ValueError('Receiver clock moved backwards')
        if self.last_feed_now != stamp:
            self.last_feed_now, self.last_feed_advance = stamp, mono
        elif mono - self.last_feed_advance >= c['max_feed_age_s']:
            raise ValueError('Receiver feed is frozen')
        active, unknown, aircraft = set(), set(), []
        fresh_outside = set()
        ignored_stale = set()
        ignored_positionless = set()
        for a in feed['aircraft']:
            if not isinstance(a, dict) or not isinstance(a.get('hex'), str) or not a['hex']:
                raise ValueError('Malformed aircraft record')
            ident = a['hex']
            lat, lon = a.get('lat'), a.get('lon')
            age = a.get('seen_pos')
            try:
                lat = number(lat, 'aircraft latitude', -90, 90)
                lon = number(lon, 'aircraft longitude', -180, 180)
                age = number(age, 'position age', 0, 1e9)
            except ValueError as exc:
                ignored = c['ignore_aircraft_without_position']
                if ignored:
                    ignored_positionless.add(ident)
                else:
                    unknown.add(ident)
                aircraft.append(dict(hex=ident, flight=str(a.get('flight', '')).strip(),
                                     distance_km=None, position_age_s=None, fresh=False,
                                     stale_ignored=False, position_ignored=ignored, blocking=not ignored,
                                     position_status=('No usable position — ignored: ' if ignored else 'No usable position: ') + str(exc).split(':')[0]))
                continue
            d = distance_km(c['latitude'], c['longitude'], lat, lon)
            fresh = age + max(0, wall-stamp) <= c['max_position_age_s']
            if not fresh:
                if c['blackout_on_stale_positions']:
                    unknown.add(ident)
                else:
                    ignored_stale.add(ident)
            elif d <= c['radius_km']:
                active.add(ident)
            else:
                fresh_outside.add(ident)
            position_status = ('Fresh position' if fresh else
                               'Stale position — ignored' if ident in ignored_stale else
                               'Stale position — blackout')
            aircraft.append(dict(hex=ident, flight=str(a.get('flight', '')).strip(), distance_km=round(d, 2), position_age_s=round(age, 1), fresh=fresh, stale_ignored=ident in ignored_stale, blocking=ident in active or ident in unknown, position_status=position_status))
        self.hazards -= fresh_outside
        # Explicit user policy: old coordinates are ignored even if the last
        # fresh position was inside the zone. An existing fault latch still
        # needs acknowledgement; completely lost tracks still block.
        self.hazards -= ignored_stale
        # Explicit policy also ignores a currently received positionless record,
        # including a previously nearby track. It does not prove the aircraft left.
        self.hazards -= ignored_positionless
        self.hazards |= active
        missing = self.hazards - active
        # Positionless local traffic cannot be proven outside the zone.
        if unknown or missing:
            self.fault()
        if self.pending_ack is not None:
            if self.pending_ack == self.fault_generation and not unknown and not active:
                self.hazards.clear()
                self.fault_latched = False
            self.pending_ack = None
        blocked = bool(active or unknown or self.hazards or self.fault_latched)
        if blocked:
            self.clear_since = None
            if active:
                reason = f'Aircraft inside exclusion zone: {len(active)}'
            elif unknown:
                reason = f'Blackout held: {len(unknown)} aircraft with missing, invalid or stale positions; see aircraft table'
            else:
                reason = 'Previous fault latched; inspect airspace, then acknowledge to begin the clear delay'
        else:
            if self.clear_since is None:
                self.clear_since = mono
            remaining = max(0, c['clear_delay_s'] - (mono-self.clear_since))
            blocked = remaining > 0
            reason = f'Clear hold: {remaining:.0f}s remaining' if blocked else 'No tracked aircraft in exclusion zone'
        self.can_ack = self.fault_latched and not unknown and not active
        if active:
            self.acknowledge_reason = 'Acknowledgement unavailable while aircraft are inside the exclusion zone'
        elif unknown:
            self.acknowledge_reason = 'Acknowledgement unavailable: resolve aircraft rows marked blackout or no usable position. Review the stale-position and ignore-aircraft-without-position settings.'
        elif self.can_ack:
            self.acknowledge_reason = 'Receiver data now permits acknowledgement. Check the airspace first; the clear delay still applies.'
        else:
            self.acknowledge_reason = 'No latched fault needs acknowledgement'
        self.latest_blocked = blocked
        return blocked, reason, sorted(aircraft, key=lambda a: (not a['blocking'], a['distance_km'] if a['distance_km'] is not None else -1))[:100]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Receiver redirects are not allowed')


class App:
    def __init__(self, directory, runtime='/run/aircraft-blackout'):
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.config_path = self.directory / 'aircraft-blackout.json'
        self.native_path = self.directory / 'aircraft-blackout.native'
        self.boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.detector = Detector()
        self.config = validate(json.loads(self.config_path.read_text())) if self.config_path.exists() else copy.deepcopy(DEFAULT)
        self.status = dict(blocked=True, reason='Starting', aircraft=[])
        key_path = self.directory / 'aircraft-blackout.key'
        if not key_path.exists():
            atomic_write(key_path, secrets.token_urlsafe(24), 0o600)
        self.key = key_path.read_text().strip()
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.publish(False, persistent=True)

    def publish(self, permit, persistent=False):
        c = self.config
        rows = [f'AB1 {self.boot_id} {boottime_ms()+3000} {int(permit)} {int(c["enforce"])} {len(c["channels"])}']
        rows += [f'{r["channel"]} {r["value"]}' for r in c['channels']]
        text = '\n'.join(rows)+'\n'
        if persistent:
            atomic_write(self.native_path, text)
        atomic_write(self.runtime / 'snapshot', text)

    def save(self, raw):
        c = validate(raw)
        with self.lock:
            atomic_write(self.config_path, json.dumps(c, indent=2)+'\n', 0o600)
            self.config = c
            # A settings change revokes permission and restarts the full clear hold.
            self.detector.clear_since = None
            self.publish(False, persistent=True)
            self.status = dict(blocked=True, reason='Settings changed; checking receiver', aircraft=[])
        LOG.info('Settings changed; enforcement=%s, channels=%d', c['enforce'], len(c['channels']))

    def poll(self):
        with self.lock:
            c = copy.deepcopy(self.config)
        feed, error = None, None
        try:
            if not c['receiver_url'] or c['latitude'] is None or c['longitude'] is None:
                raise ValueError('Configure the receiver URL and display coordinates')
            req = Request(c['receiver_url'], headers={'Cache-Control':'no-cache'})
            with self.opener.open(req, timeout=1) as response:
                data = response.read(4*1024*1024+1)
                if len(data) > 4*1024*1024:
                    raise ValueError('Aircraft feed is too large')
                feed = json.loads(data)
        except Exception as exc:
            error = str(exc)
        with self.lock:
            if c != self.config:
                return
            try:
                if error:
                    raise ValueError(error)
                blocked, reason, aircraft = self.detector.evaluate(feed, c, time.time(), time.monotonic())
            except Exception as exc:
                self.detector.fault()
                blocked, reason, aircraft = True, 'Receiver fault: '+str(exc), []
            if c['manual_blackout']:
                blocked, reason = True, 'Manual blackout'
            self.publish(not blocked)
            previous = self.status.get('reason')
            self.status = dict(blocked=blocked, reason=reason, aircraft=aircraft, updated=time.time(),
                               enforcement=c['enforce'], fault_latched=self.detector.fault_latched)
            if reason != previous and not reason.startswith('Clear hold:'):
                LOG.info('%s', reason)

    def snapshot(self):
        with self.lock:
            s = copy.deepcopy(self.status)
            s['config'] = copy.deepcopy(self.config)
            s['can_acknowledge'] = self.detector.can_ack
            s['acknowledge_reason'] = self.detector.acknowledge_reason
            try:
                native = json.loads((self.runtime / 'native-status.json').read_text())
                native['heartbeat_fresh'] = 0 <= boottime_ms()-native['heartbeat_ms'] < 3000
                s['native'] = native
            except (OSError, ValueError, KeyError):
                s['native'] = {'heartbeat_fresh':False}
            return s


def serve(app, host, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, code, data, content='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', content)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data if isinstance(data, bytes) else json.dumps(data).encode())
        def auth(self):
            expected = 'Basic '+base64.b64encode(('admin:'+app.key).encode()).decode()
            if not hmac.compare_digest(self.headers.get('Authorization',''), expected):
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Basic realm="Aircraft blackout"')
                self.end_headers()
                return False
            return True
        def do_GET(self):
            if not self.auth(): return
            if self.path == '/api/status': self.reply(200, app.snapshot())
            else: self.reply(404, {'error':'Not found'})
        def do_POST(self):
            if not self.auth(): return
            try:
                # Browsers cannot issue this cross-origin without a preflight, which we do not allow.
                if self.headers.get('X-Blackout-UI') != '1' or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Use the local settings panel')
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 128*1024: raise ValueError('Invalid request length')
                raw = json.loads(self.rfile.read(length))
                if self.path == '/api/config': app.save(raw)
                elif self.path == '/api/manual':
                    with app.lock:
                        if type(raw.get('blackout')) is not bool: raise ValueError('Invalid blackout value')
                        c = copy.deepcopy(app.config)
                        c['manual_blackout'] = raw['blackout']
                        app.save(c)
                elif self.path == '/api/acknowledge':
                    with app.lock:
                        if not app.detector.can_ack:
                            raise ValueError('Wait for fresh receiver data without active or unknown-position aircraft before acknowledging')
                        app.detector.acknowledge()
                else:
                    self.reply(404, {'error':'Not found'}); return
                self.reply(200, {'ok':True})
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {'error':str(exc)})
    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while True:
            start = time.monotonic()
            app.poll()
            time.sleep(max(.05, 1-(time.monotonic()-start)))
    finally:
        with app.lock: app.publish(False)
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-dir', default='/home/fpp/media/config')
    parser.add_argument('--runtime-dir', default='/run/aircraft-blackout')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=32380, type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    serve(App(args.config_dir, args.runtime_dir), args.host, args.port)
