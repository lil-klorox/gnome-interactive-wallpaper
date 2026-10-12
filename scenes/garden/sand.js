// Pure sand math (no gi): the height field, rake strokes, window rings, shading, settling and the save
// format. px = logical px on this monitor; the field has one height per CELL x CELL px (0 = flat,
// -1 = a full groove). Every write is clipped to `clip` (a cell rect, end-exclusive) and grows `bb`, the
// cell rect the caller marks dirty. Checked by check.js.
export const CELL = 2;
export const Q = 2;               // saved points are rounded to this many px
export const GAP = 8;             // px a stroke moves before it saves its next point
export const MAX_POINTS = 2500;   // saved points per monitor
export const MAX_MONS = 4;        // monitors that get a save slot (index 0-3)
export const MAX_LEAVES = 12;
export const STORE_LIMIT = 60000; // chars; the engine refuses a store over 64 KB
const PITCH = 14, TOOTH = 4;      // px between rake teeth; px from a tooth's middle to its edge
const RIDGE = 0.35;               // sand pushed up between grooves
const RINGS = [1, 0.7, 0.4];      // depth of the rings 14, 28, 42 px out from a window
const BAND = [7, 49];             // px from a window that its rings rewrite
const TROUGH = -0.5;              // depth of the furrow a dragged window leaves
const LINES = 0.35;               // depth of the background lines
const LIGHT = 1.6, GAIN = 0.75;   // shading strength; how opaque a full highlight/shadow gets (tuning knobs)

export const makeField = (w, h) => {
    const cw = Math.ceil(w / CELL), ch = Math.ceil(h / CELL);
    return {cw, ch, H: new Float32Array(cw * ch)};
};
export const box = (bb = {}) => {  // reset in place: called every tick
    bb.x0 = bb.y0 = Infinity;
    bb.x1 = bb.y1 = -Infinity;
    return bb;
};
export const grow = (bb, x0, y0, x1, y1) => {
    bb.x0 = Math.min(bb.x0, x0);
    bb.y0 = Math.min(bb.y0, y0);
    bb.x1 = Math.max(bb.x1, x1);
    bb.y1 = Math.max(bb.y1, y1);
};
const bump = r => Math.max(0, 1 - (r / 2) ** 2);  // r in cells: soft, 2 cells (4 px) each side

// The rake's cross-section, one sample per px across it: P[j] sits (j - J) px from the middle.
export function profile(teeth) {
    const half = ((teeth - 1) * PITCH + 2 * TOOTH) / 2, J = Math.ceil(half), P = new Float32Array(2 * J + 1);
    for (let j = 0; j <= 2 * J; j++) {
        const u = (j - J) / CELL;  // cells
        let v = RIDGE * (bump(u + half / CELL) + bump(u - half / CELL));
        for (let i = 0; i < teeth; i++) {
            const c = (i - (teeth - 1) / 2) * PITCH / CELL;
            v -= bump(u - c);
            if (i < teeth - 1)
                v += RIDGE * bump(u - c - PITCH / 2 / CELL);
        }
        P[j] = v;
    }
    return {P, J, half};
}

// One rake footprint at (px, py), teeth along the normal (nx, ny). Overwrites: a newer groove runs
// through an older one, as a real rake flattens what it crosses. k scales the depth. Each cell gets the
// profile at its own centre's distance from the path (not the sample's), so grooves don't staircase.
function stamp(F, R, px, py, nx, ny, k, clip, bb) {
    const {H, cw} = F, {P, J} = R;
    for (let j = 0; j <= 2 * J; j++) {
        const cx = Math.floor((px + nx * (j - J)) / CELL), cy = Math.floor((py + ny * (j - J)) / CELL);
        if (cx < clip.x0 || cy < clip.y0 || cx >= clip.x1 || cy >= clip.y1)
            continue;
        const u = ((cx + 0.5) * CELL - px) * nx + ((cy + 0.5) * CELL - py) * ny + J, i = Math.floor(u), f = u - i;
        H[cy * cw + cx] = (i < 0 || i >= 2 * J ? 0 : P[i] + (P[i + 1] - P[i]) * f) * k;
    }
    const r = J / CELL + 1;
    grow(bb, Math.floor(px / CELL - r), Math.floor(py / CELL - r), Math.ceil(px / CELL + r), Math.ceil(py / CELL + r));
}

