// Fish bodies. Each fish = brain.js (what it wants) -> steer.js (how it moves) -> this body:
// a sprite rendered by blender/fish.py, picked by swim phase (tail speed follows swim speed) and
// by yaw (fish turn through a 3/4 and front view instead of flipping), plus pupils drawn on top
// that look at the cursor or whatever the brain is looking at. Static textures only, no repaints.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Cairo from 'cairo';
import { makeBrain, think, PERSONALITY } from './brain.js';
import { makeFish, step } from './steer.js';

const DIR = GLib.build_filenamev([GLib.path_get_dirname(GLib.filename_from_uri(import.meta.url)[0]), 'assets', 'fish']);

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

// One sheet (rows = yaw angles, columns = frames) -> an St.ImageContent per frame, shared by every
// fish of that species. GNOME 48 wants the Cogl context first; older shells don't take it.
function loadSheet(file, m) {
    const pix = GdkPixbuf.Pixbuf.new_from_file(file);
    if (!pix.get_has_alpha() || pix.get_width() < m.fw * m.frames || pix.get_height() < m.fh * m.yaws.length)
        throw new Error(`bad sheet ${file}`);
    const cogl = global.stage.context?.get_backend?.().get_cogl_context?.();
    const frames = [];
    for (let r = 0; r < m.yaws.length; r++) {
        for (let c = 0; c < m.frames; c++) {
            const sub = pix.new_subpixbuf(c * m.fw, r * m.fh, m.fw, m.fh);
            const img = St.ImageContent.new_with_preferred_size(m.fw, m.fh);
            const args = [sub.read_pixel_bytes(), Cogl.PixelFormat.RGBA_8888, m.fw, m.fh, sub.get_rowstride()];
            try {
                img.set_bytes(cogl, ...args);
            } catch {
                img.set_bytes(...args);
            }
            frames.push(img);
        }
    }
    return frames;
}

// Sheets are shared by every fish of a species and by every School (one per monitor), and
// dropped when the last School lets go.
const sheets = new Map();  // name -> {m, users}

function acquire(name) {
    let e = sheets.get(name);
    if (!e) sheets.set(name, e = { m: loadSpecies(name), users: 0 });
    e.users++;
    return e.m;
}

function release(name) {
    const e = sheets.get(name);
    if (e && --e.users <= 0) sheets.delete(name);
}

