#!/bin/sh
# Run the extension in a nested gnome-shell window. Uses a throwaway data/config dir,
# so your real session's extension list and settings are never touched.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/data/gnome-shell/extensions"
ln -s "$here" "$tmp/data/gnome-shell/extensions/fishtank@lil-klorox"
export XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config"
export MUTTER_DEBUG_DUMMY_MODE_SPECS="${SIZE:-1600x900}"
# GNOME 49 replaced --nested with --devkit.
mode=--nested
gnome-shell --help 2>&1 | grep -q -- --devkit && mode=--devkit
dbus-run-session -- sh -c "gsettings set org.gnome.shell enabled-extensions \"['fishtank@lil-klorox']\" && gsettings set org.gnome.shell welcome-dialog-last-shown-version 999 && exec gnome-shell $mode --wayland"
