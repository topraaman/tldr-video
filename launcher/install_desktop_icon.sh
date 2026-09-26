#!/bin/bash
# Creates "TLDR.video.app" on your Desktop. Double-click it to start the
# server (if needed) and open the page in your browser.
# Re-run this script if you move the repository folder.

set -e

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Desktop/TLDR.video.app"

if [ "$(uname)" != "Darwin" ]; then
    echo "This installer is for macOS only."
    exit 1
fi

chmod +x "$LAUNCHER_DIR/launch.sh" "$LAUNCHER_DIR/run_server.sh" "$LAUNCHER_DIR/../start.sh"

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
