# Aircraft Blackout for FPP — prototype v0.1.0

Monitor a local ADS-B receiver and continuously override selected moving-head DMX channels in FPP. Intended path: FPP → Falcon F16v4 → DMX fixtures. The F16v4's existing input protocol and universe/channel mapping stay in use.

**Built for FPP 10.x on Linux. Compile on the FPP device against its installed headers. This is a tested software prototype, not a certified aviation interlock; it has not yet been tested with your FPP, Falcon or fixtures.**

## Included

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

## Install from this ZIP

1. Copy the ZIP to the FPP device. SSH into FPP and extract it so the directory is exactly `/home/fpp/media/plugins/fpp-aircraft-blackout`.
2. For a fresh installation, with the ZIP at `/home/fpp/fpp-aircraft-blackout-v0.1.0.zip`:

   ```bash
   sudo unzip /home/fpp/fpp-aircraft-blackout-v0.1.0.zip -d /home/fpp/media/plugins
   sudo chown -R fpp:fpp /home/fpp/media/plugins/fpp-aircraft-blackout
   sudo bash /home/fpp/media/plugins/fpp-aircraft-blackout/scripts/fpp_install.sh
   ```

3. When no show is running, restart FPPD using FPP's interface. This loads the native plugin.
4. Open `http://FPP-IP:32380/`. Username: `admin`. Retrieve the generated password over SSH:

   ```bash
   sudo cat /home/fpp/media/config/aircraft-blackout.key
   ```

   FPP's plugin page also includes a link to the panel (`plugin.php?plugin=fpp-aircraft-blackout&page=index.php`).

This package is a manual installation, not yet a GitHub-backed Plugin Manager release. No fabricated repository URL is included. A compiler and the installed FPP source/libfpp are required; the installer stops on build failure. Do not install the ADS-B receiver software on the FPP system itself.

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
- Unknown-position local aircraft intentionally cause blackout, even if their distance cannot be determined. This may interrupt the show frequently; do not solve that by assuming they are far away.
- Lost-track faults do not clear just because a record ages out of the decoder. Acknowledge after checking the receiver and airspace; acknowledgement is accepted only when a fresh poll has no active/unknown-position aircraft, and still starts a full clear delay.
- Logs: `sudo journalctl -u fpp-aircraft-blackout -n 100 --no-pager`
- Service: `sudo systemctl status fpp-aircraft-blackout`
- The settings panel listens on TCP 32380, protected by a generated password using HTTP Basic authentication. Use it on a trusted local/show VLAN; do not expose it to the internet. Permit FPP → receiver HTTP, and management PC → FPP TCP 32380 across VLANs if needed. No aircraft stream needs to reach the Falcon.
- Configuration/password/blocked fallback live under `/home/fpp/media/config/aircraft-blackout.*`. Runtime snapshots and native heartbeat live in `/run/aircraft-blackout`; frequent snapshots avoid SD-card writes. Native fallback channels survive reboot, but permits are tied to the boot ID and expire.
- After FPP upgrades, rebuild against installed headers using the install script, then restart FPPD and recheck native activity. The supplied preStart hook also invokes `make`.
- Before uninstalling, stop the show and secure the lights independently. Uninstalling removes this protection. The uninstall hook disables the service and retains configuration; restart FPPD after plugin removal.

## Developer validation

```
python3 -m unittest discover -s tests -v
python3 tests/http_smoke.py
g++ -std=c++17 -Wall -Wextra -fsanitize=address,undefined tests/native_test.cpp -o /tmp/blackout-native-test
ASAN_OPTIONS=detect_leaks=0 /tmp/blackout-native-test
```

Python tests cover configurable location/radius, clear delays, stale/frozen data, unknown/lost positions, faults, persistence and feed failure. Native tests cover exact overrides, unchanged unrelated channels, observation mode, expiry, boot mismatch and malformed channel specifications. FPP adapter compiled against FPP 10.0 headers in the development environment; linking/loading and physical DMX behaviour need verification on the actual FPP device.

## References

- FPP channel-data plugin API: https://github.com/FalconChristmas/fpp/blob/master/src/Plugin.h
- FPP output ordering: https://github.com/FalconChristmas/fpp/blob/master/src/Sequence.cpp
- ADS-B Feeder Image: https://github.com/dirkhh/adsb-feeder-image
- readsb JSON format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md
- CASA ADS-B coverage/equipment context: https://www.casa.gov.au/operations-safety-and-travel/airspace/automatic-dependent-surveillance-broadcast-ads-b/how-ads-b-works

License: MIT. No third-party source is bundled. FPP reference checkout is excluded from this package.
