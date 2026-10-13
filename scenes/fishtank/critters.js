// Tank critters besides the fish (no gi imports: check.js runs them with stub actors): jellyfish,
// garden eels, a moray in the wreck, seahorses, cherry shrimp, a hermit crab, and the rare visitors.
// Each is {tick(dt, t)}; missing or misshapen art skips that critter (logged once). Positions are
// screen px in the fish layers, ref px in the scaled mid/far layers.
import { FAST, SEE } from './brain.js';
import { heading, spacing, shear } from '../../bend.js';
import { pt } from './steer.js';

const TAU = Math.PI * 2;
const WALL = 120;          // px from the side glass where a jelly starts turning back
const SHELL = 3600;        // s a moulted shrimp shell takes to fade
const FRY = 600;           // s the hatched fry swirl by their plant
export const night = W => !W.lightsOn;
// Food a critter holds, or null once eaten or reused for a newer piece (the pool recycles them).
const held = o => o.food?.live && o.food.born === o.born ? o.food : null;
const ease = (v, goal, dt, tau) => v + (goal - v) * (1 - Math.exp(-dt / tau));
const deg = r => r * 180 / Math.PI;
// Seeded random numbers (same seed, same sequence).
export const rng = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;

// One rare event a day. The store keeps `tank` = {day, event, at, t, x, log}: day = local days since
// 1970, event = today's pick ('' = none can happen here), at = minute of the day it is due, t = epoch ms
// it happened (0 = not yet), x = where (the critter's own units), log = [{day: 'YYYY-MM-DD', kind}] newest last (the settings window lists it).
export const EVENTS = ['fry', 'moult', 'eggs', 'yawn'];
export const LOG = 7;
export const dayOf = ms => Math.floor((ms - new Date(ms).getTimezoneOffset() * 6e4) / 864e5);
const isoDay = day => new Date(day * 864e5).toISOString().slice(0, 10);
// Today's pick, seeded by the day so every monitor agrees; due between 8:00 and 20:00.
export function plan(day, kinds, log = []) {
    const r = rng(day % 2147483646 + 1);
    r(); r(); r();  // a plain LCG's first draws barely differ for neighbouring seeds
    return { day, event: kinds.length ? kinds[r() * kinds.length | 0] : '', at: 480 + (r() * 720 | 0), t: 0, x: 0, log: log.slice(-LOG) };
}
// The stored record, cleaned (store data is untrusted), or null.
export function readTank(v) {
    if (!(v && Number.isInteger(v.day) && (v.event === '' || EVENTS.includes(v.event)) && Number.isInteger(v.at) &&
        Number.isFinite(v.t) && Number.isFinite(v.x) && Array.isArray(v.log))) return null;
    const log = v.log.filter(e => typeof e?.day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(e.day) && EVENTS.includes(e.kind)).slice(-LOG).map(e => ({ day: e.day, kind: e.kind }));
    return { day: v.day, event: v.event, at: v.at, t: v.t, x: v.x, log };
}

// One sheet actor, every GI call cached and skipped when unchanged. (x, y) puts the sheet's point
// `key` there; scale and rotation turn about it. Opacity goes on the sheet's child, never the box.
class Sprite {
    constructor(sh, parent, key = 'anchor', op = 255) {
        this.sh = sh;
        this.a = sh.make();
        parent.add_child(this.a);
        this.p = pt(sh[key]) ? sh[key] : [sh.w / 2, sh.h / 2];
        this.a.set_pivot_point(this.p[0] / sh.w, this.p[1] / sh.h);
        this.op = -1;
        this.fade(op);
        this.on = true;
        this.x = this.y = this.sx = this.sy = this.r = NaN;
    }

    show(on) {
        if (on !== this.on) (this.on = on) ? this.a.show() : this.a.hide();
    }

    fade(op) {
        op = Math.round(op);
        if (op !== this.op) this.a._c.set_opacity(this.op = op);
    }

    put(f, x, y, sx, sy = Math.abs(sx), r = 0) {
        this.show(true);
        this.sh.show(this.a, f);
        x = Math.round((x - this.p[0]) * 4) / 4;
        y = Math.round((y - this.p[1]) * 4) / 4;
        if (x !== this.x || y !== this.y) this.a.set_translation(this.x = x, this.y = y, 0);
        sx = Math.round(sx * 100) / 100;
        sy = Math.round(sy * 100) / 100;
        if (sx !== this.sx || sy !== this.sy) this.a.set_scale(this.sx = sx, this.sy = sy);
        r = Math.round(r * 10) / 10;
        if (r !== this.r) this.a.set_rotation_angle(2, this.r = r);  // 2 = Clutter.RotateAxis.Z_AXIS
    }
}

