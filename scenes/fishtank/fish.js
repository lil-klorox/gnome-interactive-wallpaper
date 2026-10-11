// Fish bodies. Each fish = brain.js (what it wants) -> steer.js (how it moves) -> this body:
// a sprite rendered by blender/fish.py, picked by swim phase (tail speed follows swim speed) and
// by yaw (fish turn through a 3/4 and front view instead of flipping), plus pupils drawn on top
// that look at the cursor or whatever the brain is looking at. Static textures only, no repaints.
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Cairo from 'cairo';
import { makeBrain, think, PERSONALITY, drowsy, lazy, night } from './brain.js';
import { makeFish, step } from './steer.js';

// n: how many; cruise px/s at full size; burst/coast: wander gait seconds; turn rad/s
const SPECIES = [
    { name: 'clown', n: 2, cruise: 70, burst: 0.4, coast: 2 },
    { name: 'tetra', n: 7, cruise: 90, burst: 0.3, coast: 1.2, school: 'tetra' },
    { name: 'angel', n: 2, cruise: 55, burst: 0.5, coast: 4, turn: 1.6 },
    { name: 'goldfish', n: 2, cruise: 80, burst: 0.5, coast: 2.5 },
    { name: 'tang', n: 1, cruise: 110, burst: 0.4, coast: 1.5 },
    { name: 'puffer', n: 1, cruise: 50, burst: 0.4, coast: 2 },
    { name: 'cory', n: 3, cruise: 60, burst: 0.3, coast: 2.5 },
    { name: 'betta', n: 1, cruise: 45, burst: 0.5, coast: 4, turn: 1.8 },
];
const YAW_RATE = 3.5;  // rad/s a fish swings round through the front view
const FAR = { scale: 0.7, opacity: 165 };
const FLAKES = 9, FLAKE_LIFE = 20, SAVE_EVERY = 60;
const DAY = 864e5;

// Stored per fish id: {born: ms, fed: count}. Store data is untrusted: anything odd starts fresh.
const record = (r, now) => Number.isFinite(r?.born) && r.born <= now && Number.isInteger(r.fed) && r.fed >= 0
    ? { born: r.born, fed: Math.min(r.fed, 1e6) } : { born: now, fed: 0 };

// Iris + pupil + glint, painted once per eye; the actor is moved/squashed per frame.
function paintEye(area, iris) {
    const cr = area.get_context();
    try {
        const [w] = area.get_surface_size(), r = w / 2;
        const c = [1, 3, 5].map(i => parseInt(iris.slice(i, i + 2), 16) / 255);
        const g = new Cairo.RadialGradient(r, r * 1.1, 0, r, r, r * 0.66);
        g.addColorStopRGBA(0, Math.min(1, c[0] * 1.6), Math.min(1, c[1] * 1.6), Math.min(1, c[2] * 1.6), 1);
        g.addColorStopRGBA(0.75, ...c, 1);
        g.addColorStopRGBA(1, c[0] * 0.4, c[1] * 0.4, c[2] * 0.4, 1);
        cr.arc(r, r, r * 0.66, 0, 2 * Math.PI);
        cr.setSource(g);
        cr.fill();
        cr.arc(r, r, r * 0.38, 0, 2 * Math.PI);
        cr.setSourceRGBA(0.03, 0.03, 0.05, 1);
        cr.fill();
        cr.arc(r - r * 0.22, r - r * 0.26, r * 0.16, 0, 2 * Math.PI);
        cr.setSourceRGBA(1, 1, 1, 0.92);
        cr.fill();
        cr.arc(r + r * 0.2, r + r * 0.22, r * 0.07, 0, 2 * Math.PI);
        cr.setSourceRGBA(1, 1, 1, 0.6);
        cr.fill();
    } finally {
        cr.$dispose();
    }
}

