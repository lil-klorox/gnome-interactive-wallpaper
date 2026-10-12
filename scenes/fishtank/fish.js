// Fish bodies. Each fish = brain.js (what it wants) -> steer.js (how it moves) -> this body:
// a sprite rendered by blender/fish.py, picked by swim phase (tail speed follows swim speed) and
// by yaw (fish turn through a 3/4 and front view instead of flipping), plus pupils drawn on top
// that look at the cursor or whatever the brain is looking at. Static textures only, no repaints.
// Two sheet children per body crossfade between neighbouring frames on one axis at a time
// (phase while swimming, yaw while turning), so 12 frames x 7 yaws read as smooth motion.
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Cairo from 'cairo';
import { makeBrain, think, PERSONALITY, drowsy, lazy, petOf, release } from './brain.js';
import { makeFish, step, blend, drift, spotOf, here, resume, coast } from './steer.js';
import { pt } from './tank.js';

// n: default count (settings override); cruise px/s at full size; burst/coast: wander gait s;
// turn rad/s; school: id; morph: optional colour sheet `<name>-<morph>`; rate: x tail beat;
// rateMin: tail never slower (fluttering pectorals); accel: x cruise px/s² limit; coastG: coast
// gait (0 = stops between bursts); hop: bursts kick off the sand; finRate: tail rate when resting;
// snap: nearest frame, no crossfade (see-through fins double up mid-blend).
const SPECIES = [
    { name: 'clown', n: 2, cruise: 70, burst: 0.4, coast: 2 },
    { name: 'tetra', n: 6, cruise: 90, burst: 0.3, coast: 1.2, school: 'tetra' },
    { name: 'angel', n: 2, cruise: 55, burst: 0.5, coast: 4, turn: 1.6, school: 'angel', morph: 'gold', snap: true },
    { name: 'goldfish', n: 2, cruise: 80, burst: 0.5, coast: 2.5 },
    { name: 'tang', n: 1, cruise: 110, burst: 0.4, coast: 1.5 },
    { name: 'puffer', n: 1, cruise: 50, burst: 0.4, coast: 2 },
    { name: 'cory', n: 3, cruise: 60, burst: 0.3, coast: 2.5, morph: 'albino' },
    { name: 'betta', n: 1, cruise: 45, burst: 0.5, coast: 4, turn: 1.8, morph: 'koi' },
    { name: 'lionfish', n: 1, cruise: 35, burst: 0.3, coast: 5, turn: 1.0, snap: true },
    { name: 'discus', n: 2, cruise: 50, burst: 0.5, coast: 5, turn: 1.2, school: 'discus', accel: 2 },
    { name: 'guppy', n: 5, cruise: 95, burst: 0.2, coast: 0.8, turn: 3, school: 'guppy', rate: 1.4 },
    { name: 'pleco', n: 1, cruise: 40, burst: 0.3, coast: 3, turn: 1.5, coastG: 0, finRate: 0.15 },
    { name: 'mandarin', n: 1, cruise: 30, burst: 0.15, coast: 2.5, turn: 2.5, hop: true, rateMin: 1 },
];
const MAX_N = 8;           // per species, whatever the settings say
const YAW_RATE = 3.5;      // rad/s base swing round through the front view (calibration knob)
const CURL = [0.16, 0.66]; // tail phase that bends the body into a turn, by turn direction
const CURL_ON = 1;         // 0 = no curl while turning
const NOD = 0.14;          // rad nose-down on a bite
const FAR = { scale: 0.7, opacity: 165 };
const SHADOW = 150;        // px above the sand a fish still casts a shadow
const SAVE_EVERY = 60;
const DAY = 864e5;
const GROW = 14;           // days a new fish takes to grow from 0.6 to full size
const THINK = 3;           // brains think every 3rd tick (10 Hz at 30 fps), a third of the fish each tick
const HALF = Math.PI / 2;

