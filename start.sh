#!/usr/bin/env bash
#
# ML Harness — one command to run the whole thing.
#
#   ./start.sh                 engine + UI, reusing whatever is already correct
#   ./start.sh --no-ui         engine only
#   ./start.sh --status        say what is running, change nothing
#   ./start.sh --rotate-token  new bearer token (open tabs will need a reload)
#   ./start.sh --foreground    keep the children attached to this terminal
#
# This file does exactly two things: find a Python, and hand over to
# scripts/launch.py. Every decision — is an engine already running, is it the
# RIGHT one, is the port taken by a stranger, is it ready — lives there, in one
# implementation, because a bash version and a PowerShell version of that logic
# would disagree with each other inside a week and there would be no way to
# test either. start.ps1 is the same twelve lines for PowerShell users.
#
# Windows note: this runs in Git Bash, which ships with Git for Windows. From
# PowerShell or cmd, use .\start.ps1 instead.

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# A candidate is only accepted if it actually runs. On Windows, `python3` is
# very often the App Execution Alias stub that opens the Microsoft Store and
# exits 9009 — it is on PATH, `command -v` finds it, and it is not a Python.
# Asking it to print its version is the cheapest way to tell them apart.
usable() {
  [ -n "${1:-}" ] && "$1" -c 'import sys; sys.exit(0)' >/dev/null 2>&1
}

PYTHON=""
for candidate in \
  "${MLH_PYTHON:-}" \
  "$HERE/.venv/Scripts/python.exe" \
  "$HERE/.venv/bin/python" \
  "$(command -v python3 2>/dev/null || true)" \
  "$(command -v python 2>/dev/null || true)"
do
  if usable "$candidate"; then PYTHON="$candidate"; break; fi
done

if [ -z "$PYTHON" ]; then
  cat >&2 <<'EOF'

ML HARNESS DID NOT START

No usable Python was found. Tried $MLH_PYTHON, ./.venv, python3 and python.

Install Python 3.11 or newer, then from this directory:

    python -m pip install -e .
    ./start.sh

If your interpreter is somewhere unusual, name it:

    MLH_PYTHON=/path/to/python ./start.sh

EOF
  exit 127
fi

exec "$PYTHON" "$HERE/scripts/launch.py" "$@"
