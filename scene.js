// Tank scenery: static art is drawn once with Cairo; motion only moves/rotates actors.
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Cairo from 'cairo';

const TAU = Math.PI * 2;
const HAZE = [0.10, 0.32, 0.44];
const rgb = c => {
    if (typeof c !== 'string') return c;
    if (c.length === 4) c = c.replace(/\w/g, d => d + d);
    const n = parseInt(c.slice(1), 16);
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
};
const tint = (c, k) => rgb(c).map((v, i) => v + (HAZE[i] - v) * k);
const src = (cr, c, a = 1) => cr.setSourceRGBA(...rgb(c), a);
function lg(x0, y0, x1, y1, stops) {
    const g = new Cairo.LinearGradient(x0, y0, x1, y1);
    for (const [o, c, a = 1] of stops) g.addColorStopRGBA(o, ...rgb(c), a);
    return g;
}
function rg(x, y, r, stops) {
    const g = new Cairo.RadialGradient(x - r * 0.3, y - r * 0.3, r * 0.05, x, y, r);
    for (const [o, c, a = 1] of stops) g.addColorStopRGBA(o, ...rgb(c), a);
    return g;
}
const circ = (cr, x, y, r) => { cr.newSubPath(); cr.arc(x, y, r, 0, TAU); };
function ell(cr, x, y, rx, ry, rot = 0) {
    cr.save(); cr.translate(x, y); cr.rotate(rot); cr.scale(rx, ry);
    cr.newSubPath(); cr.arc(0, 0, 1, 0, TAU); cr.restore();
}
function rrect(cr, x, y, w, h, r) {
    cr.newSubPath();
    cr.arc(x + w - r, y + r, r, -Math.PI / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    cr.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI); cr.arc(x + r, y + r, r, Math.PI, 1.5 * Math.PI);
    cr.closePath();
}
function poly(cr, pts) {
    cr.moveTo(...pts[0]);
    for (const p of pts.slice(1)) cr.lineTo(...p);
    cr.closePath();
}
// Seeded so the layout is identical on every rebuild.
const rng = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;

// Static St.DrawingArea; Cairo runs only when Clutter needs the texture (first show / resize).
function art(parent, x, y, w, h, draw) {
    const a = new St.DrawingArea({x, y, width: Math.ceil(w), height: Math.ceil(h)});
    a.connect('repaint', () => {
        const cr = a.get_context();
        try { draw(cr, w, h); } finally { cr.$dispose(); }
    });
    parent.add_child(a);
    return a;
}

// ---------- backdrop ----------
function water(cr, W, H, r) {
    cr.setSource(lg(0, 0, 0, H, [[0, '#3fa3c8'], [0.3, '#1a6f96'], [0.7, '#0d4466'], [1, '#082c44']]));
    cr.paint();
    const g = new Cairo.RadialGradient(W * 0.45, -H * 0.3, 0, W * 0.45, -H * 0.3, H * 1.1);
    g.addColorStopRGBA(0, 1, 1, 0.9, 0.22); g.addColorStopRGBA(1, 1, 1, 1, 0);
    cr.setSource(g); cr.paint();
    // two rocky ridges, the farther one hazier
    for (const [top, haze, step] of [[0.62, 0.82, 260], [0.72, 0.62, 180]]) {
        const s = H / 1440;
        cr.moveTo(0, H);
        let x = -50 * s;
        cr.lineTo(x, H * top + 80 * s);
        while (x < W) {
            const nx = x + (step * 0.5 + r() * step) * s, hy = H * top + (r() * 90 - 20) * s;
            cr.curveTo(x + 10 * s, hy, nx - 10 * s, hy, nx, H * top + (40 + r() * 60) * s);
            x = nx;
        }
        cr.lineTo(W, H); cr.closePath();
        cr.setSource(lg(0, H * top, 0, H, [[0, tint('#5d7f78', haze)], [1, tint('#24413f', haze)]]));
        cr.fill();
        // a few rock face cracks
        src(cr, tint('#1b2f2e', haze), 0.5); cr.setLineWidth(2 * s);
        for (let i = 0; i < W / 300; i++) {
            const cx = r() * W, cy = H * (top + 0.06 + r() * 0.08);
            cr.moveTo(cx, cy); cr.lineTo(cx + 12 * s, cy + 18 * s); cr.lineTo(cx + 4 * s, cy + 34 * s);
        }
        cr.stroke();
    }
    cr.setSource(lg(0, H * 0.5, 0, H, [[0, HAZE, 0], [1, HAZE, 0.35]]));
    cr.paint();
}

function ray(cr, W, H) {
    for (let i = 0; i < 5; i++) {
        const f = 1 - i * 0.18, c = W / 2;
        poly(cr, [[c - W * 0.12 * f, 0], [c + W * 0.12 * f, 0], [c + W * 0.5 * f, H], [c - W * 0.5 * f, H]]);
        cr.setSource(lg(0, 0, 0, H, [[0, '#eaffff', 0.10], [0.7, '#eaffff', 0.035], [1, '#eaffff', 0]]));
        cr.fill();
    }
}

function surface(cr, W, H, r) {
    cr.setSource(lg(0, 0, 0, H * 0.3, [[0, '#e8ffff', 0.35], [1, '#e8ffff', 0]]));
    cr.rectangle(0, 0, W, H * 0.3); cr.fill();
    cr.setLineWidth(Math.max(1.5, H / 60));
    for (let j = 0; j < 6; j++) {
        const y0 = H * (0.12 + j * 0.15), k1 = 0.004 + r() * 0.004, k2 = 0.013 + r() * 0.01, p = r() * TAU;
        cr.moveTo(0, y0);
        for (let x = 0; x <= W; x += 24)
            cr.lineTo(x, y0 + H * 0.06 * Math.sin(x * k1 + p) + H * 0.025 * Math.sin(x * k2));
        src(cr, '#f0ffff', 0.22 * (1 - j / 6)); cr.stroke();
    }
}

