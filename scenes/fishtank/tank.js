// Tank scenery: Blender-rendered sprites from assets/ (made by blender/scene_*.py), composed into
// parallax layers. Art is uploaded once; motion only moves, rotates or swaps the content of actors.
// Also the tank's ambient life (bubbles, motes, plants that bend when brushed) and the world the
// fish read (fishLayers, swimBounds, sandY, perches, plants, spots, ship, food).
import Clutter from 'gi://Clutter';
import Graphene from 'gi://Graphene';
import St from 'gi://St';
import { Food } from './food.js';
import { Critters, night, pt, rng } from './critters.js';
import { drift } from './steer.js';

export { pt };  // fish.js reads manifest points through it

const TAU = Math.PI * 2;
const SAND = 1150;       // ref row of the sand's back edge
const SNAIL_Y = 1352;    // ref row the snail creeps along
const DRIFT = 22;        // parallax: how far (ref px) the nearest layer sways with the slow camera bob
const BEND_DEG = 25;     // plant tip angle (deg) per unit of brush bend
const MOTES = 20;        // per depth
const HAZE = '#1d5d6c';  // water colour laid over each depth, thicker further back
const PLANT_FLOW = 0.1;  // how much a dragged window's current bends plants (calibration knob)
const TORCH = 150;       // night flashlight opacity
const EGGS = 86400;      // s snail eggs on the glass take to fade

// Props on the sand, by screen x fraction and the ref row their base sits on (sorted by row at build).
// slot: the setting that can swap the piece; big: hidden by decor 'minimal'.
const PROPS = [
    ['rock_b', 0.30, 1205, 0.9], ['castle', 0.12, 1222, 1], ['rock_c', 0.235, 1250, 0.8], ['ship', 0.43, 1215, 1],
    ['rock_a', 0.53, 1262, 0.9], ['chest', 0.6, 1290, 1], ['bubbler', 0.71, 1268, 1], ['diver', 0.86, 1255, 1],
    ['rock_d', 0.94, 1300, 1], ['rock_a', 0.03, 1335, 0.7],
];
const BIG = ['castle', 'ship', 'chest', 'diver'];
const PLANTS = ['valli', 'valli', 'sword', 'sword', 'jfern', 'cabomba', 'ludwigia', 'anubias', 'anubias'];
const MIDPLANTS = [0.025, 0.2, 0.265, 0.345, 0.545, 0.67, 0.765, 0.905, 0.985];  // in the gaps between props

