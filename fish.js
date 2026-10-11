// Fish: steering from steer.js, each fish a small St.DrawingArea repainted per frame (tail, fins, eyes).
import St from 'gi://St';
import Cairo from 'cairo';
import { makeFish, step, NEAR } from './steer.js';

const hex = (c, a = 1) => [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255, a];
const src = (cr, c, a = 1) => cr.setSourceRGBA(...hex(c, a));

// Body outline, nose at +a, tail root at -a. m() bends every point for the turn curl.
function body(cr, g, top = 1.33, root = 0.22, blunt = 0) {
    const { m, a, h } = g, b = h * blunt;
    cr.moveTo(...m(a, -b));
    cr.curveTo(...m(a * 0.65, -h * top), ...m(-a * 0.45, -h * 1.05), ...m(-a, -h * root));
    cr.lineTo(...m(-a, h * root));
    cr.curveTo(...m(-a * 0.45, h * 1.05), ...m(a * 0.65, h * top), ...m(a, b));
    if (b) cr.curveTo(...m(a + b * 0.7, b), ...m(a + b * 0.7, -b), ...m(a, -b));
    cr.closePath();
}

// Tail drawn from its root, swinging with the wiggle. kind: fork | fan | veil
function tail(cr, g, kind, t, s, col, a = 0.95) {
    cr.save();
    cr.translate(...g.m(-g.a, 0));
    cr.rotate(g.tail);
    const w = Math.sin(g.ph - 1) * s * 0.15;
    cr.moveTo(0, -s * 0.18);
    if (kind === 'fork') {
        cr.curveTo(-t * 0.4, -s * 0.5, -t * 0.8, -s, -t, -s + w);
        cr.curveTo(-t * 0.75, -s * 0.4, -t * 0.65, 0, -t * 0.62, w);
        cr.curveTo(-t * 0.65, 0, -t * 0.75, s * 0.4, -t, s + w);
        cr.curveTo(-t * 0.8, s, -t * 0.4, s * 0.5, 0, s * 0.18);
    } else {
        // fan/veil: rear edge is a row of lobes that ripple when veil
        const n = kind === 'veil' ? 5 : 1;
        cr.curveTo(-t * 0.4, -s * 0.9, -t * 0.9, -s * 1.1, -t, -s + w);
        for (let i = 1; i <= n; i++) {
            const y = -s + w + (2 * s * i) / n, r = kind === 'veil' ? Math.sin(g.ph * 0.8 - i) * t * 0.12 : 0;
            cr.curveTo(-t * 1.12 + r, y - s / n * 1.3, -t * 1.12 + r, y - s / n * 0.7, -t + r * 0.5, y);
        }
        cr.curveTo(-t * 0.9, s * 1.1, -t * 0.4, s * 0.9, 0, s * 0.18);
    }
    cr.closePath();
    src(cr, col, a);
    cr.fillPreserve();
    src(cr, '#000000', 0.25);
    cr.setLineWidth(0.8);
    cr.stroke();
    // fin rays
    src(cr, '#ffffff', 0.18);
    for (let i = -2; i <= 2; i++) { cr.moveTo(-1, i * s * 0.05); cr.lineTo(-t * 0.9, i * s * 0.35 + w); }
    cr.stroke();
    cr.restore();
}

// A fin as one smooth lobe from (x0,y0) to (x1,y1) bulging out to (bx,by); flutters with phase.
function fin(cr, g, x0, y0, bx, by, x1, y1, col, a = 0.85, flut = 0.1) {
    const { m } = g, f = Math.sin(g.ph * 1.3) * flut * Math.abs(by - y0);
    cr.moveTo(...m(x0, y0));
    cr.curveTo(...m(bx, by + f), ...m(bx - (x1 - x0) * 0.3, by + f), ...m(x1, y1));
    cr.closePath();
    src(cr, col, a);
    cr.fillPreserve();
    src(cr, '#000000', 0.2);
    cr.setLineWidth(0.7);
    cr.stroke();
}