export class Critters {
    // tank: {fishLayers, swimBounds, mid, far, spots, perches, plants, ship, food, chain()}
    constructor(ctx, tank, S, env, rand = Math.random) {
        const miss = [];
        const c = this._c = { ctx, tank, env, rand, s: ctx.h / ctx.ref, W: ctx.world, n: 0, pool: [],
            // sheet by name if its manifest entry has the expected shape and points, else null + noted
            sheet(name, n, cols, pts = []) {
                const e = ctx.images[name];
                if (e && e.n === n && e.cols === cols && pts.every(k => pt(e[k]))) return ctx.sheet(name);
                miss.push(name);
                return null;
            },
            // single image by name if it has points pts, else null + noted
            still(name, pts = []) {
                const e = ctx.images[name];
                if (e && pts.every(k => pt(e[k]))) return ctx.sheet(name);
                miss.push(name);
                return null;
            },
            // k is visible at (x, y) this tick: its own spot object (same one every tick, so a fish
            // visiting it keeps following that critter) goes into tank.spots with on = true
            spot(k, x, y) {
                if (!k.spot) c.pool.push(k.spot = { x: 0, y: 0, on: false });
                const o = k.spot;
                o.x = x;
                o.y = y;
                o.on = true;
                tank.spots[c.n++] = o;
            },
            // what makes a shy critter hide: a fast cursor or a dragged window close to (x, y) in screen px
            threat(x, y) {
                const P = c.W.pointer;
                if (P.over && P.speed > FAST / 2 && Math.hypot(P.x - x, P.y - y) < SEE) return true;
                for (const w of c.W.windows)
                    if (w.moving && Math.hypot(Math.max(w.x - x, 0, x - w.x - w.w), Math.max(w.y - y, 0, y - w.y - w.h)) < SEE) return true;
                return false;
            },
            act: () => env?.act ?? 1,
            events: {},  // kind -> fire(age s, x | null): the x it used, or null when it can't happen here
        };
        this.list = [];
        this.events = c.events;  // tank.js adds the snail's
        this._S = S;
        this._shown = -1;  // day whose event this tank has shown
        this._due = 2;
        const add = (on, make) => {
            if (!on) return;
            try {
                const k = make();
                if (k) this.list.push(k);
            } catch (e) {  // a broken critter never takes the tank with it
                console.warn(`fishtank: critter failed: ${e.message}`);
            }
        };
        if (tank.mid) {
            add(S.gardenEels, () => eels(c));
            add(S.moray && tank.ship, () => moray(c));
            add(S.shrimp, () => shrimp(c));
            add(S.hermit, () => hermit(c));
        }
        add(S.jelly, () => jellies(c));
        add(S.seahorse, () => seahorses(c));
        add(S.visitors, () => visitors(c));
        add(true, () => hatch(c));
        if (miss.length) console.warn(`fishtank: critters skipped (art missing or bad): ${[...new Set(miss)].join(', ')}`);
    }

    tick(dt, t) {
        const c = this._c;
        c.n = 0;
        for (const o of c.pool) o.on = false;
        for (const k of this.list) k.tick(dt, t);
        c.tank.spots.length = c.n;
        if ((this._due -= dt) <= 0) { this._due = 2; this._daily(); }
    }

    // Plans today's event on the first look of the day, fires it once it is due while someone is
    // around with the lights on, and shows what's left of one that already happened (other monitor,
    // or before a rebuild).
    _daily() {
        const c = this._c, store = c.ctx.store;
        if (this._S.events === false || !store) return;
        const now = Date.now(), day = dayOf(now), save = r => store.set({ ...store.get(), tank: r });
        let rec = readTank(store.get().tank);
        if (rec?.day !== day) save(rec = plan(day, EVENTS.filter(k => this.events[k]), rec?.log));
        const fire = this.events[rec.event];
        if (!fire || this._shown === day) return;
        if (rec.t) {
            this._shown = day;
            fire((now - rec.t) / 1000, rec.x);
            return;
        }
        const d = new Date(now);
        if (d.getHours() * 60 + d.getMinutes() < rec.at || night(c.W) || c.W.idle > 120) return;
        const x = fire(0, null);
        if (x === null || !Number.isFinite(x)) return;
        this._shown = day;
        rec.t = now; rec.x = x;
        rec.log = [...rec.log, { day: isoDay(day), kind: rec.event }].slice(-LOG);
        save(rec);
    }
}