// ---------- decor (all in unit boxes, scaled to the actor width) ----------
function castle(cr, W, H, r) {
    cr.scale(W / 100, W / 100);
    const dark = '#6f634f', hole = '#122029';
    const bricks = (x, y, w, h) => {
        cr.save(); cr.rectangle(x, y, w, h); cr.clip();
        for (let row = 0, yy = y; yy < y + h; row++, yy += 5) {
            for (let xx = x - (row % 2) * 4.5; xx < x + w; xx += 9) {
                src(cr, r() < 0.5 ? '#fff' : '#000', 0.03 + r() * 0.07);
                cr.rectangle(xx + 0.3, yy + 0.3, 8.4, 4.4); cr.fill();
                cr.moveTo(xx, yy); cr.lineTo(xx, yy + 5);
            }
            cr.moveTo(x, yy); cr.lineTo(x + w, yy);
        }
        src(cr, '#4f4536', 0.5); cr.setLineWidth(0.35); cr.stroke();
        cr.restore();
    };
    const block = (x, y, w, h, merl) => {
        cr.rectangle(x, y, w, h);
        for (let i = 0; i < merl; i++) {
            const mw = w / (2 * merl - 1);
            cr.rectangle(x + i * 2 * mw, y - 5, mw, 5.5);
        }
        cr.setSource(lg(x, 0, x + w, 0, [[0, '#d8caac'], [0.55, '#b5a587'], [1, dark]])); cr.fill();
        bricks(x, y, w, h);
        src(cr, '#000', 0.18); cr.rectangle(x, y, w, 1.2); cr.fill();
    };
    const arch = (x, y, w, h) => {
        cr.moveTo(x, y + h); cr.lineTo(x, y + w / 2);
        cr.arc(x + w / 2, y + w / 2, w / 2, Math.PI, 0); cr.lineTo(x + w, y + h); cr.closePath();
    };
    const win = (x, y, w, h) => {
        src(cr, '#e0d4b8'); arch(x - 1, y - 1, w + 2, h + 1.5); cr.fill();
        src(cr, hole); arch(x, y, w, h); cr.fill();
        src(cr, '#3a5560', 0.6); cr.setLineWidth(0.4);
        cr.moveTo(x + w / 2, y); cr.lineTo(x + w / 2, y + h); cr.moveTo(x, y + h * 0.55); cr.lineTo(x + w, y + h * 0.55); cr.stroke();
    };
    // pennants (behind everything)
    const flag = (x, y0, y1, col) => {
        src(cr, '#4a3a2a'); cr.setLineWidth(0.8); cr.moveTo(x, y0); cr.lineTo(x, y1); cr.stroke();
        cr.moveTo(x, y1); cr.curveTo(x + 4, y1 - 1, x + 7, y1 + 2, x + 12, y1 + 1.5);
        cr.lineTo(x + 9, y1 + 3.5); cr.lineTo(x + 12, y1 + 5.5);
        cr.curveTo(x + 7, y1 + 6, x + 4, y1 + 5, x, y1 + 6.5); cr.closePath();
        src(cr, col); cr.fill();
        circ(cr, x, y1 - 0.6, 0.9); src(cr, '#d4a93a'); cr.fill();
    };
    flag(50, 14, 2, '#c0392b'); flag(16, 36, 24, '#e0b02a'); flag(84, 36, 24, '#2b6cb0');
    block(4, 42, 24, 88, 3); block(72, 42, 24, 88, 3); block(26, 60, 48, 70, 4); block(40, 32, 20, 30, 0);
    // conical roof with tile rows
    poly(cr, [[37, 33], [50, 13], [63, 33]]);
    cr.setSource(lg(37, 0, 63, 0, [[0, '#c4553f'], [1, '#7a2e22']])); cr.fill();
    src(cr, '#5a1f17', 0.6); cr.setLineWidth(0.4);
    for (let y = 17; y < 33; y += 3) { const hw = (y - 13) * 0.65; cr.moveTo(50 - hw, y); cr.lineTo(50 + hw, y); }
    cr.stroke();
    // door: planks, studs, stone ring
    src(cr, '#d9ccae'); arch(40.5, 100.5, 19, 30); cr.fill();
    src(cr, '#4a3020'); arch(42, 102, 16, 28); cr.fill();
    src(cr, '#2a1a10', 0.8); cr.setLineWidth(0.4);
    for (let x = 46; x < 58; x += 4) { cr.moveTo(x, 103); cr.lineTo(x, 130); }
    cr.stroke();
    src(cr, '#222'); for (const y of [112, 122]) for (let x = 44; x < 58; x += 4) circ(cr, x, y, 0.5);
    cr.fill();
    circ(cr, 55, 117, 1); src(cr, '#c9a14a'); cr.fill();
    win(12, 56, 8, 13); win(80, 56, 8, 13); win(12, 86, 8, 13); win(80, 86, 8, 13);
    win(33, 74, 6, 10); win(61, 74, 6, 10); win(46, 40, 8, 12);
    // cracks
    src(cr, '#2a241c', 0.7); cr.setLineWidth(0.4);
    for (const [x, y] of [[24, 64], [68, 92], [8, 108], [36, 96]]) {
        cr.moveTo(x, y); cr.lineTo(x + 1.5, y + 3); cr.lineTo(x - 0.5, y + 6); cr.lineTo(x + 1, y + 9);
    }
    cr.stroke();
    // moss: clumps at the base, on ledges, dripping from windows
    for (let i = 0; i < 90; i++) {
        const spots = [[r() * 100, 124 + r() * 6], [4 + r() * 24, 41 + r() * 2], [72 + r() * 24, 41 + r() * 2], [26 + r() * 48, 59 + r() * 2]];
        const [x, y] = spots[i % 4];
        src(cr, ['#3f7a34', '#5a9a3c', '#2e5f2a'][i % 3], 0.85); circ(cr, x, y, 0.8 + r() * 1.8); cr.fill();
    }
    src(cr, '#4e8a38', 0.8); cr.setLineWidth(0.6);
    for (const [x, y] of [[13, 69], [17, 69], [82, 99], [86, 99], [35, 84]]) {
        cr.moveTo(x, y); cr.curveTo(x + 0.6, y + 3, x - 0.6, y + 5, x + 0.3, y + 7 + r() * 4);
    }
    cr.stroke();
}

