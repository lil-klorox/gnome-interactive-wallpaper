// Tank scenery: Blender-rendered sprites from assets/scene (made by blender/scene_*.py), composed into
// parallax layers. Art is uploaded once; motion only moves, rotates or swaps the content of actors.
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import { night } from './brain.js';

const TAU = Math.PI * 2;
const SAND = 1150;       // ref row of the sand's back edge
const DRIFT = 22;        // parallax: how far (ref px) the nearest layer sways with the slow camera bob

// Props on the sand, by screen x fraction and the ref row their base sits on; sorted back to front.
const PROPS = [
    ['rock_b', 0.30, 1205, 0.9], ['castle', 0.12, 1222, 1], ['rock_c', 0.235, 1250, 0.8], ['ship', 0.43, 1215, 1],
    ['rock_a', 0.53, 1262, 0.9], ['chest', 0.6, 1290, 1], ['bubbler', 0.71, 1268, 1], ['diver', 0.86, 1255, 1],
    ['rock_d', 0.94, 1300, 1], ['rock_a', 0.03, 1335, 0.7],
];
const SPECIES = ['valli', 'valli', 'sword', 'sword', 'jfern', 'cabomba', 'ludwigia', 'anubias', 'anubias'];
const MIDPLANTS = [0.025, 0.2, 0.265, 0.345, 0.545, 0.67, 0.765, 0.905, 0.985];  // in the gaps between props

// Ref px are the art's own pixels (manifest ref = screen height it was drawn for).
export class Tank {
    constructor(ctx) {
        const { w, h } = ctx;
        this._ctx = ctx;
        this._m = ctx.images;
        this._anims = [];
        this._slow = [];  // slow sway: each runs every third tick (a third of the cost, steps stay far below a pixel)
        this._n = 0;
        this._pool = [];
        this._rays = 1;   // light ray strength, 0 at night
        this._notes = ctx.world.notifications;
        this._box = new Clutter.Actor({ width: w, height: h, clip_to_allocation: true });
        ctx.root.add_child(this._box);
        this.fishLayers = [0, 1].map(() => new Clutter.Actor({ width: w, height: h }));
        this.swimBounds = { x: 0, y: h * 0.06, w, h: h * 0.8 };
        try {
            this._build(w, h);
        } catch (e) {  // never take the shell down over scenery: keep whatever got built, plus the fish
            logError(e, 'fishtank: scenery failed, showing what loaded');
            if (!this._box.get_n_children())
                this._box.add_child(new St.Widget({ width: w, height: h,
                    style: 'background-gradient-direction: vertical; background-gradient-start: #1d5d6c; background-gradient-end: #031a26;' }));
            this.fishLayers.forEach(l => l.get_parent() || this._box.add_child(l));
        }
        // Tints over everything, fixed colours, only opacity changes: night/dark/idle dim, dawn/dusk warm.
        this._tint = [['#06102a', 0], ['#ff8a3c', 0]].map(([col, v]) => {
            const a = new St.Widget({ width: w, height: h, opacity: 0, style: `background-color: ${col};` });
            this._box.add_child(a);
            return { a, v, o: 0 };
        });
    }

    _build(w, h) {
        const REF = this._ctx.ref, s = h / REF, W = w / s;
        this._W = W;
        // one scaled container per depth; k = how much it moves with the camera bob
        const layer = k => {
            const a = new Clutter.Actor({scale_x: s, scale_y: s});
            this._box.add_child(a);
            let last = NaN;  // quarter-pixel steps, set only on change
            if (k) this._anims.push(t => {
                const x = Math.round(s * k * DRIFT * Math.sin(t * TAU / 47) * 4) / 4;
                if (x !== last) a.set_translation(last = x, 0, 0);
            });
            return a;
        };
        const sky = layer(0);
        this._add(sky, 'backdrop', 0, 0, {width: W, height: REF});
        this._tile(sky, 'surface', 0, -6, W, 8);
        for (let i = 0; i < 7; i++) {
            const a = this._add(sky, 'ray', (0.04 + i * 0.15 + 0.06 * Math.sin(i * 7.3)) * W, -60, {height: 1150 + 200 * Math.sin(i * 3.1)});
            if (!a) break;
            a.set_pivot_point(0.5, 0);
            const base = 8 + 6 * Math.sin(i * 5.1), ph = i * 1.7;
            let rot = NaN, op = -1;  // 0.1 degree steps; set only on change
            this._slow.push(t => {
                const r = Math.round((base + 2.5 * Math.sin(t * 0.06 + ph)) * 10) / 10, o = Math.round(this._rays * (110 + 90 * Math.sin(t * 0.11 + ph)));
                if (r !== rot) a.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, rot = r);
                if (o !== op) a.set_opacity(op = o);
            });
        }
        for (const [n, k] of [['far0', 0.2], ['far1', 0.35], ['far2', 0.5]]) {
            const m = this._m[n];
            if (m) this._tile(layer(k), n, -DRIFT, m.yb - m.h, W + 2 * DRIFT, 0);
        }
        const floor = layer(0.75);
        const sand = this._m.sand;
        if (sand) {
            this._tile(floor, 'sand', -DRIFT, REF - sand.h, W + 2 * DRIFT, 0);
            for (const [v, op] of [[7, 80], [-11, 55]]) {
                const c = this._tile(floor, 'caustics', -DRIFT, REF - this._m.caustics?.h, W + 2 * DRIFT, v);
                if (c) c.opacity = op;
            }
        }
        const r = this._rand = rng(20261011);
        for (let i = 0; i < 9; i++)
            this._plant(floor, r() * W, SAND + 15 + r() * 40, 0.55 + r() * 0.3, 1.2);
        this._box.add_child(this.fishLayers[0]);