function loadSpecies(name) {
    const [, bytes] = GLib.file_get_contents(GLib.build_filenamev([DIR, `${name}.json`]));
    const m = JSON.parse(new TextDecoder().decode(bytes));
    m.img = loadSheet(GLib.build_filenamev([DIR, `${name}.png`]), m);
    if (m.puff) {
        Object.assign(m.puff, { yaws: m.yaws });
        m.puff.img = loadSheet(GLib.build_filenamev([DIR, `${name}-puff.png`]), m.puff);
    }
    m.rmax = Math.max(1, ...[m, m.puff].filter(Boolean).flatMap(s => s.eyes.flat(2).map(e => e[2])));
    return m;
}

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
    constructor(fishLayers, swimBounds) {
        const b = this._b = swimBounds;
        this._fish = [];
        this._mates = [[], []];   // [{f, b}] per layer, for brains
        this._motion = [[], []];  // motion states per layer, for steering
        const S = Math.min(1, Math.max(0.5, b.h / 1000));  // smaller fish on small screens
        const failed = [];
        this._held = [];
        let k = 0;
        for (const sp of SPECIES) {
            let m;
            try {
                m = acquire(sp.name);
                this._held.push(sp.name);
            } catch (e) {
                failed.push(`${sp.name} (${e.message})`);
                continue;
            }
            const pers = PERSONALITY[sp.name];
            const hx = b.x + Math.random() * b.w, hy = b.y + b.h * (pers.band[0] + Math.random() * (pers.band[1] - pers.band[0]));
            for (let i = 0; i < sp.n; i++) {
                const layer = sp.school || k++ % 3 ? 1 : 0, sc = S * (layer ? 1 : FAR.scale);
                const s = makeFish({
                    // schools start bunched together, everyone else anywhere in their home band
                    x: sp.school ? hx + Math.random() * 80 : b.x + Math.random() * b.w,
                    y: sp.school ? hy + Math.random() * 40 : b.y + b.h * (pers.band[0] + Math.random() * (pers.band[1] - pers.band[0])),
                    cruise: sp.cruise * sc * (0.85 + Math.random() * 0.3), pad: m.len * sc * 0.5,
                    school: sp.school, turn: sp.turn, burst: sp.burst, coast: sp.coast,
                });
                const f = { m, s, sc, layer, brain: makeBrain(pers), ph: Math.random(), yaw: Math.cos(s.dir) > 0 ? 0 : Math.PI,
                    puff: 0, look: [0, 0], sheet: null, shown: null, rot: null, mirror: null };
                f.box = new Clutter.Actor({ reactive: false, opacity: layer ? 255 : FAR.opacity });
                f.box.set_content_scaling_filters(Clutter.ScalingFilter.TRILINEAR, Clutter.ScalingFilter.LINEAR);
                const D = Math.ceil(m.rmax * 2);
                f.eyes = [0, 1].map(() => {
                    const e = new St.DrawingArea({ width: D, height: D, reactive: false, visible: false });
                    e.set_pivot_point(0.5, 0.5);
                    e.connect('repaint', a => paintEye(a, m.iris));
                    f.box.add_child(e);
                    return e;
                });
                f.box.connect('destroy', () => { f.box = null; });  // parent torn down under us
                fishLayers[layer].add_child(f.box);
                this._fish.push(f);
                this._mates[layer].push({ f: s, b: f.brain });
                this._motion[layer].push(s);
            }
        }
        if (failed.length)
            console.warn(`fishtank: fish sheets missing or unreadable, skipped: ${failed.join(', ')}`);
    }

    tick(dt, t, pointer) {
        for (const f of this._fish) {
            if (!f.box) continue;
            const s = f.s, it = think(f.brain, { f: s, p: pointer, b: this._b, mates: this._mates[f.layer], dt, rand: Math.random });
            step(s, dt, it, this._b, this._motion[f.layer]);
            this._body(f, dt, it);
        }
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
        if (m.puff) f.puff += ((it.alarm ? 1 : 0) - f.puff) * Math.min(1, dt * (it.alarm ? 3 : 0.3));
        const sh = m.puff && f.puff > 0.04 ? m.puff : m;
        const row = Math.round(side / (Math.PI / 2) * (m.yaws.length - 1));
        const col = sh === m ? Math.floor(f.ph * m.frames) % m.frames : Math.round(f.puff * (sh.frames - 1));
        const box = f.box;
        if (sh !== f.sheet) {
            f.sheet = sh;
            box.set_size(sh.fw, sh.fh);
            box.set_pivot_point(sh.anchor[0] / sh.fw, sh.anchor[1] / sh.fh);
        }
        const i = row * sh.frames + col;
        if (i !== f.shown) {
            f.shown = i;
            box.content = sh.img[i];
        }
        // nose dips into climbs and dives, only as much as the fish is side-on
        const pitch = Math.max(-0.45, Math.min(0.45, Math.atan2(Math.sin(s.dir), Math.abs(c)))) * Math.cos(side);
        const rot = Math.round((mirror ? -pitch : pitch) * 573) / 10;  // 0.1 degree steps, set only on change
        if (rot !== f.rot) box.rotation_angle_z = f.rot = rot;
        if (mirror !== f.mirror) box.set_scale((f.mirror = mirror) ? -f.sc : f.sc, f.sc);
        box.set_translation(s.x - sh.anchor[0], s.y - sh.anchor[1], 0);  // translation: no relayout
        this._pupils(f, sh.eyes[row][col], it, mirror, pitch, side, dt);
    }

    // Pupils look at the brain's look target (cursor, buddy, food), else straight ahead.
    _pupils(f, eyes, it, mirror, pitch, side, dt) {
        const s = f.s;
        let lx = Math.cos(side) * 0.8, ly = 0;
        if (it.look) {
            const dx = it.look.x - s.x, dy = it.look.y - s.y, d = Math.hypot(dx, dy) + 30;
            const a = mirror ? pitch : -pitch;  // undo the box rotation, then the mirror
            lx = (dx * Math.cos(a) - dy * Math.sin(a)) / d * (mirror ? -1 : 1);
            ly = (dx * Math.sin(a) + dy * Math.cos(a)) / d;
        }
        const k = Math.min(1, dt * 8);
        f.look[0] += (lx - f.look[0]) * k;
        f.look[1] += (ly - f.look[1]) * k;
        f.eyes.forEach((e, j) => {
            const v = eyes[j];
            if (e.visible !== !!v) e.visible = !!v;
            if (!v) return;
            const [x, y, r, sq] = v, z = r / f.m.rmax;
            if (e.scale_y !== z || e.scale_x !== z * sq) e.set_scale(z * sq, z);
            e.set_translation(x - e.width / 2 + f.look[0] * r * 0.32 * sq, y - e.height / 2 + f.look[1] * r * 0.32, 0);
        });
    }

    destroy() {
        for (const f of this._fish) f.box?.destroy();
        this._fish = [];
        this._mates = [[], []];
        this._motion = [[], []];
        for (const n of this._held) release(n);
        this._held = [];
    }
}
