#!/bin/bash
# Gathers everything TLDR.video related into one folder:
#
#   <Ramprasad Devaraj>/TLDR/
#       tldr-video/   the project (code, downloads, settings)
#       Exports/      thumbnails and reels the app saved to ~/Downloads
#
# Your desktop launcher stays where it is and is updated to the new location.
#
#   bash launcher/move_to_tldr_folder.sh                 # find "Ramprasad Devaraj" automatically
#   bash launcher/move_to_tldr_folder.sh /path/to/parent # or say where TLDR should go

set -e

PARENT_NAME="Ramprasad Devaraj"
OLD_REPO="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$HOME/.tldr-video"
LOGIN_AGENT="$HOME/Library/LaunchAgents/local.tldrvideo.launcher.plist"

if [ "$(uname)" != "Darwin" ]; then
    echo "This script is for macOS only."
    exit 1
fi

# ---------- 1. Where does TLDR go? ----------
PARENT="$1"
if [ -z "$PARENT" ]; then
    CANDIDATES=()
    for dir in "$HOME/$PARENT_NAME" "$HOME/Desktop/$PARENT_NAME" "$HOME/Documents/$PARENT_NAME" \
               "$HOME/Library/Mobile Documents/com~apple~CloudDocs/$PARENT_NAME" "/Users/$PARENT_NAME"; do
        [ -d "$dir" ] && CANDIDATES+=("$dir")
    done
    if [ ${#CANDIDATES[@]} -eq 1 ]; then
        PARENT="${CANDIDATES[0]}"
    elif [ ${#CANDIDATES[@]} -gt 1 ]; then
        echo "Found more than one \"$PARENT_NAME\" folder. Which one?"
        select choice in "${CANDIDATES[@]}"; do
            [ -n "$choice" ] && PARENT="$choice" && break
        done
    elif [ "$(id -F 2>/dev/null)" = "$PARENT_NAME" ]; then
        # "Ramprasad Devaraj" is this Mac account's name: use its home folder
        PARENT="$HOME"
    else
        echo "No folder called \"$PARENT_NAME\" found."
        read -r -p "Create $HOME/$PARENT_NAME and use it? [y/N] " answer
        case "$answer" in
            [yY]*) PARENT="$HOME/$PARENT_NAME" ;;
            *) echo "Cancelled. You can also run: bash launcher/move_to_tldr_folder.sh /path/to/folder"; exit 0 ;;
        esac
    fi
fi
PARENT="${PARENT%/}"
TLDR_DIR="$PARENT/TLDR"
NEW_REPO="$TLDR_DIR/tldr-video"

case "$NEW_REPO/" in
    "$OLD_REPO/"*) echo "✅ The project is already in $TLDR_DIR"; exit 0 ;;
esac
if [ -e "$NEW_REPO" ]; then
    echo "❌ $NEW_REPO already exists. Move or rename it first, then run this again."
    exit 1
fi
case "$PARENT" in
    *"Mobile Documents"*)
        echo "⚠️  This folder is in iCloud Drive. The app works there, but iCloud syncing"
        echo "   the large AI models and Python packages can be slow."
        ;;
esac

# ---------- 2. What gets moved ----------
EXPORTS=()
while IFS= read -r f; do
    [ -n "$f" ] && EXPORTS+=("$f")
done < <(find "$HOME/Downloads" -maxdepth 1 -type f \
            \( -name '*_custom_thumbnail.png' -o -name '*_custom_thumbnail.jpg' \
               -o -name '*_thumbnail.jpg' -o -name '*_reel.mp4' \) 2>/dev/null | sort)

echo ""
echo "This will create:  $TLDR_DIR"
echo "and move into it:"
echo "  • the project     $OLD_REPO  →  TLDR/tldr-video"
echo "  • ${#EXPORTS[@]} saved thumbnail/reel file(s) from Downloads  →  TLDR/Exports"
echo "Your launcher stays where it is and will point to the new location."
echo "(Transcript PDF/DOCX files are named after the video, so they are left in Downloads.)"
echo ""
read -r -p "Go ahead? [y/N] " answer
case "$answer" in
    [yY]*) ;;
    *) echo "Cancelled - nothing was moved."; exit 0 ;;
esac