export class School {
    constructor(ctx, fishLayers, swimBounds) {
        const b = this._b = swimBounds, now = Date.now();
        this._ctx = ctx;
        this._fish = [];
        this._mates = [[], []];   // [{f, b}] per layer, for brains
        this._motion = [[], []];  // motion states per layer, for steering
        this._store = {};  // known fish ids only; anything else in the file is dropped
        const old = ctx.store.get().fish;
        const S = Math.min(1, Math.max(0.5, b.h / 1000));  // smaller fish on small screens
        const failed = [];
        let k = 0;
        for (const sp of SPECIES) {
            let m;
            try {
                m = this._species(sp.name);
            } catch (e) {
                failed.push(`${sp.name} (${e.message})`);
                continue;
            }
            const pers = PERSONALITY[sp.name];
            const hx = b.x + Math.random() * b.w, hy = b.y + b.h * (pers.band[0] + Math.random() * (pers.band[1] - pers.band[0]));
            for (let i = 0; i < sp.n; i++) {
                const id = sp.name + i, rec = this._store[id] = record(old?.[id], now);
                const layer = sp.school || k++ % 3 ? 1 : 0;
                const sc = S * (layer ? 1 : FAR.scale) * (0.8 + 0.2 * Math.min(1, (now - rec.born) / DAY / 30));  // grows for a month
                const s = makeFish({
                    // schools start bunched together, everyone else anywhere in their home band
                    x: sp.school ? hx + Math.random() * 80 : b.x + Math.random() * b.w,
                    y: sp.school ? hy + Math.random() * 40 : b.y + b.h * (pers.band[0] + Math.random() * (pers.band[1] - pers.band[0])),
                    cruise: sp.cruise * sc * (0.85 + Math.random() * 0.3), pad: m.len * sc * 0.5,
                    school: sp.school, turn: sp.turn, burst: sp.burst, coast: sp.coast,
                });
                const brain = makeBrain(pers);
                brain.fed = rec.fed;
                const f = { id, m, s, sc, layer, brain, ph: Math.random(), yaw: Math.cos(s.dir) > 0 ? 0 : Math.PI,
                    puff: 0, look: [0, 0], cur: null, rot: null, mirror: null, tx: 0, ty: 0, it: null, acc: 0 };
                f.bodies = m.sheets.map(sh => this._makeBody(sh, m, layer, fishLayers[layer]));
                this._fish.push(f);
                this._mates[layer].push({ f: s, b: brain });
                this._motion[layer].push(s);
            }
        }
        if (failed.length)
            console.warn(`fishtank: fish art missing, skipped: ${failed.join(', ')}`);
        this._flakes = [];
        for (let i = 0; i < FLAKES; i++) {
            const a = new St.Widget({ width: 7, height: 5, visible: false, style: 'background-color: #c9772f; border-radius: 3px;' });
            fishLayers[1].add_child(a);
            this._flakes.push({ a, x: 0, y: 0, x0: 0, life: 0, live: false, shown: false });
        }
        this._threats = [];
        this._pulses = [0, 1, 2, 3].map(() => ({ x: 0, y: 0, w: 0, h: 0, t: 0 }));
        this._maxId = -1;  // newest window id seen; -1 = none yet (first look pulses nothing)
        const W = ctx.world;
        this._notes = W.notifications;
        this._idle = W.idle;
        this._down = W.pointer.down;
        this._attnT = 0;
        this._attn = { x: b.x + b.w / 2, y: b.y + 20 };  // where the banner lands
        this._n = 0;
        this._wake = this._news = 0;  // one-shot signals held 2 ticks, so each half of the school sees them once
        this._fedSum = -1;  // -1: save once soon, so first-seen fish keep their birthday
        this._saved = 0;
        this._c = { f: null, p: null, b, mates: null, dt: 0, rand: Math.random, threats: this._threats,
            food: this._flakes, attn: null, attnNew: false, wake: false, drowsy: 1, lazy: 1, night: false };
    }

    // Sheets (main + puffer's puff) and the largest eye radius, so one eye texture fits every frame.
    _species(name) {
        const ctx = this._ctx, e = ctx.images[name];
        if (!e?.eyes || !e.yaws || typeof e.iris !== 'string') throw new Error('not in manifest');
        const sheets = [ctx.sheet(name)];
        if (e.puff && ctx.images[e.puff]?.eyes) sheets.push(ctx.sheet(e.puff));
        if (sheets.some(sh => sh.eyes.length !== sh.n)) throw new Error('eyes/frames mismatch');
        let rmax = 1;
        for (const sh of sheets) for (const fr of sh.eyes) for (const v of fr) rmax = Math.max(rmax, v[2]);
        return { sheets, rows: e.yaws.length, rmax, iris: e.iris, len: e.len };
    }