// Stored per fish id: {born: ms, fed: count}, shared by every monitor; and per monitor index, where each
// fish was: where[idx][id] = {x, y, dir, at} (steer.js spotOf). Store data is untrusted: anything odd starts fresh.
const valid = (r, now) => Number.isFinite(r?.born) && r.born <= now && Number.isInteger(r?.fed) && r.fed >= 0;
const record = (r, now) => valid(r, now) ? { born: r.born, fed: Math.min(r.fed, 1e6) } : { born: now, fed: 0 };
// ids of fish that can exist (species name + index): a species set to 0 keeps its saved history
const ID = new RegExp(`^(${SPECIES.map(s => s.name).join('|')})[0-7]$`);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const obj = v => v && typeof v === 'object' && !Array.isArray(v) ? v : {};
// Size by age in days: fast at first (the first week shows it), full size at GROW days.
export const grown = days => 0.6 + 0.4 * Math.min(1, Math.log1p(Math.max(0, days)) / Math.log1p(GROW));


// Iris + pupil + one soft highlight, painted once per eye; the actor is moved/squashed per frame.
function paintEye(area, iris) {
    const cr = area.get_context();
    try {
        const [w] = area.get_surface_size(), r = w / 2;
        const c = [1, 3, 5].map(i => parseInt(iris.slice(i, i + 2), 16) / 255), k = f => c.map(v => Math.min(1, v * f));
        const g = new Cairo.RadialGradient(r, r, 0, r, r, r * 0.62);
        g.addColorStopRGBA(0, ...k(1.3), 1);
        g.addColorStopRGBA(0.9, ...k(0.5), 1);
        g.addColorStopRGBA(0.94, ...k(0.95), 1);  // thin lighter ring at the rim
        g.addColorStopRGBA(1, ...k(0.6), 1);
        cr.arc(r, r, r * 0.62, 0, 2 * Math.PI);
        cr.setSource(g);
        cr.fill();
        cr.arc(r, r, r * 0.42, 0, 2 * Math.PI);
        cr.setSourceRGBA(0.03, 0.03, 0.04, 1);
        cr.fill();
        const hx = r - r * 0.2, hy = r - r * 0.24, h = new Cairo.RadialGradient(hx, hy, 0, hx, hy, r * 0.12);
        h.addColorStopRGBA(0, 1, 1, 1, 0.75);
        h.addColorStopRGBA(1, 1, 1, 1, 0);
        cr.arc(hx, hy, r * 0.12, 0, 2 * Math.PI);
        cr.setSource(h);
        cr.fill();
    } finally {
        cr.$dispose();
    }
}

export class School {
    // tank: {fishLayers, swimBounds, glassLayer, sandY(layer), perches, plants, spots, food}; env: {act, curiosity}
    constructor(ctx, tank, env) {
        const b = this._b = tank.swimBounds;
        this._ctx = ctx;
        this._tank = tank;
        this._env = env ?? { act: 1, curiosity: true };
        this._fish = [];
        this._mates = [[], []];   // [{f, b}] per layer, for brains
        this._motion = [[], []];  // motion states per layer, for steering
        this._store = {};  // known fish ids only; anything else in the file is dropped
        this._xy = [0, 0];
        this._w = [0, 0];
        this._k = 0;  // fish made so far: every third non-school fish swims in the far layer
        this._idx = ctx.monitor?.index ?? 0;
        this._spots = {};  // id -> saved spot on this monitor; a fish starts there
        for (const [id, r] of Object.entries(obj(obj(ctx.store.get().where)[this._idx]))) {
            const q = ID.test(id) && spotOf(r);
            if (q) this._spots[id] = q;
        }
        this._sz = Math.min(1, Math.max(0.5, b.h / 1000));  // smaller fish on small screens
        const failed = [];
        for (const sp of SPECIES) this._fill(sp, failed);
        if (failed.length)
            console.warn(`fishtank: fish skipped: ${failed.join(', ')}`);
        this._pickPet();
        this._threats = [];
        const W = ctx.world;
        this._notes = W.notifications;
        this._idle = W.idle;
        this._attnT = 0;
        this._attn = { x: b.x + b.w / 2, y: b.y + 20 };  // where the banner lands
        this._n = 0;
        this._wake = this._news = 0;  // one-shot signals held 2 ticks, so each half of the school sees them once
        this._fedSum = -1;  // -1: save once soon, so first-seen fish keep their birthday
        this._saved = 0;
        this._c = { f: null, p: null, b, mates: null, dt: 0, rand: Math.random, threats: this._threats, food: null,
            feeder: tank.food ?? null, layer: 1, attn: null, attnNew: false, wake: false, drowsy: 1, lazy: 1, night: false,
            act: 1, curiosity: true, spots: null, perches: tank.perches ?? null };
    }

