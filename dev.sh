#!/bin/sh
# Run the extension in a throwaway gnome-shell; your real session's extensions and settings are
# never touched. `./dev.sh` = nested window; `./dev.sh --headless [secs]` = virtual monitor, the
# tools/probe extension drives a cursor + notification, writes s*.png and stats.txt to $OUT.
# Env: SCENE=<id> picks a scene, SIZE=WxH the monitor, SOAK=n adds n off/on cycles (needs secs >= 22 + 3n),
# HOUR=0-23 runs the shell at that local hour (via TZ), POSTER=1 SHOT=secs and RACE=1 (lifecycle races,
# secs >= 14) see tools/probe and tools/poster.sh.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
uuid=interactive-wallpaper@lil-klorox
size=${SIZE:-1720x720}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
glib-compile-schemas "$here/schemas"
mkdir -p "$tmp/data/gnome-shell/extensions"
ln -s "$here" "$tmp/data/gnome-shell/extensions/$uuid"
export XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config" MUTTER_DEBUG_DUMMY_MODE_SPECS="$size"
exts="'$uuid'"
set_scene=true
case ${SCENE:-}$size in *[!a-z0-9_-]*) echo 'bad SCENE/SIZE' >&2; exit 1;; esac  # both are pasted into sh -c
if [ -n "${HOUR:-}" ]; then
    case $HOUR in [0-9]|1[0-9]|2[0-3]) ;; *) echo 'bad HOUR' >&2; exit 1;; esac
    export TZ="XXX$(( $(date -u +%-H) - HOUR ))"  # POSIX TZ offsets count west, so local = UTC - offset
fi
[ -n "${SCENE:-}" ] && set_scene="gsettings --schemadir '$here/schemas' set org.gnome.shell.extensions.interactive-wallpaper scene '$SCENE'"
setup="$set_scene && gsettings set org.gnome.shell welcome-dialog-last-shown-version 999"
if [ "${1:-}" = --headless ]; then
    secs=${2:-40}
    export OUT="${OUT:-$here/tools/out}" TARGET_UUID="$uuid" SECS="$secs"
    mkdir -p "$OUT" && rm -f "$OUT"/s*.png "$OUT/stats.txt"
    ln -s "$here/tools/probe" "$tmp/data/gnome-shell/extensions/probe@dev"
    timeout "$((secs + 10))" dbus-run-session -- sh -c "$setup && gsettings set org.gnome.shell enabled-extensions \"['probe@dev', $exts]\" && exec gnome-shell --headless --wayland --virtual-monitor $size" > "$OUT/log" 2>&1 || true
    grep -E 'interactive-wallpaper|JS ERROR|JS WARNING' "$OUT/log" | head -20
    cat "$OUT/stats.txt" 2>/dev/null; ls "$OUT"/s*.png 2>/dev/null || true
    exit 0
fi
# GNOME 49 replaced --nested with --devkit.
mode=--nested
gnome-shell --help 2>&1 | grep -q -- --devkit && mode=--devkit
dbus-run-session -- sh -c "$setup && gsettings set org.gnome.shell enabled-extensions \"[$exts]\" && exec gnome-shell $mode --wayland"