// Jellyfish x2 (one far, one near): bell sheet pulses, tentacle strips (plant chains) lag behind.
function jellies(c) {
    const sh = c.sheet('jelly', 12, 12, ['anchor', 'mouth']);
    if (!sh) return null;
    const glowSh = c.ctx.images.glow ? c.ctx.sheet('glow') : null;
    const tents = ['jelly_tent_0', 'jelly_tent_1'].filter(n => pt(c.ctx.images[n]?.base));
    const b = c.tank.swimBounds, all = [];
    for (const layer of [0, 1]) {
        const far = layer ? 1 : 0.7, k = c.s * far * (0.9 + 0.2 * c.rand()), par = c.tank.fishLayers[layer];
        const op = layer ? 235 : 165;
        const glow = glowSh && new Sprite(glowSh, par, 'anchor', 0);
        const strips = [];
        for (let j = 0; j < 4 && tents.length; j++) {
            const segs = c.tank.chain(par, tents[j % tents.length], k, k);
            if (!segs) continue;
            for (const [i, a] of segs.entries()) (i + 1 < segs.length ? a.get_first_child() : a).set_opacity(op);  // texture actors only
            // past the root, segments lean by shear about their joint row (a rotation split wide strips there)
            const py = segs.map((a, i) => { if (!i) return 0; const y = a.pivot_point.y * a.height; a.set_pivot_point(0, 0); return y; });
            strips.push({ segs, py, a: new Float64Array(segs.length), dx: (j - 1.5) * 7, last: new Float64Array(segs.length).fill(NaN), sy: NaN, tx: NaN, ty: NaN });
        }
        const bell = new Sprite(sh, par, 'anchor', op);
        all.push({ layer, far, k, glow, strips, bell, g: 0, ph: c.rand(), f: -1, i: layer,
            x: b.x + b.w * (0.25 + 0.5 * c.rand()), y: b.y + b.h * (0.15 + 0.3 * c.rand()), vx: 0, vy: 0, px: 0 });
    }
    const [mx, my] = [sh.mouth[0] - sh.anchor[0], sh.mouth[1] - sh.anchor[1] - 4];
    return {
        all,
        tick(dt, t) {
            const nt = night(c.W);
            for (const J of all) {
                J.ph = (J.ph + dt / 2.5) % 1;
                const u = J.ph * 12, f = Math.floor(u);
                if (f === 1 && J.f !== 1) J.vy -= 18 * J.far * (1 + 0.35 * Math.sin(t * 0.05 + J.i * 2));  // the push; the slow term lets it rise and sink for minutes
                J.f = f;
                J.vy = (J.vy + 6 * J.far * dt) * (1 - 0.4 * dt);
                J.vx = (6 * Math.sin(t * 0.3 + J.i) + 5 * Math.sin(t * 0.017 + J.i * 3)) * J.far;
                // soft walls: a spring inside WALL px of each side turns it round before the glass
                const x0 = b.x + WALL, x1 = b.x + b.w - WALL, top = b.y + 40, low = b.y + 0.6 * b.h;
                J.px = J.x < x0 ? J.px + (x0 - J.x) * 0.3 * dt : J.x > x1 ? J.px + (x1 - J.x) * 0.3 * dt : J.px * (1 - 0.5 * dt);
                J.x = Math.min(b.x + b.w - 20, Math.max(b.x + 20, J.x + (J.vx + J.px) * dt));
                if (J.y < top + 60) J.vy += (top + 60 - J.y) * 0.3 * dt;
                else if (J.y > low - 60) J.vy += (low - 60 - J.y) * 0.3 * dt;
                J.y += J.vy * dt;
                if (J.y < top || J.y > low) { J.y = Math.min(low, Math.max(top, J.y)); J.vy = 0; }
                J.bell.put(f, J.x, J.y, J.k);
                const squeeze = f < 4 ? 1 - 0.15 * u / 4 : 0.85 + 0.15 * (u - 4) / 8;
                const lean = J.vx * 0.04;
                for (let j = 0; j < J.strips.length; j++) {
                    const S = J.strips[j];
                    const sway = lean + 0.15 * Math.sin(t * 0.7 + j);
                    for (let i = 0; i < S.segs.length; i++) S.a[i] = ease(S.a[i], (i ? S.a[i - 1] : 0) + sway, dt, i ? 0.6 : 0.35);
                    const root = S.segs[0];
                    const tx = Math.round((J.x + (mx + S.dx) * J.k) * 4) / 4, ty = Math.round((J.y + my * J.k) * 4) / 4;
                    if (tx !== S.tx || ty !== S.ty) root.set_translation(S.tx = tx, S.ty = ty, 0);
                    const sy = Math.round(squeeze * 100) / 100;
                    if (sy !== S.sy) root.set_scale(J.k, J.k * (S.sy = sy));
                    for (let i = 0; i < S.segs.length; i++) {
                        const r = Math.round(((i ? 0 : 180) + deg(S.a[i] - (i ? S.a[i - 1] : 0))) * 10) / 10;
                        if (r === S.last[i]) continue;
                        if (i) shear(S.segs[i], S.last[i] = r, S.py[i]);
                        else root.set_rotation_angle(2, S.last[i] = r);  // the root flips under the bell: a turn, not a lean
                    }
                }
                if (J.glow) {
                    J.g = ease(J.g, nt ? 60 + 20 * Math.sin(J.ph * TAU) : 0, dt, 1.5);
                    J.glow.fade(J.g * J.far);
                    J.glow.put(0, J.x, J.y + J.bell.sh.h * 0.35 * J.k, J.k * 1.6);
                }
                c.spot(J, J.x, J.y + 20 * J.k);
            }
        },
    };
}