// Ref px are the art's own pixels (manifest ref = screen height it was drawn for).
export class Tank {
    constructor(ctx, settings, env) {
        const w = Math.max(1, ctx.w), h = Math.max(1, ctx.h);
        this._ctx = ctx;
        this._S = settings;
        this._m = ctx.images;
        this._anims = [];
        this._slow = [];  // slow sway: each runs every third tick (a third of the cost, steps stay far below a pixel)
        this._n = 0;
        this._pool = [];
        this._rings = [];
        this._rays = 1;   // light ray strength, 0 at night
        this._rx = new Float64Array(7);  // each ray's top centre x (screen px) and lean (tan of its angle),
        this._rt = new Float64Array(7);  // so motes can light up inside the beams
        this._haze = [];
        this._puffs = [];
        this._nt = false;
        // a window being dragged: its rect and velocity (px/s); fish, bubbles, food and plants drift in its wake
        this.flow = { x: 0, y: 0, w: 0, h: 0, vx: 0, vy: 0, on: false, kick: 0 };
        this._notes = ctx.world.notifications;
        this._s = h / ctx.ref;
        this._box = new Clutter.Actor({ width: w, height: h, clip_to_allocation: true });
        ctx.root.add_child(this._box);
        this.fishLayers = [0, 1].map(() => new Clutter.Actor({ width: w, height: h }));
        this.glassLayer = new Clutter.Actor({ width: w, height: h });
        this.swimBounds = { x: 0, y: h * 0.06, w, h: h * 0.8 };
        this.perches = [];
        this.plants = [];
        this.spots = [];
        this.tops = [];  // [{x0, x1, y}] screen px: rock and chest tops food can rest on
        this._sandTop = null;  // the sand's back edge profile in ref px, from the manifest
        this.ship = null;
        this.mid = null;
        this.far = [];
        try {
            this._build(w, h);
        } catch (e) {  // never take the shell down over scenery: keep whatever got built, plus the fish
            logError(e, 'fishtank: scenery failed, showing what loaded');
            if (!this._box.get_n_children())
                this._box.add_child(new St.Widget({ width: w, height: h,
                    style: 'background-gradient-direction: vertical; background-gradient-start: #1d5d6c; background-gradient-end: #031a26;' }));
            this.fishLayers.forEach(l => l.get_parent() || this._box.add_child(l));
        }
        this._box.add_child(this.glassLayer);
        for (let i = 0; i < 6; i++) {  // sand puffs, under the near fish
            const a = new St.Widget({ width: 10, height: 10, opacity: 0, style: 'background-color: #cdb991; border-radius: 5px;' });
            this.fishLayers[1].insert_child_at_index(a, 0);
            this._puffs.push({ a, t: 0, x: 0, y: 0 });
        }
        this.food = new Food(ctx, this);
        this.critters = new Critters(ctx, this, settings, env);
        // Tints over everything, fixed colours, only opacity changes: night/dark/idle dim, dawn/dusk warm.
        this._tint = [['#06102a', 0], ['#ff8a3c', 0]].map(([col, v]) => {
            const a = new St.Widget({ width: w, height: h, opacity: 0, style: `background-color: ${col};` });
            this._box.add_child(a);
            return { a, v, o: 0 };
        });
        // night flashlight under the cursor (the baked torch pool, or the jelly glow blown up), then the glass vignette
        const tn = pt(this._m.torch?.anchor) ? 'torch' : 'glow', ta = this._add(this._box, tn, 0, 0, { opacity: 0 });
        if (ta) {
            const m = this._m[tn], an = tn === 'torch' ? m.anchor : [m.w / 2, m.h / 2], k = this._s * (tn === 'torch' ? 1 : 6);
            ta.set_pivot_point(an[0] / m.w, an[1] / m.h);
            ta.set_scale(k, k);
            this._torch = { a: ta, an, v: 0, o: 0, max: tn === 'torch' ? TORCH : 110, x: NaN, y: NaN };
        }
        this._add(this._box, 'vignette', 0, 0, { width: w, height: h });
        const miss = ['torch', 'vignette'].filter(n => !this._m[n]);
        if (miss.length) console.warn(`fishtank: art missing, skipped: ${miss.join(', ')}`);
        this._eggsOn();
    }

    // Daily snail eggs: a clutch on the glass at the snail's x, fading over a day.
    _eggsOn() {
        const m = this._m.snail_eggs, img = pt(m?.anchor) && this._sx !== undefined && this._img('snail_eggs');
        if (!img) return;
        const a = this._actor(this.glassLayer, img, { width: m.w, height: m.h, opacity: 0 }), s = this._s;
        a.set_pivot_point(m.anchor[0] / m.w, m.anchor[1] / m.h);
        a.set_scale(s, s);
        const E = this._eggs = { a, age: -1, o: 0 };
        this.critters.events.eggs = (age, x) => {
            if (age > EGGS) return null;
            x ??= this._sx;
            E.age = age;
            a.set_translation(Math.round(x * s - m.anchor[0]), Math.round((SNAIL_Y - 70) * s - m.anchor[1]), 0);
            return x;
        };
    }

    // Sand kicked up at (x, y) screen px: a little cloud that rises and fades (bottom feeders, pellets).
    puff(x, y) {
        const p = this._puffs.find(q => q.t <= 0);
        if (p) { p.t = 0.6; p.x = x; p.y = y; }
    }

    // Food art lands on the sand here (px): near layer just below the swim box, far layer higher up.
    // Without x: one row per layer (the old flat line). With x: the top of that layer's sand band there.
    sandY(layer, x) {
        if (x === undefined) {
            const b = this.swimBounds;
            return b.y + b.h + (layer ? 6 : -24);
        }
        return this.ground(layer, x, 0);
    }