    // Live settings: a count adds or drops fish, a colour remakes that species where its fish were.
    onSettings(keys) {
        const failed = [];
        for (const sp of SPECIES) {
            const mo = keys.includes(`${sp.name}Morph`);
            if (mo) for (const f of this._fish.filter(f => f.sp === sp)) this._remove(f);
            if (mo || keys.includes(sp.name)) this._fill(sp, failed);
        }
        if (failed.length) console.warn(`fishtank: fish skipped: ${failed.join(', ')}`);
        this._pickPet();
    }

    // Makes or drops fish of one species until it matches its setting. Ids stay sp.name + 0..n-1.
    _fill(sp, failed) {
        const S = this._ctx.settings ?? {}, b = this._b, now = Date.now();
        const n = Number.isInteger(S[sp.name]) ? clamp(S[sp.name], 0, MAX_N) : sp.n;
        const have = this._fish.filter(f => f.sp === sp);
        for (const f of have.slice(n)) this._remove(f);
        if (have.length >= n) return;
        const mo = S[`${sp.name}Morph`], want = sp.morph && mo === sp.morph ? `${sp.name}-${mo}` : null;
        let m;
        try {
            m = this._species(want && this._ctx.images[want] ? want : sp.name);
        } catch (e) {
            failed.push(`${sp.name} (${e.message})`);
            return;
        }
        if (want && !this._ctx.images[want]) failed.push(`${want} (not in manifest, normal colours used)`);
        const pers = PERSONALITY[sp.name];
        const bandY = () => b.y + b.h * (pers.band[0] + Math.random() * (pers.band[1] - pers.band[0]));
        // schools start bunched together (by a mate already in, else anywhere), everyone else in their home band
        const lead = have[0]?.s, hx = lead?.x ?? b.x + Math.random() * b.w, hy = sp.school && (lead?.y ?? bandY());
        for (let i = have.length; i < n; i++) {
            try {
                this._spawn(sp, i, m, sp.school ? hx + Math.random() * 80 : b.x + Math.random() * b.w,
                    sp.school ? hy + Math.random() * 40 : bandY(), now);
            } catch (e) {  // bug fix (kept): one bad sheet must not kill the whole scene
                failed.push(`${sp.name} (${e.message})`);
                return;
            }
        }
    }

