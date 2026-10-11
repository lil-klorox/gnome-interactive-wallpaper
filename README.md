# fishtank

An interactive aquarium as your GNOME desktop wallpaper. Fish swim around behind your windows and
react to the mouse when it is over bare desktop: shy fish dart away, curious ones come over to look.
It is a GNOME Shell extension (GNOME 45 to 49), drawn inside the shell with no extra programs.
It pauses itself when every screen is covered by a maximized or fullscreen window.

## Install

    ln -s ~/personal-projects/fishtank ~/.local/share/gnome-shell/extensions/fishtank@lil-klorox

(or copy the folder there under that name). On Wayland the shell only finds new extensions at
login, so log out and back in, then:

    gnome-extensions enable fishtank@lil-klorox

To turn it off: `gnome-extensions disable fishtank@lil-klorox`. After editing the code, log out
and in again to load the new version.

## Test without touching your session

    ./dev.sh

This opens a nested GNOME Shell in a window with the extension enabled. It uses a throwaway
settings folder, so your real extensions and settings are left alone. Errors print in that
terminal (look for `fishtank`). Set the window size with `SIZE=2560x1080 ./dev.sh`.

Fish logic self-check (no shell needed): `gjs -m check.js`.

If something goes wrong in your real session: `journalctl --user -b | grep -i fishtank`.