function ship(cr, W, H, r) {
    cr.scale(W / 100, W / 100);
    cr.translate(50, 32); cr.rotate(-0.06); cr.translate(-50, -32);
    const wood = '#4a3220';
    // rigging, masts, tattered sail
    src(cr, '#2a2018', 0.7); cr.setLineWidth(0.35);
    cr.moveTo(42, 6); cr.lineTo(6, 24); cr.moveTo(42, 6); cr.lineTo(76, 28);
    cr.moveTo(42, 10); cr.curveTo(48, 20, 50, 22, 52, 30); cr.stroke();
    src(cr, wood); poly(cr, [[40, 31], [40, 7], [41.3, 4], [42, 7.5], [43, 3.5], [43.6, 6], [43.6, 31]]); cr.fill();
    poly(cr, [[70, 29], [70, 16], [71.5, 13], [72.3, 16.5], [73.5, 14], [73.5, 29]]); cr.fill();
    cr.setLineWidth(1.3); cr.moveTo(29, 13); cr.lineTo(55, 19); cr.stroke();
    cr.moveTo(30, 14); cr.lineTo(54, 19.5); cr.lineTo(52, 24); cr.lineTo(49, 22); cr.lineTo(47, 27);
    cr.lineTo(43, 23.5); cr.lineTo(39, 28); cr.lineTo(36, 22); cr.lineTo(33, 25); cr.closePath();
    src(cr, '#d8ccaa', 0.55); cr.fill();
    // anchor at the bow
    src(cr, '#333a3d'); cr.setLineWidth(0.9);
    cr.moveTo(7, 26); cr.lineTo(7, 40); cr.moveTo(3, 37); cr.curveTo(4, 41, 10, 41, 11, 37);
    cr.moveTo(4.5, 29); cr.lineTo(9.5, 29); cr.stroke();
    circ(cr, 7, 25, 1); cr.stroke();
    const hull = () => {
        cr.moveTo(3, 22); cr.lineTo(76, 27); cr.lineTo(78, 17); cr.lineTo(97, 16); cr.lineTo(95, 31);
        cr.curveTo(90, 48, 35, 56, 14, 46); cr.closePath();
    };
    hull(); cr.setSource(lg(0, 16, 0, 56, [[0, '#86603a'], [0.5, '#5c3d22'], [1, '#2e1c0e']])); cr.fill();
    cr.save(); hull(); cr.clip();
    src(cr, '#1e120a', 0.55); cr.setLineWidth(0.45);
    for (let y = 26; y < 58; y += 3.5) {
        cr.moveTo(0, y); cr.curveTo(30, y + 2, 70, y + 2, 100, y - 3);
        for (let x = 6 + r() * 10; x < 98; x += 14 + r() * 10) { cr.moveTo(x, y + 0.5); cr.lineTo(x, y + 3.8); }
    }
    cr.stroke();
    // barnacles and algae on the lower hull
    for (let i = 0; i < 70; i++) {
        const x = 12 + r() * 82, y = 40 + r() * 14, rr = 0.4 + r() * 0.9;
        if (i % 3) { circ(cr, x, y, rr); src(cr, '#d8d2c0'); cr.fill(); circ(cr, x, y, rr * 0.4); src(cr, '#3a3428'); cr.fill(); }
        else { circ(cr, x, y + 2, 1 + r() * 2); src(cr, '#4d7a34', 0.7); cr.fill(); }
    }
    cr.restore();
    // gunwale + rail posts
    src(cr, '#9a7650'); cr.setLineWidth(1.4); cr.moveTo(3, 22); cr.lineTo(76, 27); cr.lineTo(78, 17); cr.lineTo(97, 16); cr.stroke();
    cr.setLineWidth(0.5); src(cr, wood); cr.moveTo(3, 19); cr.lineTo(40, 21.5); cr.moveTo(44, 21.8); cr.lineTo(70, 23.8);
    for (let x = 6; x < 72; x += 6) { cr.moveTo(x, 22 + x * 0.068); cr.lineTo(x, 19 + x * 0.068); }
    cr.stroke();
    // stern windows with brass frames
    for (const x of [81, 86, 91]) { cr.rectangle(x, 20, 3.2, 4); src(cr, '#0d1d26'); cr.fillPreserve(); src(cr, '#c9a14a'); cr.setLineWidth(0.5); cr.stroke(); }
    // rudder
    poly(cr, [[94, 31], [97.5, 31], [97, 43], [92.5, 41]]); src(cr, '#3e2816'); cr.fill();
    // portholes
    for (const x of [20, 31, 42, 53, 64]) {
        const y = 32 + x * 0.04;
        circ(cr, x, y, 2.6); src(cr, '#b8903e'); cr.fill();
        circ(cr, x, y, 1.7); cr.setSource(rg(x, y, 1.7, [[0, '#2e5a70'], [1, '#081820']])); cr.fill();
        circ(cr, x - 0.6, y - 0.6, 0.45); src(cr, '#fff', 0.6); cr.fill();
    }
    // the hole, with splintered plank ends
    poly(cr, [[58, 39], [61, 36], [63, 39.5], [66, 35.5], [69, 38], [72, 37], [70.5, 44], [66, 47.5], [63, 45], [59, 46]]);
    src(cr, '#07121a'); cr.fill();
    src(cr, '#86603a'); cr.setLineWidth(0.6);
    cr.moveTo(61, 36); cr.lineTo(62.5, 39); cr.moveTo(66, 35.5); cr.lineTo(66.5, 39); cr.moveTo(70.5, 44); cr.lineTo(68, 43); cr.stroke();
}

function chestBody(cr, W, H, r) {
    cr.scale(W / 120, W / 120);
    const gold = '#e2b844', band = '#c9982e';
    // coin heap inside (shows when the lid lifts)
    for (let i = 0; i < 26; i++) {
        const x = 10 + r() * 80, y = 24 + r() * 8;
        ell(cr, x, y, 4, 2.2); src(cr, gold); cr.fillPreserve(); src(cr, '#9a7420'); cr.setLineWidth(0.4); cr.stroke();
    }
    circ(cr, 30, 23, 2.4); src(cr, '#d0303a'); cr.fill(); circ(cr, 66, 24, 2.2); src(cr, '#2fae6a'); cr.fill();
    circ(cr, 29.3, 22.3, 0.7); circ(cr, 65.3, 23.3, 0.7); src(cr, '#fff', 0.7); cr.fill();
    // box with planks
    cr.rectangle(5, 30, 90, 45); cr.setSource(lg(0, 30, 0, 75, [[0, '#9a6532'], [1, '#4e3016']])); cr.fill();
    src(cr, '#2e1a0a', 0.6); cr.setLineWidth(0.5);
    for (const y of [45, 60]) { cr.moveTo(5, y); cr.lineTo(95, y); }
    for (let i = 0; i < 14; i++) { const y = 33 + r() * 40, x = 8 + r() * 80; cr.moveTo(x, y); cr.curveTo(x + 4, y - 0.5, x + 8, y + 0.5, x + 12, y); }
    cr.stroke();
    // bands, corner brackets, rivets
    src(cr, band);
    for (const x of [14, 79]) cr.rectangle(x, 30, 7, 45);
    cr.rectangle(5, 30, 90, 3.5); cr.rectangle(5, 72, 90, 3); cr.fill();
    poly(cr, [[5, 75], [5, 66], [9, 75]]); poly(cr, [[95, 75], [95, 66], [91, 75]]); cr.fill();
    src(cr, '#fff1b0', 0.8);
    for (const x of [17.5, 82.5]) for (let y = 37; y < 72; y += 7) circ(cr, x, y, 0.8);
    cr.fill();
    // lock plate + keyhole
    rrect(cr, 43, 34, 14, 16, 2); src(cr, gold); cr.fillPreserve(); src(cr, '#8a6418'); cr.setLineWidth(0.6); cr.stroke();
    circ(cr, 50, 40, 1.8); cr.rectangle(49.2, 40, 1.6, 5); src(cr, '#140c06'); cr.fill();
    // pearl necklace draped over the rim
    for (let i = 0; i <= 10; i++) {
        const f = i / 10, x = 62 + f * 14, y = 31 + Math.sin(f * Math.PI) * 13;
        circ(cr, x, y, 1.3); cr.setSource(rg(x, y, 1.3, [[0, '#fff'], [1, '#c8c0d0']])); cr.fill();
    }
    // spilled coins on the sand
    for (let i = 0; i < 22; i++) {
        const x = 92 + r() * 26, y = 70 + r() * 9, stand = i % 5 === 0;
        if (stand) ell(cr, x, y - 2, 1.4, 3.6); else ell(cr, x, y, 4, 1.6, (r() - 0.5) * 0.4);
        src(cr, gold); cr.fillPreserve(); src(cr, '#8a6418'); cr.setLineWidth(0.4); cr.stroke();
        circ(cr, x - 1, y - 0.6, 0.5); src(cr, '#fff', 0.7); cr.fill();
    }
}

