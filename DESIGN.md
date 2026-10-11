# gnome-interactive-wallpaper — design

A GNOME Shell extension (ESM, GNOME 45+) that draws a living wallpaper inside the shell as
Clutter/St actors in each monitor's background actor. The host owns the background slot, the
clock, pause rules, a polled `world` snapshot, textures and a per-scene JSON store. A scene is a
folder with one `create(ctx)`. Fishtank is the first scene; `dot` is the minimal example.
No subprocess, no WebKit, no video, no IPC, no deps.

## Decisions

- **`create(ctx)` function, not a class.** One call in, `{tick, destroy}` out; the host destroys
  `ctx.root` itself, so scenes never unhook anything.
- **Host owns images and store.** The pixbuf → St.ImageContent dance and XDG paths live in the
  host once; scenes never import GdkPixbuf or Cogl.
- **`world` is a polled snapshot** the host mutates before each tick; events are counters scenes
  diff. Pull means a scene can never leak a signal connection.
- **Registry `scenes/index.js`**, no scene.json: one line gives id, name, lazy loader; prefs.js
  imports it without `gi://St`.
- **Safety:** first-party scenes only (no user scene dir); try/catch per tick and destroy; slow-tick
  watchdog; every private shell field read through `shell.js`.

## Layout

```
metadata.json        uuid interactive-wallpaper@lil-klorox, settings-schema
extension.js         lifecycle, mount per monitor, timer + fps policy, pause, watchdog, world fill, ctx build
shell.js             the ONLY private-API file (bg managers, background group, startup), each with a why-comment
world.js             pure: makeWorld(), update(world, raw, dt), fpsMs(idle)
render.js            pure: parseManifest, scaleFor, bytesOf, frameOffset
ctx.js               image(), sheet(), store — the only St.ImageContent code
prefs.js             one Adw.ComboRow bound to GSettings key `scene`
schemas/             key scene: string, default 'fishtank'
check.js             `gjs -m check.js`: render + world asserts, then each scenes/*/check.js
scenes/index.js      {fishtank: {name, load: () => import('./fishtank/scene.js')}, dot: {...}}
scenes/dot/          the minimal example scene (see docs/writing-a-scene.md)
scenes/fishtank/     scene.js, tank.js, fish.js, brain.js, steer.js, check.js, assets/, blender/
dev.sh, tools/probe/ nested / headless test shell
Makefile             check | pack | install
```

## Contract (scenes code against this only)

```js
// scenes/<id>/scene.js
export default function create(ctx) { return {tick(dt, t) {}, destroy() {}}; }

ctx = {                     // one per monitor, frozen
  root,                     // Clutter.Actor w×h, non-reactive, inside the monitor's background actor
  w, h,                     // px
  ref,                      // manifest.ref: screen height the art was drawn for
  images,                   // manifest map (frozen); check before use, missing art is not fatal
  world,                    // snapshot below; same object every tick, host mutates in place
  image(name),              // → {...entry, content: St.ImageContent}; content is empty until decoded
  sheet(name),              // → {...entry, make() → clip actor w×h with the sheet as child, show(actor, i)}
  store: {get() /* {} on missing/bad */, set(obj) /* async, whole-file JSON ≤ 64 KB, else log + skip */},
};

world = {                   // all coords monitor-local
  pointer: {x, y, speed, over, down},  // over = bare desktop; down = button 1 held
  windows: [{x, y, w, h, moving}],     // visible on this monitor + active workspace, geometry only
  idle,                                // seconds since last input
  hour,                                // 0..24 local
  dark,                                // color-scheme === 'prefer-dark'
  notifications,                       // monotonic count this session
};

ext.stats = {bytes, k, actors, tickMs /* EMA */, ticks /* monotonic */}  // Looking Glass + review
```

Store lives at `get_user_data_dir()/interactive-wallpaper/<id>.json`.

## Manifest (`scenes/<id>/assets/manifest.json`, the art contract)

```json
{"ref": 1440,
 "images": {
   "castle": {"w": 406, "h": 641, "px": [406, 641], "base": [209, 598.5]},
   "clown":  {"w": 111, "h": 52, "n": 60, "cols": 12, "px": [1332, 260], "anchor": [65.1, 28.3],
              "eyes": [[[98.7, 16.4, 4.5, 0.66]], ...], "iris": "#d0601a", "yaws": [...], "len": 107},
   "puffer": {..., "puff": "puffer-puff"}, "puffer-puff": {...}}}
```

- `w, h` = ONE frame's on-screen size at `ref`; `n` frames (default 1), `cols` per row (default `n`).
  The file `assets/<name>.png` is a `cols × ceil(n/cols)` grid; frame `i` sits at
  `frameOffset(i) = [(i % cols)·w, floor(i / cols)·h]` (row-major).
- `px` = the PNG's real pixel size. Art is often pre-downscaled (backdrop is 860×360 shown at
  3440×1440), so budget math uses `px`, never `w·h`.
- Any `[x, y, ...]` key is a point in frame px (`base`, `j1..`, `outlet`, `mouth`, ...). Fish
  `eyes[i]` = list of `[x, y, r, squash]` for frame `i`, same row-major order.
