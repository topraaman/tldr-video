#!/bin/bash
# TLDR.video launcher - run by the desktop app.
# Always opens a browser window: straight to the app if the server is up,
# otherwise a "Starting..." page that switches to the app once the server
# (started in a Terminal window, stop it with Ctrl+C) is ready.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:8000"

if curl -s -o /dev/null --max-time 2 "$URL/api/health"; then
    open "$URL"
    exit 0
fi

open "$REPO/launcher/starting.html"

# Don't start a second server if one is already booting
if ! pgrep -f "python main.py" >/dev/null 2>&1; then
    open -a Terminal "$REPO/launcher/run_server.sh"
fi