    _spawn(sp, i, m, x, y, now) {
        const tank = this._tank, id = sp.name + i, bodies = [];
        const layer = sp.school ? 1 : this._spots[id]?.layer ?? (this._k++ % 3 ? 1 : 0);  // a respawn keeps its layer
        try {
            for (const sh of m.sheets) bodies.push(this._makeBody(sh, m, layer, tank.fishLayers[layer]));
        } catch (e) {
            for (const bd of bodies) bd.box.destroy();
            throw e;
        }
        const rec = this._store[id] ??= record(obj(this._ctx.store.get().fish)[id], now);
        const sc = this._sz * (layer ? 1 : FAR.scale) * grown((now - rec.born) / DAY);
        const s = makeFish({
            x, y, cruise: sp.cruise * sc * (0.85 + Math.random() * 0.3), pad: m.len * sc * 0.5,
            school: sp.school, turn: sp.turn, burst: sp.burst, coast: sp.coast, accel: sp.accel, coastG: sp.coastG, hop: sp.hop,
        });
        resume(s, this._spots[id], this._b, now);  // back where it was, moved on for the time it was gone
        const brain = makeBrain(PERSONALITY[sp.name]);
        brain.fed = rec.fed;
        brain.homeIdx = i;
        const shadow = this._ctx.images.shadow && tank.fishLayers[1];
        const f = { id, sp, m, s, sc, layer, brain, ph: Math.random(), ph0: Math.random() * 6.3, yaw: Math.cos(s.dir) > 0 ? 0 : Math.PI,
            goal: 0, yawRate: 0, pitch: 0, bank: 0, nod: 0, nods: 0, swell: 1, faceT: 0, turning: false, ui: -1,
            puff: 0, look: [0, 0], cur: null, rot: null, mirror: null, scale: null, tx: NaN, ty: NaN, it: null, acc: 0, bodies,
            shadow: layer && shadow ? this._makeShadow(m, sc, tank.fishLayers[1]) : null, glass: null };
        f.goal = f.yaw;
        if (sp.name === 'pleco') f.glass = this._makeGlass(tank.glassLayer);
        this._fish.push(f);
        this._mates[layer].push({ f: s, b: brain });
        this._motion[layer].push(s);
    }

    _remove(f) {
        for (const bd of f.bodies) bd.box.destroy();
        f.shadow?.a.destroy();
        f.glass?.a.destroy();
        release(f.brain);  // its claimed food is free again
        this._spots[f.id] = { ...here(f.s, this._b, Date.now()), layer: f.layer };  // comes back here if added again
        this._fish.splice(this._fish.indexOf(f), 1);
        const ms = this._mates[f.layer], mo = this._motion[f.layer];
        ms.splice(ms.findIndex(o => o.f === f.s), 1);
        mo.splice(mo.indexOf(f.s), 1);
    }

