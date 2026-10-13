// Self-check for sand.js (rake, rings, settling, save format): run by the root check.js.
import * as S from './sand.js';

const ok = (c, msg) => { if (!c) throw new Error('FAIL garden: ' + msg); };
const near = (a, b, e = 0.02) => Math.abs(a - b) <= e;
const W = 800, H = 400;
const field = () => S.makeField(W, H);
const all = F => ({x0: 0, y0: 0, x1: F.cw, y1: F.ch});
const at = (F, x, y) => F.H[Math.floor(y / S.CELL) * F.cw + Math.floor(x / S.CELL)];
const rake = (F, R, pts, k = 1, clip = all(F), bb = S.box()) => {
    const st = S.makeStroke();
    for (let i = 0; i < pts.length; i += 2)
        S.rakeTo(F, R, st, pts[i], pts[i + 1], k, clip, bb);
    return bb;
};

// Rake profile: 5 teeth 14 px apart, grooves -1 at the teeth, ridges between, flat outside.
const R = S.profile(5);
ok(R.half === 32 && near(R.P[R.J], -1) && near(R.P[R.J + 14], -1) && near(R.P[R.J + 7], 0.35), 'profile teeth and ridges');

// A stroke left to right stamps grooves across it, nothing before its start, and clips.
let F = field(), bb = rake(F, R, [100, 201, 300, 201]);
ok(near(at(F, 200, 201), -1, 0.1) && near(at(F, 200, 215), -1, 0.1) && at(F, 200, 208) > 0.2, 'stroke grooves');
ok(at(F, 90, 201) === 0 && at(F, 200, 260) === 0, 'nothing outside the rake');
ok(bb.x0 <= 50 && bb.x1 >= 150 && bb.y0 <= 84 && bb.y1 >= 117, 'dirty box covers the stroke');
// Overwrite: a vertical stroke through it rewrites the crossing with its own profile.
rake(F, R, [201, 100, 201, 300]);
ok(near(at(F, 201, 201), -1, 0.1) && at(F, 208, 201) > 0.2 && at(F, 208, 201) === at(F, 208, 250), 'newer stroke wins');
// Clip: a stroke into a clipped area writes nothing there.
F = field();
rake(F, R, [100, 100, 700, 100], 1, {x0: 0, y0: 0, x1: 150, y1: F.ch});
ok(at(F, 290, 100) !== 0 && at(F, 310, 100) === 0, 'stroke clipped');

// Shading: light from the top-left, so a slope rising to the right is lit, flat sand is see-through.
const buf = new Uint8Array(4 * 4 * 4);
F = field();
F.H[1] = 0.5;
S.shade(F, buf, 0, 0, 4, 1);
ok(buf[0] > buf[2] && buf[0] > 90, 'left of a bump (rising right) is lit');
ok(buf[8] < 60 && buf[11] > 90, 'right of a bump is shadow');
ok(buf[15] === 0, 'flat is clear');

// Settling: 5 % left after the chosen hours, steps compound to the same, 0 hours never fades.
ok(near(S.settleFactor(6 * 3600, 6), 0.05, 1e-9), 'settle hours');
ok(near(S.settleFactor(300, 6) ** 72, 0.05, 1e-9), 'settle steps compound');
ok(S.settleFactor(1e6, 0) === 1, 'settle 0 = never');
F = field();
F.H.fill(1);
S.scale(F, 2, 2, 4, 3, 0.5);
ok(F.H[2 * F.cw + 2] === 0.5 && F.H[2 * F.cw + 4] === 1 && F.H[3 * F.cw + 2] === 1, 'scale only the rect');
// Background lines: grooves every 14 px, and settling goes back to them, not to flat.
F = field();
S.lines(F);
ok(near(at(F, 10, 7), -0.35, 0.05) && near(at(F, 10, 21), -0.35, 0.05) && at(F, 10, 14) > 0.05, 'background lines');
F.H[3 * F.cw + 5] = -1;
S.scale(F, 0, 0, F.cw, F.ch, 0);
ok(F.H[3 * F.cw + 5] === F.B[3], 'settles back to the lines');

// Rings: troughs 14, 28, 42 px out (depth 1, 0.7, 0.4), rounded corners, the window and far sand untouched.
ok(near(S.ringAt(14), -1) && near(S.ringAt(28), -0.7) && near(S.ringAt(42), -0.4) && S.ringAt(21) > 0, 'ring profile');
F = field();
const win = {x: 300, y: 150, w: 200, h: 100};
S.ring(F, win, all(F), S.box());
ok(near(at(F, 300 - 15, 200), -1, 0.15) && near(at(F, 300 - 29, 200), -0.7, 0.15) && near(at(F, 500 + 43, 200), -0.4, 0.15), 'ring sides');
ok(near(at(F, 400, 150 - 15), -1, 0.15) && at(F, 400, 200) === 0 && at(F, 300 - 60, 200) === 0, 'ring inside/outside');
const c = 14 / Math.SQRT2;
ok(near(at(F, 300 - c, 150 - c), -1, 0.3) && at(F, 300 - 14, 150 - 14) > -0.5, 'ring corners are round');
F = field();
S.ring(F, win, all(F), S.box(), true);  // oval: trough 14 px past the ellipse, both at the side and on the diagonal
ok(near(at(F, 300 - 14, 200), -1, 0.15) && near(at(F, 400, 150 - 14), -1, 0.15) && at(F, 400, 200) === 0, 'oval ring sides');
const ex = 400 - 100 * Math.SQRT1_2 - 14 / Math.sqrt(5), ey = 200 - 50 * Math.SQRT1_2 - 28 / Math.sqrt(5);  // 14 px along the normal at 45°
ok(at(F, 300 - 14, 150 - 14) > -0.5 && near(at(F, ex, ey), -1, 0.35), 'oval ring follows the ellipse');