// Shared layering: back fins, tail, body + clipped details + shading, outline, gill, pectoral, eye, mouth.
function fish(cr, g, o) {
    const { a, h, m } = g;
    o.back?.(cr, g);
    tail(cr, g, o.tail, o.tl * a, o.ts * h, o.tc ?? o.fin);
    body(cr, g, o.top, o.root, o.blunt);
    src(cr, o.col);
    cr.fillPreserve();
    cr.save();
    cr.clip();
    o.detail?.(cr, g);
    if (!g.shade) {
        g.shade = new Cairo.LinearGradient(0, -h * 1.1, 0, h * 1.1);
        g.shade.addColorStopRGBA(0, 1, 1, 1, 0.3);
        g.shade.addColorStopRGBA(0.45, 1, 1, 1, 0);
        g.shade.addColorStopRGBA(1, 0, 0, 0.15, 0.4);
    }
    cr.setSource(g.shade);
    cr.paint();
    cr.restore();
    body(cr, g, o.top, o.root, o.blunt);
    src(cr, '#000000', 0.3);
    cr.setLineWidth(0.9);
    cr.stroke();
    // gill line
    const gx = a * (o.gill ?? 0.4);
    cr.moveTo(...m(gx, -h * 0.55));
    cr.curveTo(...m(gx - h * 0.25, -h * 0.2), ...m(gx - h * 0.25, h * 0.2), ...m(gx, h * 0.55));
    src(cr, '#000000', 0.25);
    cr.setLineWidth(0.8);
    cr.stroke();
    o.front?.(cr, g);
    // pectoral fin, fluttering (faster when startled)
    cr.save();
    cr.translate(...m(gx - a * 0.12, h * 0.3));
    cr.rotate(0.5 + Math.sin(g.ph * 1.7) * (0.35 + g.panic * 0.3));
    cr.scale(a * 0.28, h * 0.18);
    cr.arc(-1, 0, 1, 0, 6.283);
    cr.restore();
    src(cr, o.fin, 0.6);
    cr.fill();
    // eye: white, iris, pupil looking toward g.look, highlight
    const [ex, ey] = m(a * (o.ex ?? 0.62), -h * (o.ey ?? 0.22)), r = h * (o.er ?? 0.3);
    cr.arc(ex, ey, r, 0, 6.283);
    src(cr, '#ffffff');
    cr.fillPreserve();
    src(cr, '#000000', 0.5);
    cr.setLineWidth(0.6);
    cr.stroke();
    const px = ex + g.look[0] * r * 0.35, py = ey + g.look[1] * r * 0.35;
    cr.arc(px, py, r * 0.65, 0, 6.283);
    src(cr, o.iris ?? '#c88a1e');
    cr.fill();
    cr.arc(px, py, r * 0.4, 0, 6.283);
    src(cr, '#0a0a10');
    cr.fill();
    cr.arc(ex - r * 0.3, ey - r * 0.35, r * 0.22, 0, 6.283);
    src(cr, '#ffffff', 0.95);
    cr.fill();
    // mouth opens and closes
    const [mx, my] = m(a + h * (o.blunt ?? 0) * 0.5 - 1, h * 0.12);
    cr.save();
    cr.translate(mx, my);
    cr.scale(h * 0.12, h * (0.03 + 0.09 * g.mouth));
    cr.arc(0, 0, 1, 0, 6.283);
    cr.restore();
    src(cr, '#3a1010', 0.8);
    cr.fill();
}

const band = (cr, g, x, w, c) => {
    const { m, h } = g;
    cr.moveTo(...m(x + w, -h * 1.4));
    cr.curveTo(...m(x + w + h * 0.3, -h * 0.4), ...m(x + w + h * 0.3, h * 0.4), ...m(x + w, h * 1.4));
    cr.lineTo(...m(x - w, h * 1.4));
    cr.curveTo(...m(x - w + h * 0.3, h * 0.4), ...m(x - w + h * 0.3, -h * 0.4), ...m(x - w, -h * 1.4));
    cr.closePath();
    src(cr, c);
    cr.fill();
};

