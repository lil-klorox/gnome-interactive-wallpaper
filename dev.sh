#!/bin/sh
# Run the extension in a throwaway gnome-shell; your real session is never touched.
# `./dev.sh` = nested window; `./dev.sh --headless [secs]` = virtual monitor driven by tools/probe,
# writes s*.png and stats.txt to $OUT; exits 1 if stats.txt is missing or has a FAIL line, or the
# extension failed to load.
# Env: SCENE=<id>, SIZE=WxH, SOAK=n off/on cycles (secs >= 22 + 3n), HOUR=0-23 (via TZ),
# POSTER=1 SHOT=secs (tools/poster.sh), RACE=1 lifecycle races (secs >= 14).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
uuid=$(sed -n 's/.*"uuid": "\(.*\)".*/\1/p' "$here/metadata.json")
size=${SIZE:-1720x720}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
glib-compile-schemas "$here/schemas"
mkdir -p "$tmp/data/gnome-shell/extensions"
ln -s "$here" "$tmp/data/gnome-shell/extensions/$uuid"
export XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config" MUTTER_DEBUG_DUMMY_MODE_SPECS="$size"
exts="'$uuid'"
set_scene=true
case ${SCENE:-}$size in *[!a-z0-9_-]*) echo 'bad SCENE/SIZE' >&2; exit 1;; esac  # size is pasted into sh -c
if [ -n "${HOUR:-}" ]; then
    case $HOUR in [0-9]|1[0-9]|2[0-3]) ;; *) echo 'bad HOUR' >&2; exit 1;; esac
    export TZ="XXX$(( $(date -u +%-H) - HOUR ))"  # POSIX TZ offsets count west, so local = UTC - offset
fi
export SCHEMADIR="$here/schemas"
[ -n "${SCENE:-}" ] && export SCENE && set_scene='gsettings --schemadir "$SCHEMADIR" set org.gnome.shell.extensions.interactive-wallpaper scene "$SCENE"'
setup="$set_scene && gsettings set org.gnome.shell welcome-dialog-last-shown-version 999"
if [ "${1:-}" = --headless ]; then
    secs=${2:-40}
    export OUT="${OUT:-$here/tools/out}" TARGET_UUID="$uuid" SECS="$secs"
    mkdir -p "$OUT" && rm -f "$OUT"/s*.png "$OUT/stats.txt"
    ln -s "$here/tools/probe" "$tmp/data/gnome-shell/extensions/probe@dev"
    timeout -k 5 "$((secs + 10))" dbus-run-session -- sh -c "$setup && gsettings set org.gnome.shell enabled-extensions \"['probe@dev', $exts]\" && exec gnome-shell --headless --wayland --virtual-monitor $size" > "$OUT/log" 2>&1 || true
    grep -aE 'interactive-wallpaper|JS ERROR|JS WARNING' "$OUT/log" | head -20
    cat "$OUT/stats.txt" 2>/dev/null; ls "$OUT"/s*.png 2>/dev/null || true
    [ -s "$OUT/stats.txt" ] && ! grep -q FAIL "$OUT/stats.txt" && ! grep -aq "Extension $uuid:" "$OUT/log"
    exit
fi
# GNOME 49 replaced --nested with --devkit.
mode=--nested
gnome-shell --help 2>&1 | grep -q -- --devkit && mode=--devkit
dbus-run-session -- sh -c "$setup && gsettings set org.gnome.shell enabled-extensions \"[$exts]\" && exec gnome-shell $mode --wayland"
