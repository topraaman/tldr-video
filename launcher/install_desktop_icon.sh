#!/bin/bash
# Creates "TLDR.video.app" on your Desktop. Double-click it to start the
# server (if needed) and open the page in your browser.
# Re-run this script if you move the repository folder.
#
# Options:
#   --login      also open TLDR.video automatically every time you log in
#   --no-login   stop opening it at login
#   --new-app    create TLDR.video.app even if you kept an older launcher
#                with merge_into_old_launcher.sh

set -e

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Desktop/TLDR.video.app"
LOGIN_AGENT="$HOME/Library/LaunchAgents/local.tldrvideo.launcher.plist"
LOGIN_MODE=""
NEW_APP_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --login) LOGIN_MODE="on" ;;
        --no-login) LOGIN_MODE="off" ;;
        --new-app) NEW_APP_FLAG=1 ;;
        *) echo "Unknown option: $arg (use --login, --no-login or --new-app)"; exit 1 ;;
    esac
done

# If you kept your original launcher (merge_into_old_launcher.sh), use it
# instead of creating a second one
KEPT_LAUNCHER_FILE="$HOME/.tldr-video/launcher-path"
USE_EXISTING=""
if [ -z "$NEW_APP_FLAG" ] && [ -f "$KEPT_LAUNCHER_FILE" ]; then
    KEPT="$(cat "$KEPT_LAUNCHER_FILE")"
    if [ -e "$KEPT" ]; then
        APP="$KEPT"
        USE_EXISTING=1
    fi
fi

if [ "$(uname)" != "Darwin" ]; then
    echo "This installer is for macOS only."
    exit 1
fi

chmod +x "$LAUNCHER_DIR/launch.sh" "$LAUNCHER_DIR/run_server.sh" "$LAUNCHER_DIR/../start.sh"

if [ -n "$USE_EXISTING" ]; then
    echo "✅ Using your launcher: $APP (it already runs the latest launcher code)"
else
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>TLDR.video</string>
    <key>CFBundleDisplayName</key><string>TLDR.video</string>
    <key>CFBundleIdentifier</key><string>local.tldrvideo.launcher</string>
    <key>CFBundleExecutable</key><string>TLDR.video</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

printf '#!/bin/bash\nexec %q\n' "$LAUNCHER_DIR/launch.sh" > "$APP/Contents/MacOS/TLDR.video"
chmod +x "$APP/Contents/MacOS/TLDR.video"

# Build the .icns icon from icon.png using built-in macOS tools
ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z $size $size "$LAUNCHER_DIR/icon.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z $double $double "$LAUNCHER_DIR/icon.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$(dirname "$ICONSET")"

touch "$APP"
echo "✅ Created $APP"
echo "   Double-click it to start TLDR.video. Drag it to the Dock to pin it."
fi

if [ "$LOGIN_MODE" = "on" ]; then
    mkdir -p "$(dirname "$LOGIN_AGENT")"
    cat > "$LOGIN_AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>local.tldrvideo.launcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>$APP</string>
    </array>
    <key>RunAtLoad</key><true/>
</dict>
</plist>
PLIST
    launchctl unload "$LOGIN_AGENT" >/dev/null 2>&1 || true
    launchctl load "$LOGIN_AGENT" >/dev/null 2>&1 || true
    echo "✅ TLDR.video will also open every time you log in (undo with --no-login)."
elif [ "$LOGIN_MODE" = "off" ]; then
    launchctl unload "$LOGIN_AGENT" >/dev/null 2>&1 || true
    rm -f "$LOGIN_AGENT"
    echo "✅ TLDR.video will no longer open at login."
fi