function chestLid(cr, W) {
    cr.scale(W / 120, W / 120);
    const lid = () => { cr.moveTo(5, 32); cr.lineTo(5, 16); cr.curveTo(5, 1, 95, 1, 95, 16); cr.lineTo(95, 32); cr.closePath(); };
    lid(); cr.setSource(lg(0, 2, 0, 32, [[0, '#b07a40'], [1, '#6a4220']])); cr.fill();
    cr.save(); lid(); cr.clip();
    src(cr, '#2e1a0a', 0.5); cr.setLineWidth(0.5);
    for (const y of [10, 20]) { cr.moveTo(5, y); cr.curveTo(30, y - 3, 70, y - 3, 95, y); }
    cr.stroke();
    src(cr, '#c9982e'); cr.rectangle(14, 0, 7, 32); cr.rectangle(79, 0, 7, 32); cr.rectangle(5, 28, 90, 4); cr.fill();
    src(cr, '#fff1b0', 0.8);
    for (const x of [17.5, 82.5]) for (let y = 6; y < 28; y += 7) circ(cr, x, y, 0.8);
    cr.fill();
    cr.restore();
    rrect(cr, 46, 26, 8, 8, 1.5); src(cr, '#e2b844'); cr.fill();
}

function diver(cr, W, H) {
    cr.scale(W / 70, W / 70);
    const suit = '#5f6f62', brass = (x, y, rr) => rg(x, y, rr, [[0, '#f6d27a'], [0.6, '#c08a3a'], [1, '#6a4418']]);
    // air hose rising out of view
    cr.setLineWidth(3); src(cr, '#222');
    cr.moveTo(46, 40); cr.curveTo(62, 32, 54, 14, 68, 0); cr.stroke();
    cr.setLineWidth(0.8); src(cr, '#6a6a6a', 0.7);
    cr.moveTo(46.5, 39); cr.curveTo(62, 31, 54, 13, 67.5, -0.5); cr.stroke();
    // legs + boots with soles and laces
    rrect(cr, 19, 100, 12, 28, 4); rrect(cr, 36, 100, 12, 28, 4);
    rrect(cr, 9, 66, 11, 34, 5); rrect(cr, 47, 66, 11, 34, 5);
    cr.setSource(lg(0, 0, 70, 0, [[0, '#7d8e80'], [1, '#3d4a40']])); cr.fill();
    for (const x of [16, 33]) {
        rrect(cr, x, 124, 18, 11, 3); src(cr, '#2b2b2b'); cr.fill();
        cr.rectangle(x - 1, 133, 20, 4); src(cr, '#4a3a2a'); cr.fill();
        src(cr, '#888', 0.8); cr.setLineWidth(0.4);
        for (let y = 126; y < 132; y += 2) { cr.moveTo(x + 6, y); cr.lineTo(x + 12, y + 1); }
        cr.stroke();
    }
    // torso + folds
    rrect(cr, 16, 66, 36, 40, 9); cr.setSource(lg(16, 0, 52, 0, [[0, '#7d8e80'], [1, '#3d4a40']])); cr.fill();
    src(cr, '#2f3a32', 0.6); cr.setLineWidth(0.5);
    for (const [x, y] of [[22, 82], [40, 86], [24, 116], [40, 112]]) { cr.moveTo(x, y); cr.curveTo(x + 2, y + 1, x + 4, y - 1, x + 6, y); }
    cr.stroke();
    // weight belt with lead blocks and knife
    cr.rectangle(16, 92, 36, 5); src(cr, '#3a2a1a'); cr.fill();
    for (const x of [18, 28, 38]) { rrect(cr, x, 90.5, 8, 8, 1); src(cr, '#6c7378'); cr.fill(); }
    cr.rectangle(47, 95, 3, 10); src(cr, '#2a2a2a'); cr.fill();
    rrect(cr, 30, 92, 6, 5, 1); src(cr, '#c9a14a'); cr.fill();
    // gloves
    for (const x of [14.5, 52.5]) { circ(cr, x, 101, 4.5); src(cr, '#3a3a3a'); cr.fill(); }
    // corselet with wing nuts
    cr.moveTo(14, 70); cr.curveTo(14, 58, 54, 58, 54, 70); cr.lineTo(54, 72); cr.lineTo(14, 72); cr.closePath();
    cr.setSource(brass(34, 62, 22)); cr.fill();
    for (const x of [18, 26, 42, 50]) { circ(cr, x, 68, 1.1); src(cr, '#5a3a10'); cr.fill(); }
    // helmet
    circ(cr, 34, 46, 17); cr.setSource(brass(34, 46, 17)); cr.fill();
    rrect(cr, 30, 26.5, 8, 4, 1); src(cr, '#a07030'); cr.fill();
    const port = (x, y, rr, bars) => {
        circ(cr, x, y, rr + 1.6); src(cr, '#7a5020'); cr.fill();
        circ(cr, x, y, rr); cr.setSource(rg(x, y, rr, [[0, '#3c7a96'], [1, '#08161f']])); cr.fill();
        src(cr, '#9a6a28'); cr.setLineWidth(0.9);
        for (let i = 1; i <= bars; i++) { const xx = x - rr + (2 * rr * i) / (bars + 1), dy = Math.sqrt(rr * rr - (xx - x) ** 2); cr.moveTo(xx, y - dy); cr.lineTo(xx, y + dy); }
        cr.stroke();
        for (let a = 0; a < 4; a++) circ(cr, x + (rr + 0.8) * Math.cos(a * TAU / 4 + 0.78), y + (rr + 0.8) * Math.sin(a * TAU / 4 + 0.78), 0.5);
        src(cr, '#f2d08a'); cr.fill();
        ell(cr, x - rr * 0.35, y - rr * 0.4, rr * 0.3, rr * 0.18, -0.6); src(cr, '#fff', 0.45); cr.fill();
    };
    port(35, 48, 7.5, 3); port(19.5, 45, 3, 1); port(49, 44, 2.6, 1);
    ell(cr, 27, 36, 4, 2, -0.6); src(cr, '#fff6d0', 0.5); cr.fill();
}