    // One sprite: the sheet's clip box (scaled/rotated/mirrored about the anchor), eyes on top.
    // Opacity goes on the sheet child and eyes, never on the box (would force an offscreen pass).
    _makeBody(sh, m, layer, parent) {
        const box = sh.make(), D = Math.ceil(m.rmax * 2);
        box.reactive = false;
        box.visible = false;
        box.set_pivot_point(sh.anchor[0] / sh.w, sh.anchor[1] / sh.h);
        const op = layer ? 255 : FAR.opacity;
        const child = box.get_first_child();
        child.opacity = op;
        const eyes = [0, 1].map(() => {
            const a = new St.DrawingArea({ width: D, height: D, reactive: false, visible: false, opacity: op });
            a.set_pivot_point(0.5, 0.5);
            a.connect('repaint', d => paintEye(d, m.iris));
            box.add_child(a);
            return { a, on: false, x: NaN, y: NaN, z: NaN, q: NaN };
        });
        parent.add_child(box);
        return { sh, box, eyes, half: D / 2 };
    }

    tick(dt, t) {
        const W = this._ctx.world, P = W.pointer, c = this._c, b = this._b;
        c.p = P.over ? P : null;
        c.drowsy = drowsy(W.hour, W.idle);
        c.lazy = lazy(W.hour, W.idle);
        c.night = night(W.hour);
        this._wake = this._idle > 60 && W.idle < 5 ? 2 : this._wake - 1;
        c.wake = this._wake > 0;
        this._idle = W.idle;
        if (W.notifications > this._notes) { this._news = 2; this._attnT = 2; } else this._news--;
        c.attnNew = this._news > 0;
        this._notes = W.notifications;
        c.attn = (this._attnT -= dt) > 0 ? this._attn : null;
        this._threatsFrom(W.windows, dt);
        if (P.down && !this._down && P.over) this._drop(P.x, P.y);
        this._down = P.down;
        c.food = this._sink(dt, t) ? this._flakes : null;
        // brains think at 15 Hz, alternate fish each tick; bodies move every tick
        let fed = 0, j = this._n++;
        for (const f of this._fish) {
            const s = f.s;
            f.acc += dt;
            if (j++ % 2 === 0 || !f.it) {
                c.f = s;
                c.mates = this._mates[f.layer];
                c.dt = f.acc;
                f.acc = 0;
                f.it = think(f.brain, c);
            }
            step(s, dt, f.it, b, this._motion[f.layer]);
            this._body(f, dt, f.it);
            fed += f.brain.fed;
        }
        if (fed !== this._fedSum && t - this._saved > SAVE_EVERY) { this._fedSum = fed; this._saved = t; this._save(); }
    }

    // Moving windows, plus a 1 s pulse for any window that just appeared.
    _threatsFrom(windows, dt) {
        const th = this._threats, first = this._maxId < 0;
        let max = this._maxId;
        th.length = 0;
        for (const w of windows) {
            if (w.moving) th.push(w);
            if (!(w.id > this._maxId)) continue;  // mutter window ids only grow: bigger than any seen = new
            max = Math.max(max, w.id);
            const p = !first && this._pulses.find(q => q.t <= 0);
            if (p) { p.x = w.x; p.y = w.y; p.w = w.w; p.h = w.h; p.t = 1; }
        }
        this._maxId = Math.max(max, 0);
        for (const p of this._pulses) if ((p.t -= dt) > 0) th.push(p);
    }

    _drop(x, y) {
        let n = 3;
        for (const k of this._flakes) {
            if (k.live) continue;
            k.live = true; k.life = FLAKE_LIFE; k.x0 = x + (Math.random() - 0.5) * 30; k.x = k.x0; k.y = y + (Math.random() - 0.5) * 20;
            if (--n === 0) break;
        }
    }

    _sink(dt, t) {
        const floor = this._b.y + this._b.h;
        let any = false;
        for (const k of this._flakes) {
            if (k.live && (k.life -= dt) <= 0) k.live = false;
            if (k.live !== k.shown) (k.shown = k.live) ? k.a.show() : k.a.hide();
            if (!k.live) continue;
            any = true;
            k.y = Math.min(floor, k.y + 20 * dt);
            k.x = k.x0 + 4 * Math.sin(t * 1.3 + k.x0);
            k.a.set_translation(k.x - 3, k.y - 2, 0);
        }
        return any;
    }

    _save() {
        // Every monitor's school shares one store copy and the same fish ids: keep the larger fed count.
        const prev = this._ctx.store.get().fish;
        for (const f of this._fish) this._store[f.id].fed = Math.max(f.brain.fed, record(prev?.[f.id], Infinity).fed);
        this._ctx.store.set({ fish: this._store });
    }