// len: body length incl. tail in px; a/h derive from it. n: how many.
const SPECIES = [
    { name: 'clown', n: 2, len: 54, ar: 0.36, hr: 0.2, cruise: 45, curious: 0.65, draw: (cr, g) => fish(cr, g, {
        col: '#f2701c', fin: '#f2701c', tail: 'fan', tl: 0.8, ts: 1.0, top: 1.35, blunt: 0.25, iris: '#e05a10',
        back: (cr, g) => {
            fin(cr, g, g.a * 0.3, -g.h * 0.8, 0, -g.h * 1.6, -g.a * 0.7, -g.h * 0.5, '#f2701c');
            fin(cr, g, -g.a * 0.1, g.h * 0.8, -g.a * 0.4, g.h * 1.45, -g.a * 0.75, g.h * 0.45, '#f2701c');
        },
        detail: (cr, g) => {
            for (const [x, w] of [[0.38, 0.13], [-0.12, 0.15], [-0.85, 0.09]]) {
                band(cr, g, x * g.a, w * g.a + 1.4, '#111111');
                band(cr, g, x * g.a, w * g.a, '#ffffff');
            }
        },
    }) },
    { name: 'tetra', n: 7, len: 30, ar: 0.36, hr: 0.11, cruise: 55, curious: 0.1, school: 'tetra', draw: (cr, g) => fish(cr, g, {
        col: '#c9d3dc', fin: '#dfe8ee', tail: 'fork', tl: 0.7, ts: 1.4, top: 1.25, er: 0.42, iris: '#2a6fd0',
        detail: (cr, g) => {
            const { m, a, h } = g;
            cr.moveTo(...m(-a * 0.2, h * 0.05)); cr.lineTo(...m(-a, h * 0.05)); cr.lineTo(...m(-a, h * 1.2)); cr.lineTo(...m(-a * 0.2, h * 1.2));
            src(cr, '#e8203a'); cr.fill();
            cr.moveTo(...m(a * 0.55, -h * 0.25)); cr.lineTo(...m(-a * 0.85, -h * 0.1));
            src(cr, '#21e3ff'); cr.setLineWidth(h * 0.45); cr.stroke();
            cr.moveTo(...m(a * 0.55, -h * 0.25)); cr.lineTo(...m(-a * 0.85, -h * 0.1));
            src(cr, '#b8ffff', 0.8); cr.setLineWidth(h * 0.15); cr.stroke();
        },
    }) },
    { name: 'angel', n: 2, len: 46, ar: 0.3, hr: 0.3, cruise: 30, curious: 0.5, turn: 1.6, draw: (cr, g) => fish(cr, g, {
        col: '#dfe2d8', fin: '#e8e6d6', tail: 'fork', tl: 1.0, ts: 0.9, top: 1.5, root: 0.18, iris: '#c0281e', gill: 0.5,
        back: (cr, g) => {
            const { a, h } = g, s = Math.sin(g.ph * 0.6) * h * 0.15;
            fin(cr, g, a * 0.3, -h * 0.8, -a * 0.6, -h * 2.6 + s, -a * 0.9, -h * 0.3, '#e8e6d6', 0.8, 0);
            fin(cr, g, a * 0.2, h * 0.8, -a * 0.6, h * 2.6 - s, -a * 0.9, h * 0.3, '#e8e6d6', 0.8, 0);
            src(cr, '#e8e6d6', 0.7); cr.setLineWidth(0.8);  // ventral filaments
            cr.moveTo(...g.m(a * 0.25, h * 0.85)); cr.curveTo(...g.m(0, h * 1.8), ...g.m(-a * 0.3, h * 2.4 + s), ...g.m(-a * 0.5, h * 3 + s)); cr.stroke();
        },
        detail: (cr, g) => {
            for (const x of [0.45, 0, -0.5]) band(cr, g, x * g.a, g.a * 0.07, '#24242a');
        },
    }) },
    { name: 'goldfish', n: 2, len: 52, ar: 0.3, hr: 0.22, cruise: 35, curious: 0.8, draw: (cr, g) => fish(cr, g, {
        col: '#f59a23', fin: '#ffb347', tail: 'veil', tl: 1.4, ts: 1.4, top: 1.45, blunt: 0.3, er: 0.33, iris: '#1a1a1a',
        back: (cr, g) => fin(cr, g, g.a * 0.35, -g.h * 0.85, -g.a * 0.2, -g.h * 1.9, -g.a * 0.7, -g.h * 0.55, '#ffb347', 0.8, 0.2),
        detail: (cr, g) => {
            // scale arcs
            src(cr, '#b85a10', 0.35); cr.setLineWidth(0.7);
            const s = g.h * 0.32;
            for (let i = 0; i * s * 1.2 < g.a * 1.3; i++)
                for (let y = -g.h; y < g.h; y += s * 1.3) {
                    const [px, py] = g.m(g.a * 0.3 - i * s * 1.2, y + (i % 2) * s * 0.6);
                    cr.newSubPath(); cr.arc(px, py, s * 0.7, -1.2, 1.2);
                }
            cr.stroke();
        },
    }) },
    { name: 'tang', n: 1, len: 64, ar: 0.37, hr: 0.2, cruise: 50, curious: 0.25, draw: (cr, g) => fish(cr, g, {
        col: '#1f5fd6', fin: '#1f5fd6', tc: '#f7d21e', tail: 'fork', tl: 0.55, ts: 1.1, top: 1.4, blunt: 0.15, iris: '#111111',
        back: (cr, g) => {
            fin(cr, g, g.a * 0.5, -g.h * 0.85, -g.a * 0.2, -g.h * 1.5, -g.a * 0.95, -g.h * 0.35, '#163fa0');
            fin(cr, g, g.a * 0.1, g.h * 0.85, -g.a * 0.3, g.h * 1.45, -g.a * 0.95, g.h * 0.35, '#163fa0');
        },
        detail: (cr, g) => {
            const { m, a, h } = g;  // black "palette" swoosh with a loop
            cr.moveTo(...m(a * 0.55, -h * 0.35));
            cr.curveTo(...m(a * 0.1, -h * 0.95), ...m(-a * 0.6, -h * 0.9), ...m(-a, -h * 0.2));
            cr.curveTo(...m(-a * 0.6, -h * 0.35), ...m(-a * 0.3, h * 0.05), ...m(-a * 0.45, h * 0.35));
            cr.curveTo(...m(-a * 0.1, -h * 0.2), ...m(a * 0.3, -h * 0.05), ...m(a * 0.55, -h * 0.35));
            src(cr, '#0b0f24'); cr.fill();
        },
    }) },
    { name: 'puffer', n: 1, len: 44, ar: 0.36, hr: 0.26, cruise: 30, curious: 0.7, draw: (cr, g) => {
        // puff swells the whole body and raises spikes
        cr.scale(1 + g.puff * 0.25, 1 + g.puff * 0.65);
        fish(cr, g, {
            col: '#e2d08a', fin: '#efe2a8', tail: 'fan', tl: 0.6, ts: 0.8, top: 1.45, blunt: 0.45, er: 0.36, iris: '#2f8f4a', gill: 0.3,
            detail: (cr, g) => {
                const { m, a, h } = g;
                cr.moveTo(...m(a, h * 0.1)); cr.lineTo(...m(-a, h * 0.1)); cr.lineTo(...m(-a, h * 2)); cr.lineTo(...m(a, h * 2));
                src(cr, '#fbf6e4'); cr.fill();
                src(cr, '#6b4a1e', 0.75);
                for (let i = 0; i < 9; i++) {
                    const [px, py] = m(a * (0.25 - (i % 5) * 0.27), -h * (0.25 + (i % 2) * 0.4));
                    cr.newSubPath(); cr.arc(px, py, h * 0.11, 0, 6.283);
                }
                cr.fill();
            },
            front: (cr, g) => {
                if (g.puff < 0.1) return;
                src(cr, '#8a7a40', g.puff); cr.setLineWidth(0.8);
                for (let i = 0; i < 16; i++) {
                    const t = i / 16 * 6.283, cx = Math.cos(t) * g.a * 0.9, cy = Math.sin(t) * g.h * 0.95, k = 1 + 0.25 * g.puff;
                    cr.moveTo(cx, cy); cr.lineTo(cx * k, cy * k);
                }
                cr.stroke();
            },
        });
    } },
    { name: 'cory', n: 2, len: 40, ar: 0.36, hr: 0.13, cruise: 22, curious: 0.35, bottom: true, draw: (cr, g) => fish(cr, g, {
        col: '#a8a49a', fin: '#c8c2b4', tail: 'fork', tl: 0.6, ts: 1.4, top: 1.6, root: 0.3, blunt: 0.35, ey: 0.3, iris: '#3a3a3a',
        back: (cr, g) => fin(cr, g, g.a * 0.35, -g.h * 0.9, g.a * 0.1, -g.h * 2.4, -g.a * 0.15, -g.h * 0.8, '#c8c2b4', 0.85, 0.05),
        detail: (cr, g) => {
            src(cr, '#4a463e', 0.7);
            for (let i = 0; i < 14; i++) {
                const [px, py] = g.m(g.a * (0.4 - (i * 0.37) % 1.3), g.h * (((i * 0.61) % 1.2) - 0.7));
                cr.newSubPath(); cr.arc(px, py, g.h * 0.12, 0, 6.283);
            }
            cr.fill();
            cr.moveTo(...g.m(-g.a, g.h * 0.2)); cr.lineTo(...g.m(g.a, g.h * 0.2));
            src(cr, '#e8e4d8', 0.5); cr.setLineWidth(g.h * 0.3); cr.stroke();
        },
        front: (cr, g) => {
            // whiskers (barbels) sweeping as it snuffles
            const [nx, ny] = g.m(g.a + g.h * 0.15, g.h * 0.35);
            src(cr, '#6e665a', 0.9); cr.setLineWidth(0.7);
            for (const k of [0.6, 1, 1.4]) {
                const w = Math.sin(g.ph * 0.9 + k * 2) * g.h * 0.25;
                cr.moveTo(nx, ny); cr.curveTo(nx + g.h * 0.5 * k, ny + g.h * 0.3, nx + g.h * 0.6 * k, ny + g.h * 0.6 + w, nx + g.h * 0.5 * k, ny + g.h * (0.6 + 0.4 * k) + w);
            }
            cr.stroke();
        },
    }) },
    { name: 'betta', n: 1, len: 52, ar: 0.24, hr: 0.14, cruise: 25, curious: 0.7, turn: 1.8, draw: (cr, g) => fish(cr, g, {
        col: '#7a1838', fin: '#b82a5a', tc: '#9a2050', tail: 'veil', tl: 2.4, ts: 2.6, top: 1.25, er: 0.32, iris: '#1a1a1a',
        back: (cr, g) => {
            const { a, h } = g, s = Math.sin(g.ph * 0.5) * h * 0.4;
            fin(cr, g, a * 0.2, -h * 0.85, -a * 1.3, -h * 2.8 + s, -a * 1.05, -h * 0.25, '#5a2ba0', 0.8, 0);
            fin(cr, g, a * 0.4, h * 0.85, -a * 1.4, h * 3.2 - s, -a * 1.05, h * 0.25, '#b82a5a', 0.8, 0);
        },
        detail: (cr, g) => {
            cr.moveTo(...g.m(g.a * 0.2, -g.h)); cr.lineTo(...g.m(-g.a, -g.h)); cr.lineTo(...g.m(-g.a, g.h)); cr.lineTo(...g.m(g.a * 0.2, g.h));
            src(cr, '#3a3aa8', 0.35); cr.fill();
        },
    }) },
];