export const makeStroke = () => ({x: 0, y: 0, dx: 0, dy: 0, carry: 0, on: false});

// Rake from the stroke's last point to (x, y) px, one footprint per px. The direction is smoothed so
// a shaky hand doesn't zigzag the teeth; the first call only sets the start.
export function rakeTo(F, R, s, x, y, k, clip, bb) {
    if (!s.on) {
        Object.assign(s, {x, y, dx: 0, dy: 0, carry: 0, on: true});
        return;
    }
    const sx = x - s.x, sy = y - s.y, len = Math.hypot(sx, sy);
    if (len < 1)
        return;
    const ux = sx / len, uy = sy / len;
    let dx = ux, dy = uy;
    if (s.dx || s.dy) {
        dx = 0.7 * s.dx + 0.3 * ux;
        dy = 0.7 * s.dy + 0.3 * uy;
        const n = Math.hypot(dx, dy);
        dx /= n;
        dy /= n;
    }
    // The teeth turn gradually across the segment, so a turn has no kink where two ticks meet.
    const ox = s.dx || dx, oy = s.dy || dy;
    let t = s.carry;
    for (; t <= len; t++) {
        const f = t / len, nx = ox + (dx - ox) * f, ny = oy + (dy - oy) * f, m = Math.hypot(nx, ny) || 1;
        stamp(F, R, s.x + ux * t, s.y + uy * t, -ny / m, nx / m, k, clip, bb);
    }
    s.x = x;
    s.y = y;
    s.dx = dx;
    s.dy = dy;
    s.carry = t - len;
}

// Height of a window's rings d px out from its edge.
export function ringAt(d) {
    const i = Math.round(d / PITCH), m = Math.min(2, Math.max(0, Math.round(d / PITCH - 0.5)));
    const dip = i >= 1 && i <= 3 ? RINGS[i - 1] * bump((d - i * PITCH) / CELL) : 0;
    return RIDGE * RINGS[m] * bump((d - (m + 0.5) * PITCH) / CELL) - dip;
}

// Distance from (px, py) to the ellipse filling rect r, to first order (good enough for ring spacing).
function ovalDist(r, px, py) {
    const rx = r.w / 2, ry = r.h / 2, ux = (px - r.x - rx) / rx, uy = (py - r.y - ry) / ry;
    const k = Math.hypot(ux, uy) || 1e-6;
    return (k - 1) * k / Math.hypot(ux / rx, uy / ry);
}

// Three rings around rect r ({x, y, w, h} px), rewriting the band 7-49 px out: rounded-rect for
// windows, an oval for stones (a raked ring that follows a stone is round, not boxy).
export function ring(F, r, clip, bb, oval = false) {
    const {H, cw} = F, [lo, hi] = BAND, x1 = r.x + r.w, y1 = r.y + r.h;
    const cx0 = Math.max(clip.x0, Math.floor((r.x - hi) / CELL)), cx1 = Math.min(clip.x1, Math.ceil((x1 + hi) / CELL));
    const cy0 = Math.max(clip.y0, Math.floor((r.y - hi) / CELL)), cy1 = Math.min(clip.y1, Math.ceil((y1 + hi) / CELL));
    const skip = Math.floor((x1 - lo) / CELL);  // inside the window: jump to its right side
    for (let cy = cy0; cy < cy1; cy++) {
        const py = (cy + 0.5) * CELL, dy = Math.max(r.y - py, 0, py - y1);
        for (let cx = cx0; cx < cx1; cx++) {
            const px = (cx + 0.5) * CELL, d = oval ? ovalDist(r, px, py) : Math.hypot(Math.max(r.x - px, 0, px - x1), dy);
            if (!oval && d < lo && dy === 0 && cx < skip)
                cx = skip;
            else if (d >= lo && d <= hi)
                H[cy * cw + cx] = ringAt(d);
        }
    }
    grow(bb, cx0 - 1, cy0 - 1, cx1 + 1, cy1 + 1);
}

