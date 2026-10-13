// Fish food (no gi: check.js runs it with stub actors). A click drops a pinch that sinks, lands on the
// sand or briefly on a rock top, and fades; fish and critters read `pieces` and call bite()/kick().
import { pt } from './steer.js';

export const POOL = 24;
const CRUMBS = 9;          // per layer
const TAU = Math.PI * 2;
const FAR = 0.7;           // far layer: smaller and sinks slower
const FADE = 20;           // s a settled piece lies on the sand before it is gone
const SINK = 16;           // ref px/s a small flake sinks lying flat (calibration knob)
const KINDS = 4;           // sheet rows: red, green, yellow-brown flake, pellet (3)
// Pointer gestures on bare desktop (the pointer is polled, so these are timed `down` edges).
export const HOLD_S = 0.35, POUR_S = 0.12;  // holding the button this long pours one piece every POUR_S

export const hand = () => ({ down: false, on: false, held: 0, pour: 0, n: 0 });
// One tick of the pointer P: 'drop' (a click), 'pour' (held), or null.
export function gesture(g, P, dt) {
    const edge = P.down && !g.down && P.over;
    g.down = P.down;
    if (edge) {
        g.on = true; g.held = g.pour = 0;
        return 'drop';
    }
    if (!P.down || !P.over) { g.on = false; return null; }
    if (!g.on || (g.held += dt) < HOLD_S || (g.pour -= dt) > 0) return null;
    g.pour += POUR_S;
    g.n++;
    return 'pour';
}

export class Food {
    // tank: {fishLayers, swimBounds, ground(layer, x, z), tops: [{x0, x1, y}]}
    constructor(ctx, tank, rand = Math.random) {
        this._tank = tank;
        this._rand = rand;
        this._s = ctx.h / ctx.ref;
        this.any = false;
        this.farShare = 0.4;  // chance a piece falls in the far layer; scene.js sets it to the far fish share
        this.pieces = [];
        this._a = [];      // piece actors, parallel to pieces
        this._crumbs = [[], []];
        this._kx = new Float64Array(POOL);  // kick velocity, decays
        this._seq = 0;
        const e = ctx.images.food, ok = e && e.n === KINDS * 8 && e.cols === 8;
        if (e && !ok) console.warn('fishtank: food art has the wrong shape, pieces are invisible');
        this._sh = ok ? ctx.sheet('food') : null;
        const an = this._sh && pt(e.anchor) ? e.anchor : [e?.w / 2, e?.h / 2];
        this._an = an;
        for (let i = 0; i < POOL; i++) {
            // z: depth in the sand band (0 back .. 1 front); perch: s left on a rock top; top: which one
            this.pieces.push({ i, live: false, layer: 1, kind: 0, size: 1, x: 0, y: 0, vy: 0, phi: 0, w: 0, bites: 0,
                settled: false, fade: 0, claims: 0, age: 0, born: 0, z: 0, perch: 0, top: -1, slid: false });
            const a = this._sh?.make() ?? null;
            if (a) {
                a.visible = false;
                a.set_pivot_point(an[0] / e.w, an[1] / e.h);
                tank.fishLayers[1].add_child(a);
            }
            this._a.push({ a, col: -1, op: -1, rot: NaN, k: NaN, q: NaN, tx: NaN, ty: NaN, gone: 0 });
        }
        const cm = ctx.images.crumb;
        if (cm) for (const l of [0, 1]) for (let i = 0; i < CRUMBS; i++) {
            const a = ctx.sheet('crumb').make();
            a.visible = false;
            a.set_pivot_point(0.5, 0.5);
            a.set_scale(this._s, this._s);
            tank.fishLayers[l].add_child(a);
            this._crumbs[l].push({ a, live: false, x: 0, y: 0, vx: 0, vy: 0, t: 0, w: cm.w, h: cm.h });
        }
    }