// Garden eel colony in a sand gap: out swaying, ducks into the sand at a threat, then pokes out
// again one after another.
function eels(c) {
    const sh = c.sheet('garden_eel', 12, 12, ['base']);
    if (!sh) return null;
    const Wr = c.ctx.w / c.s, all = [];
    for (let i = 0; i < 5; i++) {
        const x = (0.645 + i * 0.012 + (c.rand() - 0.5) * 0.006) * Wr, y = 1278 + (i % 2) * 14 + c.rand() * 8;
        all.push({ i, x, y, mir: c.rand() < 0.5 ? -1 : 1, st: 'emerge', f: 0, wait: i * 0.4, e: 0, hold: 0, dir: 1,
            spr: new Sprite(sh, c.tank.mid, 'base') });
    }
    return {
        all,
        tick(dt, t) {
            const act = c.act();
            for (const E of all) {
                if ((E.st === 'out' || E.st === 'emerge') && c.threat(E.x * c.s, (E.y - 60) * c.s)) E.st = 'retract';
                if (E.st === 'out') {  // frames 8..11..8 at 4 fps, with the odd pause
                    if ((E.hold -= dt) <= 0) {
                        E.f += E.dir * dt * 4;
                        if (E.f >= 11 || E.f <= 8) { E.f = Math.min(11, Math.max(8, E.f)); E.dir = -E.dir; if (c.rand() < 0.4) E.hold = c.rand() * 1.5; }
                    }
                } else if (E.st === 'retract') {
                    E.f = Math.min(E.f, 7) - dt * 7 / 0.3;
                    if (E.f <= 0) { E.f = 0; E.st = 'wait'; E.wait = (3 + 5 * c.rand()) / act + E.i * 0.6; }
                } else if (E.st === 'wait') {
                    if ((E.wait -= dt) <= 0) { E.st = 'emerge'; E.wait = 0; E.e = 0; }
                } else if ((E.wait -= dt) <= 0) {  // emerge 0..7 over 2 s, easing out
                    E.e = Math.min(1, E.e + dt / 2);
                    E.f = 7 * (1 - (1 - E.e) ** 2);
                    if (E.e >= 1) { E.st = 'out'; E.f = 8; E.dir = 1; }
                }
                const out = E.f >= 7;
                E.spr.put(Math.round(E.f), E.x, E.y, E.mir, 1, out ? 3 * Math.sin(t * 0.5 + E.i) : 0);
                if (out) c.spot(E, E.x * c.s, (E.y - 80) * c.s);
            }
        },
    };
}

