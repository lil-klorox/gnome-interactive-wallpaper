# Interactive Wallpaper

This is a small engine for living wallpapers on GNOME. It runs inside GNOME Shell itself as one extension, so there's no video playing, no hidden web browser and no extra program running in the background. GNOME draws everything, and the engine's job is to keep that cheap and safe so that a wallpaper which reacts to your desktop can stay on all day without you noticing it.

What makes it different is how little a wallpaper has to do. A wallpaper here is called a scene, and a scene is just one folder with one function in it. The engine hands that function a spot on the background plus a running summary of what's happening on your desktop, and the scene decides how to react. Everything hard, like memory, loading art, multiple monitors and knowing when to stop, is handled once by the engine, so no scene has to get it right on its own.

## What a scene gets

Here's a trimmed copy of the demo scene in `scenes/dot`, a dot that drifts toward your mouse (the full file also makes it pop on notifications and dim at night):

```js
import St from 'gi://St';

export default function create(ctx) {
    const r = ctx.h / 20; let x = ctx.w / 2, y = ctx.h / 2;
    const dot = new St.Widget({width: 2 * r, height: 2 * r, style: `background-color: #ffbe3c; border-radius: ${r}px;`});
    ctx.root.add_child(dot);
    return {
        tick(dt) {
            const p = ctx.world.pointer, f = 1 - Math.exp(-3 * dt);
            if (p.over) { x += (p.x - x) * f; y += (p.y - y) * f; }
            dot.set_translation(x - r, y - r, 0);
        },
    };
}
```

That's the whole deal. The engine calls `create` once with `ctx` so you can build your things, then calls `tick` about 30 times a second, and you can also return a `destroy` if you need cleanup, though the engine removes everything under the root for you. Inside `ctx` you'll find:

- a root actor covering one monitor, which is just the blank spot on the background you draw into
- your pictures and sprite sheets (a sprite sheet is one image holding all the frames of an animation), loaded for you
- a `world` snapshot the engine refreshes before every tick: where the mouse is and whether it's over bare desktop, where the windows are and which one is being dragged, how long you've been away, the hour, whether dark mode is on, and a count of notifications. It never includes window titles or what a notification says, so a scene can react to your desktop without seeing what's on it.
- a small save store (up to 64 KB per scene) for things that should last between logins

And here's what the engine does so the scene doesn't have to:

- shrinks any art to fit your screen, and keeps shrinking until the whole scene fits a memory budget of about 65 MB
- loads and decodes pictures in the background, so the desktop never stutters while art loads
- shares one copy of each picture across all your monitors
- plays sprite sheet animations by sliding the visible window over the sheet, so a new frame doesn't mean sending the picture to the graphics card again
- stops completely when nobody can see it (a window fills the screen, the overview is open, or the screen has gone blank), and drops to a slower frame rate once you've been idle for a minute
- runs a watchdog, which means a scene that throws an error or keeps running too slowly gets stopped and logged once, while the rest of your desktop carries on as normal

For now it only runs scenes that ship in this repo. There's no folder where you can drop in someone else's scene, because a scene runs inside GNOME Shell with the same access the shell has, and that's not something to hand to code you haven't read.

## See it in action: the fishtank

![A fishtank wallpaper with a castle, a sunken ship, a diver and fish swimming](docs/screenshot.png)

The fishtank is the showcase scene, and it's there to show what the engine can carry. Fish wander around and loosely hang out together. When you move your mouse over the empty desktop, some swim over to see what you are and some dart away. Drag a window across the tank and the fish scatter out from under it. Walk away for a while and they settle down and doze, then come say hi when you're back. At night the tank goes dim and blue, a notification sends up a little burst of bubbles, and clicking the empty desktop drops in some food. Fish you feed get braver over the following days and slowly grow, which is the save store at work.

All of its art was modeled and rendered ahead of time in Blender, so your computer only has to slide pictures around, and the whole tank fits in about 40 MB of memory.

## What you need

GNOME 45 or newer, on any Linux that ships it. That includes Debian 13 and later, recent Ubuntu, and Fedora. It's built and tested on Wayland; X11 should work but hasn't been tested much.

## Install it

Grab the code and install it:

    git clone https://github.com/lil-klorox/gnome-interactive-wallpaper
    cd gnome-interactive-wallpaper
    make install

GNOME only notices new extensions when you log in, so log out and back in, then switch it on:

    gnome-extensions enable interactive-wallpaper@lil-klorox

If you ever want to pick a different scene, open its settings with `gnome-extensions prefs interactive-wallpaper@lil-klorox`.

To remove it, run `gnome-extensions uninstall interactive-wallpaper@lil-klorox`.

## Try it without touching your desktop

`./dev.sh` opens a separate test copy of GNOME in a window, with the wallpaper already running, so you can play with it without changing anything on your real desktop. `./dev.sh --headless 40` runs that test copy invisibly for 40 seconds and saves a few screenshots plus a small file with the memory and speed numbers. `make check` runs the quick logic tests, which don't need GNOME at all.

If something looks wrong, the wallpaper writes short notes to GNOME's log, which you can watch with `journalctl -f /usr/bin/gnome-shell`.

## Make your own scene

[docs/writing-a-scene.md](docs/writing-a-scene.md) walks through the dot scene from start to finish, covers how to describe your art so the engine can size it, and lists the few rules the engine enforces. [DESIGN.md](DESIGN.md) explains how all the pieces fit together. If you make something you like, open a pull request and it can ship with the next version.

## License

GPL-2.0-or-later. See [LICENSE](LICENSE).
