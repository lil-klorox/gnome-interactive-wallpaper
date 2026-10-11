# Writing a scene

A scene is a folder under `scenes/` with a `scene.js` that exports one function. The host hands it
a `ctx` (a root actor, the screen size, a snapshot of what's happening on the desktop, images and a
small save file) and calls `tick` about 30 times a second. Full details: [DESIGN.md](../DESIGN.md).

## The contract

```js
export default function create(ctx) {
    // build actors under ctx.root once, here
    return {
        tick(dt, t) {},   // dt, t in seconds; read ctx.world, move actors
        destroy() {},     // optional cleanup; the host destroys ctx.root for you
    };
}
```

What `ctx` gives you:

| field | what it is |
|---|---|
| `root`, `w`, `h` | a non-reactive `Clutter.Actor` covering one monitor, and its size in px |
| `world.pointer` | `{x, y, speed, over, down}`: `over` = cursor is on bare desktop, `down` = button held |
| `world.windows` | `[{x, y, w, h, moving}]` for windows on this monitor |
| `world.idle`, `hour`, `dark` | seconds since input, local hour 0–24, dark style on |
| `world.notifications` | a count that goes up by one per notification; compare to last tick |
| `image(name)`, `sheet(name)` | art from `assets/` (see below) |
| `ref`, `images` | the height your art was drawn for, and the manifest entries |
| `store.get()`, `store.set(obj)` | a small JSON save file for this scene (≤ 64 KB) |

`ctx.world` is the same object every tick and the host updates it in place, so keep a reference
and read it; never connect your own shell signals.

## Walkthrough: `scenes/dot/scene.js`

The demo scene is the whole contract in about 30 lines: a dot that eases toward the cursor, pops
on each new notification and dims at night or in dark mode. Open it next to this page.

1. **Build once.** `create` makes one `St.Widget` (a round orange dot sized from `ctx.h`), adds it
   to `ctx.root`, and keeps its state (`x, y, notes, pop`) in local variables. No module-level
   state: the host may build your scene again after a disable/enable.
2. **Read `world` in `tick`.** When `pointer.over` is true (cursor on bare desktop) the dot moves a
   time-based fraction of the way there, `1 - Math.exp(-3 * dt)`, so speed doesn't depend on the
   frame rate. It moves with `set_translation`, which is cheap.
3. **Turn counters into events.** It keeps the last `world.notifications`; when the number changes
   it sets `pop = 1`, which then decays and drives `set_scale`.
4. **React to time and theme.** `hour` and `dark` pick the opacity.
5. **`destroy` is empty**, because everything it made lives under `ctx.root`, which the host
   destroys.

To register a scene, add one line to `SCENES` in `scenes/index.js` (the first entry is the default):

```js
dot: {name: 'Dot (demo)', load: () => import('./dot/scene.js')},
```

## Rules the host enforces

- A `tick` that throws, or keeps running over two frames, gets the scene destroyed and logged once.
  Budget: all ticks together under 1 ms on average.
- No `new` actors per tick: build pools in `create` and reuse them.
- Move with `set_translation`; put opacity on the actor that holds the texture, not its parent.
- No sync file IO, no subprocesses, no Gtk/Gdk/Adw imports, no GdkPixbuf/Cogl (use `ctx.image`).
- Check `ctx.images[name]` before using art, so a missing file doesn't break the scene.

## Art

Put PNGs in `scenes/<id>/assets/` and describe them in `assets/manifest.json`:

```json
{"ref": 1440, "images": {"rock": {"w": 300, "h": 200, "px": [300, 200], "base": [150, 190]}}}
```

`w, h` are the on-screen size when the monitor is `ref` px tall (scale by `ctx.h / ctx.ref`), `px`
is the PNG's real size, and any `[x, y]` key is a named point you can use. A sprite sheet adds
`n` (frames) and `cols` (frames per row); `ctx.sheet(name).make()` gives an actor and
`show(actor, i)` picks frame `i`. Textures load in the background, so art appears a moment after
the scene starts.

You can paint art by hand and write the entry yourself, or render it with Blender like fishtank
does. Its helpers in `scenes/fishtank/blender/common.py` set up the camera and lights;
`sprite(name, points)` renders, crops and writes the manifest entry (including `px`) for you:

    blender -b --factory-startup -P scenes/fishtank/blender/scene_castle.py

## Test it

    make check                 # logic self-checks, no shell needed
    ./dev.sh                   # nested GNOME Shell in a window, your session untouched
    ./dev.sh --headless 40     # off-screen run: screenshots + stats.txt (memory, tick ms)

Pick your scene in the nested shell's extension settings. Errors show up in that terminal.
If your scene has logic worth checking, add a `scenes/<id>/check.js` with plain asserts (no `gi`
imports); the root `check.js` runs it.

## Open a PR

Fork the repo, add `scenes/<id>/` and its line in `scenes/index.js`, run `make check` and a
`./dev.sh --headless` pass, and open a pull request with a screenshot. Keep art within the memory
budget (all decoded textures ≤ 65 MB; `stats.txt` shows the total).
