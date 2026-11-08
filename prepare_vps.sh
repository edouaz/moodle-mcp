#!/usr/bin/env bash
# Compatibility entry point. Run as a dedicated non-root user.
set -euo pipefail
cd "$(dirname "$0")"
exec bash setup.sh --vps
