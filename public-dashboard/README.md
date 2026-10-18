# Lights on Elizabeth aircraft dashboard

A read-only public aircraft map and blackout status page for PHP hosting. FPP pushes an allowlisted snapshot over HTTPS every 10 seconds; visitors connect only to this website. No incoming connection or port forwarding to FPP is needed. The website cannot change the zone, acknowledge faults or control fixtures.

## Install on the website

Requires PHP 7.4 or newer, HTTPS, a writable private directory and permission for the `Authorization` header to reach PHP. The default page path is `/aircraft/`.

1. Upload **only** `index.html`, `dashboard.css`, `dashboard.js` and `api.php` into your website's public `aircraft` directory. Do not upload the FPP monitor, configuration or test files into this public folder.
2. Copy `config.example.php` **outside your public document root** and rename it `aircraft-dashboard-config.php`. For example:

   ```text
   /home/account/aircraft-dashboard-config.php
   /home/account/public_html/aircraft/index.html
   /home/account/public_html/aircraft/dashboard.css
   /home/account/public_html/aircraft/dashboard.js
   /home/account/public_html/aircraft/api.php
   ```

   With that layout, `api.php` finds the private configuration automatically. For a different layout, set the hosting environment variable `AIRCRAFT_PUBLIC_CONFIG` to its absolute path, or edit the `$configPath` assignment in `api.php` to the correct absolute private path. Do not place the key or saved JSON under `public_html`.
3. Generate a private key on your hosting account:

   ```bash
   php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
   ```

   Replace the example `token` value in the private configuration with this key. Retain it for FPP; do not paste it into a public page, URL or Git commit. `data_file` defaults to the private directory alongside the configuration. PHP must be able to create and replace that JSON file and its lock file. Restrict the configuration to the hosting account/PHP process (typically mode 600), and use a private writable directory. No database or cron job is needed.
4. Open `/aircraft/api.php` in your browser. Before FPP connects, a working setup returns `{"fresh":false,"age_s":null,"snapshot":null}`. `Dashboard not configured` means the private config/key needs attention. `Private data storage required` means the data path is inside your web root or otherwise invalid.
5. Exclude `/aircraft/api.php` from any CDN, page cache, service worker or hosting cache. It sends `Cache-Control: no-store`. Retain normal browser caching for map tiles. If using Apache/FastCGI and uploads receive 401 despite the correct key, ask the host to pass the `Authorization` header to PHP; some Apache hosts use `CGIPassAuth On` in the directory configuration.

## Connect FPP

With the show stopped, update the plugin and restart its monitor:

```bash
cd /home/fpp/media/plugins/fpp-aircraft-blackout
git pull --ff-only
sudo systemctl restart fpp-aircraft-blackout
```

Refresh **Status/Control → Aircraft Blackout**, then under **Public website dashboard** enter:

- The final HTTPS endpoint, e.g. `https://lightsonelizabeth.com/aircraft/api.php` or `https://www.lightsonelizabeth.com/aircraft/api.php`. Use the canonical hostname; uploads intentionally do not follow redirects.
- The upload key from the private website configuration.
- Check **Publish aircraft and blackout status to Lights on Elizabeth**, then **Save settings**.

Publishing is disabled by default. Enabling it publishes the display latitude/longitude and zone radius, received aircraft positions/details, and controller status. It excludes the receiver's local IP/URL, DMX channels, credentials and raw receiver error messages. The settings page shows the last successful upload or a generic upload failure. Allow outbound HTTPS from FPP to your website; retain local FPP access controls because the authenticated settings API holds the upload key. Do not enable publishing until the website endpoint has been installed.

Open `/aircraft/`. A website navigation link can point there, or embed it with:

```html
<iframe src="/aircraft/" title="Aircraft watch at Lights on Elizabeth"
        style="width:100%;height:1200px;border:0" loading="lazy"></iframe>
```

The page is responsive and can be restyled in `dashboard.css`. If the host uses a restrictive Content Security Policy, allow the pinned Leaflet assets from `https://unpkg.com` and map images from `https://tile.openstreetmap.org`, along with same-origin scripts/styles/fetch. Restrict embedding to your own site if desired.

## What visitors see

- **Aircraft protection** reflects the saved channel-enforcement setting; native hook reporting is shown separately. A fresh heartbeat is not optical confirmation.
- **Blackout request** shows the monitor's decision, including manual blackout, aircraft in the zone, tracking faults and the clear delay. Observation mode may request blackout without changing output.
- The map uses your configured horizontal radius without an altitude cutoff. Aircraft with fresh positions inside the zone are red, those outside teal, and old reported positions grey. Click an aircraft for details. Unknown-position aircraft appear only in the table. “In the zone” counts only fresh positions; the table labels old positions as such. Altitude is reported barometric feet and speed is knots when supplied.
- The receiver may contain more than 100 aircraft; the public table/map show the same maximum 100 records as the plugin. The total and fresh-inside count cover the full evaluated feed.
- The page checks for updates every 5 seconds. Snapshots more than 30 seconds old, failed fetches, or a stalled local monitor display **Status unavailable** and hide aircraft. A browser timer also expires status if the tab stays open while updates stop. Cached data must never be treated as current.
- Disabling publication causes the last website snapshot to expire within 30 seconds. It does not change local detection or enforcement. The uploader uses a separate worker so website delays do not block the local monitor.

This is an informational viewer with roughly 10-second publishing delay, not an aviation tracker or proof of clear airspace. “Blackout requested” does not confirm physical darkness.

## Map provider

The page uses Leaflet 1.9.4 and standard OpenStreetMap tiles, with visible attribution, ordinary browser caching, and no tile prefetch. Before production use review the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/). The standard service has no availability guarantee; for higher traffic select a suitable tile provider by replacing the `L.tileLayer` URL and attribution in `dashboard.js`. Keep attribution visible and a valid referrer policy. Leaflet is loaded from a pinned CDN release with integrity checks. Aircraft/status details still work if the map library cannot load. No aircraft data is sent to a public flight tracking service by this plugin; visitors' browsers contact the map/CDN providers for assets.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 tests/http_smoke.py
python3 tests/php_bridge_smoke.py
python3 tests/public_dashboard_smoke.py
node tests/dashboard_ui_test.cjs
```

Use `PHP_BIN=/path/to/php` if PHP CLI is not on PATH. Tests use temporary private files and a local PHP server; they do not contact the live website or disclose real display coordinates. Verify the final HTTPS URL and PHP permissions on your actual hosting before enabling FPP publication. Set the hosting and FPP clocks correctly; snapshots more than 30 seconds from server time are rejected.
