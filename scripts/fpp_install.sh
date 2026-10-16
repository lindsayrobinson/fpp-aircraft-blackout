#!/bin/bash
set -euo pipefail
PLUGIN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$EUID" -ne 0 ]]; then echo 'Run this script with sudo.'; exit 1; fi
if [[ "$PLUGIN_DIR" != /home/fpp/media/plugins/fpp-aircraft-blackout ]]; then
    echo 'Extract the plugin into /home/fpp/media/plugins/fpp-aircraft-blackout first.'; exit 1
fi
command -v python3 >/dev/null
command -v g++ >/dev/null
make -C "$PLUGIN_DIR" "SRCDIR=${SRCDIR:-/opt/fpp/src}"
install -d -o fpp -g fpp -m 0750 /run/aircraft-blackout
# Initialize configuration and a blocked snapshot before FPP can load the plugin.
sudo -u fpp python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from monitor import App; App("/home/fpp/media/config")' "$PLUGIN_DIR"
cat > /etc/systemd/system/fpp-aircraft-blackout.service <<'UNIT'
[Unit]
Description=Local ADS-B aircraft blackout monitor
Wants=network-online.target
After=network-online.target
[Service]
User=fpp
Group=fpp
ExecStart=/usr/bin/python3 /home/fpp/media/plugins/fpp-aircraft-blackout/monitor.py --host 127.0.0.1
Restart=always
RestartSec=1
RuntimeDirectory=aircraft-blackout
RuntimeDirectoryMode=0750
RuntimeDirectoryPreserve=yes
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/fpp/media/config /run/aircraft-blackout
ProtectHome=read-only
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
chmod +x "$PLUGIN_DIR/callbacks.sh" "$PLUGIN_DIR/scripts/"*.sh
systemctl daemon-reload
systemctl enable --now fpp-aircraft-blackout.service
systemctl restart fpp-aircraft-blackout.service
echo 'Installed. Restart FPPD when no show is running, then open Status/Control -> Aircraft Blackout in FPP.'
echo 'Direct page: http://FPP-IP/plugin.php?plugin=fpp-aircraft-blackout&page=index.php'
echo 'Settings use FPP access controls; no separate panel login or port is required.'
echo 'Observation mode is the default. Configure and bench-test before enabling enforcement.'
