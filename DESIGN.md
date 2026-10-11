# fishtank design

GNOME Shell extension (ESM, GNOME 45+; shell-version list "45".."49"). Everything renders inside gnome-shell as
Clutter/St actors added to each monitor's background actor. No subprocess, no WebKit, no IPC, no deps.
Research picks: Clutter over a hidden WebKit window (Hanabi-style is ~1500 lines of window hacks);
procedural Cairo art (no Blender, no sprite assets); Reynolds steering for fish.

## Files and owners (do not edit files you don't own)
- `metadata.json`, `extension.js`, `dev.sh`, `README.md` — A (host)
- `scene.js` — B (tank scenery, bubbler)
- `fish.js`, `steer.js`, `check.js` — C (fish)

## Contract
All coords are tank-local pixels, origin top-left of the monitor. `t`, `dt` in seconds.

    // scene.js
    export class Scene {
      constructor(root /* Clutter.Actor sized w x h */, w, h)
      fishLayers   // [farActor, nearActor] Clutter.Actors sized w x h; fish add children here
      swimBounds   // {x, y, w, h} water region fish may use (above sand, below surface)
      tick(dt, t)
      destroy()
    }
    // fish.js
    export class School {
      constructor(fishLayers, swimBounds)
      tick(dt, t, pointer /* {x, y, speed} or null when cursor not over bare desktop */)
      destroy()
    }

Scene builds children of `root` back→front: water gradient + light rays/caustics, far rocks/plants,
fishLayers[0], mid decor (castle, sunken ship, chest, diver), bubbler + bubbles, sand/pebbles/snail,
fishLayers[1], foreground plants. Gentle parallax = far layers drift/sway less than near ones.

## Host (extension.js)
- enable: for each `Main.layoutManager._bgManagers[i].backgroundActor`, add a reactive `St.Widget`
  sized to its monitor; build Scene then School(scene.fishLayers, scene.swimBounds). Rebuild on
  `monitors-changed` and when the bg manager emits `changed` (background actor replaced).
- Pointer: `motion-event` on the widget → `transform_stage_point` → pointer {x,y,speed};
  `leave-event` → null. Return `Clutter.EVENT_PROPAGATE` so the desktop right-click menu still works.
  Only the main background (not overview thumbnails/lock screen).
- One `GLib.timeout_add` (~30 fps, PRIORITY_DEFAULT_IDLE-ish) calls tick on all tanks; wrap tick in
  try/catch, log once and stop that tank on error (a throw must never break gnome-shell).
- Auto-pause: stop the timer when the desktop can't be seen (a maximized/fullscreen window on the
  active workspace on every monitor, screen locked) and resume on change. Overview counts as visible.
- disable: remove every timer and signal, destroy all actors. No state outside the extension instance.
- `dev.sh`: run a nested shell for testing (`dbus-run-session -- gnome-shell --nested --wayland`) with
  this dir symlinked/installed and enabled.

## Perf rules (Intel iGPU, 3440x1440)
- Static art is rasterized once (St.DrawingArea / Cairo, repaint only on resize). Motion comes from
  moving/rotating/scaling actors (pivot at plant base for sway), not re-drawing big surfaces.
- Only small actors repaint per frame (fish bodies for tail wiggle). Never a full-screen repaint per tick.
- Bubbles pooled, no per-frame allocation churn.

## Fish
5-8 species with distinct shapes/colors/sizes (e.g. clownfish, neon tetra school, angelfish, goldfish,
blue tang, pufferfish, betta, bottom-dwelling catfish). Wander + soft bounds + separation; tetras
school. Smooth heading (max turn rate), body bends into turns, tail wiggle speed follows swim speed.
Cursor: each fish has a personality — skittish fish flee (fast burst, panic decays), curious fish
approach to ~80px, hover, lose interest after a few seconds; some switch depending on how fast the
cursor moves (a fast cursor scares everyone). Fish on the far layer are smaller/dimmer.
`steer.js` is pure math (no gi imports) so `gjs -m check.js` can assert flee/curious/bounds behavior.