// Moray in the wreck: slides out of its hole (a random side each time), lingers there swaying and
// breathing, and slides back in; a threat sends it back in fast. The body is one smooth curve out of
// the hole: head, 10 overlapping segments and the tail sit along it by distance from the hole, and a
// clip at the hole's plane cuts them, so it slides in and out instead of popping or fading.
function moray(c) {
    const head = c.sheet('moray_head', 6, 6, ['anchor']), segSh = c.still('moray_seg'), tailSh = c.still('moray_tail', ['anchor']);
    if (!head || !segSh || !tailSh) return null;
    const mid = c.tank.mid, hx = c.tank.ship.hole.x / c.s, hy = c.tank.ship.hole.y / c.s, ship = c.tank.ship.actor;
    // the seg art fades 21 % of its width at each end; HL: snout ahead of the head's anchor
    const NSEG = 10, sp = spacing(segSh.w, 0.21), HL = head.w - head.anchor[0];
    const box = c.tank.group(mid);  // clipped at the hole plane, just above the ship
    if (ship) mid.set_child_above_sibling(box, ship);
    // later children paint on top: tail under the body, head on top
    const tail = new Sprite(tailSh, box), segs = [];
    for (let k = 0; k < NSEG; k++) segs.unshift(new Sprite(segSh, box));
    const H = new Sprite(head, box);
    // Lmax = how far it comes out: the tail root (L - 10 sp) stays at the hole, so it never floats free
    const M = { st: 'in', timer: 2 + 4 * c.rand(), face: 1, L: -HL, Lmax: 120, v: 30, lt: 0, ph: 0, yawn: 0, x: hx, y: hy, side: 0 };
    c.events.yawn = age => age > 120 ? null : (M.yawn = 2, M.st === 'in' && (M.timer = 0), hx);  // a big slow gape, next time it is out
    // the curve: rises gently from the hole with a wave that is still at the hole and grows along the body
    const Y = d => hy - 0.25 * d + 10 * Math.min(1, Math.max(0, d) / 60) * Math.sin(d / 40 + M.ph);
    const place = (s, f, d, back) => {  // back: the tail points back into the hole
        const dy = (Y(d + 1) - Y(d - 1)) * (back ? -1 : 1), dx = 2 * (back ? -M.face : M.face);
        s.put(f, hx + M.face * d, Y(d), dx >= 0 ? 1 : -1, 1, heading(dx, dy));
    };
    const side = () => {  // pick a side and how far out; the clip opens on that side of the hole
        M.face = c.rand() < 0.5 ? -1 : 1;
        M.Lmax = 20 + 150 * c.rand();
        if (M.side !== M.face) box.set_clip(M.face > 0 ? hx : hx - 400, hy - 220, 400, 320);
        M.side = M.face;
    };
    side();
    return {
        M,
        tick(dt, t) {
            const act = c.act(), L0 = M.L;
            if (M.st !== 'in' && M.st !== 'back' && c.threat(M.x * c.s, M.y * c.s)) { M.st = 'back'; M.v = 150; }  // a flinch
            if (M.st === 'in') {
                if ((M.timer -= dt * act) <= 0) { side(); M.st = 'out'; }
            } else if (M.st === 'out') {
                if ((M.L += 25 * act * dt) >= M.Lmax) { M.L = M.Lmax; M.st = 'linger'; M.lt = 0; M.timer = 6 + 14 * c.rand(); }
            } else if (M.st === 'linger') {  // eases in and out a little while it waves
                M.L = M.Lmax - 8 * (1 - Math.cos(0.7 * (M.lt += dt)));
                if ((M.timer -= dt) <= 0) { M.st = 'back'; M.v = Math.max(10, 30 * act); }
            } else if ((M.L -= M.v * dt) <= -HL) { M.L = -HL; M.st = 'in'; M.timer = 15 + 45 * c.rand(); }
            // the wave runs back along the body as it slides out, forward as it backs in
            M.ph += 2 * Math.sign(M.L - L0) * dt + (M.st === 'linger' ? 0.8 * dt : 0);
            const L = M.L;
            M.x = hx + M.face * L; M.y = Y(L);
            // a sprite is hidden only once it is wholly behind the hole plane (the clip cuts the rest)
            H.show(L > -HL);
            if (L > -HL) {
                const yawn = M.yawn > 0 && L > 0 && (M.yawn -= dt) > 0;
                place(H, yawn ? 5 : Math.min(5, Math.max(0, Math.round((M.st === 'linger' ? 3 : 1) + 2 * Math.sin(t * TAU * 0.5)))), L);
                if (L > 0) c.spot(M, M.x * c.s, M.y * c.s);
            }
            for (let k = 0; k <= NSEG; k++) {
                const s = k < NSEG ? segs[k] : tail, d = L - sp * Math.min(k + 0.5, NSEG);  // the tail tucks under the last segment
                if (k < NSEG ? d < -segSh.w / 2 : d < 0) s.show(false);
                else place(s, 0, d, k === NSEG);
            }
        },
    };
}

// Seahorses x2 hang on to plant stems, rest, then drift slowly to another perch.
function seahorses(c) {
    const sh = c.sheet('seahorse', 24, 12, ['anchor']);
    if (!sh) return null;
    const b = c.tank.swimBounds, par = c.tank.fishLayers[1];
    const perches = c.tank.perches.length ? c.tank.perches
        : [0.2, 0.5, 0.8].map(f => ({ x: b.x + b.w * f, y: b.y + b.h * 0.85 }));
    const all = [];
    for (let i = 0; i < 2; i++) {
        const k = c.s * (0.9 + 0.2 * c.rand()), pi = (i * 3 + (c.rand() * perches.length | 0)) % perches.length;
        const p = perches[pi];
        all.push({ i, k, pi, st: 'rest', timer: 5 + 20 * c.rand(), x: p.x, y: p.y - 40 * k, f: c.rand() * 12, mir: c.rand() < 0.5 ? -1 : 1, v: 15,
            scan: c.rand() * 0.5, food: null, spr: new Sprite(sh, par, 'anchor') });
    }
    const goal = (H, xy) => { const p = perches[H.pi]; xy[0] = p.x + 4 * H.k * H.mir; xy[1] = p.y - 40 * H.k; return xy; };
    const g = [0, 0];
    return {
        all,
        tick(dt, t) {
            const act = c.act();
            for (const H of all) {
                const bob = 3 * H.k * Math.sin(t * 0.8 + H.i * 2);
                if (H.st === 'snap') {  // a quick tilt at a passing piece of food, then back to resting
                    if ((H.snap -= dt) <= 0) { if (held(H)) c.tank.food.bite(H.food); H.food = null; H.st = 'rest'; }
                } else if (H.st === 'rest') {
                    H.f = (H.f + dt * 3) % 12;
                    if ((H.scan -= dt) <= 0 && c.tank.food?.any) {
                        H.scan = 0.5;
                        for (const q of c.tank.food.pieces)
                            if (q.live && q.layer && Math.hypot(q.x - H.x, q.y - H.y) < 60 * H.k) { H.food = q; H.born = q.born; H.st = 'snap'; H.snap = 0.2; H.mir = q.x >= H.x ? 1 : -1; break; }
                    }
                    const scared = c.threat(H.x, H.y);
                    if (scared || (H.timer -= dt * act) <= 0) {
                        H.v = scared ? 30 : 15;
                        if (perches.length > 1) H.pi = (H.pi + 1 + (c.rand() * (perches.length - 1) | 0)) % perches.length;
                        H.st = 'drift';
                    }
                } else {
                    H.f = (H.f + dt * 8) % 12;
                    goal(H, g);
                    const dx = g[0] - H.x, dy = g[1] - H.y, d = Math.hypot(dx, dy), step = H.v * act * c.s * dt;
                    if (Math.abs(dx) > 1) H.mir = dx > 0 ? 1 : -1;
                    if (d <= step) { H.x = g[0]; H.y = g[1]; H.st = 'rest'; H.timer = 20 + 40 * c.rand(); } else {
                        H.x += dx / d * step;
                        H.y = ease(H.y, g[1], dt, 1.2) + dy / d * step * 0.3;
                    }
                }
                H.spr.put((H.st === 'drift' ? 0 : 12) + Math.floor(H.f), H.x, H.y + bob, H.k * H.mir, H.k, H.st === 'snap' ? -15 * H.mir : 0);
                c.spot(H, H.x, H.y + bob);
            }
        },
    };
}