    // Sheets (main + puffer's puff) and the largest eye radius, so one eye texture fits every frame.
    // The manifest is untrusted: checked here once, a bad entry drops only this species.
    _species(name) {
        const ctx = this._ctx, e = ctx.images[name];
        if (!e) throw new Error('not in manifest');
        const rows = e.yaws?.length, eye = v => Array.isArray(v) && v.length === 4 && v.every(Number.isFinite);
        if (!rows || !Number.isFinite(e.len) || e.len <= 0 || typeof e.iris !== 'string' || !/^#[0-9a-f]{6}$/i.test(e.iris))
            throw new Error('bad manifest entry');
        const names = e.puff && ctx.images[e.puff]?.eyes ? [name, e.puff] : [name], sheets = names.map(n => ctx.images[n]);
        // frame i = row * cols + col must exist for every yaw row, with eyes for each frame
        if (!sheets.every(sh => pt(sh.anchor) && sh.n === rows * sh.cols && sh.eyes?.length === sh.n &&
            sh.eyes.every(fr => Array.isArray(fr) && fr.every(eye))))
            throw new Error('bad manifest entry');
        let rmax = 1;
        for (const sh of sheets) for (const fr of sh.eyes) for (const v of fr) rmax = Math.max(rmax, v[2]);
        return { sheets: names.map(n => ctx.sheet(n)), rows, rmax, iris: e.iris, len: e.len };
    }

    // One sprite: the sheet's clip box (scaled/rotated/mirrored about the anchor) holding two sheet
    // children (A, B: the two frames being blended), eyes on top. Opacity goes on the children and
    // eyes, never on the box (would force an offscreen pass).
    _makeBody(sh, m, layer, parent) {
        const box = sh.make(), D = Math.ceil(m.rmax * 2), op = layer ? 255 : FAR.opacity;
        box.reactive = false;
        box.visible = false;
        box.set_pivot_point(sh.anchor[0] / sh.w, sh.anchor[1] / sh.h);
        const a = box.get_first_child();
        const b = new Clutter.Actor({ content: a.content, width: a.width, height: a.height, opacity: 0 });
        b.set_content_scaling_filters(Clutter.ScalingFilter.LINEAR, Clutter.ScalingFilter.LINEAR);
        box.insert_child_above(b, a);
        a.opacity = op;
        const eyes = [0, 1].map(() => {
            const e = new St.DrawingArea({ width: D, height: D, reactive: false, visible: false, opacity: op });
            e.set_pivot_point(0.5, 0.5);
            e.connect('repaint', d => paintEye(d, m.iris));
            box.add_child(e);
            return { a: e, on: false, x: NaN, y: NaN, z: NaN, q: NaN };
        });
        parent.add_child(box);
        return { sh, box, eyes, half: D / 2, op, kids: [{ a, f: -1, o: op }, { a: b, f: -1, o: 0 }] };
    }

    // Soft dark ellipse on the sand under a near fish (B's `shadow` still), below every fish.
    _makeShadow(m, sc, parent) {
        const e = this._ctx.image('shadow'), w = m.len * sc * 0.9, h = w / 3;
        const a = new Clutter.Actor({ content: e.content, width: w, height: h, opacity: 0, reactive: false });
        parent.insert_child_at_index(a, 0);
        return { a, w, h, o: 0, x: NaN };
    }

    // The pleco's belly-on-the-glass still, shown in front of everything while it clings.
    _makeGlass(parent) {
        const e = this._ctx.images['pleco-glass'];
        if (!e || !pt(e.anchor) || !parent) return null;
        const a = new Clutter.Actor({ content: this._ctx.image('pleco-glass').content, width: e.w, height: e.h, opacity: 0, reactive: false });
        a.set_pivot_point(e.anchor[0] / e.w, e.anchor[1] / e.h);
        parent.add_child(a);
        return { a, e, x: 0, y: 0, ty: NaN, o: 0, on: false };
    }

    tick(dt, t) {
        const W = this._ctx.world, P = W.pointer, c = this._c, b = this._b, env = this._env, tank = this._tank;
        const night = !(W.lightsOn ?? true);
        c.p = P.over ? P : null;
        c.night = night;
        c.act = env.act ?? 1;
        c.curiosity = env.curiosity !== false;
        c.spots = c.curiosity ? tank.spots ?? null : null;
        c.drowsy = drowsy(night, W.idle);
        c.lazy = lazy(night, W.idle) * c.act;
        this._wake = this._idle > 60 && W.idle < 5 ? THINK : this._wake - 1;
        c.wake = this._wake > 0;
        this._idle = W.idle;
        if (W.notifications > this._notes) { this._news = THINK; this._attnT = 2; } else this._news--;
        c.attnNew = this._news > 0;
        this._notes = W.notifications;
        c.attn = (this._attnT -= dt) > 0 ? this._attn : null;
        this._threatsFrom(W.windows);
        c.food = tank.food?.any ? tank.food.pieces : null;
        c.torch = night && !!c.p && this._ctx.settings?.flashlight !== false;
        const F = tank.flow?.on ? tank.flow : null;
        if (W.gap) for (const f of this._fish) coast(f.s, W.gap, b);  // unseen a while: they swam on meanwhile
        // brains think at 10 Hz, a third of the fish each tick; bodies move every tick
        let fed = 0, j = this._n++;
        for (const f of this._fish) {
            const s = f.s;
            f.acc += dt;
            if (F) {  // a dragged window's current drifts the fish without turning it
                const k = drift(F, s.x, s.y);
                s.x += F.vx * k * dt; s.y += F.vy * k * dt;
            }
            if (j++ % THINK === 0 || !f.it) {
                c.f = s;
                c.mates = this._mates[f.layer];
                c.layer = f.layer;
                c.dt = f.acc;
                f.acc = 0;
                f.it = think(f.brain, c);
            }
            step(s, dt, f.it, b, this._motion[f.layer]);
            this._body(f, dt, t, f.it);
            if (f.layer && tank.plants) this._brush(s, tank.plants, dt);
            fed += f.brain.fed;
        }
        if (fed !== this._fedSum && t - this._saved > SAVE_EVERY) { this._fedSum = fed; this._saved = t; this._save(); }
    }

    // A near fish swimming through a plant pushes it aside (tank.js springs it back).
    _brush(s, plants, dt) {
        for (const p of plants)
            if (Math.abs(s.x - p.x) < s.pad * 0.6 + 8 && s.y < p.y && s.y > p.y - p.h) p.bv += s.vx * 0.6 * dt;
    }

    // Windows that move, slide, or opened less than a second ago.
    _threatsFrom(windows) {
        const th = this._threats;
        th.length = 0;
        for (const w of windows) if (w.moving || w.age < 1 || Math.hypot(w.vx || 0, w.vy || 0) > 20) th.push(w);
    }

    _save() {
        // Every monitor's school shares one store copy and the same fish ids: keep the larger fed count.
        const all = this._ctx.store.get(), prev = obj(all.fish), now = Date.now(), out = {}, where = { ...this._spots };
        for (const [id, r] of Object.entries(prev)) if (ID.test(id) && valid(r, now)) out[id] = { born: r.born, fed: Math.min(r.fed, 1e6) };
        for (const f of this._fish) {
            this._store[f.id].fed = f.brain.fed;
            where[f.id] = here(f.s, this._b, now);
        }
        for (const [id, r] of Object.entries(this._store)) r.fed = Math.max(r.fed, out[id]?.fed ?? 0);
        // keep the tank's other keys and the other monitors' spots
        this._ctx.store.set({ ...all, fish: Object.assign(out, this._store), where: { ...obj(all.where), [this._idx]: where } });
        this._pickPet();
    }

    // The tame favourite: the most-fed fish (store counts, so every monitor picks the same one).
    _pickPet() {
        const i = petOf(this._fish.map(f => this._store[f.id].fed));
        this._fish.forEach((f, k) => { f.brain.pet = k === i; });
    }

    // Yaw swing, tail phase, frame blend, pitch/bank/bob/nod, swell, shadow. Every GI call is
    // cached and skipped when unchanged.
    _body(f, dt, t, it) {
        const { m, s, sp, brain } = f, pers = brain.pers, cruise = s.cruise, rel = Math.min(2, s.speed / cruise);
        // yaw: 0 = facing right, PI/2 = facing the viewer, PI = facing left. Swing through the front.
        // Turns only once the heading is clearly the other way (hysteresis); `face` holds 0.5 s.
        f.faceT = it.face ? 0.5 : f.faceT - dt;
        const c = Math.cos(s.dir), right = f.yaw < HALF;
        if (f.faceT > 0) f.goal = HALF;
        else if (s.speed > cruise * 0.15 || f.goal === HALF) f.goal = right ? (c < -0.3 ? Math.PI : 0) : (c > 0.3 ? 0 : Math.PI);
        const gap = f.goal - f.yaw;
        const rate = clamp(YAW_RATE * (0.5 + rel) * (0.35 + Math.abs(gap) / HALF), 1.5, 7);
        const dy = clamp(gap, -rate * dt, rate * dt);
        f.yaw += dy;
        f.yawRate = dt > 0 ? dy / dt : 0;
        const mirror = f.yaw > HALF, side = mirror ? Math.PI - f.yaw : f.yaw;
        // tail phase: frequency carries speed; glide holds the body straight while coasting; a turn
        // curls the tail into it. Forward-only, so the tail never runs backwards.
        let r = it.chomp ? 2.5 : (0.5 + 2.4 * rel) * (sp.rate ?? 1);
        if (it.fin) r = sp.finRate ?? 0.3;
        r = Math.max(r, sp.rateMin ?? 0);
        const swing = Math.abs(gap) > 0.01;  // 0.05 left a small pop at the end of each turn
        if (swing && CURL_ON) f.ph += Math.min(2 * dt, (CURL[(f.yawRate > 0) !== mirror ? 0 : 1] - f.ph + 1) % 1);
        else if (pers.glide && s.gliding) f.ph += Math.min(r * dt, (0.5 - f.ph % 0.5) % 0.5);
        else f.ph += r * dt;
        // mirrored profile at p = profile at p + 0.5: no pop. Accepted: at the flip the pattern's two
        // flanks swap (left side shown mirrored), invisible on near-symmetric fish, faint on the rest.
        if (mirror !== f.mirror && f.mirror !== null) f.ph += 0.5;
        f.ph %= 1;
        const puffy = f.bodies.length > 1;
        if (puffy) f.puff += ((it.alarm ? 1 : 0) - f.puff) * Math.min(1, dt * (it.alarm ? 3 : 0.3));
        const bd = f.bodies[puffy && f.puff > 0.04 ? 1 : 0], sh = bd.sh, box = bd.box;
        // pleco on the glass: the body hides, the belly still shows in front
        const cling = f.glass && brain.cling > 0;
        if (f.glass) this._glass(f, cling, dt);
        const want = cling ? null : bd;
        if (want !== f.cur) {
            f.cur?.box.hide();
            want?.box.show();
            f.cur = want;
            f.rot = f.mirror = f.scale = null;
            f.tx = f.ty = NaN;  // bug fix: new box kept translation (0,0) until the fish moved
        }
        if (cling) { this._shadow(f, s, false); return; }
        // frame blend on one axis: yaw while swinging, else phase; the axis switches when the phase
        // crosses a whole frame or a swing starts/ends (the curl holds the phase still mid-swing)
        const cols = sh.cols, u = f.ph * cols, ui = Math.floor(u), v = side / HALF * (m.rows - 1);
        if (ui !== f.ui || swing !== f.turning) { f.ui = ui; f.turning = swing && Math.abs(f.yawRate) > 0.3; }
        let ia, ib, bt;
        if (bd !== f.bodies[0]) {  // puff sheet: inflation steps, no blend
            ia = ib = Math.round(v) * cols + Math.round(f.puff * (cols - 1)); bt = 0;
        } else if (f.turning) {
            const r0 = Math.min(m.rows - 2, Math.floor(v)), col = Math.round(u) % cols;
            ia = r0 * cols + col; ib = ia + cols; bt = clamp(v - r0, 0, 1);
        } else {
            const row = Math.round(v) * cols;
            ia = row + ui % cols; ib = row + (ui + 1) % cols; bt = u - ui;
        }
        // tail outrunning the frame clock (a frame or more per tick): blending only smears, show one frame
        if (bt < 0.02 || (!f.turning && r * cols * dt >= 1)) bt = 0;
        else bt = sp.snap ? Math.round(bt) : Math.round(bt * 6) / 6;  // 6 blend steps: far fewer opacity sets, still smooth
        const w = blend(bt, bd.op, this._w);
        this._frame(bd.kids[0], sh, ia, w[0]);
        this._frame(bd.kids[1], sh, ib, w[1]);
        // nose dips into climbs and dives (only as much as the fish is side-on), eased; plus the
        // feeding nod, the bank into a turn and a slow idle bob
        const pg = it.pitch ?? clamp(Math.atan2(Math.sin(s.dir), Math.abs(c)), -0.45, 0.45) * Math.cos(side);
        const e6 = 1 - Math.exp(-6 * dt);
        f.pitch += (pg - f.pitch) * e6;
        f.bank += ((swing ? -0.22 * Math.sin(side) * Math.sign(f.yawRate) : 0) - f.bank) * e6;
        if (brain.nods !== f.nods) {
            f.nods = brain.nods; f.nod = 1;
            if (pers.bottom && f.layer) {  // nosing the sand kicks up a puff at the mouth
                const nx = s.x + (mirror ? -1 : 1) * m.len * f.sc * 0.42, ny = s.y + m.len * f.sc * 0.12;
                this._tank.puff?.(nx - 4, ny); this._tank.puff?.(nx + 4, ny + 2);
            }
        }
        f.nod = Math.max(0, f.nod - dt / 0.3);  // the nod dips and comes back up as one smooth bump (it used to snap down)
        // same angle for both facings (Clutter mirrors after it rotates); the bank flips with the mirror so a turn does not snap
        const ang = f.pitch + (mirror ? -f.bank : f.bank) + Math.sin(Math.PI * (1 - f.nod)) * NOD + 0.02 * Math.sin(t * 0.9 + f.ph0 + 1);
        const rot = Math.round(ang * 229) / 4;  // 0.25 degree steps, set only on change
        if (rot !== f.rot) box.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, f.rot = rot);
        f.swell += ((it.flare ? 1.08 : 1) - f.swell) * Math.min(1, dt / 0.15);  // betta flare
        const sc = Math.round(f.sc * f.swell * 200) / 200;
        if (mirror !== f.mirror || sc !== f.scale) box.set_scale((f.mirror = mirror) ? -(f.scale = sc) : (f.scale = sc), sc);
        const tx = Math.round((s.x - sh.anchor[0]) * 4) / 4;
        const ty = Math.round((s.y - sh.anchor[1] + 1.5 * f.sc * Math.sin(t * 0.9 + f.ph0)) * 4) / 4;
        if (tx !== f.tx || ty !== f.ty) box.set_translation(f.tx = tx, f.ty = ty, 0);  // translation: no relayout
        this._pupils(f, bd, sh.eyes[w[1] > w[0] ? ib : ia], it, mirror, ang, side, dt);
        if (f.shadow) this._shadow(f, s, true);
    }