# Stop the server if it's running from the old location
SERVER_PIDS="$(pgrep -f "python main.py" || true)"
if [ -n "$SERVER_PIDS" ]; then
    echo "⏹  Stopping the running TLDR.video server..."
    kill $SERVER_PIDS 2>/dev/null || true
    sleep 1
fi

# ---------- 3. Move ----------
mkdir -p "$TLDR_DIR"
mv "$OLD_REPO" "$NEW_REPO"
echo "✅ Moved the project to $NEW_REPO"

# The Python environment only works where it was created; the launcher rebuilds it
rm -rf "$NEW_REPO/venv"

if [ ${#EXPORTS[@]} -gt 0 ]; then
    mkdir -p "$TLDR_DIR/Exports"
    for f in "${EXPORTS[@]}"; do
        mv -n "$f" "$TLDR_DIR/Exports/"
    done
    echo "✅ Moved ${#EXPORTS[@]} file(s) to $TLDR_DIR/Exports"
fi

# ---------- 4. Point the launcher(s) at the new location ----------
# Rewrites every mention of the old project path. Scripts get shell-escaped
# paths (printf %q style); pass "plain" for data files like plists.
repoint() {
    python3 - "$1" "$OLD_REPO" "$NEW_REPO" "${2:-script}" <<'PY'
import re, sys
path, old, new, mode = sys.argv[1:5]
try:
    text = open(path, encoding="utf-8").read()
except (UnicodeDecodeError, OSError):
    sys.exit(1)  # binary or unreadable: not a launcher script
escaped_old = old.replace(" ", "\\ ")
if old not in text and escaped_old not in text:
    sys.exit(1)
if mode == "script":
    # Inside quotes use the plain path; unquoted (printf %q style) escape spaces
    def swap(match):
        start = match.start()
        quoted = start > 0 and text[start - 1] in "'\""
        return new if quoted else new.replace(" ", "\\ ")
    pattern = "|".join(re.escape(p) for p in sorted({escaped_old, old}, key=len, reverse=True))
    text = re.sub(pattern, swap, text)
else:
    text = text.replace(old, new)
open(path, "w", encoding="utf-8").write(text)
PY
}

LAUNCHERS=()
[ -f "$STATE_DIR/launcher-path" ] && LAUNCHERS+=("$(cat "$STATE_DIR/launcher-path")")
while IFS= read -r path; do
    [ -n "$path" ] && LAUNCHERS+=("$path")
done < <(find "$HOME/Desktop" "$HOME/Applications" /Applications -maxdepth 2 \
            \( -iname '*tldr*' -o -iname '*video*transcript*' \) \
            \( -name '*.app' -o -name '*.command' -o -name '*.sh' -o -name '*.py' \) 2>/dev/null)

UPDATED=0
for launcher in "${LAUNCHERS[@]}"; do
    # A launcher that lived inside the project moved with it
    case "$launcher" in "$OLD_REPO"/*) launcher="$NEW_REPO${launcher#$OLD_REPO}" ;; esac
    [ -e "$launcher" ] || continue
    changed=""
    if [ -d "$launcher" ]; then
        for exe in "$launcher"/Contents/MacOS/*; do
            [ -f "$exe" ] && repoint "$exe" && changed=1
        done
        if [ -n "$changed" ]; then
            codesign --force --deep --sign - "$launcher" >/dev/null 2>&1 || true
        fi
    else
        repoint "$launcher" && changed=1
    fi
    if [ -n "$changed" ]; then
        echo "✅ Updated launcher: $launcher"
        UPDATED=$((UPDATED + 1))
    fi
done

if [ -f "$STATE_DIR/launcher-path" ]; then
    repoint "$STATE_DIR/launcher-path" plain || true
fi
if [ -f "$LOGIN_AGENT" ] && repoint "$LOGIN_AGENT" plain; then
    launchctl unload "$LOGIN_AGENT" >/dev/null 2>&1 || true
    launchctl load "$LOGIN_AGENT" >/dev/null 2>&1 || true
fi

if [ "$UPDATED" -eq 0 ]; then
    echo "⚠️  Couldn't find a launcher that points to the project."
    echo "   Run: bash \"$NEW_REPO/launcher/install_desktop_icon.sh\""
fi

echo ""
echo "Done. Everything TLDR.video is now in: $TLDR_DIR"
echo "The next launch rebuilds the Python environment once (a few minutes)."
echo "In Terminal, the project is now at:  cd \"$NEW_REPO\""