// A dragged window: cells it just left (inside rect a, outside rect b) become a furrow.
export function trough(F, a, b, clip, bb) {
    const {H, cw} = F;
    const cx0 = Math.max(clip.x0, Math.floor(a.x / CELL)), cx1 = Math.min(clip.x1, Math.ceil((a.x + a.w) / CELL));
    const cy0 = Math.max(clip.y0, Math.floor(a.y / CELL)), cy1 = Math.min(clip.y1, Math.ceil((a.y + a.h) / CELL));
    for (let cy = cy0; cy < cy1; cy++) {
        const py = (cy + 0.5) * CELL, inY = py >= b.y && py < b.y + b.h;
        for (let cx = cx0; cx < cx1; cx++) {
            const px = (cx + 0.5) * CELL;
            if (!(inY && px >= b.x && px < b.x + b.w))
                H[cy * cw + cx] = TROUGH;
        }
    }
    grow(bb, cx0 - 1, cy0 - 1, cx1 + 1, cy1 + 1);
}

// Background lines: straight grooves across the whole garden, the calm state the sand settles back to.
// Sets F.B (one height per cell row) and fills the field with it.
export function lines(F) {
    F.B = new Float32Array(F.ch);
    for (let y = 0; y < F.ch; y++) {
        const m = ((y + 0.5) * CELL) % PITCH;
        F.B[y] = LINES * (RIDGE * (bump(m / CELL) + bump((m - PITCH) / CELL)) - bump((m - PITCH / 2) / CELL));
        F.H.fill(F.B[y], y * F.cw, (y + 1) * F.cw);
    }
}

// Move every height in a cell rect a share 1 - f of the way back to rest (settling, a furrow filling
// in): rest is flat sand, or the background lines when the field has them.
export function scale(F, x0, y0, x1, y1, f) {
    const {H, cw, ch, B} = F;
    x0 = Math.max(0, x0);
    x1 = Math.min(cw, x1);
    for (let y = Math.max(0, y0); y < Math.min(ch, y1); y++) {
        const b = B ? B[y] : 0;
        for (let i = y * cw + x0, e = y * cw + x1; i < e; i++)
            H[i] = b + (H[i] - b) * f;
    }
}

// Share of a groove left after `sec` seconds: 5 % after `hours` (0 = never fades).
export const settleFactor = (sec, hours) => hours > 0 ? 0.05 ** (Math.max(0, sec) / (hours * 3600)) : 1;

// Canvas fill: light from the top-left (as in the art), so each groove's top-left wall is in shadow
// and its bottom-right wall catches the light. Premultiplied RGBA; flat sand is see-through.
export function shade(F, buf, x0, y0, tw, th) {
    const {H, cw, ch} = F;
    let o = 0;
    for (let y = y0; y < y0 + th; y++) {
        const row = y * cw, up = (y > 0 ? y - 1 : y) * cw, dn = (y < ch - 1 ? y + 1 : y) * cw;
        for (let x = x0; x < x0 + tw; x++, o += 4) {
            const h = H[row + x];
            const gx = H[row + (x < cw - 1 ? x + 1 : x)] - H[row + (x > 0 ? x - 1 : x)];
            const s = LIGHT * (0.6 * gx + 0.8 * (H[dn + x] - H[up + x])) - (h < 0 ? -0.25 * h : 0);
            const a = Math.min(1, Math.abs(s)) * GAIN;
            if (s > 0) {
                buf[o] = 255 * a;
                buf[o + 1] = 247 * a;
                buf[o + 2] = 225 * a;
            } else {
                buf[o] = 70 * a;
                buf[o + 1] = 52 * a;
                buf[o + 2] = 32 * a;
            }
            buf[o + 3] = 255 * a;
        }
    }
}

// Save format, per monitor: {saved: epoch s, w, h, strokes: [{t: age s, d}], leaves: [[x, y, frame]]}.
// d = points rounded to Q px, the first as is and each next one as the step from the one before.
export function encode(q) {
    const d = q.slice();
    for (let i = d.length - 1; i >= 2; i--)
        d[i] -= d[i - 2];
    return d;
}
export function decode(d) {
    const q = d.slice();
    for (let i = 2; i < q.length; i++)
        q[i] += q[i - 2];
    return q;
}