- `parseManifest` is the trust boundary: an entry with bad `w/h/n/cols` is dropped and logged once.
- Written only by the Blender helper `common.manifest()`; runtime never writes it.

## Render layer

- **Budget first:** at mount, `k = scaleFor(maxMonitorH, ref, bytesOf(images, 1))`, one factor per
  scene, logged once. Over-budget art simply loads smaller.
- **Async load:** `image()` creates the content synchronously (empty paints nothing, so art pops in
  ~0.5 s after enable), then `read_async → new_from_stream_at_scale_async` decodes off the main
  loop. Missing file → log once, content stays empty; never throws from a callback.
- **Cache on the extension instance** (not module state): every monitor and every fish of a species
  share one texture; dropped in `disable()`.
- **Filters `LINEAR, LINEAR`**, no mipmaps: textures are already ≈ screen size, mipmaps cost +33 %.
- **Sheets:** clip parent `w×h` + one child holding the whole sheet; a frame change is one child
  translation. Opacity on the child (and eye actors); scale/rotate/mirror/pivot on the parent.
- **Actors:** move with `set_translation`; no `new` per tick (pool bubbles/flakes); no
  OffscreenRedirect unless a measured layer proves hot (a full-screen FBO is ~20 MB).

## Host behaviour

- Pointer: `global.get_pointer()` sampled per tick; "bare desktop" = no visible non-minimized
  window on the active workspace contains the point (DESKTOP-type windows count as desktop).
  Works under DING/desktop-icons, which swallow motion events.
- Windows from `list_windows()` → `get_frame_rect()` on restack/grab begin/end, plus one rect per
  tick during a grab. Idle from the core idle monitor; dark from `color-scheme`; notifications from
  `Main.messageTray` source/notification-added (a counter, never the object).
- Timer 33 ms, 100 ms when idle > 60 s; stopped when every monitor is covered by a
  maximized/fullscreen window, screen locked, or in overview.
- Watchdog: tick > 2× frame → `slow++`, else decay; `slow > 30` → destroy + log once (same path as
  a throw). A throw never reaches gnome-shell.
- e.g.o rules: nothing created before `enable()`, full cleanup in `disable()`, no Gtk/Gdk/Adw in
  the shell process, no sync IO in ticks, no log spam, no module-level mutable state.

## Budget (lightweight is a top priority)

- Decoded textures ≤ 65 MB total (fishtank at k=1: ~41 MB).
- All scene ticks < 1 ms avg at 30 fps; 10 fps when idle > 60 s; 0 when covered/locked/overview.
- Measured with `./dev.sh --headless` (`stats.txt`) before review.

## Fishtank scene

`scene.js` wires `Tank(ctx)` (scenery, bubbler, lid, snail, plants) and `School(ctx, layers,
bounds)`. Back to front: water + rays/caustics, far plates, far fish layer, decor (castle, ship,
chest, diver), bubbler + bubbles, sand/rocks/snail, near fish layer, foreground plants. Plant sway
segments are clip boxes over one texture.

Fish = brain / motor / body, so each can change alone:
- `brain.js` — the thinking: a per-fish state machine (wander, curious, flee, rest, feed, ...), each
  state returns an intent `{target|away, speed, look}`. Personality is plain per-species data.
  A new behaviour = one state + one transition.
- `steer.js` — the motion: intent → movement (wander, bounds, separation, schooling, turn limits).
- `fish.js` — the body: sheet frame from yaw and tail phase, pupil overlay looking at `look`, puff.

World reactions: moving/new windows are threats → `flee`; idle > 600 s → rest more, light dims;
night 21–6 and dawn/dusk tints (`ponytail:` fixed hour bands); dark mode cools the light;
a notification → bubble burst and fish glance top-centre; click on bare desktop → flakes sink,
fish `feed`. Store `{fish: {id: {born, fed}}}`: fish grow over 30 days, fed fish get bolder.

## Art pipeline (Blender, offline)

Headless bpy scripts in `scenes/fishtank/blender/` are the source of truth; runtime never needs
Blender. `~/opt/blender/blender -b --factory-startup -P scenes/fishtank/blender/<script>.py`.
- `common.py`: Cycles, ortho camera, shared underwater light rig and PBR helpers, `sprite()` (render
  + crop + points), `manifest()` (flock'd write of one entry, adds `px`).
- `scene_*.py`: one prop each. `fish.py [species ...]`: swim frames × yaws (profile → front; the
  runtime mirrors the other half), per-frame eye points, puffer inflation sheet.
- Look: fully lit, solid, a little dorky but detailed (wear, moss, grime, translucent fins); no
  plastic CG. Light, density (`PPU` at `ref`) and haze are shared so scenery and fish match.

## Not building

OOP/WebKit/Godot host, user scene dir, scene.json, pub/sub bus, power-saver, sunrise math,
MPRIS/weather, per-monitor scene picks, fish names, breeding/hunger, prefs beyond one combo row,
translations, eslint.
