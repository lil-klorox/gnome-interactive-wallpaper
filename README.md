# Interactive Wallpaper

<!-- DRAFT: final plain-language rewrite + screenshot/GIF comes last. -->

Living wallpapers for GNOME Shell that notice your desktop: fish scatter from dragged windows,
doze when you're idle, dim at night and glance at notifications. No video, no browser, one
extension. The first scene is a fishtank.

Everything is drawn inside GNOME Shell itself, so there is no extra program running. It pauses
when every screen is covered by a maximized or fullscreen window, when the screen is locked, and
in the overview, and it slows to 10 frames a second once you've been idle for a minute.

## Compatibility

GNOME Shell 45 or newer, on any distro that ships it (Debian 13 and later, for example).

## Install from source

    git clone https://github.com/lil-klorox/gnome-interactive-wallpaper
    cd gnome-interactive-wallpaper
    make install

On Wayland the shell only finds new extensions at login, so log out and back in, then run
`gnome-extensions enable interactive-wallpaper@lil-klorox`. Pick the scene in the extension's
settings (`gnome-extensions prefs interactive-wallpaper@lil-klorox`).

## Uninstall

    gnome-extensions uninstall interactive-wallpaper@lil-klorox

## Try it without touching your session

`./dev.sh` opens a nested GNOME Shell in a window with the extension enabled and a throwaway
settings folder. `./dev.sh --headless 40` runs it off-screen and saves screenshots plus a
`stats.txt` with memory and tick time. `make check` runs the logic self-checks (no shell needed).

## Logs

    journalctl -f /usr/bin/gnome-shell

## Make your own scene

A scene is one folder with one function. See [docs/writing-a-scene.md](docs/writing-a-scene.md),
and [DESIGN.md](DESIGN.md) for how the pieces fit.

## License

GPL-2.0-or-later, see [LICENSE](LICENSE).
