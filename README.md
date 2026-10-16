# Aircraft Blackout for FPP — prototype v0.2.1

Monitor a local ADS-B receiver and continuously override selected moving-head DMX channels in FPP. Intended path: FPP → Falcon F16v4 → DMX fixtures. The F16v4's existing input protocol and universe/channel mapping stay in use.

**Built for FPP 10.x on Linux. Compile on the FPP device against its installed headers. This is a tested software prototype, not a certified aviation interlock; it has not yet been tested with your FPP, Falcon or fixtures.**

## Included

- All settings, status and manual controls are embedded in FPP: **Status/Control → Aircraft Blackout**. No separate web panel or browser login.

- Settings panel with display latitude and longitude in decimal degrees.
- Configurable horizontal blackout radius; **15 km default, suggested only as a commissioning starting point**. This is not an aviation-approved safe distance. Assess local traffic, beam direction/intensity and end-to-end response before operation. No altitude cutoff: aircraft at any reported altitude within the radius trigger blackout.
- Default 60-second clear hold, 1-second receiver polling, 5-second feed and position freshness thresholds.
- Exact channel/value overrides: absolute FPP channels, including documented shutter-closed values if nonzero. Dimmer and shutter only; never lamp-off or reset commands.
- Native `modifyChannelData` callback after FPP overlays. Overrides apply on each processed output frame, including sequence playback, while other channels are untouched.
- Observation mode by default. Receiver faults, stale/unknown positions, startup checks and manual blackout request blackout, but observation mode deliberately does not alter output.
- Manual blackout persisted across restarts. Releasing it does not bypass automatic detection or the clear hold.
- Feed loss and unresolved lost tracks latch blackout until the receiver is healthy and an operator acknowledges the fault after checking the airspace. A positively received position outside the zone resolves the track, but the fault latch still requires acknowledgement.
- Fresh permission expires after 3 seconds if the monitor stops. The native hook checks expiry on every callback, independently of its background reader.
- Receiver data stays local to this plugin. Your adsb.im feeder may separately share data according to its own settings.

## Before installation

Confirm FPP version 10.x and that this FPP device sends the moving-head data to the Falcon. Keep the fixtures blacked out using an independent method during installation and commissioning. Have the moving-head DMX chart and FPP/Falcon channel mapping ready.

Use a separate adsb-feeder-image receiver with wired Ethernet and a reserved IP. Obtain its actual aircraft JSON URL. Possible URLs are:

```
http://RECEIVER-IP:8080/data/aircraft.json
http://RECEIVER-IP:1090/data/aircraft.json
http://RECEIVER-IP/tar1090/data/aircraft.json
```

These are examples, not a confirmed address for your receiver. Open the actual URL: it must return JSON with `now` and an `aircraft` array. Aircraft records use `hex`, `lat`, `lon` and `seen_pos`. If your map uses only binary data, enable a compatible JSON endpoint in its receiver configuration before continuing. Use an IP literal in the URL; public hosts, DNS names and redirects are rejected. Ensure the FPP and receiver clocks are synchronized. Local reception does not depend on public tracking websites.

## Install from GitHub

For a fresh installation, stop the show and secure the fixtures independently. SSH into the FPP device and run:

```bash
cd /home/fpp/media/plugins
git clone https://github.com/lindsayrobinson/fpp-aircraft-blackout.git
cd fpp-aircraft-blackout
sudo bash scripts/fpp_install.sh
```

Restart FPPD using the FPP web interface when no show is running. Open **Status/Control → Aircraft Blackout**, or this relative page on the FPP device:

```
/plugin.php?plugin=fpp-aircraft-blackout&page=index.php
```

The page uses FPP's normal web access controls. There is no separate plugin password to enter and no port 32380 to open in your browser. The background monitor listens only on `127.0.0.1:32380`; FPP communicates with it locally using its retained internal credential.

A compiler and the installed FPP source/libfpp are required; the installer stops on build failure. Do not install the ADS-B receiver software on the FPP device.

## Upgrade from v0.1

With the show stopped and fixtures secured:

```bash
cd /home/fpp/media/plugins/fpp-aircraft-blackout
git pull --ff-only
sudo bash scripts/fpp_install.sh
```

