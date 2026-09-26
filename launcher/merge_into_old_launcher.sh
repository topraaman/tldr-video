#!/bin/bash
# One-time cleanup when you have two TLDR launchers.
# Keeps your ORIGINAL launcher (its name, place and icon), makes it use the
# latest launcher behavior, and removes the newer TLDR.video.app.
#
#   ./launcher/merge_into_old_launcher.sh                 # find the old launcher automatically
#   ./launcher/merge_into_old_launcher.sh /path/to/old    # or point at it yourself
#
# A backup of the old launcher is saved in ~/.tldr-video/ first.

set -e

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$LAUNCHER_DIR/.." && pwd)"
LAUNCH="$LAUNCHER_DIR/launch.sh"
NEW_APP="$HOME/Desktop/TLDR.video.app"
LOGIN_AGENT="$HOME/Library/LaunchAgents/local.tldrvideo.launcher.plist"
STATE_DIR="$HOME/.tldr-video"
BACKUP_DIR="$STATE_DIR/launcher-backup-$(date +%Y%m%d-%H%M%S)"

if [ "$(uname)" != "Darwin" ]; then
    echo "This script is for macOS only."
    exit 1
fi

chmod +x "$LAUNCH" "$LAUNCHER_DIR/run_server.sh" "$REPO/start.sh"

# ---------- 1. Find the old launcher ----------
OLD="$1"
if [ -z "$OLD" ]; then
    CANDIDATES=()
    while IFS= read -r path; do
        [ -n "$path" ] && CANDIDATES+=("$path")
    done < <(
        {
            find "$HOME/Desktop" "$HOME/Applications" /Applications "$REPO/dist" -maxdepth 2 \
                \( -iname '*tldr*' -o -iname '*video*transcript*' \) \
                \( -name '*.app' -o -name '*.command' -o -name '*.sh' \) 2>/dev/null
            find "$REPO" "$HOME" -maxdepth 1 \
                \( -name 'launch_tldr.command' -o -iname '*tldr*.command' -o -name 'desktop_app.py' \) 2>/dev/null
        } | grep -v "^$NEW_APP" | grep -v "^$LAUNCHER_DIR/" | grep -v '\.app/.' | sort -u
    )

    if [ ${#CANDIDATES[@]} -eq 0 ]; then
        echo "❌ Couldn't find your old TLDR launcher automatically."
        echo "   Run this again with its location, for example:"
        echo "   ./launcher/merge_into_old_launcher.sh ~/Desktop/launch_tldr.command"
        echo "   (Tip: drag the old launcher from Finder into the Terminal window to paste its path.)"
        exit 1
    elif [ ${#CANDIDATES[@]} -eq 1 ]; then
        OLD="${CANDIDATES[0]}"
    else
        echo "Found more than one possible old launcher. Which one do you want to keep?"
        select choice in "${CANDIDATES[@]}"; do
            [ -n "$choice" ] && OLD="$choice" && break
        done
    fi
fi

OLD="${OLD%/}"
if [ ! -e "$OLD" ]; then
    echo "❌ Not found: $OLD"
    exit 1
fi
if [ "$OLD" = "$NEW_APP" ]; then
    echo "❌ That's the new launcher. Point me at the OLD one instead."
    exit 1
fi
case "$OLD" in
    *.app|*.command|*.sh|*.py) ;;
    *)
        echo "❌ $OLD doesn't look like a launcher (.app, .command, .sh or .py)."
        echo "   If it's an alias, right-click it in Finder → Show Original, and use that file."
        exit 1
        ;;
esac

echo "Keeping your original launcher: $OLD"
read -r -p "Update it and delete $(basename "$NEW_APP")? [y/N] " answer
case "$answer" in
    [yY]*) ;;
    *) echo "Cancelled - nothing was changed."; exit 0 ;;
esac

# ---------- 2. Back it up ----------
mkdir -p "$BACKUP_DIR"
ditto "$OLD" "$BACKUP_DIR/$(basename "$OLD")"
echo "📦 Backup saved to $BACKUP_DIR"

# ---------- 3. Point it at the latest launcher ----------
# Files are rewritten in place so Finder keeps any custom icon.
case "$OLD" in
    *.app)
        EXE_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$OLD/Contents/Info.plist" 2>/dev/null || true)"
        if [ -z "$EXE_NAME" ]; then
            echo "❌ Couldn't read $OLD/Contents/Info.plist - is it a normal app?"
            exit 1
        fi
        EXE="$OLD/Contents/MacOS/$EXE_NAME"
        mkdir -p "$(dirname "$EXE")"
        printf '#!/bin/bash\n# TLDR.video launcher (updated by merge_into_old_launcher.sh)\nexec %q\n' "$LAUNCH" > "$EXE"
        chmod +x "$EXE"
        # Re-sign locally so macOS accepts the edited app
        codesign --remove-signature "$OLD" >/dev/null 2>&1 || true
        codesign --force --deep --sign - "$OLD" >/dev/null 2>&1 || true
        ;;
    *.py)
        printf '# TLDR.video launcher (updated by merge_into_old_launcher.sh)\nimport os\nos.execv(%s, [%s])\n' \
            "\"$LAUNCH\"" "\"$LAUNCH\"" > "$OLD"
        ;;
    *)
        # .command / .sh: run the server in this launcher's own Terminal window
        printf '#!/bin/bash\n# TLDR.video launcher (updated by merge_into_old_launcher.sh)\nexec %q --here\n' "$LAUNCH" > "$OLD"
        chmod +x "$OLD"
        ;;
esac
touch "$OLD"
echo "✅ Updated $OLD"

# ---------- 4. Remove the newer launcher ----------
if [ -e "$NEW_APP" ]; then
    rm -rf "$NEW_APP"
    echo "🗑  Removed $NEW_APP"
fi

# Remember which launcher to use, so install_desktop_icon.sh won't create a second one
mkdir -p "$STATE_DIR"
printf '%s\n' "$OLD" > "$STATE_DIR/launcher-path"

# ---------- 5. Keep "open at login" working ----------
if [ -f "$LOGIN_AGENT" ]; then
    launchctl unload "$LOGIN_AGENT" >/dev/null 2>&1 || true
    /usr/libexec/PlistBuddy -c "Set :ProgramArguments:1 $OLD" "$LOGIN_AGENT"
    launchctl load "$LOGIN_AGENT" >/dev/null 2>&1 || true
    echo "✅ Open-at-login now uses your original launcher."
fi

echo ""
echo "Done. Double-click $(basename "$OLD") to open TLDR.video."