    _frame(k, sh, i, o) {
        if (o && k.f !== i) { k.f = i; k.a.set_translation(-(i % sh.cols) * sh.w, -Math.floor(i / sh.cols) * sh.h, 0); }
        if (k.o !== o) k.a.set_opacity(k.o = o);
    }

    _shadow(f, s, on) {
        const sd = f.shadow;
        if (!sd) return;
        const y = this._tank.sandY(1), d = y - s.y;
        const o = on && d < SHADOW ? Math.round(90 * (1 - Math.max(0, d) / SHADOW) / 4) * 4 : 0;
        if (o !== sd.o) sd.a.set_opacity(sd.o = o);
        const x = Math.round(s.x - sd.w / 2);
        if (o && x !== sd.x) sd.a.set_translation(sd.x = x, Math.round(y - sd.h / 2), 0);
    }

    // Glass cling: fade the belly still in at a random spot, slide it slowly down, fade out.
    _glass(f, on, dt) {
        const g = f.glass, b = this._b;
        if (on && !g.on) {
            g.x = b.x + b.w * (0.1 + Math.random() * 0.8);
            g.y = b.y + b.h * (0.3 + Math.random() * 0.45);
            g.a.set_scale(Math.random() < 0.5 ? -f.sc : f.sc, f.sc);
            g.a.set_rotation_angle(Clutter.RotateAxis.Z_AXIS, (Math.random() - 0.5) * 50);
            g.ty = NaN;
        }
        g.on = on;
        if (on) g.y += dt;  // 1 px/s slide
        const o = Math.round(clamp(g.o + (on ? 1 : -1) * dt * 2, 0, 1) * 50) / 50, ty = Math.round(g.y - g.e.anchor[1]);
        if (o !== g.o) g.a.set_opacity(Math.round(255 * (g.o = o)));
        if (o && ty !== g.ty) g.a.set_translation(Math.round(g.x - g.e.anchor[0]), g.ty = ty, 0);
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
        this._save();  // every rebuild, lock and monitor change starts the next school where this one left off
    }
}