        const mid = layer(0.75);
        const at = {};
        const items = [...PROPS];
        for (const fx of MIDPLANTS) items.push([null, fx + (r() - 0.5) * 0.02, SAND + 70 + r() * 140, 0.7 + r() * 0.35]);
        items.sort((a, b) => a[2] - b[2]);
        for (const [n, fx, y, k] of items) {
            if (!n) { this._plant(mid, fx * W, y, k, 1.8); continue; }
            const a = this._place(mid, n, fx * W, y, k);
            if (a) at[n] = a;
        }
        this._bubbles(mid, at);
        this._snail(mid, 0.3 * W, 0.56 * W, 1352);
        this._box.add_child(this.fishLayers[1]);

        const front = layer(1);
        for (const fx of [0.0, 0.025, 0.05, 0.95, 0.975, 1.0])
            this._plant(front, fx * W + (r() - 0.5) * 40, REF + 30, 1.0 + r() * 0.4, 2.6);
        for (let i = 0; i < 12; i++)
            this._plant(front, r() * W, REF + 10, 0.8 + r() * 0.5, 3, 'hair');
    }

    // Texture by sprite name; null when the manifest lacks it.
    _img(name) {
        return this._m[name] ? this._ctx.image(name).content : null;
    }

    _actor(parent, img, props) {
        const a = new Clutter.Actor({ content: img, ...props });
        a.set_content_scaling_filters(Clutter.ScalingFilter.LINEAR, Clutter.ScalingFilter.LINEAR);
        parent.add_child(a);
        return a;
    }

    _add(parent, name, x, y, props = {}) {
        const m = this._m[name], img = m && this._img(name);
        return img ? this._actor(parent, img, {x, y, width: m.w, height: m.h, ...props}) : null;
    }

    // Prop with its manifest 'base' point put at (x, y), scaled k.
    _place(parent, name, x, y, k = 1) {
        const m = this._m[name], b = m?.base;
        const a = b && this._add(parent, name, x - b[0], y - b[1]);
        if (a) {
            a.set_pivot_point(b[0] / m.w, b[1] / m.h);
            a.set_scale(k, k);
        }
        return a;
    }

    // Horizontally repeating strip: side-by-side copies sharing one texture (content repeat tiles at
    // the decoded size, not the ref size); vx = drift speed in ref px/s, which needs a moving holder.
    _tile(parent, name, x, y, width, vx) {
        const m = this._m[name], img = m && this._img(name);
        if (!img) return null;
        const a = vx ? new Clutter.Actor({ x, y }) : parent;
        if (vx) parent.add_child(a);
        const x0 = vx ? 0 : x, y0 = vx ? 0 : y, n = Math.ceil((width + (vx ? m.w : 0)) / m.w);
        for (let i = 0; i < n; i++)
            this._actor(a, img, { x: x0 + i * m.w, y: y0, width: m.w, height: m.h });
        if (vx) this._anims.push(t => { a.set_translation(-(((t * vx) % m.w + m.w) % m.w), 0, 0); });
        return a;
    }

    // Plant sprite cut into segments at its joints (j1, j2, ...), each rotating about the one below.
    _plant(parent, x, y, k, amp, species = null) {
        const r = this._rand;
        const name = `plant_${species ?? SPECIES[(r() * SPECIES.length) | 0]}_${(r() * 2) | 0}`;
        const m = this._m[name];
        if (!m?.base) return;
        const js = [m.base];
        for (let i = 1; m['j' + i]; i++) js.push(m['j' + i]);
        const mir = r() < 0.5 ? -k : k, ph = r() * TAU, sp = 0.35 + r() * 0.25, lean = (r() - 0.5) * 6;
        const img = this._img(name);
        if (!img) return;
        // Segment = pivot actor + the whole image clipped to its band, the next segment hanging off the
        // pivot (a clip cuts children too). The top segment has no children: one clipped image actor.
        let par = parent, prevTop = 0;
        for (let i = 0; i < js.length; i++) {
            const top = Math.round(i + 1 < js.length ? js[i + 1][1] : 0), bot = Math.round(i ? js[i][1] + 3 : m.h);
            const x0 = i ? 0 : x - m.base[0], y0 = i ? top - prevTop : y - m.base[1] + top;
            let a;
            if (i + 1 === js.length) {
                a = this._actor(par, img, { x: x0, y: y0 - top, width: m.w, height: m.h });
                if (top || bot < m.h) a.set_clip(0, top, m.w, bot - top);
                a.set_pivot_point(js[i][0] / m.w, js[i][1] / m.h);
            } else {
                a = new Clutter.Actor({ x: x0, y: y0, width: m.w, height: bot - top });
                par.add_child(a);
                this._actor(a, img, { y: -top, width: m.w, height: m.h }).set_clip(0, top, m.w, bot - top);
                a.set_pivot_point(js[i][0] / m.w, (js[i][1] - top) / (bot - top));
            }
            if (!i) a.set_scale(mir, k);
            const ai = amp * (0.6 + 0.3 * i), base = i ? 0 : lean;
            let last = NaN;  // 0.1 degree steps, set only on change (the bulk of the slow sway calls)
            this._slow.push(t => {
                const r = Math.round((base + ai * Math.sin(t * sp + ph - i * 0.6)) * 10) / 10;
                if (r !== last) a.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, last = r);
            });
            par = a;
            prevTop = top;
        }
    }

    _bubbles(parent, at) {
        const bm = this._m.bubble, img = bm && this._img('bubble');
        if (!img) return;
        const layer = new Clutter.Actor();
        parent.add_child(layer);
        for (let i = 0; i < 32; i++) {
            const a = this._actor(layer, img, { width: bm.w, height: bm.h, visible: false });
            a.set_pivot_point(0.5, 0.5);
            this._pool.push({a, live: false, x: 0, y: 0, v: 0, vmax: 0, amp: 0, f: 0, ph: 0});
        }
        const pt = (n, p) => {
            const a = at[n], m = this._m[n];
            return a && m[p] ? [a.x + m.base[0] + (m[p][0] - m.base[0]) * a.scale_x, a.y + m.base[1] + (m[p][1] - m.base[1]) * a.scale_y] : null;
        };
        const stone = pt('bubbler', 'outlet'), valve = pt('diver', 'valve'), mouth = pt('chest', 'mouth');
        const lid = at.chest && [...Array(10).keys()].map(i => this._img(`chest_lid_${i}`));
        let lidA = null;
        if (lid?.every(Boolean)) {  // lid frames are cropped on their own: ox/oy place them on the body
            const cm = this._m.chest, lm = this._m.chest_lid_0, dx = lm.ox - cm.ox, dy = lm.oy - cm.oy;
            lidA = this._actor(parent, lid[0], {x: at.chest.x + dx, y: at.chest.y + dy, width: lm.w, height: lm.h});
            parent.set_child_above_sibling(lidA, at.chest);
            lidA.set_pivot_point((cm.base[0] - dx) / lm.w, (cm.base[1] - dy) / lm.h);
            lidA.set_scale(at.chest.scale_x, at.chest.scale_y);
        }
        const diver = at.diver;
        let next = 0, burst = 0, dnext = 2, frame = 0, tilt = NaN;
        const top = SAND - 50;  // a notification's bubble burst rises from here, top-centre
        this._anims.push((t, dt) => {
            const W = this._ctx.world;
            if (W.notifications > this._notes)
                for (let k = 0; k < 8; k++) this._emit(this._W / 2 + (k - 3.5) * 25, top + Math.random() * 40, 0.3 + Math.random() * 0.5);
            this._notes = W.notifications;
            if (stone && (next -= dt * (W.idle > 600 ? 0.5 : 1)) <= 0) {
                this._emit(stone[0] + (Math.random() - 0.5) * 30, stone[1], 0.3 + Math.random() * (burst ? 0.4 : 0.7));
                if (burst > 0) { burst--; next = 0.03 + Math.random() * 0.05; } else {
                    next = Math.random() < 0.12 ? 0.8 + Math.random() * 2 : 0.08 + Math.random() * 0.3;
                    if (Math.random() < 0.015) burst = 12 + (Math.random() * 25 | 0);
                }
            }
            if (valve && (dnext -= dt) <= 0) {
                for (let k = 0; k < 4; k++) this._emit(valve[0] + k * 2, valve[1] - k * 14, 0.35 + Math.random() * 0.45);
                dnext = 3 + Math.random() * 5;
            }
            const r = Math.round(8 * Math.sin(t * 0.37)) / 10;  // 0.1 degree steps
            if (diver && r !== tilt) diver.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, tilt = r);
            if (lidA) {
                const o = Math.max(0, Math.sin(t * 0.17)) ** 4, f = Math.round(o * 9);
                if (f !== frame) lidA.content = lid[frame = f];
                if (mouth && o > 0.85 && Math.random() < 0.12) this._emit(mouth[0] + (Math.random() - 0.5) * 60, mouth[1], 0.25 + Math.random() * 0.4);
            }
            for (const b of this._pool) {
                if (!b.live) continue;
                b.v = Math.min(b.vmax, b.v + 50 * dt);
                b.y -= b.v * dt;
                b.a.set_translation(b.x + b.amp * Math.sin(t * b.f + b.ph), b.y, 0);
                if (b.y < 40) { b.live = false; b.a.hide(); }
            }
        });
    }

    _emit(x, y, size) {
        const b = this._pool.find(p => !p.live);
        if (!b) return;
        const m = this._m.bubble;
        Object.assign(b, {live: true, x: x - m.w / 2, y: y - m.h / 2, v: 40 + 40 * size, vmax: 140 + 180 * size,
            amp: 4 + 10 * Math.random(), f: 2 + 3 * Math.random(), ph: Math.random() * TAU});
        b.a.set_scale(size, size);
        b.a.set_translation(b.x, b.y, 0);
        b.a.show();
    }

    // Snail creeping between x0 and x1: frames cycle, it only advances while stretching.
    _snail(parent, x0, x1, y) {
        const frames = [...Array(8).keys()].map(i => this._img(`snail_${i}`));
        const m = this._m.snail_0;
        if (!m?.base || !frames.every(Boolean)) return;
        const a = this._actor(parent, frames[0], {width: m.w, height: m.h, y: y - m.base[1]});
        a.set_pivot_point(m.base[0] / m.w, 0);
        let x = x0 + (x1 - x0) * 0.3, dir = 1, ph = 0, f = 0, rest = 0, tx = NaN;
        this._anims.push((t, dt) => {
            if ((rest -= dt) > 0) return;
            ph += dt * 5;
            const nf = Math.floor(ph) % 8;
            if (nf !== f) a.content = frames[f = nf];
            x += dir * dt * 9 * Math.max(0, Math.sin(ph / 8 * TAU));
            if (x > x1 || x < x0) { dir = -dir; a.scale_x = dir; x = Math.min(x1, Math.max(x0, x)); }
            if (Math.random() < dt / 40) rest = 3 + Math.random() * 6;
            const nx = Math.round((x - m.base[0]) * 4) / 4;  // translation, not x: no relayout
            if (nx !== tx) a.set_translation(tx = nx, 0, 0);
        });
    }

    tick(dt, t) {
        for (const f of this._anims) f(t, dt);
        for (let i = this._n++ % 3; i < this._slow.length; i += 3) this._slow[i](t);
        if (this._n % 10 === 0) this._light(dt * 10);
    }

    // Light mood from hour, dark scheme and idle; eased so changes fade over a few seconds.
    _light(dt) {
        const { hour, dark, idle } = this._ctx.world, nt = night(hour);
        const warm = !nt && (hour < 8 || hour >= 18);  // ponytail: fixed dawn/dusk bands
        const dim = Math.min(0.8, (nt ? 0.4 : 0) + (dark ? 0.15 : 0) + (idle > 600 ? 0.2 : 0));
        const k = Math.min(1, dt * 0.5);
        this._rays += ((nt ? 0 : 1) - this._rays) * k;
        fade(this._tint[0], dim, k);
        fade(this._tint[1], warm ? 0.13 : 0, k);
    }

    destroy() {  // actors go with ctx.root, which the host destroys
        this._anims = this._slow = this._pool = [];
    }
}

function fade(g, goal, k) {
    g.v += (goal - g.v) * k;
    const o = Math.round(g.v * 255);
    if (o !== g.o) g.a.set_opacity(g.o = o);
}

// Seeded so the layout is identical on every rebuild.
const rng = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;