// The nearest food lying on the front sand (near layer, not on a rock top) within 300 screen px of
// ref x, at most dy ref px off row y and inside ref x0..x1; or null.
function settled(c, x, y, dy, x0 = -Infinity, x1 = Infinity) {
    let best = null, bd = 300;
    for (const p of c.tank.food?.pieces ?? []) {
        if (!p.live || !p.settled || !p.layer || p.perch > 0 || Math.abs(p.y / c.s - y) > dy || p.x / c.s < x0 || p.x / c.s > x1) continue;
        const d = Math.abs(p.x - x * c.s);
        if (d < bd) { bd = d; best = p; }
    }
    return best;
}

// Cherry shrimp x3 by the low plants: walk, pick at the sand, flick away from danger, eat food.
function shrimp(c) {
    const sh = c.sheet('shrimp', 12, 12, ['base']);
    if (!sh) return null;
    const Wr = c.ctx.w / c.s, homes = c.tank.plants.filter(p => p.y / c.s > 1200 && p.y / c.s < 1400).map(p => [p.x / c.s, p.y / c.s]);
    const all = [];
    for (let i = 0; i < 3; i++) {
        const [hx, hy] = homes.length ? homes[(i * 2) % homes.length] : [Wr * (0.25 + i * 0.25), 1300];
        const y0 = hy + 4 + 6 * c.rand();
        all.push({ hx, y0, y: y0, ty: y0, x: hx + (c.rand() - 0.5) * 80, tx: hx, st: 'pick', timer: c.rand() * 4, f: 6, dir: 1,
            food: null, chew: 0, e: 0, ex: 0, scan: c.rand() * 0.5, spr: new Sprite(sh, c.tank.mid, 'base') });
    }
    // daily moult: the first shrimp holds still 5 s, then walks out of its old shell, which fades over an hour
    const shellSh = c.ctx.images.shrimp_shell ? c.still('shrimp_shell', ['base']) : null;
    const shell = shellSh && new Sprite(shellSh, c.tank.mid, 'base', 0);
    shell?.show(false);
    let shellAge = -1;
    const drop = (x, y, dir, age) => { if (shell) { shellAge = age; shell.put(0, x, y, dir); } };
    c.events.moult = (age, x) => {
        if (age > SHELL) return null;
        const R = all[0];
        if (age < 5) { R.st = 'moult'; R.timer = 5 - age; R.food = null; R.ty = R.y; } else drop(x, R.y0, R.dir, age);
        return R.x;
    };
    return {
        all,
        tick(dt) {
            const act = c.act();
            if (shellAge >= 0 && (shellAge += dt) < SHELL) shell.fade(255 * (1 - shellAge / SHELL));
            else if (shellAge >= 0) { shellAge = -1; shell.show(false); }
            for (const R of all) {
                if (R.st !== 'escape' && R.st !== 'moult' && c.threat(R.x * c.s, R.y * c.s)) { R.st = 'escape'; R.e = 0; R.ex = R.x; R.food = null; }
                if ((R.scan -= dt) <= 0 && R.st !== 'escape' && R.st !== 'moult') {
                    R.scan = 0.5;
                    const p = settled(c, R.x, R.y0, 80);
                    if (p && p !== R.food) { R.food = p; R.born = p.born; R.tx = p.x / c.s; R.ty = p.y / c.s; R.st = 'walk'; }
                }
                if (R.food && !held(R)) { R.food = null; R.ty = R.y0; }
                R.y = ease(R.y, R.ty, dt, 1.5);  // walks up or down the sand to its food
                if (R.st === 'walk') {
                    const dx = R.tx - R.x, step = 8 * act * dt;
                    R.dir = dx >= 0 ? 1 : -1;
                    R.f = (R.f + dt * 6) % 6;
                    if (Math.abs(dx) <= step && Math.abs(R.ty - R.y) < 3) { R.x = R.tx; R.st = 'pick'; R.timer = (3 + 5 * c.rand()) / act; R.chew = 0.5; }
                    else if (Math.abs(dx) > step) R.x += R.dir * step;
                } else if (R.st === 'pick') {
                    R.f = 6 + (R.f - 6 + dt * 4 + 4) % 4;
                    if (R.food && (R.chew -= dt) <= 0) { R.chew = 1; c.tank.food.bite(R.food); }
                    if (!R.food && (R.timer -= dt) <= 0) { R.tx = R.hx + (c.rand() - 0.5) * 160; R.st = 'walk'; }
                } else if (R.st === 'moult') {
                    R.f = 6;
                    if ((R.timer -= dt) <= 0) { drop(R.x, R.y, R.dir, 0); R.tx = R.x + R.dir * 70; R.st = 'walk'; }
                } else {  // escape: tail flick, shoots backwards 40 px in 0.25 s
                    R.e = Math.min(1, R.e + dt / 0.25);
                    R.f = R.e < 0.5 ? 10 : 11;
                    R.x = R.ex - R.dir * 40 * (1 - (1 - R.e) ** 2);
                    if (R.e >= 1) { R.st = 'pick'; R.f = 6; R.timer = (3 + 5 * c.rand()) / act; }
                }
                R.spr.put(Math.floor(R.f), R.x, R.y, R.dir);
            }
        },
    };
}

