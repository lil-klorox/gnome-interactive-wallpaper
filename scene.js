// Tank scenery: Blender-rendered sprites from assets/scene (made by blender/scene_*.py), composed into
// parallax layers. Art is uploaded once; motion only moves, rotates or swaps the content of actors.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import GLib from 'gi://GLib';
import St from 'gi://St';
import System from 'system';

const DIR = GLib.filename_from_uri(GLib.uri_resolve_relative(import.meta.url, 'assets/scene/', GLib.UriFlags.NONE))[0];
const TAU = Math.PI * 2;
const REF = 1440;        // art is rendered for a 1440 px tall screen; everything below is in those pixels
const SAND = 1150;       // ref row of the sand's back edge
const DRIFT = 22;        // parallax: how far (ref px) the nearest layer sways with the slow camera bob
let warned = false;
const warn = (e, what) => { if (!warned) logError(e, `fishtank: scenery ${what}`); warned = true; };

// Props on the sand, by screen x fraction and the ref row their base sits on; sorted back to front.
const PROPS = [
    ['rock_b', 0.30, 1205, 0.9], ['castle', 0.12, 1222, 1], ['rock_c', 0.235, 1250, 0.8], ['ship', 0.43, 1215, 1],
    ['rock_a', 0.53, 1262, 0.9], ['chest', 0.6, 1290, 1], ['bubbler', 0.71, 1268, 1], ['diver', 0.86, 1255, 1],
    ['rock_d', 0.94, 1300, 1], ['rock_a', 0.03, 1335, 0.7],
];
const SPECIES = ['valli', 'sword', 'jfern', 'cabomba', 'ludwigia', 'anubias'];

function upload(pb) {
    const img = St.ImageContent.new_with_preferred_size(pb.width, pb.height);
    const args = [pb.get_pixels(), pb.has_alpha ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888, pb.width, pb.height, pb.rowstride];
    let ctx = null;
    try { ctx = global.stage.context.get_backend().get_cogl_context(); } catch {}
    if (!(ctx ? img.set_data(ctx, ...args) : img.set_data(...args)))  // GNOME 48+ wants the Cogl context first
        throw new Error('set_data failed');
    return img;
}

