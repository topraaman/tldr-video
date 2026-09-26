#!/bin/bash
# TLDR.video launcher - run by the desktop launcher.
# Always opens a browser window: straight to the app if the server is up,
# otherwise a "Starting..." page that switches to the app once the server
# is ready (stop the server with Ctrl+C in its Terminal window).
#
#   launch.sh          start the server in a new Terminal window (for .app launchers)
#   launch.sh --here   run the server in the current Terminal window (for .command launchers)

REPO="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:8000"

if curl -s -o /dev/null --max-time 2 "$URL/api/health"; then
    open "$URL"
    exit 0
fi

open "$REPO/launcher/starting.html"

# Don't start a second server if one is already booting
if pgrep -f "python main.py" >/dev/null 2>&1; then
    exit 0
fi

if [ "$1" = "--here" ]; then
    exec "$REPO/launcher/run_server.sh"
fi
open -a Terminal "$REPO/launcher/run_server.sh"