    // Where food at depth z (0 = back of the band, 1 = front) lies on the floor at screen x. Near band:
    // from the swim box's bottom down the front sand; far band: a thin strip on the sand's real back edge.
    ground(layer, x, z) {
        const b = this.swimBounds, h = this._ctx.h, near = b.y + b.h;
        if (layer) return near + z * Math.max(0, Math.min(h * 0.08, h - 4 - near));
        let top = SAND;
        const P = this._sandTop;
        if (P) {
            const u = ((((x / this._s + DRIFT) % P.w) + P.w) % P.w) / P.w * (P.top.length - 1), i = Math.min(P.top.length - 2, u | 0);
            top = this._ctx.ref - P.h + P.top[i] + (P.top[i + 1] - P.top[i]) * (u - i);
        }
        const y0 = Math.min(top * this._s + h * 0.008, near - 4);
        return y0 + z * Math.max(0, Math.min(h * 0.03, near - 2 - y0));
    }

    // A ring spreading on the surface (food dropped near the top).
    splash(x) {
        const r = this._rings.find(q => q.t <= 0);
        if (r) { r.t = 0.8; r.x = x; }
    }

    _build(w, h) {
        const REF = this._ctx.ref, s = this._s, W = w / s, S = this._S;
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
        const rays = new Clutter.Actor();
        sky.add_child(rays);
        let rx = NaN;
        this._slow.push(t => {  // the whole sheaf of rays drifts slowly sideways
            const x = Math.round(6 * Math.sin(t * 0.05) * 4) / 4;
            if (x !== rx) rays.set_translation(rx = x, 0, 0);
        });
        this._nRays = 0;
        for (let i = 0; i < 7; i++) {
            const a = this._add(rays, 'ray', (0.04 + i * 0.15 + 0.06 * Math.sin(i * 7.3)) * W, -60, {height: 1150 + 200 * Math.sin(i * 3.1)});
            if (!a) break;
            this._nRays = i + 1;
            a.set_pivot_point(0.5, 0);
            const base = 8 + 6 * Math.sin(i * 5.1), ph = i * 1.7, cx = a.x + this._m.ray.w / 2;
            let rot = NaN, op = -1;  // 0.1 degree steps; set only on change
            this._slow.push(t => {
                const r = Math.round((base + 2.5 * Math.sin(t * 0.06 + ph)) * 10) / 10, o = Math.round(this._rays * (110 + 90 * Math.sin(t * 0.11 + ph)));
                this._rx[i] = (cx + (rx || 0)) * s;
                this._rt[i] = Math.tan(r * Math.PI / 180);
                if (r !== rot) a.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, rot = r);
                if (o !== op) a.set_opacity(op = o);
            });
        }
        // depth haze: one flat water-coloured sheet over each far depth, so distance reads as water
        const haze = o => {
            const a = new St.Widget({ width: w, height: h, opacity: o, style: `background-color: ${HAZE};` });
            this._box.add_child(a);
            this._haze.push({ a, o, v: o });
        };
        for (const [n, k, o] of [['far0', 0.2, 20], ['far1', 0.35, 25], ['far2', 0.5, 30]]) {
            const m = this._m[n], l = layer(k);
            this.far.push(l);
            if (m) this._tile(l, n, -DRIFT, m.yb - m.h, W + 2 * DRIFT, 0);
            haze(o);
        }
        const floor = layer(0.75);
        const sub = S.substrate === 'gravel' && this._m.gravel ? 'gravel' : 'sand', sand = this._m[sub];
        if (sand) {
            this._tile(floor, sub, -DRIFT, REF - sand.h, W + 2 * DRIFT, 0);
            if (Array.isArray(sand.top) && sand.top.length > 1 && sand.top.every(v => Number.isFinite(v) && v >= 0 && v <= sand.h))
                this._sandTop = sand;
            for (const [v, op] of [[7, 80], [-11, 55]]) {
                const c = this._tile(floor, 'caustics', -DRIFT, REF - this._m.caustics?.h, W + 2 * DRIFT, v);
                if (c) c.opacity = op;
            }
        }
        const r = this._rand = rng(20261011);
        for (let i = 0; i < 9; i++)
            this._plant(floor, r() * W, SAND + 15 + r() * 40, 0.55 + r() * 0.3, 1.2);
        this._motes(0, w, h);
        this._box.add_child(this.fishLayers[0]);
        haze(55);