export class Scene {
    constructor(root, w, h) {
        const s = h / REF, W = w / s;
        this._anims = [];
        this._pool = [];
        this._tex = new Map();
        this.bytes = 0;
        this._box = new Clutter.Actor({width: w, height: h, clip_to_allocation: true});
        root.add_child(this._box);
        this._box.connect('destroy', () => { this._box = null; });
        this.fishLayers = [0, 1].map(() => new Clutter.Actor({width: w, height: h}));
        this.swimBounds = {x: 0, y: h * 0.06, w, h: h * 0.8};
        try {
            this._m = JSON.parse(new TextDecoder().decode(GLib.file_get_contents(DIR + 'manifest.json')[1]));
        } catch (e) {
            warn(e, 'manifest missing, plain water instead');
            this._box.add_child(new St.Widget({width: w, height: h,
                style: 'background-gradient-direction: vertical; background-gradient-start: #1d5d6c; background-gradient-end: #031a26;'}));
            this.fishLayers.forEach(l => this._box.add_child(l));
            return;
        }
        // one scaled container per depth; k = how much it moves with the camera bob
        const layer = k => {
            const a = new Clutter.Actor({scale_x: s, scale_y: s});
            this._box.add_child(a);
            if (k) this._anims.push(t => { a.translation_x = s * k * DRIFT * Math.sin(t * TAU / 47); });
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
            this._anims.push(t => { a.rotation_angle_z = base + 2.5 * Math.sin(t * 0.06 + ph); a.opacity = 110 + 90 * Math.sin(t * 0.11 + ph); });
        }
        for (const [n, k] of [['far0', 0.2], ['far1', 0.35], ['far2', 0.5]]) {
            const m = this._m[n];
            if (m) this._tile(layer(k), n, -DRIFT, m.yb - m.h, W + 2 * DRIFT, 0);
        }
        const floor = layer(0.75);
        const sand = this._m.sand;
        if (sand) {
            this._tile(floor, 'sand', -DRIFT, REF - sand.h, W + 2 * DRIFT, 0);
            for (const [v, op] of [[7, 150], [-11, 110]]) {
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
        for (let i = 0; i < 10; i++) items.push([null, r(), SAND + 60 + r() * 150, 0.7 + r() * 0.35]);
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
        System.gc();  // the decoded PNGs are only referenced from JS now; free them
    }

    // Texture by sprite name (optionally a row band of it), uploaded once per scene.
    _img(name, y0 = 0, y1 = 0) {
        const key = `${name}:${y0}:${y1}`;
        if (this._tex.has(key)) return this._tex.get(key);
        let img = null;
        try {
            let pb = this._pb?.name === name ? this._pb.pb : GdkPixbuf.Pixbuf.new_from_file(`${DIR}${name}.png`);
            this._pb = {name, pb};
            if (y1) pb = pb.new_subpixbuf(0, y0, pb.width, y1 - y0);
            img = upload(pb);
            this.bytes += pb.width * pb.height * 4;
        } catch (e) {
            warn(e, `art ${name} missing`);
        }
        this._tex.set(key, img);
        return img;
    }

    _actor(parent, img, props) {
        const a = new Clutter.Actor({content: img, ...props});
        a.set_content_scaling_filters(Clutter.ScalingFilter.TRILINEAR, Clutter.ScalingFilter.LINEAR);
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

    // Horizontally repeating strip (side-by-side copies sharing one texture; St.ImageContent can't
    // repeat); vx = drift speed in ref px/s.
    _tile(parent, name, x, y, width, vx) {
        const m = this._m[name], img = m && this._img(name);
        if (!img) return null;
        const a = new Clutter.Actor({x, y});
        parent.add_child(a);
        for (let i = 0; i * m.w < width + (vx ? m.w : 0); i++)
            this._actor(a, img, {x: i * m.w, width: m.w, height: m.h});
        if (vx) this._anims.push(t => { a.translation_x = -(((t * vx) % m.w + m.w) % m.w); });
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
        const holder = new Clutter.Actor({x, y, scale_x: r() < 0.5 ? -k : k, scale_y: k});
        parent.add_child(holder);
        const ph = r() * TAU, sp = 0.35 + r() * 0.25, lean = (r() - 0.5) * 6;
        let par = holder, prevTop = 0;
        for (let i = 0; i < js.length; i++) {
            const top = Math.round(i + 1 < js.length ? js[i + 1][1] : 0), bot = Math.round(i ? js[i][1] + 3 : m.h);
            const img = this._img(name, top, bot);
            if (!img) return;
            const a = this._actor(par, img, i ? {x: 0, y: top - prevTop, width: m.w, height: bot - top}
                : {x: -m.base[0], y: top - m.base[1], width: m.w, height: bot - top});
            a.set_pivot_point(js[i][0] / m.w, (js[i][1] - top) / (bot - top));
            const ai = amp * (0.6 + 0.3 * i), base = i ? 0 : lean;
            this._anims.push(t => { a.rotation_angle_z = base + ai * Math.sin(t * sp + ph - i * 0.6); });
            par = a;
            prevTop = top;
        }
    }

    _bubbles(parent, at) {
        const bm = this._m.bubble, img = bm && this._img('bubble');
        if (!img) return;
        const layer = new Clutter.Actor();
        parent.add_child(layer);
        for (let i = 0; i < 90; i++) {
            const a = this._actor(layer, img, {width: bm.w, height: bm.h, visible: false});
            a.set_pivot_point(0.5, 0.5);
            this._pool.push({a, live: false, x: 0, y: 0, v: 0, vmax: 0, amp: 0, f: 0, ph: 0, k: 0});
        }
        const pt = (n, p) => {
            const a = at[n], m = this._m[n];
            return a && m[p] ? [a.x + m.base[0] + (m[p][0] - m.base[0]) * a.scale_x, a.y + m.base[1] + (m[p][1] - m.base[1]) * a.scale_y] : null;
        };
        const stone = pt('bubbler', 'outlet'), valve = pt('diver', 'valve'), mouth = pt('chest', 'mouth');
        const lid = at.chest && [...Array(10).keys()].map(i => this._img(`chest_lid_${i}`));
        let lidA = null;
        if (lid?.every(Boolean)) {
            const m = this._m.chest;
            lidA = this._actor(parent, lid[0], {x: at.chest.x, y: at.chest.y, width: m.w, height: m.h});
            parent.set_child_above_sibling(lidA, at.chest);
            lidA.set_pivot_point(m.base[0] / m.w, m.base[1] / m.h);
            lidA.set_scale(at.chest.scale_x, at.chest.scale_y);
        }
        const diver = at.diver;
        let next = 0, burst = 0, dnext = 2, frame = 0;
        this._anims.push((t, dt) => {
            if (stone && (next -= dt) <= 0) {
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
            if (diver) diver.rotation_angle_z = 0.8 * Math.sin(t * 0.37);
            if (lidA) {
                const o = Math.max(0, Math.sin(t * 0.22)) ** 3, f = Math.round(o * 9);
                if (f !== frame) lidA.content = lid[frame = f];
                if (mouth && o > 0.7 && Math.random() < o * 0.2) this._emit(mouth[0] + (Math.random() - 0.5) * 60, mouth[1], 0.25 + Math.random() * 0.4);
            }
            for (const b of this._pool) {
                if (!b.live) continue;
                b.v = Math.min(b.vmax, b.v + 50 * dt);
                b.y -= b.v * dt;
                b.a.set_position(b.x + b.amp * Math.sin(t * b.f + b.ph), b.y);
                const g = b.k * (1 + 0.25 * (1 - b.y / SAND));  // bubbles swell a little as they rise
                b.a.set_scale(g, g);
                if (b.y < 40) { b.live = false; b.a.hide(); }
            }
        });
    }

    _emit(x, y, size) {
        const b = this._pool.find(p => !p.live);
        if (!b) return;
        const m = this._m.bubble;
        Object.assign(b, {live: true, x: x - m.w / 2, y: y - m.h / 2, v: 40 + 40 * size, vmax: 140 + 180 * size,
            amp: 4 + 10 * Math.random(), f: 2 + 3 * Math.random(), ph: Math.random() * TAU, k: size});
        b.a.set_scale(size, size);
        b.a.set_position(b.x, b.y);
        b.a.show();
    }

    // Snail creeping between x0 and x1: frames cycle, it only advances while stretching.
    _snail(parent, x0, x1, y) {
        const frames = [...Array(8).keys()].map(i => this._m[`snail_${i}`] && this._img(`snail_${i}`));
        const m = this._m.snail_0;
        if (!m?.base || !frames.every(Boolean)) return;
        const a = this._actor(parent, frames[0], {width: m.w, height: m.h, y: y - m.base[1]});
        a.set_pivot_point(m.base[0] / m.w, 0);
        let x = x0 + (x1 - x0) * 0.3, dir = 1, ph = 0, f = 0, rest = 0;
        this._anims.push((t, dt) => {
            if ((rest -= dt) > 0) return;
            ph += dt * 5;
            const nf = Math.floor(ph) % 8;
            if (nf !== f) a.content = frames[f = nf];
            x += dir * dt * 9 * Math.max(0, Math.sin(ph / 8 * TAU));
            if (x > x1 || x < x0) { dir = -dir; a.scale_x = dir; x = Math.min(x1, Math.max(x0, x)); }
            if (Math.random() < dt / 40) rest = 3 + Math.random() * 6;
            a.x = x - m.base[0];
        });
    }

    tick(dt, t) {
        if (!this._box) return;
        for (const f of this._anims) f(t, dt);
    }

    destroy() {
        this._box?.destroy();
        this._box = this._anims = this._pool = this._tex = this._pb = this.fishLayers = null;
    }
}

// Seeded so the layout is identical on every rebuild.
const rng = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;
