# gnome-interactive-wallpaper — design

A small engine for living wallpapers that runs inside GNOME Shell as one extension (ESM,
GNOME 45+), drawing Clutter/St actors in each monitor's background actor. The engine (the "host")
does the hard parts once, so scenes stay small: it owns the background slot, the frame clock and
pausing, a polled `world` snapshot (lights schedule included), texture sizing/loading/sharing under a
memory budget, per-scene settings with a generated settings page, a poster wallpaper, a Quick
Settings tile, a per-scene JSON store and a watchdog. A scene is a folder with one `create(ctx)`. Fishtank and the
sand garden are the scenes that prove the engine (sprites vs. a hand-painted canvas); `dot` is the
minimal example.
No subprocess, no WebKit, no video, no IPC, no deps.

## Decisions

- **`create(ctx)` function, not a class.** One call in, `{tick, destroy}` out; the host destroys
  `ctx.root` itself, so scenes never unhook anything.
- **Host owns images and store.** The pixbuf → St.ImageContent dance and XDG paths live in the
  host once; scenes never import GdkPixbuf or Cogl.
- **`world` is a polled snapshot** the host mutates before each tick; events are counters scenes
  diff. Pull means a scene can never leak a signal connection.
- **Registry `scenes/index.js`**, no scene.json: one line gives id, name, lazy loader and the
  scene's settings list; prefs.js imports it without `gi://St`.
- **Settings are data.** A scene lists its knobs in `settings.js`; the host stores them all in one
  GSettings key and builds the settings page from the list, so a new scene never touches the schema.
- **Safety:** first-party scenes only (no user scene dir); try/catch around build and tick; slow-tick
  watchdog; three strikes per scene load and it stays stopped; every private shell field read through
  `shell.js` (a missing one is logged once, never a half-built enable).

## Layout

```
metadata.json        uuid interactive-wallpaper@lil-klorox, settings-schema
extension.js         lifecycle, mount per monitor, frame clock, pause, watchdog, world fill, poster, Quick Settings tile
shell.js             the ONLY private-API file (bg managers, background group, startup), each with a why-comment
world.js             pure: makeWorld(), update(world, raw, dt), covers(rects, area), changed(raw, last)
render.js            pure: parseManifest, scaleFor, bytesOf, frameOffset, BUDGET
bend.js              pure: bendy many-sprite bodies (spacing, heading, shear, spring), see docs/writing-a-scene.md
settings.js          pure: resolve/encode (scene settings), lightsAt, posterPlan, parseStore
ctx.js               image(), sheet(), store, settings — the only St.ImageContent code
prefs.js             settings window: on/off, scene, then the scene's own rows built from its list
schemas/             keys scene, live, frozen, scene-settings, saved-background
check.js             `gjs -m check.js`: render/world/settings/poster asserts, then each scenes/*/check.js
scenes/index.js      {fishtank: {name, load: () => import('./fishtank/scene.js'), settings}, garden: {...}, dot: {...}}
scenes/garden/       scene.js, sand.js (pure sand math), settings.js, check.js, assets/, blender/
scenes/dot/          the minimal example scene (see docs/writing-a-scene.md)
scenes/fishtank/     scene.js, tank.js, fish.js, brain.js, steer.js, food.js, critters.js, settings.js, assets/, blender/
dev.sh, tools/probe/ nested / headless test shell; tools/poster.sh makes a scene's poster
tools/restore-wallpaper.js  `make uninstall` puts the saved wallpaper back
tools/parse-check.js `make pack`: staged files parse and their relative imports are packed
tools/*.desktop      app-search entry that opens the settings window (installed by make install)
Makefile             check | pack | install | uninstall
```

## Contract