    // n pieces around (x, y); when the pool is full the oldest settled piece is reused. A click below the
    // water (on the sand) drops nothing: food starts in the water and sinks.
    drop(x, y, n) {
        const r = this._rand, b = this._tank.swimBounds, T = this._tank;
        if (y > b.y + b.h) return;
        for (let j = 0; j < n; j++) {
            let p = null;
            for (const q of this.pieces) if (!q.live) { p = q; break; }
            if (!p) {
                for (const q of this.pieces) if (q.settled && (!p || q.born < p.born)) p = q;
                if (!p) return;
            }
            const i = p.i, kind = Math.min(KINDS - 1, r() * KINDS | 0);
            p.x = x + (r() - 0.5) * 80;
            p.y = Math.min(b.y + b.h, Math.max(b.y * 0.5, y + (r() - 0.5) * 30));
            p.z = r();
            p.layer = r() < this.farShare && p.y < T.ground(0, p.x, p.z) ? 0 : 1;  // never starts below its floor
            Object.assign(p, { live: true, kind, size: 0.6 + r() * 0.6, bites: 0, settled: false, fade: 0, age: 0, claims: 0,
                born: this._seq++, vy: 0, phi: r() * TAU, w: kind === 3 ? 0.8 : 2.5 + 2 * r(), perch: 0, top: -1, slid: false });
            this._kx[i] = 0;
            const s = this._a[i];
            if (s.a) {
                const par = T.fishLayers[p.layer];
                if (s.a.get_parent() !== par) { s.a.get_parent()?.remove_child(s.a); par.add_child(s.a); }
                s.col = s.op = -1;
                s.rot = s.k = s.q = s.tx = s.ty = NaN;
                s.gone = 0;
                s.a.visible = true;
                this._sh.show(s.a, kind * 8);
            }
        }
    }

    // A real bite: the piece shrinks (smoothly, see tick) and a crumb or two flies; the third bite
    // finishes it, and it shrinks away to nothing at the mouth instead of blinking out.
    bite(p) {
        if (!p.live) return false;
        p.bites++;
        p.size *= 0.7;
        for (let j = 0; j < 2; j++) this._crumb(p);
        if (p.bites >= 3) { p.live = false; this._a[p.i].gone = 1; }
        return true;
    }

    // Nudge a piece sideways (a missed snap, a fish swimming through it); a settled one hops up a little.
    kick(p, vx) {
        if (!p.live) return;
        this._kx[p.i] += vx;
        if (p.settled) { p.settled = false; p.y -= 4; p.fade = 0; p.slid ||= p.perch > 0; p.perch = 0; }
    }

    _kill(p) {
        p.live = false;
        const s = this._a[p.i];
        if (s.a) s.a.visible = false;
    }

    // Unseen for gap s: landed food is gone by now, sinking food has sunk (the next tick lands it). A piece
    // on a rock top keeps its fade for the sand.
    skip(gap) {
        for (const p of this.pieces) {
            if (!p.live) continue;
            if (!p.settled) p.y += p.vy * Math.min(gap, 20);
            else if (!p.perch) p.fade += gap;
        }
    }

    _crumb(p) {
        let c = null;
        for (const q of this._crumbs[p.layer]) if (!q.live) { c = q; break; }
        if (!c) return;
        const r = this._rand;
        c.live = true; c.x = p.x; c.y = p.y; c.vx = (r() - 0.5) * 40; c.vy = -10 * r(); c.t = 0.8;
        c.a.visible = true;
    }

