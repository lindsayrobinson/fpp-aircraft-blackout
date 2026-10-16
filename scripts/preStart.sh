#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# Rebuild to match the current installed headers after FPP upgrades.
make "SRCDIR=${SRCDIR:-/opt/fpp/src}"
