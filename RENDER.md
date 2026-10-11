# RENDER — host render layer (ponytail full)

Principle: the host sizes every texture to the screen and to the budget *before* decoding, from the
manifest alone. Authors bring any art; the manifest (written by the export helper) is the contract.
Ranked by impact per line.

## 1. Files

```
render.js   pure, no gi (checked headless): parseManifest, scaleFor, bytesOf, frameOffset
ctx.js      image(), sheet(), stats — the only St.ImageContent code in the repo
tools/sheet.py  (moves out of blender/common.py) sheet()/manifest() export helpers
```

## 2. Manifest (one `assets/manifest.json` per scene, author-space pixels)

```json
{"ref": 1440,                         // screen height the art was rendered for
 "images": {
   "castle":   {"w": 406, "h": 641, "base": [209, 598.5]},
   "clown":    {"w": 160, "h": 96, "n": 64, "cols": 8, "anchor": [80, 48],
                "pts": {"eye": [[112, 30, 6, 1.0], ...]}}}}       // per-frame lists, length n
```
`w,h` = ONE frame; file is `w*cols × h*ceil(n/cols)`; `n` defaults 1. Any `[x,y,...]` key is a
point in frame px. Frames must be pre-cropped to their union bbox and padded ≥2 px (bilinear
bleed) — the helper does it; runtime never scans alpha.

`parseManifest(text) → {ref, images}` is the trust boundary: missing/non-finite `w,h,n` or
`n % cols`-impossible → that entry is dropped and logged once; the rest loads.

## 3. ctx API (extends PLATFORM §2; scenes keep building in ref px, nothing else changes)

```js
ctx.image(name) → entry            // manifest entry + .content (St.ImageContent), cached forever
ctx.sheet(name) → {...entry, make(), show(actor, i)}
ctx.ref                             // manifest.ref, replaces per-scene REF constants
ext.stats → {bytes, k, actors, tickMs}   // on the extension object for Looking Glass + review
```

**Load path** (`ctx.js`, ~40 lines):
1. At scene mount: `k = scaleFor(maxMonitorH, ref, bytesOf(images, 1), BUDGET)` where
   `scaleFor = min(1, h/ref) * min(1, sqrt(BUDGET / bytesAt(min(1,h/ref))))`. One factor per scene,
   computed before any decode, logged once (`bytes, k`). Over-budget art simply loads smaller.
2. `image(name)`: cache hit → return. Else create `St.ImageContent.new_with_preferred_size(w*cols, h*rows)`
   **now** (empty content paints nothing, so the actor just appears when the data lands — free
   fade-in, scenes stay synchronous), then
   `Gio.File.read_async → GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(stream, W*k, H*k, true)`
   (decode + scale in GdkPixbuf's thread), then `set_data(cogl?, …)` on the main loop (the
   48+/45 Cogl-context dance from `scene.js upload()` moves here). Missing file →
   log once, content stays empty; never throws from a callback.
3. Cache is module-level `Map<sceneId/name, entry>`, so two monitors and every fish of a species
   share one GPU texture; cleared in `disable()`.
4. Filters: every actor the host makes gets `LINEAR, LINEAR`. Texture ≈ screen size now, so
   mipmaps (+33 % memory) buy nothing. 
**Sheet** (clip-parent + translated child, primary):
```js
make() {           // fw×fh clip box; child holds the whole sheet (one texture for all users)
  const a = new Clutter.Actor({width: w, height: h, clip_to_allocation: true});
  a.add_child(new Clutter.Actor({content, width: w*cols, height: h*rows}));
  return a; }
show(a, i) { if (a._f === i) return; a._f = i;
  const [x, y] = frameOffset(entry, i); a.first_child.set_translation(-x, -y, 0); }
```
Why: one upload per sheet, no per-frame objects, a frame change is one translation.
Scale/rotate/mirror/pivot go on the parent as today; **opacity goes on the child** (single-texture
actor, cheap) because opacity on an actor with children may force an offscreen pass.
Verify in the nested shell first: (a) clip follows parent `set_scale(-1,1)` + rotation without a
1-px seam, (b) child translation doesn't relayout the parent, (c) 100 fish tick < 1 ms.
Fallback if (a) fails: per-frame `new_subpixbuf` contents (gnome-critter style) — same bytes, `n`
textures, `show` becomes `a.content = frames[i]`; same API, 6 lines different. Cogl.SubTexture is
not pursued: no GJS path from a Cogl texture into St.ImageContent.

## 4. Actor rules (host defaults + guideline in docs/writing-a-scene.md)

- Move with `set_translation`/`translation_x` — no relayout; `set_position` only at build.
  (? claim: the §3 timing settles it; if equal, drop the rule.)
- No `new` per tick: pool bubbles/flakes at build (fishtank already does). The watchdog is the
  enforcement; `stats.tickMs` (EMA of tick time) is how review sees it.
- `stats.actors` = root descendant count at mount; log once if > 300.
- OffscreenRedirect: **not** default. An FBO costs `w*h*4` (a 3440×1440 layer = 20 MB, a third of
  the budget) to save compositing a few dozen quads. Add only if a measured layer proves hot.

## 5. Export helper (`tools/sheet.py`, replaces `sprite()`/`crop_frames()`/`manifest()` in common.py)

```python
sheet(name, frames, cols=None, pts=None, pad=4, cut=8)
  # frames: list of HxWx4 float arrays from render(); crops to union bbox (+pad), packs a grid,
  # shifts every point by the crop offset, writes assets/<name>.png and the manifest entry
manifest(name, ent)          # flock'd read-modify-write of assets/manifest.json (exists today)
points(world_pts) -> {k: [px, py]}   # world_to_camera_view wrapper (lifted from sprite())
```
Density stays `PPU` at `ref` (already how common.py works); `ref` is written once per run.
fish.py changes keys only (`fw→w, frames→n, eyes→pts.eye`), scene scripts call `sheet()` with one
frame. 
## 6. Headless check (`render.js` asserts, run by `check.js`)

- `scaleFor(1440, 1440, 10e6, 64e6) === 1`; `scaleFor(720, 1440, …) === 0.5`
- `bytesOf(images, scaleFor(1440, 1440, 128e6, 64e6)) <= 64e6` (over-budget art shrinks under)
- `frameOffset({w:160,h:96,n:64,cols:8}, 9)` → `[160, 96]`
- `parseManifest('{"ref":1440,"images":{"a":{"w":"x"},"b":{"w":1,"h":1}}}')` keeps `b`, drops `a`

## 7. Cut (not worth the lines)

Runtime alpha-crop (helper does it offline); mipmaps/trilinear; Cogl.SubTexture; per-actor budget
nagging (one scene-wide `k` is the whole mechanism); a loader class/priority queue; `ponytail:` budget counts every manifest entry even if a scene never loads some — conservative,
upgrade to as-loaded accounting if a scene ships optional art.

## Main-agent amendments (binding)
- Texture cache lives on the extension instance (created in enable, dropped in disable), NOT module-level:
  module state survives disable/enable and breaks e.g.o rules + our "no module-level mutable state" standard.
- Ownership: render.js + ctx.js + check.js asserts → A (host). `tools/sheet.py` (from blender/common.py) → C.
  B (fishtank) uses only ctx.image / ctx.sheet and the manifest format; never GdkPixbuf directly.
