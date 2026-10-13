// Pure texture math: budget scale, decoded sizes, sprite-sheet frames.
export const BUDGET = 100e6;  // decoded bytes of every image in the manifest, optional art included

// Upper caps keep a bad manifest from sizing huge textures/loops.
const pos = v => Number.isFinite(v) && v > 0 && v <= 16384;
export const int = (v, max = 16384) => Number.isInteger(v) && v > 0 && v <= max;
const nums = v => Array.isArray(v) && v.every(x => Number.isFinite(x) || nums(x));

// Trust boundary for a scene's manifest.json: bad entries are dropped (logged once), the rest load.
export function parseManifest(text) {
    const m = JSON.parse(text);
    if (!pos(m?.ref) || typeof m.images !== 'object' || !m.images)
        throw new Error('manifest needs ref and images');
    const images = {}, bad = [];
    for (const [name, e] of Object.entries(m.images)) {
        const n = e?.n ?? 1, cols = e?.cols ?? n;
        const px = e?.px ?? [Math.ceil(e?.w * cols), Math.ceil(e?.h * Math.ceil(n / cols))];
        if (!/^[\w-]+$/.test(name) || !pos(e?.w) || !pos(e?.h) || !int(n, 4096) || !int(cols) || cols > n ||
            !Array.isArray(px) || !int(px[0]) || !int(px[1])) {
            bad.push(name);
            continue;
        }
        const ent = {...e, n, cols, px};
        for (const k in ent) if (Array.isArray(ent[k]) && !nums(ent[k])) delete ent[k];  // points/lists: numbers or gone
        images[name] = Object.freeze(ent);
    }
    if (bad.length)
        console.warn(`interactive-wallpaper: manifest entries dropped: ${bad.join(', ')}`);
    return {ref: m.ref, images: Object.freeze(images)};
}

// Decoded texture size of an entry at scale k (k applies to the PNG's own pixels).
export const sizeAt = (e, k) => [Math.max(1, Math.floor(e.px[0] * k)), Math.max(1, Math.floor(e.px[1] * k))];

export function bytesOf(images, k) {
    let b = 0;
    for (const e of Object.values(images)) {
        const [w, h] = sizeAt(e, k);
        b += w * h * 4;
    }
    return b;
}

// One factor per scene: shrink with the screen, then until the whole manifest fits the budget.
// bytes = bytesOf(images, 1). floor() in sizeAt keeps bytesOf(images, k) <= budget.
export const scaleFor = (h, ref, bytes, budget = BUDGET) => Math.min(1, h / ref, Math.sqrt(budget / bytes));

// Tallest monitor in physical px (Wayland geometry is logical; X11 is already physical). 0 with no
// monitors, never -Infinity; the host skips the build then instead of using it.
export const maxHeight = (mons, x11) => mons.reduce((h, m) => Math.max(h, m.height * (x11 ? 1 : m.geometry_scale ?? 1)), 0);

// out: pass a reused pair to keep per-frame calls allocation-free.
export const frameOffset = (e, i, out = [0, 0]) => {
    out[0] = (i % e.cols) * e.w;
    out[1] = Math.floor(i / e.cols) * e.h;
    return out;
};

// Canvas grid (ctx.canvas): bytes of every tile, edge tiles counted whole since that's what's allocated.
export const canvasBytes = (w, h, tile) => Math.ceil(w / tile) * Math.ceil(h / tile) * tile * tile * 4;

// Tiles a cell rect touches: [c0, r0, c1, r1], end-exclusive and clamped (empty when c0 >= c1 or r0 >= r1).
export const tileRange = (x0, y0, x1, y1, tile, cols, rows) => [
    Math.max(0, Math.floor(x0 / tile)), Math.max(0, Math.floor(y0 / tile)),
    Math.min(cols, Math.ceil(x1 / tile)), Math.min(rows, Math.ceil(y1 / tile))];