    _body(f, dt, it) {
        const { m, s } = f;
        // yaw: 0 = facing right, PI/2 = facing the viewer, PI = facing left. Swing through the front.
        const c = Math.cos(s.dir), slow = s.speed < s.cruise * 0.15;
        const goal = it.face ? Math.PI / 2 : slow ? f.yaw : c > 0.15 ? 0 : c < -0.15 ? Math.PI : f.yaw;
        f.yaw += Math.max(-dt * YAW_RATE, Math.min(dt * YAW_RATE, goal - f.yaw));
        const mirror = f.yaw > Math.PI / 2, side = mirror ? Math.PI - f.yaw : f.yaw;
        // tail beat follows speed: quick on a burst, lazy while coasting, busy when nibbling
        f.ph += dt * (it.chomp ? 2.5 : 0.7 + 2.2 * Math.min(2, s.speed / s.cruise));
        const puffy = f.bodies.length > 1;
        if (puffy) f.puff += ((it.alarm ? 1 : 0) - f.puff) * Math.min(1, dt * (it.alarm ? 3 : 0.3));
        const bd = f.bodies[puffy && f.puff > 0.04 ? 1 : 0], sh = bd.sh, box = bd.box;
        if (bd !== f.cur) {
            f.cur?.box.hide();
            box.show();
            f.cur = bd;
            f.rot = f.mirror = null;
        }
        const row = Math.round(side / (Math.PI / 2) * (m.rows - 1));
        const col = bd === f.bodies[0] ? Math.floor(f.ph * sh.cols) % sh.cols : Math.round(f.puff * (sh.cols - 1));
        const i = row * sh.cols + col;
        sh.show(box, i);
        // nose dips into climbs and dives, only as much as the fish is side-on
        const pitch = Math.max(-0.45, Math.min(0.45, Math.atan2(Math.sin(s.dir), Math.abs(c)))) * Math.cos(side);
        const rot = Math.round((mirror ? -pitch : pitch) * 573) / 10;  // 0.1 degree steps, set only on change
        if (rot !== f.rot) box.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, f.rot = rot);
        if (mirror !== f.mirror) box.set_scale((f.mirror = mirror) ? -f.sc : f.sc, f.sc);
        const tx = Math.round((s.x - sh.anchor[0]) * 4) / 4, ty = Math.round((s.y - sh.anchor[1]) * 4) / 4;
        if (tx !== f.tx || ty !== f.ty) box.set_translation(f.tx = tx, f.ty = ty, 0);  // translation: no relayout
        this._pupils(f, bd, sh.eyes[i], it, mirror, pitch, side, dt);
    }

    // Pupils look at the brain's look target (cursor, buddy, food), else straight ahead. Every GI
    // call is cached on the JS side and skipped when unchanged: this is the hottest loop.
    _pupils(f, bd, eyes, it, mirror, pitch, side, dt) {
        const s = f.s;
        let lx = Math.cos(side) * 0.8, ly = 0;
        if (it.look) {
            const dx = it.look.x - s.x, dy = it.look.y - s.y, d = Math.sqrt(dx * dx + dy * dy) + 30;
            const a = mirror ? pitch : -pitch;  // undo the box rotation, then the mirror
            lx = (dx * Math.cos(a) - dy * Math.sin(a)) / d * (mirror ? -1 : 1);
            ly = (dx * Math.sin(a) + dy * Math.cos(a)) / d;
        }
        const k = Math.min(1, dt * 8);
        f.look[0] += (lx - f.look[0]) * k;
        f.look[1] += (ly - f.look[1]) * k;
        for (let j = 0; j < 2; j++) {
            const e = bd.eyes[j], v = eyes[j], on = !!v;
            if (e.on !== on) (e.on = on) ? e.a.show() : e.a.hide();
            if (!on) continue;
            const [x, y, r, sq] = v, z = Math.round(r / f.m.rmax * 50) / 50, q = Math.round(sq * 50) / 50;  // 2 % steps: fewer rescales
            if (e.z !== z || e.q !== q) { e.a.set_scale(z * q, z); e.z = z; e.q = q; }
            const ex = Math.round((x - bd.half + f.look[0] * r * 0.32 * sq) * 2) / 2;
            const ey = Math.round((y - bd.half + f.look[1] * r * 0.32) * 2) / 2;
            if (ex !== e.x || ey !== e.y) e.a.set_translation(e.x = ex, e.y = ey, 0);
        }
    }

    destroy() {  // actors go with ctx.root, which the host destroys
        // bug fix: saving unconditionally let an unfed monitor's stale copy overwrite another
        // monitor's feeding on disable; only a school with unsaved changes writes
        if (this._fish.reduce((n, f) => n + f.brain.fed, 0) !== this._fedSum) this._save();
        this._fish = [];
    }
}