function bubbler(cr, W) {
    cr.scale(W / 100, W / 100);
    // clear airline tube curving into the sand
    cr.setLineWidth(4); src(cr, '#d8f0f0', 0.35);
    cr.moveTo(18, 33); cr.curveTo(8, 34, 6, 40, 0, 46); cr.stroke();
    cr.setLineWidth(1); src(cr, '#ffffff', 0.5);
    cr.moveTo(18, 32); cr.curveTo(8, 33, 6, 39, 0, 45); cr.stroke();
    // brass fitting
    rrect(cr, 14, 30, 7, 6, 1); src(cr, '#c08a3a'); cr.fill();
    // the stone: speckles, pores, highlight
    rrect(cr, 18, 22, 66, 22, 9); cr.setSource(lg(0, 22, 0, 44, [[0, '#a7b5bd'], [1, '#55626b']])); cr.fill();
    cr.save(); rrect(cr, 18, 22, 66, 22, 9); cr.clip();
    for (let i = 0; i < 120; i++) {
        const x = 19 + (i * 37 % 64), y = 23 + (i * 13 % 20);
        circ(cr, x, y, 0.3 + (i % 3) * 0.25); src(cr, i % 2 ? '#2f3a40' : '#e6eef2', 0.5);
        cr.fill();
    }
    cr.restore();
    ell(cr, 38, 26, 14, 2, 0); src(cr, '#fff', 0.25); cr.fill();
    // tiny bubbles clinging to the top
    for (const [x, y, rr] of [[40, 21, 1.4], [52, 20.5, 1.8], [61, 21.2, 1.1], [46, 19.5, 0.9], [56, 18, 0.8]]) {
        circ(cr, x, y, rr); src(cr, '#fff', 0.6); cr.setLineWidth(0.4); cr.stroke();
    }
}

function snail(cr, W) {
    cr.scale(W / 60, W / 60);
    // foot + head
    cr.moveTo(3, 34); cr.curveTo(8, 27, 40, 26, 48, 24); cr.curveTo(56, 22, 59, 28, 58, 33);
    cr.curveTo(57, 35, 10, 36, 3, 34); cr.closePath();
    cr.setSource(lg(0, 24, 0, 36, [[0, '#c9b08a'], [1, '#8a7356']])); cr.fill();
    src(cr, '#6a5640', 0.5);
    for (let x = 10; x < 52; x += 4) circ(cr, x, 31 + Math.sin(x) * 1.2, 0.5);
    cr.fill();
    // eye stalks + lower tentacles
    src(cr, '#a8906c'); cr.setLineWidth(1.6); cr.setLineCap(Cairo.LineCap.ROUND);
    cr.moveTo(50, 25); cr.curveTo(51, 18, 52, 12, 53, 7);
    cr.moveTo(53, 25); cr.curveTo(55, 19, 57, 14, 59, 10);
    cr.moveTo(56, 31); cr.lineTo(60, 33); cr.stroke();
    for (const [x, y] of [[53, 6.5], [59, 9.5]]) {
        circ(cr, x, y, 1.6); src(cr, '#111'); cr.fill();
        circ(cr, x - 0.5, y - 0.6, 0.5); src(cr, '#fff'); cr.fill();
    }
    // shell: gradient, growth stripes, spiral, lip
    circ(cr, 24, 18, 15); cr.setSource(rg(24, 18, 15, [[0, '#f3c27a'], [0.7, '#c0702c'], [1, '#6e3a14']])); cr.fill();
    cr.save(); circ(cr, 24, 18, 15); cr.clip();
    src(cr, '#5a2e10', 0.35); cr.setLineWidth(1.2);
    for (let a = 0; a < TAU; a += TAU / 14) { cr.moveTo(24, 18); cr.lineTo(24 + 16 * Math.cos(a), 18 + 16 * Math.sin(a)); }
    cr.stroke(); cr.restore();
    cr.setLineWidth(1.4); src(cr, '#4a240c');
    for (let a = 0; a <= 4 * Math.PI; a += 0.15) {
        const rr = 14 * (1 - a / (4.4 * Math.PI)), x = 25 + rr * Math.cos(a), y = 18 + rr * Math.sin(a);
        if (a === 0) cr.moveTo(x, y); else cr.lineTo(x, y);
    }
    cr.stroke();
    ell(cr, 18, 9, 5, 2, -0.5); src(cr, '#fff', 0.35); cr.fill();
}

