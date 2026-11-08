#!/usr/bin/env bash
# Bootstrap only. All account-specific setup lives in the Python wizard.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo 'Install Python 3.11+ and run this script again.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ required")'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo 'On Debian/Ubuntu: sudo apt install python3-venv' >&2; exit 1; }
fi
.venv/bin/python -m pip install -r requirements.txt
if [ "${1:-}" = '--vps' ]; then
  .venv/bin/python -m playwright install --with-deps chromium
else
  .venv/bin/python -m playwright install chromium
fi
exec .venv/bin/python moodle.py setup "$@"
