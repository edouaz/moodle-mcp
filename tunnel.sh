#!/usr/bin/env bash
# Compatibility wrapper; the Python CLI owns the shared configuration.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-help}" in
  init) exec .venv/bin/python -c 'import sys; from moodle import init_tunnel; init_tunnel(sys.argv[1])' "${2:?Tunnel ID required}" ;;
  run|doctor|status) exec .venv/bin/python moodle.py tunnel "$1" ;;
  *) echo 'python3 moodle.py setup | tunnel {run,doctor,status}' ;;
esac