export class School {
    constructor(fishLayers, swimBounds) {
        this._b = swimBounds;
        this._fish = [];
        this._layers = [[], []];
        let k = 0;
        for (const sp of SPECIES) {
            const hx = swimBounds.x + Math.random() * swimBounds.w, hy = swimBounds.y + Math.random() * swimBounds.h;
            for (let i = 0; i < sp.n; i++) {
                const layer = sp.school || k++ % 3 ? 1 : 0, sc = layer ? 1 : 0.6;
                const L = sp.len * sc, size = Math.ceil(L * 2);
                const s = makeFish({
                    // schools start bunched together, everyone else anywhere
                    x: sp.school ? hx + Math.random() * 80 : swimBounds.x + Math.random() * swimBounds.w,
                    y: sp.school ? hy + Math.random() * 40 : swimBounds.y + (sp.bottom ? swimBounds.h - L : Math.random() * swimBounds.h),
                    cruise: sp.cruise * (0.85 + Math.random() * 0.3) * (layer ? 1 : 0.7),
                    pad: L * 0.5, curious: sp.curious, school: sp.school, bottom: sp.bottom, turn: sp.turn,
                });
                const area = new St.DrawingArea({ width: size, height: size, opacity: layer ? 255 : 150, reactive: false });
                const f = {
                    sp, s, area, size, sc, layer, flip: Math.cos(s.dir) > 0 ? 1 : -1, ph: Math.random() * 9, puff: 0,
                    look: [1, 0], g: { a: sp.len * sp.ar, h: sp.len * sp.hr, shade: null },
                };
                area.connect('repaint', () => this._paint(f));
                area.connect('destroy', () => { f.area = null; });  // parent torn down under us
                fishLayers[layer].add_child(area);
                this._fish.push(f);
                this._layers[layer].push(s);
            }
        }
    }

