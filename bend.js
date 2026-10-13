// Pure helpers for bendy many-sprite bodies (plants, tentacles, eels); see docs/writing-a-scene.md.
// Rules: overlap the faded ends (spacing), shear don't rotate (shear), clamp the bend (spring).

// Centre-to-centre gap for pieces w px long whose art fades out over the fraction soft at each end.
export const spacing = (w, soft) => w * (1 - 2 * soft);

// Angle (deg) for a +x-facing sprite moving (dx, dy). Mirror with scale x -1 but keep this angle:
// Clutter mirrors after it rotates.
export const heading = (dx, dy) => Math.atan2(dy, Math.abs(dx)) * 180 / Math.PI;

// Leans piece a by deg about row py (px from its top; pivot must be 0, 0); edges stay level.
let mtx = null;  // scratch matrix, reused (set_transform copies it)
export function shear(a, deg, py) {
    const tn = Math.tan(deg * Math.PI / 180);
    mtx ??= a.get_transform();
    a.set_transform(mtx.init_from_2d(1, 0, -tn, 1, tn * py, 0));
}

// Springs p = {bend, bv} back to rest (push by adding to bv); bend within ±limit, bv within ±maxSpeed.
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export function spring(p, dt, {limit = 1, maxSpeed = 4, stiff = 12, damp = 3} = {}) {
    p.bend = clamp(p.bend + p.bv * dt, -limit, limit);
    p.bv = clamp(p.bv - (p.bend * stiff + p.bv * damp) * dt, -maxSpeed, maxSpeed);
    if (Math.abs(p.bend) < 1e-3 && Math.abs(p.bv) < 1e-3) p.bend = p.bv = 0;
}