// Furrow: cells the dragged window left go to -0.5, its new spot is untouched.
F = field();
S.trough(F, {x: 100, y: 100, w: 100, h: 100}, {x: 150, y: 100, w: 100, h: 100}, all(F), S.box());
ok(at(F, 120, 150) === -0.5 && at(F, 160, 150) === 0, 'furrow');

// Save format: delta round trip, caps keep the newest points, slots validate, the store stays small.
const q = [10, 20, 13, 18, 13, 25];
ok(JSON.stringify(S.decode(JSON.parse(JSON.stringify(S.encode(q))))) === JSON.stringify(q), 'encode round trip');
const big = n => Array.from({length: 2 * n}, (_, i) => i);
let ks = [{born: 0, q: big(9)}, {born: 1, q: big(1500)}, {born: 2, q: big(1500)}, {born: 3, q: big(400)}];
S.cap(ks);
ok(ks.length === 3 && ks[0].born === 1 && ks[0].q.length === 2 * 600 && ks[0].q.at(-1) === 2999, 'cap drops oldest, cuts the crossing stroke');
const slot = S.writeSlot([{born: 900, q}], [[5, 6, 17]], 1000, 500, 1000);
const back = S.readSlot(JSON.parse(JSON.stringify(slot)));
ok(back.w === 1000 && back.strokes[0].born === 900 && back.strokes[0].q.join() === q.join() && back.leaves[0][2] === 17, 'slot round trip');
ok(S.readSlot({w: 0, h: 1, saved: 1}) === null && S.readSlot({...slot, w: 1}) === null && S.readSlot(null) === null, 'bad slot');
ok(S.readSlot({...slot, strokes: [{t: 1, d: [10, 10, 1e5, 0]}], leaves: [[1e5, 5, 17]]}).strokes.length === 0 &&
    S.readSlot({...slot, leaves: [[1e5, 5, 17]]}).leaves.length === 0, 'off-screen points dropped');
// Replay budget: a file full of screen-wide zigzags keeps only the newest MAX_REPLAY px of path.
const zig = {t: 1, d: S.encode(Array.from({length: 2 * S.MAX_POINTS}, (_, i) => (i % 4 < 2 ? 0 : 499)))};
const kept = S.readSlot({...slot, strokes: [zig, zig, zig]}).strokes;
ok(kept.reduce((n, k) => n + k.q.length, 0) < 3 * 2 * S.MAX_POINTS, 'replay budget');
ok(Object.keys(S.fit({mons: {0: slot, 1: {strokes: [{d: 5}]}}}).mons).join() === '0', 'fit drops a malformed slot');
ok(S.readSlot({...slot, strokes: [{t: 1, d: [1, 'x', 2, 3]}, {t: -1, d: [1, 2, 3, 4]}, ...slot.strokes]}).strokes.length === 1, 'bad strokes skipped');
// Worst case: 5 monitors, each with MAX_POINTS of big jumps -> 4 slots, under the 64 KB the engine allows.
const jumpy = () => [{born: 0, q: Array.from({length: 2 * S.MAX_POINTS}, (_, i) => (i % 4 < 2 ? 0 : 999))}];
const mons = {};
for (let i = 0; i < 5; i++)
    mons[i] = S.writeSlot(jumpy(), [], 3440, 1440, 10);
const fitted = S.fit({mons, junk: 1});
ok(Object.keys(fitted.mons).join() === '0,1,2,3' && JSON.stringify(fitted).length <= S.STORE_LIMIT, 'store fits 64 KB');
ok(JSON.stringify(S.fit({mons: {0: {leaves: Array(30000).fill([1, 2, 3])}}})).length <= S.STORE_LIMIT, 'fit drops a slot oversized by leaves');

// Resample: a stroke saved on a 1000x500 screen replays at the same spot on a 2000x1000 one.
F = S.makeField(2000, 1000);
const moved = S.resample([100 / S.Q, 48 / S.Q, 148 / S.Q, 48 / S.Q], 2000 / 1000, 1000 / 500);
rake(F, R, moved.map(v => v * S.Q));
ok(near(at(F, 250, 96), -1, 0.1) && at(F, 125, 48) === 0, 'resampled stroke lands scaled');
