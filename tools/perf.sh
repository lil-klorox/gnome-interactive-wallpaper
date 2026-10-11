#!/bin/sh
D=$(cd "$(dirname "$0")" && pwd); tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/data/gnome-shell/extensions"
ln -s /tmp/claude-1000/-home-john/b7fa5569-ff9c-4daa-99f3-8112e4e109b5/scratchpad/scn/perfext "$tmp/data/gnome-shell/extensions/fishtank@lil-klorox"
ln -s "$D/probe" "$tmp/data/gnome-shell/extensions/probe@scratch"
export XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config" MUTTER_DEBUG_DUMMY_MODE_SPECS=1720x720 SHOT_DIR="$D"
rm -f "$D"/s*.png
timeout 40 dbus-run-session -- sh -c "gsettings set org.gnome.shell welcome-dialog-last-shown-version 999 && gsettings set org.gnome.shell enabled-extensions \"['fishtank@lil-klorox','probe@scratch']\" && exec gnome-shell --headless --wayland --virtual-monitor 1720x720" > "$D/log" 2>&1
grep -iE 'fishtank|JS ERROR|error' "$D/log" | grep -v -iE 'ibus|portal|xdg' | head -20; ls "$D"/s*.png