function sand(cr, W, H, r, s) {
    const edge = x => H * 0.08 + 6 * s * Math.sin(x * 0.004 / s) + 4 * s * Math.sin(x * 0.011 / s + 1);
    cr.moveTo(0, H);
    for (let x = 0; x <= W + 20; x += 20) cr.lineTo(x, edge(x));
    cr.lineTo(W, H); cr.closePath();
    cr.setSource(lg(0, 0, 0, H, [[0, '#e9d7a8'], [0.4, '#d4b985'], [1, '#a98a58']])); cr.fill();
    cr.setLineWidth(3 * s); src(cr, '#fff6dc', 0.5);
    cr.moveTo(0, edge(0)); for (let x = 0; x <= W + 20; x += 20) cr.lineTo(x, edge(x));
    cr.stroke();
    // ripples
    src(cr, '#8a6e44', 0.18); cr.setLineWidth(1.5 * s);
    for (let i = 0; i < W / 60; i++) {
        const x = r() * W, y = H * (0.2 + r() * 0.75), l = (20 + r() * 40) * s;
        cr.moveTo(x, y); cr.curveTo(x + l * 0.3, y - 3 * s, x + l * 0.7, y - 3 * s, x + l, y);
    }
    cr.stroke();
    // grain, batched per colour
    for (const [c, a] of [['#7a5e36', 0.35], ['#fff8e0', 0.45], ['#b08a50', 0.4]]) {
        for (let i = 0; i < W * H / 900; i++) {
            const x = r() * W, y = edge(x) + r() * H;
            cr.rectangle(x, y, 1.6 * s, 1.6 * s);
        }
        src(cr, c, a); cr.fill();
    }
    // pebbles, bigger toward the front
    const pal = ['#8c8f94', '#6d6560', '#b0603a', '#d8cfc0', '#4f5a66', '#9a7a52', '#c9a27a', '#5f7f6a', '#3a3a40'];
    for (let i = 0; i < W / 9; i++) {
        const yn = r() ** 0.7, x = r() * W, y = H * (0.15 + yn * 0.8), rx = (2 + 9 * yn) * s * (0.6 + r() * 0.8), ry = rx * (0.55 + r() * 0.2);
        ell(cr, x + rx * 0.2, y + ry * 0.4, rx, ry * 0.8); src(cr, '#3a2a14', 0.25); cr.fill();
        ell(cr, x, y, rx, ry, (r() - 0.5) * 0.5); src(cr, pal[i % pal.length]); cr.fill();
        ell(cr, x - rx * 0.3, y - ry * 0.4, rx * 0.4, ry * 0.25); src(cr, '#fff', 0.3); cr.fill();
    }
    // starfish
    for (const [fx, fy, rr, c] of [[0.27, 0.55, 26, '#e0703a'], [0.9, 0.75, 20, '#d24a5a'], [0.52, 0.85, 16, '#e8a03a']]) {
        const x = fx * W, y = fy * H, R = rr * s, rot = r() * TAU;
        cr.moveTo(x + R * Math.cos(rot), y + R * Math.sin(rot));
        for (let k = 1; k <= 10; k++) {
            const a = rot + k * Math.PI / 5, d = k % 2 ? R * 0.42 : R;
            cr.lineTo(x + d * Math.cos(a), y + d * Math.sin(a));
        }
        cr.closePath(); src(cr, c); cr.fill();
        src(cr, '#fff3d0', 0.7);
        for (let k = 0; k < 5; k++) for (let j = 1; j < 4; j++) {
            const a = rot + k * TAU / 5;
            circ(cr, x + R * 0.22 * j * Math.cos(a), y + R * 0.22 * j * Math.sin(a), 1.1 * s);
        }
        cr.fill();
    }
    // scallop shells
    for (const [fx, fy, rr] of [[0.08, 0.6, 18], [0.63, 0.5, 14], [0.78, 0.88, 20]]) {
        const x = fx * W, y = fy * H, R = rr * s;
        cr.moveTo(x, y + R * 0.2); cr.arc(x, y + R * 0.2, R, Math.PI * 1.1, Math.PI * 1.9); cr.closePath();
        cr.setSource(lg(0, y - R, 0, y, [[0, '#fbe6d8'], [1, '#d8a890']])); cr.fill();
        src(cr, '#a0705a', 0.7); cr.setLineWidth(1 * s);
        for (let k = 1; k < 8; k++) { const a = Math.PI * (1.1 + k * 0.1); cr.moveTo(x, y + R * 0.2); cr.lineTo(x + R * Math.cos(a), y + R * 0.2 + R * Math.sin(a)); }
        cr.stroke();
        cr.rectangle(x - R * 0.25, y + R * 0.1, R * 0.5, R * 0.25); src(cr, '#d8a890'); cr.fill();
    }
    // conch
    {
        const x = 0.45 * W, y = 0.45 * H, R = 16 * s;
        cr.moveTo(x - R, y); cr.curveTo(x - R, y - R * 0.9, x + R * 0.8, y - R * 0.8, x + R * 1.3, y);
        cr.curveTo(x + R * 0.6, y + R * 0.5, x - R * 0.5, y + R * 0.5, x - R, y); cr.closePath();
        cr.setSource(lg(0, y - R, 0, y + R * 0.5, [[0, '#fff0e0'], [1, '#e0a080']])); cr.fill();
        src(cr, '#9a5a40', 0.6); cr.setLineWidth(1 * s);
        for (let k = 0; k < 4; k++) { const xx = x - R * 0.7 + k * R * 0.45; cr.moveTo(xx, y - R * 0.5); cr.lineTo(xx + R * 0.2, y + R * 0.3); }
        cr.stroke();
    }
}

// ---------- plants: chain of segments, each rotating about its base ----------
function leaf(cr, x, y, ang, len, wid, c1, c2) {
    cr.save(); cr.translate(x, y); cr.rotate(ang);
    cr.moveTo(0, 0); cr.curveTo(len * 0.3, -wid, len * 0.7, -wid, len, 0); cr.curveTo(len * 0.7, wid, len * 0.3, wid, 0, 0);
    cr.setSource(lg(0, -wid, 0, wid, [[0, c2], [1, c1]])); cr.fill();
    src(cr, c1, 0.8); cr.setLineWidth(Math.max(0.6, wid * 0.12)); cr.moveTo(0, 0); cr.lineTo(len * 0.9, 0); cr.stroke();
    cr.restore();
}