// Keep the newest MAX_POINTS points: older strokes go first, the one that crosses the line is cut.
// strokes = [{born: epoch s, q: [x, y, ...] in Q px}], oldest first; changed in place.
export function cap(strokes, max = MAX_POINTS) {
    let n = 0, i = strokes.length;
    while (i > 0 && n + strokes[i - 1].q.length / 2 <= max)
        n += strokes[--i].q.length / 2;
    if (i > 0 && max - n >= 2) {
        strokes[i - 1].q = strokes[i - 1].q.slice(-2 * (max - n));
        i--;
    }
    strokes.splice(0, i);
    return strokes;
}

const isInt = v => Number.isInteger(v) && Math.abs(v) <= 1e5;
const size = v => Number.isInteger(v) && v >= 200 && v <= 16384;
export const MAX_REPLAY = 200000;  // px of saved path replayed on load; build is not watched, so it must stay short

// Trust boundary for one saved monitor: bad strokes or leaves are skipped, a bad slot gives null.
// Every point must sit on (or just off) the saved screen, and only the newest MAX_REPLAY px of path are
// kept, so a corrupt file can't stall the shell while the scene builds.
export function readSlot(m) {
    if (!m || typeof m !== 'object' || !size(m.w) || !size(m.h) || !Number.isFinite(m.saved))
        return null;
    const inX = v => v >= -64 / Q && v <= (m.w + 64) / Q, inY = v => v >= -64 / Q && v <= (m.h + 64) / Q;
    const strokes = [];
    let budget = MAX_REPLAY;
    for (const s of (Array.isArray(m.strokes) ? m.strokes : []).slice().reverse()) {
        const d = s?.d;
        if (!(Number.isFinite(s?.t) && s.t >= 0 && Array.isArray(d) && d.length >= 4 && d.length % 2 === 0 &&
            d.length <= 2 * MAX_POINTS && d.every(isInt)))
            continue;
        const q = decode(d);
        let len = 0, good = true;
        for (let i = 0; i < q.length && good; i += 2) {
            good = inX(q[i]) && inY(q[i + 1]);
            if (i)
                len += Math.hypot(q[i] - q[i - 2], q[i + 1] - q[i - 1]) * Q;
        }
        if (!good)
            continue;
        if ((budget -= len) < 0)
            break;
        strokes.unshift({born: m.saved - s.t, q});
    }
    const leaves = (Array.isArray(m.leaves) ? m.leaves : [])
        .filter(l => Array.isArray(l) && l.length === 3 && l.every(isInt) && inX(l[0] / Q) && inY(l[1] / Q)).slice(-MAX_LEAVES);
    return {saved: m.saved, w: m.w, h: m.h, strokes: cap(strokes), leaves};
}

// A saved stroke's points for a screen sx, sy times the size it was saved on.
export const resample = (q, sx, sy) => q.map((v, i) => Math.round(v * (i % 2 ? sy : sx)));

export const writeSlot = (strokes, leaves, w, h, now) => ({saved: Math.round(now), w, h, leaves,
    strokes: strokes.map(s => ({t: Math.max(0, Math.round(now - s.born)), d: encode(s.q)}))});

// The whole store: v 1, slots for monitors 0-3 only, and under STORE_LIMIT (dropping the oldest stroke
// of the fullest monitor until it fits). Returns a fresh object.
export function fit(data) {
    const mons = {};
    for (const [k, m] of Object.entries(data?.mons ?? {})) {
        if (/^[0-3]$/.test(k) && m && typeof m === 'object' && (m.strokes === undefined ||
            Array.isArray(m.strokes) && m.strokes.every(s => Array.isArray(s?.d))))
            mons[k] = m;
    }
    const smoothed = Number.isInteger(data?.smoothed) && data.smoothed >= 0 ? data.smoothed : 0;  // last Smooth press acted on
    const out = {v: 1, mons, smoothed};
    const pts = m => (m.strokes ?? []).reduce((n, s) => n + s.d.length, 0);
    while (JSON.stringify(out).length > STORE_LIMIT) {
        const m = Object.values(mons).reduce((a, b) => pts(b) > pts(a) ? b : a);
        if (!m.strokes?.length)
            break;
        m.strokes.shift();
    }
    return out;
}
