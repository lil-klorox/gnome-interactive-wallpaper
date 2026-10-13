# Writing a scene

A scene is a folder under `scenes/` with a `scene.js` that exports one function. The engine hands
that function a `ctx` (a spot on the background to draw into, the screen size, a running summary of
what's happening on the desktop, your pictures, your settings and a small save file) and then calls
`tick` about 30 times a second while anyone can see it. Full details are in [DESIGN.md](../DESIGN.md).

## The contract

```js
export default function create(ctx) {
    // build actors under ctx.root once, here
    return {
        tick(dt, t) {},   // dt, t in seconds; read ctx.world, move actors; return false = nothing moves
        destroy() {},     // optional cleanup; the engine destroys ctx.root for you
    };
}
```

What `ctx` gives you:

| field | what it is |
|---|---|
| `root`, `w`, `h` | the spot you draw into (a `Clutter.Actor` covering one monitor that ignores clicks), and its size in px |
| `world.pointer` | `{x, y, speed, over, down}`: `over` = the mouse is on bare desktop, `down` = button held |
| `world.windows` | `[{x, y, w, h, moving, id, vx, vy, age}]` for windows on this monitor; `id` stays the same for a window while it lives (see Window motion) |
| `world.area` | `{x, y, w, h}`: the part of the monitor not covered by the top bar or a dock |
| `monitor` | `{index, count, primary}`: which monitor this is, how many there are, and whether it's the main one |
| `canvas({w, h, tile, px})` | a picture you paint yourself, byte by byte (see Canvas) |
| `world.idle`, `hour`, `dark` | seconds since the last input, local hour 0–24, dark style on |
| `world.lightsOn`, `warm` | whether the lights are on right now, and whether it's dawn/dusk (see Lights) |
| `world.notifications` | a count that goes up by one per notification; compare it to last tick |
| `world.ready` | turns true once your first pictures have loaded, or after 3 s (some may still be empty then) |
| `world.gap` | on the first tick after a pause (window covering the screen, overview, freeze) the seconds it was away (over 1 s), else 0 |
| `image(name, fallback)`, `sheet(name, fallback)` | art from `assets/`: the manifest entry plus `content`, an `St.ImageContent` that stays empty until decoded (see Art and Fallback art) |
| `ref`, `images` | the screen height your art was drawn for, and the manifest entries |
| `settings`, `onSettings(fn)` | your scene's settings and a way to hear when they change (see Settings) |
| `store.get()`, `store.set(obj)` | a small JSON save file for this scene (up to 64 KB). It stays in memory while GNOME runs, so what you save in `destroy()` is there for the next `create`, even right after a lock and unlock |

`ctx.world` and `ctx.settings` are the same objects every tick and the engine updates them in place,
so keep a reference and read them; never connect your own shell signals.

## Walkthrough: `scenes/dot/`

The demo scene is the whole contract in about 40 lines: a dot that eases toward the mouse, pops on
each new notification, dims when its lights are off, and has a colour and size you can change in the
settings window. Open `scenes/dot/scene.js` and `scenes/dot/settings.js` next to this page.

Two things in it are easy to miss. Its state lives in local variables, never at module level,
because the engine may build your scene again at any time. And it moves a time-based fraction of
the way each tick, `1 - Math.exp(-3 * dt)`, so its speed doesn't depend on the frame rate.

To register a scene, add one line to `SCENES` in `scenes/index.js` (the first entry is the default)
and import its settings list at the top:

```js
import {SETTINGS as dot} from './dot/settings.js';
dot: {name: 'Dot (demo)', load: () => import('./dot/scene.js'), settings: dot},
```

## Settings

Your scene's knobs are a plain list in `scenes/<id>/settings.js`. The engine stores them, checks
them, and builds the rows of the settings window from the list, so you never write any settings UI
or touch the GSettings schema.

```js
export const SETTINGS = [
    {key: 'color', type: 'choice', label: 'Colour', group: 'Dot', default: 'amber',
        choices: [['amber', 'Amber'], ['mint', 'Mint'], ['rose', 'Rose']]},
    {key: 'size', type: 'int', label: 'Size', group: 'Dot', default: 5, min: 1, max: 10, step: 1, rebuild: true},
];
```

Each entry has a `key`, a `type`, a `label` people will read, a `group` (one box in the window per
group) and a `default`. The types are `bool` (a switch), `int` and `double` (a number box; give
`min`, `max` and `step`), `choice` (a drop-down; `choices` is a list of `[id, label]`) and `time`
(hours and minutes; the value is minutes since midnight, so 06:30 is 390).

One more type shows things instead of changing them. A `log` row lists recent events your scene
saved in its store, newest first, up to 7 (or `max`):

```js
{key: 'tankLog', type: 'log', label: 'Tank log', group: 'This week', path: ['tank', 'log'],
    kinds: {fry: 'Baby fish were born', moult: 'A shrimp shed its shell'}, empty: 'Nothing yet'},
```

`path` says where the list sits in your store (here `store.get().tank.log`), and each entry is
`{day: 'YYYY-MM-DD', kind}`. The row shows the sentence from `kinds` and the day; entries with an
unknown kind or a bad day are skipped. The settings window reads your store file but never writes it,
and a `log` row has no value in `ctx.settings`.

An `action` row is a button, for things like "smooth all the sand":

```js
{key: 'resetSand', type: 'action', label: 'Smooth all the sand', group: 'Rake', default: 0},
```

Its value is how many times the button was pressed. Each press reaches your scene as an ordinary
change, so check for it with `keys.includes('resetSand')` in `onSettings` (other keys may come in
the same call). It never rebuilds the scene, and "Reset to defaults" leaves it alone.

In your scene, `ctx.settings.size` is always a valid value: a wrong type, a number out of range or a
choice that isn't listed falls back to the default before your scene ever sees it. When someone
changes a setting, `ctx.settings` updates in place and your `ctx.onSettings(keys => ...)` runs with
the keys that changed. If a setting is only read in `create` (like how many fish there are, or the
dot's size), mark it `rebuild: true` and the engine simply builds your scene again instead. A
rebuild loses whatever was moving, so use it only for what `create` alone can do: adding or removing
a fish, or swapping one prop for another, is nicer in `onSettings`. Use the plainest label you can
and keep the list short.

A setting can also say `still: <value>`: the value used when the poster is made (below), for example
`still: 0` on a fish count or `still: false` on a critter, so the poster shows only the scenery.

When your scene was paused, the first tick back has `world.gap` set to how many seconds it was away
(else 0). The engine never fakes the missed ticks; if you want things to have moved meanwhile, jump
them forward once, and cap it (say 20 s of travel) so an hour away doesn't fling everything around.

## Lights

Lots of scenes want day and night, so the engine runs one lights schedule and puts the answer in
`world.lightsOn` (and `world.warm`, which is true for 45 minutes either side of an automatic switch,
for a dawn/dusk tint). By default the lights are on from 06:00 to 21:00. To let people change that,
declare these three reserved keys in your settings, exactly like the dot does:

```js
{key: 'lights', type: 'choice', label: 'Lights', group: 'Lights', default: 'auto',
    choices: [['auto', 'On a schedule'], ['on', 'Always on'], ['off', 'Always off']]},
{key: 'lightsOn', type: 'time', label: 'Lights on at', group: 'Lights', default: 360},
{key: 'lightsOff', type: 'time', label: 'Lights off at', group: 'Lights', default: 1260},
```

The schedule can wrap past midnight (on at 22:00, off at 06:00), and the same on and off time means
always on.

## Poster

The lock screen, the overview and the workspace-switch animation can't show a live scene; they show
GNOME's normal wallpaper. So a scene can ship a still picture of itself, `scenes/<id>/poster.jpg`
(plus an optional `poster-dark.jpg`, used while your scene's lights are off). While your scene runs,
the engine makes the poster GNOME's wallpaper and swaps it when the lights switch, and when the live
wallpaper is turned off it puts the user's own wallpaper back. The poster has no wildlife (see
`still`), so when the live scene comes back the fish appear on top of the same scenery instead of
jumping. The poster also shows for the moment while your pictures load, so add one only if your
scene paints the whole screen (that's why the dot has a plain backdrop).

Make it with `SCENE=<id> tools/poster.sh`: it runs your scene in a hidden test shell at noon and at
23:00 and saves both pictures (use `SIZE=WxH` for a smaller one; the dot's is 860x360, and your
monitor's own size makes the overview line up exactly). Nothing goes in the registry; the engine
just looks for the files.

## Fallback art

`ctx.image(name, fallback)` and `ctx.sheet(name, fallback)` take an optional second name. If `name`
is missing from the manifest (or its entry is broken), you get `fallback` instead and the log says
so once. With no usable fallback either, `image()` throws, which stops the scene like any other
error. Together with a `choice` setting, that's how optional pieces work: offer `castle | temple`,
call `ctx.image(ctx.settings.castle, 'castle')`, and if the temple art isn't there the castle shows.
Keep alternatives the same shape (same points, same frame layout) so the rest of your code doesn't
care which one it got.

## Window motion

Each window in `world.windows` also has `vx, vy` (how fast it's moving, in px per second, smoothed a
little) and `age` (seconds since it showed up on this monitor). Windows that were already open when
your scene was built start with `age` 3600, so only windows that really just opened look new. A
window that leaves the monitor or the workspace and comes back counts as new again.

## Work area and monitors

`world.area` is the free part of the screen, without the top bar or a dock, in your own coordinates.
Use it to keep things where people can see them. `ctx.monitor` tells you which monitor you're on, so
a scene can, say, put its title only on the main screen or save one thing per monitor. After a
monitor is plugged in or out the numbers can point at a different screen; plan for that.

## Sleepy ticks

If nothing in your scene is moving, return `false` from `tick`. The engine then calls you only about
5 times a second, and right away when something happens (the mouse moves or clicks, a window moves
or opens, a notification, the lights or dark style change, a setting changes). `dt` is the real time
since your last tick, up to 0.3 s. Return anything else (or nothing) to keep the normal 30 ticks a
second. The dot does this: `return p.over || pop > 0;`.

## Canvas

For things you can't make from ready-made pictures, like grooves raked into sand, ask for a canvas:

```js
const cv = ctx.canvas({w: cols, h: rows, tile: 256, px: 2});  // w × h cells, each px × px on screen
ctx.root.add_child(cv.actor);
cv.dirty(x0, y0, x1, y1);   // cells that changed (end not included); safe with any numbers
cv.flush((buf, x, y, tw, th) => {
    // write tw × th cells starting at cell (x, y): 4 bytes each (premultiplied RGBA), row length tw * 4
}, 4);                      // at most 4 tiles this tick; returns how many are still waiting
```

The canvas is a grid of tiles and only the tiles you marked get painted and sent to the screen again,
so keep your own state (a height map, say) and turn it into colours inside `fill`. One 256 px tile
takes well under a millisecond to send. Its memory (every tile, `tile × tile × 4` bytes) counts
toward the scene's 100 MB budget; a canvas that doesn't fit makes `canvas()` throw, which stops the
scene like any other error. It's freed with `ctx.root`.

## Bendy bodies

A plant, a tail, a rope or an eel is easiest to draw as a row of pieces, each a sprite, that bend
one after another. `bend.js` in the engine has the four small helpers that keep such a row looking
like one smooth body instead of a stack of blocks:

```js
import {spacing, heading, shear, spring} from '../../bend.js';

const gap = spacing(seg.w, 0.2);       // pieces whose art fades out over 20 % at each end
piece.set_pivot_point(0, 0);           // shear replaces the piece's own move/rotate/mirror, so do those on its parent
shear(piece, 12, jointY);              // lean 12° about the joint row jointY (px from the piece's top)
sprite.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, heading(dx, dy));
sprite.set_scale(dx < 0 ? -1 : 1, 1);  // going left: mirror it, same angle
const p = {bend: 0, bv: 0};            // something brushes it: p.bv += push
spring(p, dt, {limit: 1, maxSpeed: 4, stiff: 12, damp: 3});   // every tick; lean = p.bend * your max angle
```

Three rules sit behind them. Soft edges overlap: if each piece's art fades out at both ends, place
the pieces `spacing(width, fade)` apart so the fades overlap and no seam shows. Shear, don't rotate:
a rotated piece tilts its edge, so a wide piece splits open at the joint; `shear` slides its rows
sideways instead, so the edges stay level and meet across the full width. Clamp the bend: pushes add
up, and without a limit a plant brushed over and over leans flat and its art stretches out sideways,
so `spring` holds the bend to ±`limit` and its speed to ±`maxSpeed` (the defaults are the ones shown).
One catch with mirrored sprites: Clutter mirrors after it rotates, so keep the angle `heading` gives
and only flip the scale. The fishtank's plants, jellyfish tentacles and moray all use these.

## Rules the engine enforces

- A `create` or `tick` that throws gets that monitor's scene stopped and logged. A tick that keeps
  taking longer than two frames (about 3 seconds in a row) gets a 60 second rest. The first problem
  shows the user one notification; after three, the scene stays off until they turn it off and on.
- Budget: about 1.5-2 ms per tick for the whole scene at default settings.
- No `new` actors per tick: build pools in `create` and reuse them.
- Move with `set_translation`; put opacity on the actor that holds the picture, not its parent.
- No sync file IO, no subprocesses, no Gtk/Gdk/Adw imports, no GdkPixbuf/Cogl (use `ctx.image`).
- Check `ctx.images[name]` before using art, so a missing file doesn't break the scene.
- `settings.js` is pure data: no `gi://` imports, because the settings window loads it too.

## Art

Put PNGs in `scenes/<id>/assets/` and describe them in `assets/manifest.json`:

```json
{"ref": 1440, "images": {"rock": {"w": 300, "h": 200, "px": [300, 200], "base": [150, 190]}}}
```

`w, h` are the on-screen size when the monitor is `ref` px tall (scale by `ctx.h / ctx.ref`), `px`
is the PNG's real size, and any `[x, y]` key is a named point. A sprite sheet adds `n` and `cols`;
`ctx.sheet(name).make()` gives an actor and `show(actor, i)` picks frame `i`. The full format is in
[DESIGN.md](../DESIGN.md#manifest-scenesidassetsmanifestjson-the-art-contract).

You can paint art by hand and write the entry yourself, or render it with Blender like fishtank
does. Its helpers in `scenes/fishtank/blender/common.py` set up the camera and lights;
`sprite(name, points)` renders, crops and writes the manifest entry (including `px`) for you:

    blender -b --factory-startup -P scenes/fishtank/blender/scene_castle.py

## Test it

    make check                 # logic self-checks, no shell needed
    ./dev.sh                   # nested GNOME Shell in a window, your session untouched
    ./dev.sh --headless 40     # hidden run: screenshots + stats.txt (memory, tick ms, ticks/s)
    SCENE=dot HOUR=23 ./dev.sh --headless 40   # pick the scene and the hour

Pick your scene and its settings in the test shell's Quick Settings tile. Errors show up in that
terminal. If your scene has logic worth checking, add a `scenes/<id>/check.js` with plain asserts
(no `gi` imports); the root `check.js` runs it, and it also checks that every default in your
settings list fits its own rules.

## Open a PR

Fork the repo, add `scenes/<id>/` and its line in `scenes/index.js`, run `make check` and a
`./dev.sh --headless` pass, and open a pull request with a screenshot. Keep art within the memory
budget (all decoded pictures in your manifest ≤ 100 MB; `stats.txt` shows the total).