        const mid = this.mid = layer(0.75);
        const at = {};
        const items = [];
        for (const [n, ...rest] of PROPS) {
            if (BIG.includes(n) && S.decor === 'minimal' || n === 'bubbler' && !S.bubbler) continue;
            const pick = S[n] && S[n] !== n && this._m[S[n]] ? S[n] : n;  // slot swap, default piece when the art is missing
            items.push([pick, ...rest, n]);
        }
        for (const fx of MIDPLANTS) items.push([null, fx + (r() - 0.5) * 0.02, SAND + 70 + r() * 140, 0.7 + r() * 0.35]);
        items.sort((a, b) => a[2] - b[2]);
        for (const [n, fx, y, k, role] of items) {
            if (!n) {
                const p = this._plant(mid, fx * W, y, k, 1.8);
                if (p) {
                    this.plants.push(p);
                    this.perches.push({ x: p.x, y: p.y - p.h * 0.4 });
                }
                continue;
            }
            const a = this._place(mid, n, fx * W, y, BIG.includes(role) ? k * Math.min(1, W / 1800) : k);  // narrow/portrait: big props shrink
            if (!a) continue;
            at[role] = [a, n];
            const rest = this._point([a, n], 'rest'), hw = this._m[n].w * 0.3 * a.scale_x;
            if (rest) this.tops.push({ x0: (rest[0] - hw) * s, x1: (rest[0] + hw) * s, y: rest[1] * s });
        }
        const hole = this._point(at.ship, 'hole');
        if (hole) this.ship = { hole: { x: hole[0] * s, y: hole[1] * s }, actor: at.ship[0] };
        this._bubbles(mid, at);
        this._snail(mid, 0.3 * W, 0.56 * W, SNAIL_Y);
        this._box.add_child(this.fishLayers[1]);
        this._motes(1, w, h);