    tick(dt) {
        const r = this._rand, s = this._s, T = this._tank;
        let any = false;
        for (let i = 0; i < POOL; i++) {
            const p = this.pieces[i], st = this._a[i];
            if (!p.live) {  // eaten: shrinks to nothing over 0.15 s, then hides
                if (st.gone > 0 && st.a && (st.gone -= dt / 0.15) > 0) st.a.set_scale(st.k * st.gone, st.k * st.q * st.gone);
                else if (st.gone > 0) { st.gone = 0; if (st.a) st.a.visible = false; }
                continue;
            }
            any = true;
            p.age += dt;
            const far = p.layer ? 1 : FAR, v = far * s;  // speeds are ref px/s
            let col = 0, rot = 0;
            this._kx[i] *= Math.exp(-3 * dt);
            if (!p.settled) {
                p.phi += p.w * dt;
                const c = Math.cos(p.phi), pellet = p.kind === 3, y = p.y;
                p.vy = (pellet ? 40 : (SINK + 20 * p.size) * (0.55 + 0.45 * c * c)) * v;  // edge-on it slips down faster
                p.x += ((pellet ? 0 : 14 * Math.sin(p.phi)) * v + this._kx[i]) * dt;
                p.y += p.vy * dt;
                p.size *= 1 - 0.01 * dt;  // soaks and softens
                if (r() < dt / 4) this._crumb(p);
                col = pellet ? Math.floor(p.age * 2) % 8 : Math.floor((((p.phi / TAU) % 1) + 1) % 1 * 8);
                rot = pellet ? 0 : Math.round(12 * Math.sin(p.phi));
                const floor = T.ground(p.layer, p.x, p.z);
                if (p.layer && !p.slid) for (let j = 0; j < T.tops.length; j++) {  // near pieces can land on a rock or the chest
                    const o = T.tops[j];
                    if (p.x >= o.x0 && p.x <= o.x1 && y < o.y && p.y >= o.y && o.y < floor) {
                        p.y = o.y; p.settled = true; p.perch = 2.5 + 3 * r(); p.top = j;
                        break;
                    }
                }
                if (!p.settled && p.y >= floor) {  // sinks in a touch
                    p.y = floor + 2; p.settled = true;
                    if (pellet && p.layer) T.puff(p.x, p.y);
                }
            } else if (p.perch > 0) {  // on a rock: rests, then slides off the nearer edge and falls on
                const o = T.tops[p.top];
                if ((p.perch -= dt) <= 0) {
                    p.perch = 0.01;  // still on top while it slides
                    p.x += (p.x - o.x0 < o.x1 - p.x ? -30 : 30) * s * dt;
                    if (p.x < o.x0 || p.x > o.x1) { p.settled = false; p.slid = true; p.perch = 0; }
                }
            } else {
                p.x += this._kx[i] * dt;
                p.fade += dt;
                if (p.fade >= FADE) { this._kill(p); continue; }
            }
            if (!st.a) continue;
            const a = st.a, f = p.kind * 8 + col;
            if (f !== st.col) this._sh.show(a, st.col = f);
            // closer = a little bigger; eases toward the size so a bite shrinks it smoothly, not in a jump
            const kk = p.size * far * s * (0.9 + 0.2 * Math.min(1.5, p.z));
            const ke = Number.isNaN(st.k) ? kk : st.k + (kk - st.k) * Math.min(1, dt * 12);
            let k = Math.round(ke * 50) / 50;
            if (k === st.k) k = Math.round(kk * 50) / 50;  // bug fix: a small gap rounded back to the old size and stuck there
            const q = p.settled && !p.perch ? 0.85 : 1;  // pressed into the sand
            if (k !== st.k || q !== st.q) a.set_scale(st.k = k, k * (st.q = q));
            if (rot !== st.rot) a.set_rotation_angle(2, st.rot = rot);  // 2 = Clutter.RotateAxis.Z_AXIS
            const op = p.settled ? Math.round(255 * Math.min(1, (FADE - p.fade) / 5)) : 255;
            if (op !== st.op) a._c.set_opacity(st.op = op);
            const tx = Math.round((p.x - this._an[0]) * 4) / 4, ty = Math.round((p.y - this._an[1]) * 4) / 4;
            if (tx !== st.tx || ty !== st.ty) a.set_translation(st.tx = tx, st.ty = ty, 0);
        }
        for (const l of this._crumbs) for (const c of l) {
            if (!c.live) continue;
            if ((c.t -= dt) <= 0) { c.live = false; c.a.visible = false; continue; }
            c.vy = Math.min(15, c.vy + 40 * dt);
            c.x += c.vx * dt;
            c.y += c.vy * dt;
            c.vx *= 1 - 2 * dt;
            c.a._c.set_opacity(Math.round(255 * c.t / 0.8));
            c.a.set_translation(Math.round(c.x - c.w / 2), Math.round(c.y - c.h / 2), 0);
        }
        this.any = any;
    }
}