Restart FPPD through FPP and refresh the browser page. Existing receiver URL, location, radius, channel overrides and manual blackout setting are retained. The installer updates the service to listen locally and adds the FPP menu entry. Native hook activity must be checked again after the restart. If the directory is not a Git checkout, back it up and replace the plugin source with a fresh clone; configuration remains separately under `/home/fpp/media/config`.

## Install from a source ZIP

Extract the source so the installer is exactly `/home/fpp/media/plugins/fpp-aircraft-blackout/scripts/fpp_install.sh`. GitHub source archives may add a `-main` suffix to the folder; rename it before installation. Ensure the `fpp` user owns the plugin directory, run the installation script with `sudo`, and follow the same restart and FPP page steps above.

## Stale-position option

In the FPP settings page, **Request blackout for stale aircraft positions** is enabled by default, including after upgrading an older configuration. Uncheck it and save to ignore coordinates older than **Maximum position age**. The aircraft table labels those rows **STALE — ignored**.

This also ignores a stale record whose last fresh position was inside the exclusion zone; it is not evidence that the aircraft has left. Fresh aircraft inside the zone still request blackout. Records with no usable coordinates/position age, completely lost tracks, stale or unavailable receiver feeds and manual blackout still request blackout. If an earlier fault is latched, inspect the airspace and acknowledge it when the button becomes available; the normal clear delay still applies.

## Configure

1. Leave **Enable actual channel overrides** unchecked during initial observation.
2. Enter the aircraft JSON URL.
3. Enter your **display's** latitude and longitude. Southern latitudes are negative; Queensland longitudes are positive. Do not use an example coordinate as your address.
4. Set the radius in kilometres. The default is 15 km, measured horizontally from the display, without altitude filtering. Aircraft travel quickly: at 250 knots, 15 km is about two minutes of travel; this example does not account for blind spots or establish a safety margin.
5. Set the clear delay (60 seconds initially). A larger exit radius is not used in v0.1; the clear hold reduces repeated switching at the boundary.
6. Enter one `channel,value` pair per line. Example syntax only:

   ```text
   12001,0
   12002,8
   ```

   The first number is the absolute **FPP channel**, not the fixture's channel offset or DMX start address. The second is the blackout value from the fixture manual. If the Falcon serial output starts at a particular absolute FPP channel, add the fixture's DMX address minus 1 and the function offset minus 1. Verify mapping against the Falcon setup. If using universe mapping, use the configured FPP universe start, not an assumed 512-channel multiplication.
7. Save. Initial unconfigured receiver faults may require acknowledgement after valid data arrives and the airspace is checked.
8. Verify the panel reports the native hook heartbeat, channel count and increasing frame count while a sequence plays. A heartbeat alone does not prove that DMX reaches the lights.

Both manual and automatic output overrides require enforcement to be enabled. Disabling enforcement deliberately removes this plugin's output protection. Changing settings revokes clear permission and restarts the clear delay. Settings are applied within the native reader's approximately 100 ms cycle.

## Commissioning checklist

Keep beams contained in a safe direction and retain an independent blackout control throughout testing.

- Check each selected dimmer/shutter channel independently and confirm the actual fixture blacks out with its configured value.
- Enable enforcement, run a sequence that repeatedly sets the moving heads bright, and engage manual blackout. Check all heads stay dark while music and other lights continue.
- Release manual blackout. Confirm the automatic conditions and clear delay are respected.
- Compare actual aircraft to receiver coverage in every relevant direction, particularly low-flying traffic. Many distant aircraft on a map do not establish good local coverage.
- Temporarily enlarge the radius to include a currently tracked aircraft and verify automatic blackout. Restore the assessed radius afterward.
- Disconnect the receiver network, stop its decoder, reboot it and test a frozen JSON feed. Confirm blackout and fault acknowledgement behaviour.
- Stop the monitor (`sudo systemctl stop fpp-aircraft-blackout`): the native hook should blackout within 3 seconds of its last permit plus frame timing. Restart it afterward. Healthy receiver recovery still needs acknowledgement after faults.
- Test FPP startup, playlist changes, sequence end, idle output, manual test output, and any other installed channel-modifying plugins or output processors. Confirm nothing later in the output chain restores brightness or changes a nonzero shutter value.
- Test FPP/network/Falcon failure separately. This plugin cannot transmit new DMX if FPP stops, and cannot change a fixture that holds its last DMX state after a connection failure. Configure and verify controller/fixture loss behaviour and an independent blackout method.
- Do not treat unplugging the antenna as equivalent to disconnecting the feed: a decoder can serve fresh empty JSON with a failed antenna. This software cannot reliably detect that condition.