    tick(dt, t, pointer) {
        for (const f of this._fish) {
            if (!f.area) continue;
            const s = f.s;
            step(s, dt, pointer, this._b, this._layers[f.layer]);
            const c = Math.cos(s.dir), facing = c > 0.2 ? 1 : c < -0.2 ? -1 : Math.sign(f.flip) || 1;
            f.flip += Math.max(-dt * 5, Math.min(dt * 5, facing - f.flip));
            f.pitch = Math.max(-0.4, Math.min(0.4, Math.atan2(Math.sin(s.dir), Math.abs(c))));
            f.ph += dt * (4 + (s.speed / f.sp.len) * 7);
            f.puff += ((s.panic > 0.2 ? 1 : 0) - f.puff) * Math.min(1, dt * 4);
            // eyes follow the cursor while curious, otherwise look ahead
            let lx = 1, ly = 0;
            if (pointer && s.mode === 'curious') {
                const dx = pointer.x - s.x, dy = pointer.y - s.y, d = Math.hypot(dx, dy) || 1, r = f.pitch * f.flip;
                lx = (dx * Math.cos(r) + dy * Math.sin(r)) / d * Math.sign(f.flip || 1);
                ly = (dy * Math.cos(r) - dx * Math.sin(r)) / d;
            }
            f.look[0] += (lx - f.look[0]) * Math.min(1, dt * 6);
            f.look[1] += (ly - f.look[1]) * Math.min(1, dt * 6);
            // curious fish do a little happy wiggle now and then while hovering
            f.wiggle = pointer && s.mode === 'curious' && Math.hypot(pointer.x - s.x, pointer.y - s.y) < NEAR + 40 &&
                Math.sin(t * 1.3 + f.ph * 0.01) > 0.75 ? Math.sin(t * 16) * 0.6 : 0;
            f.mouth = 0.5 + 0.5 * Math.sin(t * (2 + s.panic * 6) + f.ph * 0.1);
            f.area.set_position(Math.round(s.x - f.size / 2), Math.round(s.y - f.size / 2));
            f.area.queue_repaint();
        }
    }

