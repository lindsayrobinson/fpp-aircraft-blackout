#!/bin/bash
set -euo pipefail
# Removing this interlock removes protection. Stop the show and secure lights first.
systemctl disable --now fpp-aircraft-blackout.service || true
rm -f /etc/systemd/system/fpp-aircraft-blackout.service
systemctl daemon-reload
echo 'Configuration retained. Restart FPPD after removing the plugin. Blackout protection will be removed.'