// Hermit crab on the sand: wanders, stops, eats food it finds, pulls into its shell when startled.
function hermit(c) {
    const sh = c.sheet('hermit', 12, 12, ['base']);
    if (!sh) return null;
    const Wr = c.ctx.w / c.s, x0 = 0.58 * Wr, x1 = 0.84 * Wr;
    const R = { x: x0 + (x1 - x0) * c.rand(), y: 1334, dir: 1, st: 'stop', timer: 3, f: 1, food: null, scan: 0, spr: new Sprite(sh, c.tank.mid, 'base') };
    const OUT = [0, 10, 11, 1], HIDE = [11, 10, 0];
    return {
        R,
        tick(dt) {
            const act = c.act();
            if (R.st !== 'hide' && R.st !== 'out' && c.threat(R.x * c.s, R.y * c.s)) { R.st = 'hide'; R.timer = 0; R.food = null; }
            if ((R.scan -= dt) <= 0 && (R.st === 'walk' || R.st === 'stop')) {
                R.scan = 0.5;
                const p = settled(c, R.x, R.y, 30, x0, x1);
                if (p) { R.food = p; R.born = p.born; R.st = 'walk'; R.timer = 60; }
            }
            if (R.food && !held(R)) { R.food = null; if (R.st === 'eat') { R.st = 'stop'; R.timer = 3; } }
            if (R.st === 'walk') {
                const tx = R.food ? R.food.x / c.s : null;
                if (tx !== null) R.dir = tx >= R.x ? 1 : -1;
                R.x += R.dir * 6 * act * dt;
                if (R.x > x1 || R.x < x0) { R.x = Math.min(x1, Math.max(x0, R.x)); R.dir = -R.dir; }
                R.f = 1 + (R.f - 1 + dt * 5) % 6;
                if (tx !== null && Math.abs(tx - R.x) < 3) { R.st = 'eat'; R.timer = 3; c.tank.food.bite(R.food); }
                else if (tx === null && (R.timer -= dt) <= 0) { R.st = 'stop'; R.timer = (3 + 7 * c.rand()) / act; R.f = 1; }
            } else if (R.st === 'stop') {
                if ((R.timer -= dt) <= 0) { R.st = 'walk'; R.timer = 5 + 15 * c.rand(); if (c.rand() < 0.5) R.dir = -R.dir; }
            } else if (R.st === 'eat') {
                R.f = 7 + (R.f - 7 + dt * 3) % 3;
                if ((R.timer -= dt) <= 0) { R.st = 'stop'; R.timer = 1; }
            } else if (R.st === 'hide') {  // 11 -> 10 -> 0 over 0.3 s, 4 s inside
                R.timer += dt;
                R.f = HIDE[Math.min(2, Math.floor(R.timer / 0.1))];
                if (R.timer > 4.3) { R.st = 'out'; R.timer = 0; }
            } else {  // out: 0 -> 10 -> 11 -> 1
                R.timer += dt;
                R.f = OUT[Math.min(3, Math.floor(R.timer / 0.2))];
                if (R.timer > 0.8) { R.st = 'stop'; R.timer = 2; R.f = 1; }
            }
            R.spr.put(Math.floor(R.f), R.x, R.y, R.dir);
        },
    };
}