    _paint(f) {
        const cr = f.area.get_context();
        try {
            const g = f.g, s = f.s, B = (s.bend * 0.18 + (f.wiggle ?? 0) * 0.15) * Math.sign(f.flip || 1) / g.a;
            g.m = (x, y) => [x, y + B * x * x];
            g.ph = f.ph;
            g.tail = Math.sin(f.ph) * (0.22 + Math.min(0.3, s.speed / f.sp.len * 0.12)) - B * g.a * 1.5;
            g.look = f.look; g.mouth = f.mouth ?? 0; g.puff = f.puff; g.panic = s.panic;
            cr.translate(f.size / 2, f.size / 2);
            cr.rotate((f.pitch ?? 0) * f.flip);
            const fl = f.flip >= 0 ? Math.max(0.08, f.flip) : Math.min(-0.08, f.flip);  // never a zero scale
            cr.scale(fl * f.sc, f.sc);
            cr.translate(g.a * 0.3, 0);  // centre body+tail in the box
            cr.setLineCap(Cairo.LineCap.ROUND);
            f.sp.draw(cr, g);
        } finally {
            cr.$dispose();
        }
    }

    destroy() {
        for (const f of this._fish) f.area?.destroy();
        this._fish = [];
        this._layers = [[], []];
    }
}
