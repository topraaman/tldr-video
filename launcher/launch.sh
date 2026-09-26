#!/bin/bash
# TLDR.video launcher - run by the desktop app.
# Opens the page if the server is already up; otherwise starts it in a
# Terminal window (so you can see logs / stop it with Ctrl+C) and opens the
# page as soon as it responds.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:8000"

server_up() {
    curl -s -o /dev/null --max-time 2 "$URL/api/health"
}

if server_up; then
    open "$URL"
    exit 0
fi

open -a Terminal "$REPO/launcher/run_server.sh"

# First run may install dependencies, so allow up to 15 minutes.
for _ in $(seq 1 450); do
    if server_up; then
        open "$URL"
        exit 0
    fi
    sleep 2
done

osascript -e 'display alert "TLDR.video" message "The server did not start. Check the Terminal window for errors."' >/dev/null
exit 1