function segDraw(kind, c1, c2, wid, f0, f1, last, i) {
    return (cr, W, H) => {
        const cx = W / 2;
        if (kind === 'blade' || kind === 'kelp') {
            const w0 = wid * (1 - 0.7 * f0), w1 = last ? 0 : wid * (1 - 0.7 * f1), L = [], R = [];
            for (let k = 0; k <= 12; k++) {
                const f = k / 12, hw = (w0 + (w1 - w0) * (last ? Math.sqrt(f) : f)) / 2;
                const rf = kind === 'kelp' ? Math.sin(f * Math.PI * 7) * hw * 0.12 : 0;
                L.push([cx - hw - rf, H * (1 - f)]); R.push([cx + hw + rf, H * (1 - f)]);
            }
            poly(cr, [...L, ...R.reverse()]);
            cr.setSource(lg(cx - w0 / 2, 0, cx + w0 / 2, 0, [[0, c1], [0.45, c2], [1, c1]])); cr.fill();
            src(cr, c1, 0.7); cr.setLineWidth(Math.max(1, w0 * 0.07));
            cr.moveTo(cx, H); cr.lineTo(cx, last ? H * 0.15 : 0); cr.stroke();
            return;
        }
        const ll = wid * (1 - 0.4 * f0);
        src(cr, c1); cr.setLineWidth(Math.max(1.5, wid * 0.12)); cr.moveTo(cx, H); cr.lineTo(cx, last ? H * 0.3 : 0); cr.stroke();
        const side = i % 2 ? 1 : -1;
        if (kind === 'leafy') {
            leaf(cr, cx, H * 0.75, side > 0 ? -0.6 : -Math.PI + 0.6, ll * 0.95, ll * 0.32, c1, c2);
            leaf(cr, cx, H * 0.3, side > 0 ? -Math.PI + 0.7 : -0.7, ll * 0.85, ll * 0.3, c1, c2);
            if (last) leaf(cr, cx, H * 0.32, -Math.PI / 2, H * 0.3, ll * 0.2, c1, c2);
        } else if (kind === 'fern') {
            for (let k = 0; k < 6; k++) {
                const y = H * (0.95 - k * 0.15), l = ll * (last ? 0.9 - k * 0.12 : 0.85);
                leaf(cr, cx, y, -0.5, l, l * 0.14, c1, c2); leaf(cr, cx, y - H * 0.05, -Math.PI + 0.5, l, l * 0.14, c1, c2);
            }
        } else { // round leaves on short stalks (pennywort-ish)
            for (const [y, sd] of [[H * 0.7, side], [H * 0.25, -side]]) {
                const lx = cx + sd * ll * 0.5, ly = y - ll * 0.15, rr = ll * 0.38;
                cr.setLineWidth(Math.max(1, wid * 0.06)); src(cr, c1); cr.moveTo(cx, y); cr.lineTo(lx, ly); cr.stroke();
                circ(cr, lx, ly, rr); cr.setSource(rg(lx, ly, rr, [[0, c2], [1, c1]])); cr.fill();
                src(cr, c1, 0.6); cr.setLineWidth(Math.max(0.6, rr * 0.06));
                for (let a = 0; a < TAU; a += TAU / 8) { cr.moveTo(lx, ly); cr.lineTo(lx + rr * 0.85 * Math.cos(a), ly + rr * 0.85 * Math.sin(a)); }
                cr.stroke();
            }
        }
    };
}

const PLANTS = [
    ['blade', '#2f7d3a', '#6fc05a'], ['kelp', '#6b6a1e', '#b0b04a'], ['leafy', '#2e6e3a', '#7cc864'],
    ['fern', '#245f30', '#5fae4a'], ['round', '#3a7a30', '#8fd06a'], ['blade', '#8a2f2a', '#d0604a'],
    ['leafy', '#7a3a5a', '#c0708a'],
];

