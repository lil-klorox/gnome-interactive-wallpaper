// Bendy bodies made of several sprites in a row: a plant, a tentacle, an eel, a rope, a tail, a reed.
// No gi imports, so pure checks can load it; checked by check.js, explained in docs/writing-a-scene.md.
// Three rules keep such a body looking like one piece:
//  1. Overlap: art that fades out at its ends must overlap its neighbours by both fades (spacing()).
//  2. Shear, don't rotate: a rotated piece tilts its edge and opens a gap at the joint (shear()).
//  3. Clamp the bend: pushes add up, so hold the bend and its speed to a limit (spring()).

// Centre-to-centre gap for pieces w px long whose art fades out over the fraction soft at each end.
export const spacing = (w, soft) => w * (1 - 2 * soft);

// Rotation (deg) for a sprite drawn facing +x and moving (dx, dy). Flip it with scale x -1 when dx < 0
// but keep this angle: Clutter mirrors after it rotates, so the mirrored sprite tilts the right way.
export const heading = (dx, dy) => Math.atan2(dy, Math.abs(dx)) * 180 / Math.PI;

// Leans piece a by deg about its joint row py (px from its top; its pivot point must be 0, 0) by
// sliding rows sideways, so every edge stays level and the pieces meet across the full width.
let mtx = null;  // scratch matrix, borrowed from the first actor (set_transform copies it)
export function shear(a, deg, py) {
    const tn = Math.tan(deg * Math.PI / 180);
    mtx ??= a.get_transform();
    a.set_transform(mtx.init_from_2d(1, 0, -tn, 1, tn * py, 0));
}

// Springs a pushed bend p = {bend, bv} back to rest; push it by adding to bv. bend stays within
// ±limit and its speed bv within ±maxSpeed (per second); stiff pulls it back, damp slows it.
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export function spring(p, dt, {limit = 1, maxSpeed = 4, stiff = 12, damp = 3} = {}) {
    p.bend = clamp(p.bend + p.bv * dt, -limit, limit);
    p.bv = clamp(p.bv - (p.bend * stiff + p.bv * damp) * dt, -maxSpeed, maxSpeed);
    if (Math.abs(p.bend) < 1e-3 && Math.abs(p.bv) < 1e-3) p.bend = p.bv = 0;
}