// Daily fry hatch: eggs on a leaf by a mid plant, then a swirl of baby fish by that plant for 10 min
// (fish come over to look: it is a spot).
function hatch(c) {
    const sh = c.ctx.images.fry ? c.sheet('fry', 8, 8, ['anchor']) : null;
    const plants = c.tank.plants.filter(p => p.y / c.s < 1400);  // mid plants (the front ones stand at 1470)
    if (!sh || !plants.length) return null;
    const eggSh = c.ctx.images.egg_cluster ? c.still('egg_cluster', ['base']) : null;
    const egg = eggSh && new Sprite(eggSh, c.tank.mid, 'base', 0), fry = [];
    egg?.show(false);
    for (let i = 0; i < 7; i++) { const s = new Sprite(sh, c.tank.fishLayers[1], 'anchor', 0); s.show(false); fry.push(s); }
    const F = { age: -1, x: 0, y: 0 };
    c.events.fry = age => {
        if (age > FRY) return null;
        const p = plants[c.rand() * plants.length | 0];
        F.age = age; F.x = p.x; F.y = p.y - 30 * c.s;
        egg?.put(0, p.x / c.s + 6, p.y / c.s - 2, 1);
        return p.x;
    };
    return {
        F,
        tick(dt, t) {
            if (F.age < 0) return;
            if ((F.age += dt) > FRY) { F.age = -1; egg?.show(false); for (const s of fry) s.show(false); return; }
            egg?.fade(255 * Math.min(1, Math.max(0, 1 - (F.age - 30) / 60)));  // empty eggs fade after the hatch
            const k = c.s, spread = Math.min(1, F.age / 20), op = 220 * Math.min(1, F.age / 5, (FRY - F.age) / 30);
            for (let i = 0; i < fry.length; i++) {
                const a = t * 0.9 + i * 0.9, ox = spread * (30 * Math.cos(a) + (i - 3) * 8) * k, oy = spread * (-20 - 25 * Math.sin(a * 1.3)) * k;
                fry[i].fade(op);
                fry[i].put(Math.floor(t * 12 + i * 2.3) % 8, F.x + ox, F.y + oy, Math.sin(a) < 0 ? k : -k, k);
            }
            c.spot(F, F.x, F.y - 20 * k);
        },
    };
}

// Rare visitors (off by default): a turtle through the far hills every 10-30 min, a shark shadow in
// the deep every 20-60 min, a puff of baby fish about once an hour. One timer each, one pass at a time.
function visitors(c) {
    const turtleSh = c.sheet('turtle', 12, 12, ['anchor']), frySh = c.sheet('fry', 8, 8, ['anchor']);
    const sharkSh = c.still('shark');
    const Wr = c.ctx.w / c.s, far = c.tank.far, b = c.tank.swimBounds, r = c.rand;
    const V = [];
    const add = (sh, par, op, n, min, max, speed, y, k) => {
        if (!sh || !par) return;
        const sprs = [];
        for (let i = 0; i < n; i++) { const s = new Sprite(sh, par, 'anchor', op); s.show(false); sprs.push(s); }
        V.push({ sprs, min, max, speed, y, k, span: par === c.tank.fishLayers[1] ? c.ctx.w : Wr, due: min + (max - min) * r(), on: false, x: 0, y0: 0, dir: 1 });
    };
    add(turtleSh, far[2], 170, 1, 600, 1800, 45, () => 760 + 140 * r(), 0.8);
    add(sharkSh, far[0], 90, 1, 1200, 3600, 60, () => 620 + 160 * r(), 1);
    add(frySh, c.tank.fishLayers[1], 220, 7, 3000, 4200, 50 * c.s, () => b.y + b.h * (0.2 + 0.5 * r()), c.s);
    if (!V.length) return null;
    return {
        V,
        tick(dt, t) {
            for (const v of V) {
                const span = v.span, m = v.sprs[0].sh.w * v.k;
                if (!v.on) {
                    if ((v.due -= dt) > 0) continue;
                    v.on = true; v.dir = r() < 0.5 ? 1 : -1; v.x = v.dir > 0 ? -m : span + m; v.y0 = v.y();
                }
                v.x += v.dir * v.speed * dt;
                if (v.x < -m - 10 || v.x > span + m + 10) {
                    v.on = false; v.due = v.min + (v.max - v.min) * r();
                    for (const s of v.sprs) s.show(false);
                    continue;
                }
                for (let i = 0; i < v.sprs.length; i++) {  // the fry swirl around their school's centre
                    const s = v.sprs[i];
                    const ox = i ? 22 * v.k * Math.cos(t * 1.3 + i * 0.9) + (i - 3) * 9 * v.k : 0, oy = i ? 10 * v.k * Math.sin(t * 1.7 + i * 1.3) : 0;
                    const n = s.sh.n, f = n > 1 ? Math.floor(t * (n > 8 ? 6 : 12) + i * 2.3) % n : 0;
                    s.put(f, v.x + ox, v.y0 + oy + 6 * Math.sin(t * 0.5), v.k * v.dir, v.k);
                }
            }
        },
    };
}
