// Pure texture math (no gi): budget scale, decoded sizes, sprite-sheet frames. Checked by check.js.
export const BUDGET = 65e6;

// Upper caps keep a bad manifest from sizing huge textures/loops.
const pos = v => Number.isFinite(v) && v > 0 && v <= 16384;
const int = (v, max = 16384) => Number.isInteger(v) && v > 0 && v <= max;

// Trust boundary for a scene's manifest.json: bad entries are dropped (logged once), the rest load.
export function parseManifest(text) {
    const m = JSON.parse(text);
    if (!pos(m?.ref) || typeof m.images !== 'object' || !m.images)
        throw new Error('manifest needs ref and images');
    const images = {}, bad = [];
    for (const [name, e] of Object.entries(m.images)) {
        const n = e?.n ?? 1, cols = e?.cols ?? n;
        const px = e?.px ?? [Math.ceil(e?.w * cols), Math.ceil(e?.h * Math.ceil(n / cols))];
        if (/^[\w-]+$/.test(name) && pos(e?.w) && pos(e?.h) && int(n, 4096) && int(cols) && cols <= n &&
            Array.isArray(px) && int(px[0]) && int(px[1]))
            images[name] = Object.freeze({...e, n, cols, px});
        else
            bad.push(name);
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

// out: pass a reused pair to keep per-frame calls allocation-free.
export const frameOffset = (e, i, out = [0, 0]) => {
    out[0] = (i % e.cols) * e.w;
    out[1] = Math.floor(i / e.cols) * e.h;
    return out;
};
