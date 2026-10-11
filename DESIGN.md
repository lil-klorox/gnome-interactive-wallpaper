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
- Pointer: polled each tick with `global.get_pointer()`; "over the desktop" = the reactive actor under it is
  the stage, the background group, or a DESKTOP-type window (desktop-icons). Widget is non-reactive, so
  desktop clicks/menus are untouched.
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

## Art direction (user)
A little dorky/stylized is fine, not lifelike, but every piece gets a LOT of detail and thought (bricks, portholes, coins, whiskers, eye highlights, varied leaves, shells in the sand). Detail goes in once-rasterized art so perf rules still hold.

## Phase 2: Blender art (user: every asset detailed, upfront time/cost no object)
Art is modeled + rendered by headless Blender scripts in `blender/` (`~/opt/blender/blender -b --factory-startup -P blender/<x>.py`),
output PNGs + JSON manifests committed under `assets/`. Runtime never needs Blender; scripts are the source of truth,
so a tweak = edit script + re-render. Headless bpy scripts, not blender-mcp: reproducible, versioned, no GUI.
- `blender/common.py` (shared, owned by scenery agent; fish agent imports read-only): Eevee, orthographic side camera,
  transparent film, "Standard" view transform, warm key light from the surface + cool fill + rim, stylized
  slightly-chunky "dorky aquarium toy" look, shared palette/material helpers, `render(obj, path, px)` helper.
- Scenery: backdrop (deep water, far rock silhouettes in 2-3 parallax depth plates with haze), sand bed with
  pebbles/shells, castle, sunken ship, treasure chest (lid as separate sprite to bob), diver (helmet, hose, boots),
  bubbler/air stone, rocks, plants rendered in segments or as single sprites pivoting at base, snail sprite frames,
  caustic/light-ray overlay textures. scene.js loads them as actors (St.ImageContent / GdkPixbuf), keeps all perf rules.
- Fish: each species modeled + shape-keyed (tail swing, fin flutter, mouth open, puffer puff) and rendered as sprite
  sheets: swim-cycle frames x yaw angles (profile → 3/4 → front; mirror for the other side) so fish TURN in
  3D instead of flipping. Manifest gives frame size, counts, and per-frame eye position so fish.js overlays a
  pupil that looks at the cursor. Memory budget: all sheets together < ~80 MB decoded.

### Look (user): fully realized 3D, not "corny 3D"
Every piece should read as a real, lit, solid object with depth: think a polished animated film's aquarium,
not plastic CG. So:
- Render with Cycles (denoised; time is no object), PBR materials with real procedural texture detail: stone
  grain + chipped edges, wood grain + rot, tarnished metal, wet sand, translucent fins (subsurface/transmission),
  iridescent scales. Bevels + ambient occlusion + soft contact shadows so things sit IN the sand.
- One consistent underwater light rig for scenery AND fish: soft key from the surface with projected caustic
  texture, blue-green absorption/haze that grows with distance, so far plates are dimmer + bluer.
- Avoid the corny look: no oversaturated plastic, no hard CG shadows, no uniform bevel-on-everything, no
  perfect symmetry; add wear, moss, algae, dirt, color variation. Stylized proportions (a little dorky) are
  fine, but surfaces and light must feel real.
- Runtime keeps the depth: contact shadows baked under props, parallax between plates, depth haze per layer.

## Research follow-up (to apply)
- Pointer: motion-event on the bg widget never fires if DING/desktop-icons or another wallpaper/blur extension sits
  above it. Robust way (mouse-tail, tokidachi): `global.backend.get_cursor_tracker()` `position-invalidated` → dirty
  flag, sample `global.get_pointer()` on the tick; "bare desktop" = no visible non-minimized window on the active
  workspace whose frame rect contains the point (DESKTOP-type windows count as desktop). Pointer events then unneeded.
- Overview thumbnails also show background-group content; fish may freeze there.

## Fish = brain / motor / body (user: change thinking, motion and actions independently later)
- `brain.js` — the thinking. Each fish runs a small state machine: a table of named states
  (e.g. idle wander, curious, flee, bored, plus room for nibble-plants, rest-by-decor, follow-buddy, sleep),
  each with `enter`/`update` returning an intent `{target|away, speed, look}` and the next state.
  Per-species personality is plain data (curiosity, skittishness, boredom, home zone, sociability).
  Adding a behavior = add one state + hook it into a transition; nothing else changes.
- `steer.js` — the motion. Turns an intent into movement (wander, bounds, separation, schooling, turn limits,
  bend). Knows nothing about moods.
- `fish.js` — the body. Draws/animates sprites from motion state (frame, yaw, tail speed, pupil look, puff).
- `check.js` covers brain transitions and steer bounds headless.

## Prior art for phase 2 (patterns only; most are GPL, copy no code)
- Sprite loading in shell: GdkPixbuf `new_from_file` → `new_subpixbuf` per frame → `St.ImageContent` +
  `set_data`; swap `actor.content` per frame; trilinear scaling filters (gnome-critter).
- Caustics shader if wanted: `Shell.GLSLEffect`, falling back to `Clutter.ShaderEffect`/Cogl snippet when it's
  missing (Burn-My-Windows Shader.js) — keeps it version-agnostic.
- Fish swim math (FishSim): tail angle = sin(phase)*maxTail*effort + steer*maxSteer, chest counter-rotates.
  In bpy: subdivided body + shape keys / Wave-style sine deform driven per frame.
- Turn sheets: rotate object (not camera) on yaw, ortho cam, render yaw 0..180 and mirror the rest; JSON manifest.
- Seaweed: bezier curve + bevel + sine deform; rocks: voronoi-displaced meshes.
