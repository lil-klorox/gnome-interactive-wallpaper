// Fish food (no gi imports: check.js runs it with stub actors). A click drops a pinch of flakes and
// pellets; each falls in its own depth layer, rocking and flipping as a flat flake does (the sheet's
// tumble frame is locked to the rock), softens and sheds crumbs, and lands on the floor at its own
// depth in that layer's sand band (so leftovers scatter over the sand instead of lining up), or on a
// rock/chest top for a few seconds before it slides off. Then it sinks in a touch and fades.
// Fish (fish.js) and shrimp/hermit (critters.js) read `pieces`, claim them and call bite()/kick().
// A pellet landing on the front sand kicks up a little puff (tank.puff, if the tank has one).
export const POOL = 24;
const CRUMBS = 9;          // per layer
const TAU = Math.PI * 2;
const FAR = 0.7;           // far layer: smaller and sinks slower
const FADE = 45;           // s a settled piece lies on the sand before it is gone
const SINK = 16;           // ref px/s a small flake sinks lying flat (calibration knob)
const KINDS = 4;           // sheet rows: red, green, yellow-brown flake, pellet (3)
// Pointer gestures on bare desktop (the pointer is polled, so these are timed `down` edges).
export const TAP_S = 0.4, TAP_PX = 20;  // a second click this soon and this close taps the glass
export const HOLD_S = 0.35, POUR_S = 0.12;  // holding the button this long pours one piece every POUR_S

export const hand = () => ({ down: false, on: false, t: 0, last: -9, lx: 0, ly: 0, held: 0, pour: 0, n: 0 });
// One tick of the pointer P: 'drop' (a click), 'tap' (a double click), 'pour' (held), or null.
export function gesture(g, P, dt) {
    g.t += dt;
    const edge = P.down && !g.down && P.over;
    g.down = P.down;
    if (edge) {
        const tap = g.t - g.last < TAP_S && Math.hypot(P.x - g.lx, P.y - g.ly) < TAP_PX;
        g.last = tap ? -9 : g.t; g.lx = P.x; g.ly = P.y; g.on = true; g.held = g.pour = 0;
        return tap ? 'tap' : 'drop';
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
        this._h = ctx.h;
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
        const an = this._sh && Array.isArray(e.anchor) && e.anchor.every(Number.isFinite) ? e.anchor : [e?.w / 2, e?.h / 2];
        this._an = an;
        for (let i = 0; i < POOL; i++) {
            // z: depth in the sand band (0 back .. 1 front); perch: s left on a rock top; top: which one
            this.pieces.push({ live: false, layer: 1, kind: 0, size: 1, x: 0, y: 0, vy: 0, phi: 0, w: 0, bites: 0,
                settled: false, fade: 0, claims: 0, age: 0, born: 0, z: 0, perch: 0, top: -1, slid: false });
            const a = this._sh?.make() ?? null;
            if (a) {
                a.visible = false;
                a.set_pivot_point(an[0] / e.w, an[1] / e.h);
                tank.fishLayers[1].add_child(a);
            }
            this._a.push({ a, col: -1, op: -1, rot: NaN, k: NaN, q: NaN, tx: NaN, ty: NaN });
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

    // n pieces around (x, y); when the pool is full the oldest settled piece is reused. A click on the
    // front sand drops them right there, in the near layer.
    drop(x, y, n) {
        const r = this._rand, b = this._tank.swimBounds, T = this._tank;
        for (let j = 0; j < n; j++) {
            let p = null;
            for (const q of this.pieces) if (!q.live) { p = q; break; }
            if (!p) {
                for (const q of this.pieces) if (q.settled && (!p || q.born < p.born)) p = q;
                if (!p) return;
            }
            const i = this.pieces.indexOf(p), kind = Math.min(KINDS - 1, r() * KINDS | 0);
            p.x = x + (r() - 0.5) * 80;
            p.y = Math.max(b.y * 0.5, y + (r() - 0.5) * 30);
            const y0 = T.ground(1, p.x, 0), y1 = T.ground(1, p.x, 1);
            const onSand = p.y > y0;
            p.layer = onSand || r() >= this.farShare ? 1 : 0;
            p.z = onSand ? Math.min((this._h - 4 - y0) / Math.max(1, y1 - y0), (p.y - y0) / Math.max(1, y1 - y0)) : r();
            Object.assign(p, { live: true, kind, size: 0.6 + r() * 0.6, bites: 0, settled: false, fade: 0, age: 0, claims: 0,
                born: this._seq++, vy: 0, phi: r() * TAU, w: kind === 3 ? 0.8 : 2.5 + 2 * r(), perch: 0, top: -1, slid: false });
            this._kx[i] = 0;
            const s = this._a[i];
            if (s.a) {
                const par = T.fishLayers[p.layer];
                if (s.a.get_parent() !== par) { s.a.get_parent()?.remove_child(s.a); par.add_child(s.a); }
                s.col = s.op = -1;
                s.rot = s.k = s.q = s.tx = s.ty = NaN;
                s.a.visible = true;
                this._sh.show(s.a, kind * 8);
            }
        }
    }

    // A real bite: piece shrinks, crumbs fly, it jumps; the third bite finishes it.
    bite(k) {
        const p = typeof k === 'number' ? this.pieces[k] : k;
        if (!p?.live) return false;
        p.bites++;
        p.size *= 0.75;
        for (let j = 0; j < 3; j++) this._crumb(p);
        this.kick(p, (this._rand() - 0.5) * 24);
        if (p.bites >= 3) this._kill(p);
        return true;
    }

    // Nudge a piece sideways (a missed snap, a fish swimming through it); a settled one hops up a little.
    kick(k, vx) {
        const p = typeof k === 'number' ? this.pieces[k] : k;
        if (!p?.live) return;
        this._kx[this.pieces.indexOf(p)] += vx;
        if (p.settled) { p.settled = false; p.y -= 4; p.fade = 0; p.slid ||= p.perch > 0; p.perch = 0; }
    }

    _kill(p) {
        p.live = false;
        const s = this._a[this.pieces.indexOf(p)];
        if (s.a) s.a.visible = false;
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
            const p = this.pieces[i];
            if (!p.live) continue;
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
                    if (pellet && p.layer) T.puff?.(p.x, p.y);
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
            const st = this._a[i];
            if (!st.a) continue;
            const a = st.a, f = p.kind * 8 + col;
            if (f !== st.col) this._sh.show(a, st.col = f);
            const k = Math.round(p.size * far * s * (0.9 + 0.2 * Math.min(1.5, p.z)) * 50) / 50;  // closer = a little bigger
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