export class Scene {
    constructor(root, w, h) {
        const s = h / 1440, sandTop = h * 0.83, r = rng(20261011);
        this._s = s;
        this._r = r;
        this._anims = [];
        this._box = new Clutter.Actor({width: w, height: h, clip_to_allocation: true});
        root.add_child(this._box);
        this._box.connect('destroy', () => { this._box = null; });
        const box = this._box, A = f => this._anims.push(f);

        art(box, 0, 0, w, h, (cr, W, H) => water(cr, W, H, rng(7)));
        for (const [dir, seed] of [[1, 3], [-1, 5]]) {
            const a = art(box, -0.15 * w, 0, w * 1.3, h * 0.12, (cr, W, H) => surface(cr, W, H, rng(seed)));
            A(t => { a.translation_x = dir * 0.08 * w * Math.sin(t * 0.04 + seed); a.opacity = 170 + 80 * Math.sin(t * 0.3 + seed); });
        }
        for (let i = 0; i < 6; i++) {
            const rw = 0.3 * h, a = art(box, (0.05 + i * 0.17 + r() * 0.08) * w - rw / 2, -0.03 * h, rw, h * 0.9, ray);
            const base = (r() - 0.3) * 18, ph = r() * TAU;
            a.set_pivot_point(0.5, 0);
            A(t => { a.rotation_angle_z = base + 2.5 * Math.sin(t * 0.07 + ph); a.opacity = 150 + 100 * Math.sin(t * 0.13 + ph); });
        }
        for (let i = 0; i < 22; i++) {
            const [kind, c1, c2] = PLANTS[(r() * PLANTS.length) | 0];
            this._plant(box, r() * w, sandTop + 0.03 * h, kind, (110 + r() * 240) * s, (20 + r() * 16) * s, c1, c2, 1.5, 0.35, 0.42);
        }

        this.fishLayers = [0, 1].map(() => new Clutter.Actor({width: w, height: h}));
        box.add_child(this.fishLayers[0]);

        // mid decor; x by screen fraction, size by height so it fits any aspect
        const place = (fx, bw, bh, sink, draw) => art(box, fx * w - bw / 2, sandTop + sink * h - bh, bw, bh, (cr, W, H) => draw(cr, W, H, rng(Math.round(fx * 1000))));
        place(0.12, 0.3 * h, 0.39 * h, 0.035, castle);
        place(0.4, 0.5 * h, 0.3 * h, 0.06, ship);
        const cw = 0.14 * h, cx0 = 0.6 * w - cw / 2, cy = sandTop + 0.03 * h - cw * 80 / 120;
        place(0.6, cw, cw * 80 / 120, 0.03, chestBody);
        const lid = art(box, cx0, cy + cw * 28 / 120 - cw * 32 / 120, cw, cw * 32 / 120, chestLid);
        lid.set_pivot_point(95 / 120, 1);
        A(t => {
            const o = Math.max(0, Math.sin(t * 0.25)) ** 4;
            lid.rotation_angle_z = -16 * o;
            if (o > 0.6 && Math.random() < o * 0.15) this._emit(cx0 + cw * (0.2 + Math.random() * 0.5), cy + cw * 0.2, 0.25 + Math.random() * 0.4);
        });
        const dw = 0.14 * h, dh = dw * 140 / 70, dv = place(0.85, dw, dh, 0.035, diver);
        dv.set_pivot_point(0.5, 1);
        A(t => { dv.rotation_angle_z = 1.2 * Math.sin(t * 0.4); });
        const bw = 0.07 * h, bx = 0.71 * w, by = sandTop + 0.01 * h - bw * 0.3;
        place(0.71, bw, bw * 0.5, 0.01, bubbler);

        // pooled bubbles, all drawn once at size B and scaled
        const B = Math.ceil(30 * s), bl = new Clutter.Actor();
        box.add_child(bl);
        this._B = B;
        this._top = h * 0.03;
        this._pool = Array.from({length: 90}, () => {
            const a = art(bl, 0, 0, B, B, (cr, W) => {
                const c = W / 2, rr = c - 1;
                circ(cr, c, c, rr); cr.setSource(rg(c, c, rr, [[0, '#ffffff', 0.02], [0.8, '#dff8ff', 0.12], [1, '#ffffff', 0.5]])); cr.fill();
                circ(cr, c, c, rr); src(cr, '#fff', 0.6); cr.setLineWidth(1); cr.stroke();
                ell(cr, c - rr * 0.35, c - rr * 0.4, rr * 0.3, rr * 0.18, -0.7); src(cr, '#fff', 0.9); cr.fill();
            });
            a.set_pivot_point(0.5, 0.5);
            a.hide();
            return {a, live: false, x: 0, y: 0, v: 0, vmax: 0, amp: 0, f: 0, ph: 0};
        });
        let next = 0, burst = 0, dnext = 2;
        const hx = 0.85 * w + dw * (34 / 70 - 0.5), hy = sandTop + 0.035 * h - dh + dw * 28 / 70;
        A((t, dt) => {
            if ((next -= dt) <= 0) {
                this._emit(bx + (Math.random() - 0.5) * bw * 0.6, by, 0.3 + Math.random() * (burst ? 0.5 : 0.9));
                if (burst > 0) { burst--; next = 0.03 + Math.random() * 0.05; } else {
                    next = Math.random() < 0.12 ? 0.8 + Math.random() * 2 : 0.08 + Math.random() * 0.3;
                    if (Math.random() < 0.015) burst = 12 + (Math.random() * 25 | 0);
                }
            }
            if ((dnext -= dt) <= 0) {
                for (let k = 0; k < 3; k++) this._emit(hx, hy - k * 10 * s, 0.4 + Math.random() * 0.5);
                dnext = 3 + Math.random() * 5;
            }
            for (const b of this._pool) {
                if (!b.live) continue;
                b.v = Math.min(b.vmax, b.v + 25 * s * dt);
                b.y -= b.v * dt;
                b.a.set_position(b.x + b.amp * Math.sin(t * b.f + b.ph), b.y);
                if (b.y < this._top) { b.live = false; b.a.hide(); }
            }
        });

        art(box, 0, sandTop - 0.01 * h, w, h - sandTop + 0.01 * h, (cr, W, H) => sand(cr, W, H, rng(11), s));

        // snail creeping along the sand
        const sw = 60 * s, sn = art(box, 0, sandTop + 0.07 * h - sw * 0.6, sw, sw * 0.6, snail);
        sn.set_pivot_point(0.5, 0.5);
        let sx = 0.3 * w, sd = 1;
        A((t, dt) => {
            sx += sd * 4 * s * dt * (0.5 + 0.5 * Math.sin(t * 0.6) ** 2);
            if (sx > w - sw || sx < 0) { sd = -sd; sn.scale_x = sd; }
            sn.x = sx;
        });

        for (let i = 0; i < 14; i++) {
            const [kind, c1, c2] = PLANTS[(r() * PLANTS.length) | 0];
            this._plant(box, r() * w, sandTop + (0.05 + r() * 0.04) * h, kind, (90 + r() * 150) * s, (18 + r() * 14) * s, c1, c2, 2.5, 0.5);
        }

        box.add_child(this.fishLayers[1]);

        // foreground: tall plants framing the edges, grass tufts along the bottom
        for (const fx of [0.005, 0.03, 0.055, 0.945, 0.97, 0.995]) {
            for (let k = 0; k < 2; k++) {
                const [kind, c1, c2] = PLANTS[(r() * PLANTS.length) | 0];
                this._plant(box, fx * w + (r() - 0.5) * 40 * s, h * 1.02, kind, (0.3 + r() * 0.4) * h, (34 + r() * 18) * s, c1, c2, 3.5, 0.55);
            }
        }
        for (const fx of [0.2, 0.33, 0.5, 0.66, 0.8]) {
            for (let k = 0; k < 5; k++)
                this._plant(box, fx * w + (r() - 0.5) * 50 * s, h * 1.02, 'blade', (60 + r() * 90) * s, (8 + r() * 6) * s, '#2a6a30', '#5cb04a', 4, 0.7);
        }

        this.swimBounds = {x: 0, y: h * 0.06, w, h: sandTop + 0.04 * h - h * 0.06};
    }

    _plant(parent, x, base, kind, len, wid, c1, c2, amp, sp, haze = 0) {
        if (haze) [c1, c2] = [tint(c1, haze), tint(c2, haze)];
        const segs = Math.max(2, Math.min(6, Math.round(len / (60 * this._s)))), sh = len / segs, ov = 2;
        const stem = kind !== 'blade' && kind !== 'kelp', sw = stem ? wid * 2.2 + 6 : wid * 1.5 + 6;
        const ph = this._r() * TAU, lean = (this._r() - 0.5) * 8, k = 0.8 + this._r() * 0.4;
        let par = parent, px = x - sw / 2, py = base - sh;
        for (let i = 0; i < segs; i++) {
            // St.DrawingArea doesn't paint children, so each joint is a plain actor holding art + next joint
            const a = new Clutter.Actor({x: px, y: py, width: Math.ceil(sw), height: Math.ceil(sh + ov)});
            par.add_child(a);
            art(a, 0, 0, sw, sh + ov, segDraw(kind, c1, c2, wid, i / segs, (i + 1) / segs, i === segs - 1, i));
            a.set_pivot_point(0.5, 1);
            const l = i ? 0 : lean;
            this._anims.push(t => { a.rotation_angle_z = l + amp * Math.sin(t * sp * k + ph - i * 0.7); });
            par = a; px = 0; py = -sh;
        }
    }

    _emit(x, y, size) {
        const b = this._pool.find(p => !p.live);
        if (!b) return;
        const s = this._s;
        Object.assign(b, {live: true, x: x - this._B / 2, y: y - this._B / 2, v: (20 + 20 * size) * s, vmax: (70 + 90 * size) * s,
            amp: (2 + 5 * Math.random()) * s, f: 2 + 3 * Math.random(), ph: Math.random() * TAU});
        b.a.set_scale(size, size);
        b.a.set_position(b.x, b.y);
        b.a.show();
    }

    tick(dt, t) {
        if (!this._box) return;
        for (const f of this._anims) f(t, dt);
    }

    destroy() {
        this._box?.destroy();
        this._box = this._anims = this._pool = this.fishLayers = null;
    }
}