Not all aircraft carry ADS-B OUT; one receiver cannot position every Mode-S-only aircraft. Buildings, antenna faults and interference can hide aircraft. An empty aircraft list is not proof of clear airspace. This plugin is an additional safeguard alongside suitable beam restrictions, monitoring and applicable CASA requirements.

## Operation and troubleshooting

- Status shows **blackout requested** separately from **observation/enforcement**. It describes the decision and software activity, not confirmation of optical darkness.
- Aircraft with no usable position intentionally cause blackout because their distance cannot be determined. The stale-position checkbox affects valid coordinates that have become too old; it does not bypass records with no usable position.
- Lost-track faults do not clear just because a record ages out of the decoder. Acknowledge after checking the receiver and airspace; acknowledgement is accepted only when a fresh poll has no active/unknown-position aircraft, and still starts a full clear delay.
- Logs: `sudo journalctl -u fpp-aircraft-blackout -n 100 --no-pager`
- Service: `sudo systemctl status fpp-aircraft-blackout`
- Settings and controls use FPP's own web interface and access controls. Keep FPP on a trusted network and use its normal authentication settings. The monitor listens only on loopback TCP 32380 and is accessed by a fixed-route PHP bridge; its credential never reaches the browser. If using VLANs, allow FPP → receiver HTTP and management PC → FPP's normal web port. No additional browser port or aircraft stream to the Falcon is needed.
- If settings report a missing credential, run the installer. If the monitor is unavailable, check the service log. If a settings token expires after two hours, reload the FPP plugin page.
- Existing authentication keys remain internal and are retained for upgrades; you no longer need to retrieve or type them to manage settings.
- Configuration/password/blocked fallback live under `/home/fpp/media/config/aircraft-blackout.*`. Runtime snapshots and native heartbeat live in `/run/aircraft-blackout`; frequent snapshots avoid SD-card writes. Native fallback channels survive reboot, but permits are tied to the boot ID and expire.
- After FPP upgrades, rebuild against installed headers using the install script, then restart FPPD and recheck native activity. The supplied preStart hook also invokes `make`.
- Before uninstalling, stop the show and secure the lights independently. Uninstalling removes this protection. The uninstall hook disables the service and retains configuration; restart FPPD after plugin removal.

## Developer validation

```
python3 -m unittest discover -s tests -v
python3 tests/http_smoke.py
python3 tests/php_bridge_smoke.py  # requires PHP CLI
g++ -std=c++17 -Wall -Wextra -fsanitize=address,undefined tests/native_test.cpp -o /tmp/blackout-native-test
ASAN_OPTIONS=detect_leaks=0 /tmp/blackout-native-test
```

Python tests cover configurable location/radius, clear delays, stale/frozen data, unknown/lost positions, faults, persistence and feed failure. The PHP integration test renders the FPP-style page and exercises persisted settings, status and manual controls through the real bridge, plus token/method validation and offline-monitor errors. Native tests cover exact overrides, unchanged unrelated channels, observation mode, expiry, boot mismatch and malformed channel specifications. FPP adapter compiled against FPP 10.0 headers in the development environment; linking/loading and physical DMX behaviour need verification on the actual FPP device.

## References

- FPP channel-data plugin API: https://github.com/FalconChristmas/fpp/blob/master/src/Plugin.h
- FPP output ordering: https://github.com/FalconChristmas/fpp/blob/master/src/Sequence.cpp
- ADS-B Feeder Image: https://github.com/dirkhh/adsb-feeder-image
- readsb JSON format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md
- CASA ADS-B coverage/equipment context: https://www.casa.gov.au/operations-safety-and-travel/airspace/automatic-dependent-surveillance-broadcast-ads-b/how-ads-b-works

License: MIT. No third-party source is bundled. FPP reference checkout is excluded from this package.