        const front = layer(1);
        for (const fx of [0.0, 0.025, 0.05, 0.95, 0.975, 1.0]) {
            const p = this._plant(front, fx * W + (r() - 0.5) * 40, REF + 30, 1.0 + r() * 0.4, 2.6);
            if (p) this.plants.push(p);
        }
        for (let i = 0; i < 12; i++)
            this._plant(front, r() * W, REF + 10, 0.8 + r() * 0.5, 3, 'hair');
    }

    // Prop point p in ref px (layer coords), from the placed actor; null if missing.
    _point(entry, p) {
        if (!entry) return null;
        const [a, n] = entry, m = this._m[n];
        return pt(m[p]) ? [a.x + m.base[0] + (m[p][0] - m.base[0]) * a.scale_x, a.y + m.base[1] + (m[p][1] - m.base[1]) * a.scale_y] : null;
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
        const m = this._m[name], img = this._img(name);
        return img ? this._actor(parent, img, {x, y, width: m.w, height: m.h, ...props}) : null;
    }

    // Prop with its manifest 'base' point put at (x, y), scaled k.
    _place(parent, name, x, y, k = 1) {
        const m = this._m[name], b = m?.base;
        const a = pt(b) && this._add(parent, name, x - b[0], y - b[1]);
        if (a) {
            a.set_pivot_point(b[0] / m.w, b[1] / m.h);
            a.set_scale(k, k);
        }
        return a;
    }

    // Horizontally repeating strip: side-by-side copies sharing one texture (content repeat tiles at
    // the decoded size, not the ref size); vx = drift speed in ref px/s, which needs a moving holder.
    _tile(parent, name, x, y, width, vx) {
        const m = this._m[name], img = this._img(name);
        if (!img) return null;
        const a = vx ? new Clutter.Actor({ x, y }) : parent;
        if (vx) parent.add_child(a);
        const x0 = vx ? 0 : x, y0 = vx ? 0 : y, n = Math.ceil((width + (vx ? m.w : 0)) / m.w);
        for (let i = 0; i < n; i++)
            this._actor(a, img, { x: x0 + i * m.w, y: y0, width: m.w, height: m.h });
        let last = NaN;  // quarter-pixel steps, set only on change
        if (vx) this._anims.push(t => {
            const x = -Math.round((((t * vx) % m.w + m.w) % m.w) * 4) / 4;
            if (x !== last) a.set_translation(last = x, 0, 0);
        });
        return a;
    }

    // Sprite cut into segments at its joints (j1, j2, ...), each rotating about the one below; the
    // base sits at (0, 0) of parent, scaled (sx, sy). Returns the segment actors, root first, or null.
    // Segment = pivot actor + the whole image clipped to its band, the next segment hanging off the
    // pivot (a clip cuts children too). The top segment has no children: one clipped image actor.
    chain(parent, name, sx = 1, sy = 1) {
        const m = this._m[name], img = pt(m?.base) && this._img(name);
        if (!img) return null;
        const js = [m.base];
        for (let i = 1; pt(m['j' + i]); i++) js.push(m['j' + i]);
        const segs = [];
        let par = parent, prevTop = 0;
        for (let i = 0; i < js.length; i++) {
            const top = Math.round(i + 1 < js.length ? js[i + 1][1] : 0), bot = Math.round(i ? js[i][1] + 3 : m.h);
            const x0 = i ? 0 : -m.base[0], y0 = i ? top - prevTop : -m.base[1] + top;
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
            if (!i) a.set_scale(sx, sy);
            segs.push(a);
            par = a;
            prevTop = top;
        }
        return segs;
    }

    // Plant at ref (x, y) in a layer, swaying out of step with its neighbours. Returns the brush
    // record {x, y, h (screen px), bend, bv}: fish push bv, tick() springs bend back.
    _plant(parent, x, y, k, amp, species = null) {
        const r = this._rand;
        const name = `plant_${species ?? PLANTS[(r() * PLANTS.length) | 0]}_${(r() * 2) | 0}`;
        const mir = r() < 0.5 ? -k : k, ph = r() * TAU, sp = 0.35 + r() * 0.25, lean = (r() - 0.5) * 6;
        const holder = new Clutter.Actor({ x, y });
        parent.add_child(holder);
        holder.set_scale(mir, k);  // mirrored here, so every segment bends in the same (mirrored) space
        const segs = this.chain(holder, name);
        if (!segs) { holder.destroy(); return null; }
        const s = this._s, n = segs.length, last = new Float64Array(n).fill(NaN), mtx = new Graphene.Matrix();
        const p = { x: x * s, y: y * s, h: this._m[name].base[1] * k * s, bend: 0, bv: 0 };
        // Each segment leans by a horizontal shear about its joint, not a rotation: a rotated band
        // tilts its edge, so a wide leaf or the whole far half of the plant split open at the joint
        // line. A shear keeps every band edge level, so the bands meet across the full width.
        const py = segs.map(a => { const y = a.pivot_point.y * a.height; a.set_pivot_point(0, 0); return y; });
        // 0.1 degree steps, set only on change (the bulk of the slow sway calls)
        p.sway = t => {
            for (let i = 0; i < n; i++) {
                const v = Math.round(((i ? 0 : lean) + amp * (0.6 + 0.3 * i) * Math.sin(t * sp + ph - i * 0.6) +
                    p.bend * BEND_DEG / n * Math.sign(mir)) * 10) / 10;
                if (v === last[i]) continue;
                const tn = Math.tan((last[i] = v) * Math.PI / 180);
                segs[i].set_transform(mtx.init_from_2d(1, 0, -tn, 1, tn * py[i], 0));
            }
        };
        this._slow.push(p.sway);
        return p;
    }

    // Specks drifting in the water: d = 0 behind the far fish, 1 in front of the near ones.
    _motes(d, w, h) {
        const box = new Clutter.Actor({ width: w, height: h });
        this._box.add_child(box);
        const r = this._rand, sz = d ? 3 : 2, op = d ? 90 : 55;
        for (let i = 0; i < MOTES; i++) {
            const a = new St.Widget({ width: sz, height: sz, opacity: op, style: `background-color: #d8eef0; border-radius: ${sz}px;` });
            box.add_child(a);
            const x0 = r() * w, y0 = r() * h * 0.8, ph = r() * TAU, vy = 1.5 + r();
            let tx = NaN, ty = NaN, to = op;
            const top = 60 * this._s;
            this._slow.push(t => {  // closed form: x += 3 sin(0.2t + ph) dt, y -= vy dt, wrapped
                const x = Math.round((x0 - 15 * Math.cos(t * 0.2 + ph)) * 4) / 4;
                const y = Math.round(((((y0 - vy * t) % (h * 0.85)) + h * 0.85) % (h * 0.85)) * 4) / 4;
                if (x !== tx || y !== ty) a.set_translation(tx = x, ty = y, 0);
                // a speck inside a light ray glints (a ray tilted +a degrees drifts right going down)
                let o = op;
                if (this._rays > 0.02) {
                    let d = 1e9;
                    for (let i = 0; i < this._nRays; i++) d = Math.min(d, Math.abs(x - this._rx[i] - (y + top) * this._rt[i]));
                    o = Math.min(255, Math.round((op + 110 * Math.max(0, 1 - d / 70) * this._rays) / 5) * 5);
                }
                if (o !== to) a.set_opacity(to = o);
            });
        }
        if (!d) return;
        const rm = this._m.ring, img = this._img('ring');  // surface rings ride in front of the fish
        if (!img) return;
        for (let i = 0; i < 3; i++) {
            const a = this._actor(box, img, { width: rm.w, height: rm.h, opacity: 0 });
            a.set_pivot_point(0.5, 0.5);
            this._rings.push({ a, t: 0, x: 0 });
        }
        const y = this.swimBounds.y * 0.5 - rm.h / 2;
        this._anims.push((t, dt) => {
            for (const q of this._rings) {
                if (q.t <= 0) continue;
                q.t -= dt;
                const u = 1 - Math.max(0, q.t) / 0.8, k = (0.3 + 1.3 * u) * this._s * 1.5;
                q.a.set_translation(q.x - rm.w / 2, y, 0);
                q.a.set_scale(k, k);
                q.a.set_opacity(Math.round(200 * (1 - u)));
            }
        });
    }

    _bubbles(parent, at) {
        const bm = this._m.bubble, img = this._img('bubble');
        if (!img) return;
        const layer = new Clutter.Actor();
        parent.add_child(layer);
        for (let i = 0; i < 32; i++) {
            const a = this._actor(layer, img, { width: bm.w, height: bm.h, visible: false });
            a.set_pivot_point(0.5, 0.5);
            this._pool.push({a, live: false, x: 0, y: 0, y0: 0, v: 0, vmax: 0, amp: 0, f: 0, ph: 0, size: 1, pop: 0, k: NaN});
        }
        const stone = this._point(at.bubbler, 'outlet'), valve = this._point(at.diver, 'valve'), mouth = this._point(at.chest, 'mouth');
        const chest = at.chest?.[0];
        const lid = chest && [...Array(10).keys()].map(i => this._img(`chest_lid_${i}`));
        let lidA = null;
        if (lid?.every(Boolean)) {  // lid frames are cropped on their own: ox/oy place them on the body
            const cm = this._m.chest, lm = this._m.chest_lid_0, dx = lm.ox - cm.ox, dy = lm.oy - cm.oy;
            lidA = this._actor(parent, lid[0], {x: chest.x + dx, y: chest.y + dy, width: lm.w, height: lm.h});
            parent.set_child_above_sibling(lidA, chest);
            lidA.set_pivot_point((cm.base[0] - dx) / lm.w, (cm.base[1] - dy) / lm.h);
            lidA.set_scale(chest.scale_x, chest.scale_y);
        }
        const diver = at.diver?.[0];
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
            if (valve) {
                if ((dnext -= dt) <= 0) {
                    for (let k = 0; k < 4; k++) this._emit(valve[0] + k * 2, valve[1] - k * 14, 0.35 + Math.random() * 0.45);
                    dnext = 3 + Math.random() * 5;
                } else if (Math.random() < dt / 6) this._emit(valve[0], valve[1], 0.2 + Math.random() * 0.2);  // a stray one between bursts
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
                if (b.pop > 0) {  // flattens and fades at the surface
                    const u = 1 - (b.pop -= dt) / 0.25;
                    if (b.pop <= 0) { b.live = false; b.a.hide(); continue; }
                    b.a.set_scale(b.size * (1.3 + 0.4 * u), b.size * (1.3 - u));
                    b.a.set_opacity(Math.round(255 * (1 - u)));
                    continue;
                }
                b.v = Math.min(b.vmax, b.v + 50 * dt);
                b.y -= b.v * dt;
                if (this.flow.on) b.x += this.flow.vx * drift(this.flow, b.x * this._s, b.y * this._s) * dt / this._s;
                const p = Math.min(1, Math.max(0, (b.y0 - b.y) / Math.max(1, b.y0 - 40)));  // grows and wobbles more as it rises
                const k = Math.round(b.size * (1 + 0.3 * p) * 100) / 100;
                if (k !== b.k) b.a.set_scale(b.k = k, k);
                b.a.set_translation(b.x + b.amp * (1 + p) * Math.sin(t * b.f + b.ph), b.y, 0);
                if (b.y < 40) { b.pop = 0.25; b.size = k; }
            }
        });
    }

    _emit(x, y, size) {
        let b = null;
        for (const p of this._pool) if (!p.live) { b = p; break; }
        if (!b) return;
        const m = this._m.bubble;
        b.live = true; b.x = x - m.w / 2; b.y = b.y0 = y - m.h / 2; b.v = 40 + 40 * size; b.vmax = 140 + 180 * size;
        b.amp = 4 + 10 * Math.random(); b.f = 2 + 3 * Math.random(); b.ph = Math.random() * TAU; b.size = b.k = size; b.pop = 0;
        b.a.set_scale(size, size);
        b.a.set_opacity(255);
        b.a.set_translation(b.x, b.y, 0);
        b.a.show();
    }

    // Snail creeping between x0 and x1: frames cycle, it only advances while stretching. Each leg
    // has its own pace; it stops for a rest now and then.
    _snail(parent, x0, x1, y) {
        const frames = [...Array(8).keys()].map(i => this._img(`snail_${i}`));
        const m = this._m.snail_0;
        if (!pt(m?.base) || !frames.every(Boolean)) return;
        const a = this._actor(parent, frames[0], {width: m.w, height: m.h, y: y - m.base[1]});
        a.set_pivot_point(m.base[0] / m.w, 0);
        this._sx = x0 + (x1 - x0) * 0.3;
        let x = this._sx, dir = 1, ph = 0, f = 0, rest = 0, tx = NaN, pace = 6;
        this._anims.push((t, dt) => {
            if ((rest -= dt) > 0) return;
            ph += dt * pace * 0.6;
            const nf = Math.floor(ph) % 8;
            if (nf !== f) a.content = frames[f = nf];
            x += dir * dt * pace * 1.5 * Math.max(0, Math.sin(ph / 8 * TAU));
            if (x > x1 || x < x0) {
                dir = -dir; a.scale_x = dir; x = Math.min(x1, Math.max(x0, x));
                pace = 5 + 3 * Math.random();
            }
            if (Math.random() < dt / 40) rest = 3 + Math.random() * 9;
            this._sx = x;
            const nx = Math.round((x - m.base[0]) * 4) / 4;  // translation, not x: no relayout
            if (nx !== tx) a.set_translation(tx = nx, 0, 0);
        });
    }

    tick(dt, t) {
        this._flow();
        this._glass(dt);
        for (const f of this._anims) f(t, dt);
        for (let i = this._n++ % 3; i < this._slow.length; i += 3) this._slow[i](t);
        const F = this.flow;
        if (F.on) for (const p of this.plants) {  // a dragged window's wake bends the plants it passes
            const k = drift(F, p.x, p.y - p.h * 0.5);
            if (k) p.bv += F.vx * k * dt * PLANT_FLOW;
        }
        if (F.on && (F.kick -= dt) <= 0) {  // and shoves food along, a few times a second
            F.kick = 0.3;
            for (const p of this.food.pieces) {
                const k = p.live && drift(F, p.x, p.y);
                if (k) this.food.kick(p, F.vx * k * 0.2);
            }
        }
        for (const p of this.plants) {  // brushed plants spring back, redrawn every tick while moving
            if (!p.bv && !p.bend) continue;
            p.bend += p.bv * dt;
            p.bv -= (p.bend * 12 + p.bv * 3) * dt;
            if (Math.abs(p.bend) < 1e-3 && Math.abs(p.bv) < 1e-3) p.bend = p.bv = 0;
            p.sway(t);
        }
        this.food.tick(dt, t);
        this.critters.tick(dt, t);
        if (this._n % 10 === 0) this._light(dt * 10);
    }

    // The first moving window becomes the current, with the engine's smoothed window velocity.
    _flow() {
        const F = this.flow, cl = v => Math.max(-1500, Math.min(1500, v || 0));
        let w = null;
        for (const q of this._ctx.world.windows) if (q.moving) { w = q; break; }
        F.on = !!w;
        if (!w) return;
        F.x = w.x; F.y = w.y; F.w = w.w; F.h = w.h; F.vx = cl(w.vx); F.vy = cl(w.vy);
    }

    // Glass-side things that move every tick: the torch follows the cursor, sand puffs rise and fade.
    _glass(dt) {
        const T = this._torch, P = this._ctx.world.pointer;
        if (T) {
            T.v += ((this._nt && P.over && this._S.flashlight !== false ? 1 : 0) - T.v) * Math.min(1, dt * 4);
            const o = Math.round(T.v * T.max / 5) * 5;
            if (o !== T.o) T.a.set_opacity(T.o = o);
            const x = Math.round(P.x - T.an[0]), y = Math.round(P.y - T.an[1]);
            if (o && (x !== T.x || y !== T.y)) T.a.set_translation(T.x = x, T.y = y, 0);
        }
        for (const p of this._puffs) {
            if (p.t <= 0) continue;
            const u = 1 - Math.max(0, p.t -= dt) / 0.6;
            p.a.set_translation(Math.round(p.x - 5), Math.round(p.y - 5 - 8 * u), 0);
            p.a.set_scale(1 + u, 1 + u * 0.6);
            p.a.set_opacity(Math.round(110 * (1 - u)));
        }
    }

    // Light mood from the engine's lights schedule, dark scheme and idle; eased over a few seconds.
    _light(dt) {
        const W = this._ctx.world, nt = night(W);
        const warm = W.lightsOn === undefined ? !nt && (W.hour < 8 || W.hour >= 18) : !!W.warm;
        const dim = Math.min(0.8, (nt ? 0.4 : 0) + (W.dark ? 0.15 : 0) + (W.idle > 600 ? 0.2 : 0));
        const k = Math.min(1, dt * 0.5);
        this._rays += ((nt ? 0 : 1) - this._rays) * k;
        this._nt = nt;
        const hk = 0.6 + 0.4 * this._rays;  // thinner haze at night
        for (const z of this._haze) {
            const o = Math.round(z.o * hk);
            if (o !== z.v) z.a.set_opacity(z.v = o);
        }
        const E = this._eggs;
        if (E && E.age >= 0) {
            const o = (E.age += dt) < EGGS ? Math.round(230 * (1 - E.age / EGGS)) : 0;
            if (o !== E.o) E.a.set_opacity(E.o = o);
            if (!o) E.age = -1;
        }
        fade(this._tint[0], dim, k);
        fade(this._tint[1], warm ? 0.13 : 0, k);
    }
}

function fade(g, goal, k) {
    g.v += (goal - g.v) * k;
    const o = Math.round(g.v * 255);
    if (o !== g.o) g.a.set_opacity(g.o = o);
}