The scene-facing contract (`create(ctx)` and every `ctx` and `world` field) is written once, in
[docs/writing-a-scene.md](docs/writing-a-scene.md#the-contract). Host-side facts it leaves out:

- `ctx` and `ctx.monitor` are frozen; `world` and `settings` are the same objects every tick, updated in place.
- The store lives at `get_user_data_dir()/interactive-wallpaper/<id>.json`.
- `ext.stats = {bytes, k, actors, tickMs /* EMA */, ticks}` for Looking Glass and review.

## Settings

- Declared in `scenes/<id>/settings.js` as pure data: `export const SETTINGS = [{key, type, label,
  group, default, min, max, step, choices: [[id, label]], rebuild, still}]`; types `bool | int | double |
  choice | time | action` (time = minutes since midnight, 0..1439; action = a button, value = how often
  it was pressed, default 0, a press arrives as `onSettings([key])`, never with `rebuild`), plus read-only
  `log` ({path, kinds, max?, empty?}: prefs reads the scene's store file and lists `{day, kind}` entries
  via `logLines()`, never writes it). `still` = the value poster runs use (fish count 0, critters off).
  "Reset to defaults" keeps action counts, so it doesn't press every button.
  Registered as `settings` in `scenes/index.js`.
- Stored in ONE key, `scene-settings` = JSON `{sceneId: {key: value}}`, only non-default values.
- Mark `rebuild` only for what `create` alone can do; counts and swaps belong in `onSettings`.
- `settings.js resolve()` is the trust boundary: wrong type, out of range, unlisted choice or bad JSON
  → clamp or default, unknown keys dropped, never throws. `encode()` writes declared keys only and
  keeps other scenes' blocks. `check.js` also checks every registered default fits its own declaration.
- Live: on `changed::scene-settings` the host resolves again, updates `ctx.settings` in place and
  calls `onSettings(changed)`; if a changed key has `rebuild: true` it rebuilds the scene instead
  (texture cache survives). Rebuilds wait for 250 ms of quiet, so holding a spin button builds once,
  and a rebuild shows at once without the fade from the poster (unless the texture scale changed).
- Reserved keys `lights` (auto|on|off), `lightsOn`, `lightsOff` (time) drive `world.lightsOn/warm` via
  `lightsAt()`; a scene that doesn't declare them gets 06:00-21:00.
- Other keys: `scene`, `live` (the Quick Settings switch; off = scene unmounted, textures freed,
  wallpaper restored, extension still enabled), `frozen` (every monitor takes the normal pause path,
  so the last frame stays on screen, the scene stays mounted and unfreezing resumes with one normal
  frame; no poster swap), `saved-background` (below).
- Quick Settings tile (`QuickMenuToggle` in a `SystemIndicator` with no panel icon): on/off, a
  "Freeze motion" switch, scene picker, "Wallpaper settings…" → `openPreferences()`. `make install` also adds an app-search entry.

## Poster wallpaper

The lock screen, overview and workspace-switch animation each draw GNOME's own wallpaper with their
own background actors, which our scene doesn't live in, and before a picture decodes GNOME paints its
blue `primary-color`. So each scene can ship `poster.jpg` (lights on) + optional `poster-dark.jpg`
(lights off), a still of its scenery without the wildlife, and while it runs the host makes the one
that matches the scene's lights right now GNOME's wallpaper (both the light and dark style key). The
live scene then adds the fish on top instead of moving them, and the light matches:
- On load (before the scene mounts) `posterPlan()` saves the user's wallpaper keys once into
  `saved-background` (never one of our posters), then sets `picture-uri`, `-dark`, `picture-options`
  'zoom' and `primary-color` #031a26, each only when different.
- Put back only on a real turn-off: `live` off, a switch to a scene without a poster, or `disable()`
  when the session is not locked (locking disables us too; the poster stays for the lock screen).
  If the user picked a new wallpaper meanwhile, theirs is kept.
- Not restored when GNOME disables us by itself (after a shell crash, or while locked) or on logout; the
  poster stays until the user picks a wallpaper or the extension starts again. Accepted: no hook runs
  on those paths.
- The next start fixes a leftover: with `live` off, login and enable run the turn-off logic (a poster
  path that no longer exists still counts as ours). `make uninstall` disables the extension first (its
  `disable()` restores the wallpaper), then runs `tools/restore-wallpaper.js` as a net, then removes it.
- Follows the lights: when `lights.on` flips, the other poster is set. The shell then puts a new bg
  actor under the old one and fades the old one out over 1 s; the host moves the live scene into the
  new actor and leaves a `Clutter.Clone` of it in the old one, so nothing visible changes and the scene
  is never rebuilt. Picking another wallpaper does the same.
- Made by `tools/poster.sh` from headless runs at noon and 23:00 with every `still` value applied; an
  old poster is kept if the run fails. It only lines up pixel-exact in the overview when `SIZE` is the
  monitor's own size (`zoom` crops otherwise); the lock screen blurs it anyway.

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
- `parseManifest` is the trust boundary: an entry with bad `w/h/n/cols` is dropped and logged once;
  a list key holding anything but numbers is dropped from its entry.
- Written only by the Blender helper `common.manifest()`; runtime never writes it.

## Render layer

- **Budget first:** at mount, `k = scaleFor(maxMonitorH, ref, bytesOf(images, 1))`, one factor per
  scene, logged once. Over-budget art simply loads smaller.
- **Async load:** `image()` creates the content synchronously (empty paints nothing), then
  `read_async → new_from_stream_at_scale_async` decodes off the main loop at low priority. Missing
  file → log once, content stays empty; never throws from a callback.
- **No pop-in:** each monitor's root starts at opacity 0 and the host counts the decodes requested
  while it is not ready; at zero (or after 3 s) it sets `world.ready` and fades the root in. The
  poster underneath hides the wait.
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
- Frame clock: one `Clutter.Timeline` on the background group; on each `new-frame` the host ticks
  once 25 ms have passed (every 2nd frame at 60 Hz, with jitter slack), so 30 fps in step with the screen (a GLib timeout beats against the
  display and gets starved by shell work, which judders). No idle slowdown while visible.
- Paused (0 ticks, timeline stopped) when nobody can see it: overview open, screen shield up
  (`active-changed`), locked (we're disabled), or every monitor's work area covered by windows
  (`covers()`, so side-by-side tiles count). Monitor power saving is not watched: mutter 16 only
  signals that it changed and has no way to ask whether a monitor is off, so the screen shield (which
  comes up before the screens blank) is the signal. A monitor switched off by hand may keep ticking.
  `dt` is clamped to 0.1 s, so a resume is one normal frame, and that tick's `world.gap` says how long
  it was away (also after a watchdog rest or an unfreeze); the scene caps its own catch-up.
- Sleepy ticks: a tick that returns `false` puts that monitor's scene to sleep; it is ticked every 0.2 s,
  or at once when pure `changed(raw, last)` (world.js) sees pointer/button/notification/lights/dark change,
  or on a restack, a drag or a settings change. Each monitor has its own `dt` (clamped 0.1 s awake,
  0.3 s asleep). The host clock and pointer poll keep running; that poll is the whole cost of a sleeper.
- Hotplug: no monitors (lid shut, nothing plugged in) unmounts and keeps the textures for when a screen
  returns; a monitor whose work area is already gone counts as paused until `monitors-changed` rebuilds.
- Watchdog: 90 ticks in a row over 66 ms (~3 s) and that monitor rests 60 s, then tries again; a busy
  machine resets the count with one fast tick. A throw in build or tick destroys that monitor's scene.
  Both count as a strike: the first one shows one notification (no details, those go to the log), and
  after three per scene load the scene stays stopped until a scene switch or a live off/on. A throw
  never reaches gnome-shell.
- e.g.o rules: nothing created before `enable()`, full cleanup in `disable()`, no Gtk/Gdk/Adw in
  the shell process, no sync IO in ticks, no log spam, no module-level mutable state.

## Budget (lightweight is a top priority)

- Decoded textures ≤ 100 MB, counted over every image in the manifest (optional art too), so no
  setting can push a scene past it. Canvas tiles count too (`sc.canvas`, freed with the root). Fishtank with defaults at k=1: ~90 MB.
- Scene ticks about 1.5-2 ms per scene (the fishtank; the garden is far under) at default settings while visible; 0 when not.
- Measured with `./dev.sh --headless` (`stats.txt`) before review. `RACE=1 ./dev.sh --headless 16`
  runs the lifecycle races (disable mid-decode, double scene switch, monitor storm, lock/unlock).
- Memory: RSS climbs after enable/disable cycles because GJS frees garbage late, not because of a leak;
  the probe calls `System.gc()` before each reading. Each unlock re-decodes the textures (e.g.o forbids
  keeping them across disable), which is why the texture budget stays tight.

## Scenes

Scene internals live with the scene: `scenes/fishtank/scene.js` (layers, brain/motor/body split,
world reactions) and `scenes/fishtank/blender/common.py` (the Blender art pipeline).

## Not building

OOP/WebKit/Godot host, user scene dir, scene.json, pub/sub bus, power-saver, sunrise math,
MPRIS/weather, per-monitor scene picks, fish names, breeding/hunger, translations, eslint.
Skipping single actors hidden under a window: Clutter still walks and culls every actor and the
uncovered part animates anyway, so it saves a few quads a frame and freezes fish behind see-through
windows; the whole-monitor pause (`covers()`) is the real saving. Staying enabled on the lock screen
(`unlock-dialog` mode): e.g.o accepts it only when the extension can't work without it, and our Quick
Settings tile would show there; the scene's own store keeps fish where they were instead.
Pausing on a VT/user switch: the shell has no signal for it (needs our own logind proxy), and the
screen shield or monitor power saving already covers the usual case.
