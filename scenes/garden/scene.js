// Sand garden. Hold the left button on bare desktop and drag to rake the sand. Windows sit in it like
// stones: rings get raked around a window once it settles, and dragging one leaves a furrow that fills
// back in. Raked lines fade over hours. Notifications drop a leaf from the branch.
// Strokes and resting leaves are saved per monitor number; after a monitor is plugged in or out a
// number can point at another screen, and that garden then shows there (accepted).
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as S from './sand.js';

const SLOTS = [[0.12, 0.78], [0.6, 0.3], [0.78, 0.84], [0.2, 0.18], [0.5, 0.9]];  // stone spots (screen fractions)
const LANTERN = [0.055, 0.5];
const SAND = '#d6c7a6';                  // under the sand picture, and all there is without it
const SETTLE_S = 300;                    // s between settling steps
const SAVE_AFTER = 2, SAVE_GAP = 10;     // s after a stroke ends; s between saves
const TROUGHS = 8, FILL = 0.93, FILL_STEPS = 40;  // furrows kept; filled by FILL once a second, FILL_STEPS times
const TILES = 4, FIRST_TILES = 6;        // canvas tiles painted per tick (more while the saved garden appears)
const FALL_S = 1.5, SLIDE_S = 0.2, FADE_S = 1, POOL = 14, SWAY = 30;
const LINEAR = Clutter.ScalingFilter.LINEAR;

export default function create(ctx) {
    const {w, h, world, settings: set, images: img} = ctx, s = h / ctx.ref, idx = ctx.monitor.index;
    const now = () => Date.now() / 1000;
    const F = S.makeField(w, h), all = {x0: 0, y0: 0, x1: F.cw, y1: F.ch}, clip = {...all};
    const bb = S.box(), tb = S.box();
    let R = S.profile(set.teeth);
    const warned = new Set();
    const art = name => {
        if (img[name])
            return ctx.image(name);
        if (!warned.has(name))
            console.warn(`interactive-wallpaper: garden has no "${name}" picture, skipped`);
        warned.add(name);
        return null;
    };
    const actor = (parent, e, x, y, props) => {
        const a = new Clutter.Actor({content: e.content, x, y, width: e.w * s, height: e.h * s, ...props});
        a.set_content_scaling_filters(LINEAR, LINEAR);
        parent.add_child(a);
        return a;
    };
    const layer = () => {
        const a = new Clutter.Actor({width: w, height: h});
        ctx.root.add_child(a);
        return a;
    };
    // Put sprite e's `base` point (or its bottom middle) at (x, y); returns the top-left corner.
    const at = (e, x, y) => [x - (e.base?.[0] ?? e.w / 2) * s, y - (e.base?.[1] ?? e.h) * s];
    const footRect = (e, x, y) => Array.isArray(e.foot) && e.foot.length === 4 && e.foot.every(Number.isFinite)
        ? {x: x + e.foot[0] * s, y: y + e.foot[1] * s, w: e.foot[2] * s, h: e.foot[3] * s} : null;

    // Back to front: sand, grooves, border, stones/lantern/branch, leaves, tint, lantern glow.
    ctx.root.add_child(new St.Widget({width: w, height: h, style: `background-color: ${SAND};`}));
    const sand = art('sand');
    if (sand)
        actor(ctx.root, sand, 0, 0, {width: w, height: h, content_repeat: Clutter.ContentRepeat.BOTH});
    const cv = ctx.canvas({w: F.cw, h: F.ch, tile: 128, px: S.CELL})  // small tiles: a stroke repaints less;
    ctx.root.add_child(cv.actor);

    const edge = set.border !== 'none' && art(`edge-${set.border}`), inset = edge ? edge.h * s + 12 : 20;
    if (edge) {
        const eh = edge.h * s, strip = (x, y, len, deg) => actor(ctx.root, edge, x, y,
            {width: len, height: eh, rotation_angle_z: deg, content_repeat: Clutter.ContentRepeat.X_AXIS});
        strip(0, 0, w, 0);
        strip(w, h, w, 180);
        strip(eh, 0, h, 90);
        strip(w - eh, h, h, -90);
    }

    if (set.lines)  // drawn first: stone rings and strokes cut through them
        S.lines(F);
    S.grow(bb, 0, 0, F.cw, F.ch);

    const props = layer(), placed = [];  // stones and lantern, drawn top to bottom so lower ones overlap
    for (let i = 0; i < set.stones; i++) {
        const name = img[`stone-${i + 1}`] ? `stone-${i + 1}` : 'stone-1', e = art(name);
        if (e)
            placed.push({e, x: SLOTS[i][0] * w, y: SLOTS[i][1] * h, moss: art(`moss-${i % 3 + 1}`), side: i % 2 ? 1 : -1});
    }
    const lantern = set.lantern && art('lantern');
    if (lantern)
        placed.push({e: lantern, x: LANTERN[0] * w + lantern.w * s / 2, y: LANTERN[1] * h});
    let glow = null;
    for (const p of placed.sort((a, b) => a.y - b.y)) {
        const [x, y] = at(p.e, p.x, p.y);
        if (p.moss)  // at the stone's foot, half behind it
            actor(props, p.moss, ...at(p.moss, p.x + p.side * (p.e.foot?.[2] ?? p.e.w) * 0.32 * s, p.y + 6 * s));
        actor(props, p.e, x, y);
        const r = footRect(p.e, x, y);
        if (r)
            S.ring(F, r, all, bb, true);
        const g = p.e === lantern && Array.isArray(lantern.light) && art('glow');
        if (g) {
            const gs = 2.4 * s;  // the glow spreads well past the lantern
            glow = {e: g, x: x + lantern.light[0] * s - g.w * gs / 2, y: y + lantern.light[1] * s - g.h * gs / 2, gs};
        }
    }
    const branch = set.season !== 'none' && (img[`branch-${set.season}`] ? art(`branch-${set.season}`) : art('branch-autumn'));
    if (branch)
        actor(props, branch, w - branch.w * s, 0);

    // Leaves: a pool of sprites. st: 0 unused, 1 falling, 2 resting, 3 sliding, 4 fading out.
    const leafName = img[`leaf-${set.season}`] ? `leaf-${set.season}` : 'leaf-autumn';
    const sheet = set.season !== 'none' && art(leafName) ? ctx.sheet(leafName) : null;
    const rest = sheet && Array.isArray(sheet.rest) && sheet.rest.every(i => Number.isInteger(i) && i >= 0 && i < sheet.n)
        ? sheet.rest : [0];
    const anchor = sheet && Array.isArray(sheet.anchor) ? sheet.anchor : sheet ? [sheet.w / 2, sheet.h / 2] : null;
    const leaves = [];
    if (sheet) {
        const ll = layer();
        for (let i = 0; i < POOL; i++) {
            const a = sheet.make();
            a.set_pivot_point(anchor[0] / sheet.w, anchor[1] / sheet.h);
            a.set_scale(s, s);
            a.visible = false;
            ll.add_child(a);
            leaves.push({a, st: 0, t: 0, x: 0, y: 0, x0: 0, y0: 0, x1: 0, y1: 0, r0: 0, r1: 0, f: 0, ph: 0, born: 0});
        }
    }
    const tint = new St.Widget({width: w, height: h, opacity: 0}), shade = new St.Widget({width: w, height: h,
        opacity: 0, style: 'background-color: #000;'});
    ctx.root.add_child(tint);
    ctx.root.add_child(shade);
    const glowA = glow && actor(ctx.root, glow.e, glow.x, glow.y, {width: glow.e.w * glow.gs, height: glow.e.h * glow.gs, opacity: 0});

    let pal = '';
    const palette = () => {
        const {lightsOn, warm, dark} = world, key = `${lightsOn}${warm}${dark}`;
        if (key === pal)
            return;
        pal = key;
        tint.style = `background-color: ${lightsOn ? '#ffaa46' : '#0a1430'};`;
        tint.opacity = !lightsOn ? 120 : warm ? 40 : 0;
        shade.opacity = dark ? 60 : 0;
        if (glowA)
            glowA.opacity = lightsOn ? 0 : warm ? 90 : 180;
    };

    // Saved garden: replay strokes (scaled to this screen size), each as deep as its age leaves it.
    let strokes = [];
    const slot = idx < S.MAX_MONS ? S.readSlot(ctx.store.get().mons?.[idx]) : null;
    const t0 = now(), hours = () => set.settle;
    if (slot) {
        const sx = w / slot.w, sy = h / slot.h, st = S.makeStroke();
        for (const k of slot.strokes) {
            const age = t0 - k.born;
            if (hours() > 0 && age > hours() * 3600)
                continue;
            k.q = S.resample(k.q, sx, sy);
            st.on = false;
            for (let i = 0; i < k.q.length; i += 2)
                S.rakeTo(F, R, st, k.q[i] * S.Q, k.q[i + 1] * S.Q, S.settleFactor(age, hours()), all, bb);
            strokes.push(k);
        }
    }

    // Leaf helpers. A leaf's (x, y) is where its anchor sits on screen.
    const move = l => l.a.set_translation(l.x - anchor[0], l.y - anchor[1], 0);
    const resting = () => leaves.filter(l => l.st === 2 || l.st === 3);
    const land = (l, x, y, f) => {
        Object.assign(l, {st: 2, x, y, f});
        sheet.show(l.a, f);
        l.a.visible = true;
        l.a.opacity = 255;
        move(l);
    };
    if (slot && sheet) {
        slot.leaves.forEach(([x, y, f], i) => {
            const l = leaves.find(q => q.st === 0);
            if (l) {
                land(l, x * w / slot.w, y * h / slot.h, rest.includes(f) ? f : rest[0]);
                l.born = t0 + i;  // keeps the oldest-first order for the 12-leaf limit
            }
        });
    }

    cv.dirty(bb.x0, bb.y0, bb.x1, bb.y1);  // stone rings and the replayed strokes
    let notes = world.notifications, wasDown = world.pointer.down, held = false, cur = null, lastSave = 0, saveAt = 0;
    let lastSettle = t0, n = 0, first = true;
    const stroke = S.makeStroke(), stamped = new Map(), troughs = new Map();
    const save = () => {
        saveAt = 0;
        lastSave = now();
        if (idx >= S.MAX_MONS)
            return;
        const lv = resting().map(l => [Math.round(l.x), Math.round(l.y), l.f]);
        const data = ctx.store.get();
        ctx.store.set(S.fit({...data, mons: {...data.mons, [idx]: S.writeSlot(strokes, lv, w, h, lastSave)}}));
    };
    const later = t => (saveAt = Math.max(t + SAVE_AFTER, lastSave + SAVE_GAP));

    const spawn = () => {
        const a = world.area.w > 0 ? world.area : {x: 0, y: 0, w, h};
        let x = 0, y = 0, ok = false;
        for (let i = 0; i < 10 && !ok; i++) {
            x = a.x + inset + Math.random() * (a.w - 2 * inset);  // never on the border
            y = a.y + inset + Math.random() * (a.h * 2 / 3 - inset);
            ok = !world.windows.some(r => x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h);
        }
        const l = ok && leaves.find(q => q.st === 0);
        if (!l)
            return;
        const lying = resting();
        if (lying.length >= S.MAX_LEAVES) {
            const old = lying.reduce((p, q) => q.born < p.born ? q : p);
            Object.assign(old, {st: 4, t: 0});
        }
        Object.assign(l, {st: 1, t: 0, x0: a.x + Math.random() * a.w, y0: a.y - sheet.h * s, x1: x, y1: y,
            ph: Math.random() * 6.28, r0: 0, r1: Math.random() * 360, born: now()});
        l.a.visible = true;
        l.a.opacity = 255;
        l.a.rotation_angle_z = 0;
    };

    // A rake footprint passing over a resting leaf pushes it to the rake's near side.
    const brush = (px, py, len) => {
        for (const l of leaves) {
            if (l.st !== 2)
                continue;
            const ox = l.x - px, oy = l.y - py, u = -ox * stroke.dy + oy * stroke.dx, along = ox * stroke.dx + oy * stroke.dy;
            if (Math.abs(u) > R.half + 4 || along > R.half || along < -len - R.half)
                continue;
            const push = Math.sign(u || 1) * (R.half + 6) - u;
            Object.assign(l, {st: 3, t: 0, x0: l.x, y0: l.y, x1: l.x - stroke.dy * push, y1: l.y + stroke.dx * push,
                r0: l.a.rotation_angle_z, r1: l.a.rotation_angle_z + 30 * Math.sign(u || 1)});
        }
    };

    const same = (a, b) => a && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
    const fill = (buf, x, y, tw, th) => S.shade(F, buf, x, y, tw, th);

    ctx.onSettings(keys => {
        if (keys.includes('teeth'))
            R = S.profile(set.teeth);
    });

    return {
        tick(dt) {
            const p = world.pointer, a = world.area, t = now();
            n++;
            S.box(bb);
            palette();
            if (a.w > 0) {  // rake and rings stay off the top bar and docks
                clip.x0 = Math.max(0, Math.floor(a.x / S.CELL));
                clip.y0 = Math.max(0, Math.floor(a.y / S.CELL));
                clip.x1 = Math.min(F.cw, Math.ceil((a.x + a.w) / S.CELL));
                clip.y1 = Math.min(F.ch, Math.ceil((a.y + a.h) / S.CELL));
            }

            // Rake: the press has to start on bare sand (a text drag out of a window never rakes);
            // leaving the sand ends the stroke, coming back starts a new one.
            if (!p.down)
                held = false;
            else if (!wasDown && p.over)
                held = true;
            wasDown = p.down;
            if (held && p.over) {
                if (!stroke.on)
                    cur = {born: t, q: []};
                const lx = stroke.x, ly = stroke.y, was = stroke.on;
                S.rakeTo(F, R, stroke, p.x, p.y, 1, clip, bb);
                if (was && sheet)
                    brush(p.x, p.y, Math.hypot(p.x - lx, p.y - ly));
                const q = cur.q;  // a point every GAP px keeps the replay smooth and the save small
                if (q.length === 0 || Math.hypot(p.x - q[q.length - 2] * S.Q, p.y - q[q.length - 1] * S.Q) >= S.GAP)
                    q.push(Math.round(p.x / S.Q), Math.round(p.y / S.Q));
            } else if (stroke.on) {
                stroke.on = false;
                if (cur.q.length >= 4) {
                    strokes.push(cur);
                    S.cap(strokes);
                    later(t);
                }
                cur = null;
            }

            // Windows: a furrow while dragged, rings once settled (one window per tick keeps ticks short).
            let busy = false, ringed = false;
            for (const win of world.windows) {
                if (win.moving) {
                    busy = true;
                    let tr = troughs.get(win.id);
                    if (!tr) {
                        if (troughs.size >= TROUGHS)
                            troughs.delete(troughs.keys().next().value);
                        troughs.set(win.id, tr = {a: {x: win.x, y: win.y, w: win.w, h: win.h}, bb: S.box(), n, steps: 0, next: 0});
                    }
                    tr.n = n;
                    tr.steps = 0;
                    if (!same(tr.a, win)) {
                        S.trough(F, tr.a, win, clip, S.box(tb));
                        S.grow(tr.bb, tb.x0, tb.y0, tb.x1, tb.y1);
                        S.grow(bb, tb.x0, tb.y0, tb.x1, tb.y1);
                        Object.assign(tr.a, {x: win.x, y: win.y, w: win.w, h: win.h});
                    }
                    continue;
                }
                const old = stamped.get(win.id);
                if (same(old, win))
                    continue;
                busy = true;  // a ring is still to come
                if (ringed || win.age < 0.5 || Math.hypot(win.vx, win.vy) >= 2)
                    continue;
                ringed = true;
                S.ring(F, win, clip, bb);
                stamped.set(win.id, {x: win.x, y: win.y, w: win.w, h: win.h});
            }
            if (stamped.size > world.windows.length) {  // a window closed
                for (const id of stamped.keys()) {
                    if (!world.windows.some(q => q.id === id))
                        stamped.delete(id);
                }
            }
            for (const [id, tr] of troughs) {  // released furrows fill back in
                if (tr.n === n || t < tr.next)
                    continue;
                tr.next = t + 1;
                if (tr.steps++ >= FILL_STEPS) {
                    troughs.delete(id);
                    continue;
                }
                S.scale(F, tr.bb.x0, tr.bb.y0, tr.bb.x1, tr.bb.y1, FILL);
                S.grow(bb, tr.bb.x0, tr.bb.y0, tr.bb.x1, tr.bb.y1);
            }

            // Settling, on the wall clock: everything a little flatter every few minutes.
            if (t - lastSettle >= SETTLE_S || t < lastSettle) {
                if (hours() > 0 && t > lastSettle) {
                    S.scale(F, 0, 0, F.cw, F.ch, S.settleFactor(t - lastSettle, hours()));
                    S.grow(bb, 0, 0, F.cw, F.ch);
                    const keep = strokes.filter(k => t - k.born <= hours() * 3600);
                    if (keep.length !== strokes.length) {
                        strokes = keep;
                        later(t);
                    }
                }
                lastSettle = t;
            }

            // Leaves.
            if (world.notifications !== notes) {
                notes = world.notifications;
                if (sheet && set.season !== 'none')
                    spawn();
            }
            for (const l of leaves) {
                if (l.st === 0 || l.st === 2)
                    continue;
                busy = true;
                l.t += dt;
                if (l.st === 1) {
                    const k = Math.min(1, l.t / FALL_S);
                    l.x = l.x0 + (l.x1 - l.x0) * k + Math.sin(k * 9 + l.ph) * SWAY * s * (1 - k);
                    l.y = l.y0 + (l.y1 - l.y0) * k;
                    sheet.show(l.a, Math.floor(l.t * 12 + l.ph) % 16);
                    l.a.rotation_angle_z = l.r1 * k;
                    if (k === 1) {
                        land(l, l.x1, l.y1, rest[Math.floor(Math.random() * rest.length)]);
                        later(t);
                    }
                } else if (l.st === 3) {
                    const k = Math.min(1, l.t / SLIDE_S), e = k * (2 - k);
                    l.x = l.x0 + (l.x1 - l.x0) * e;
                    l.y = l.y0 + (l.y1 - l.y0) * e;
                    l.a.rotation_angle_z = l.r0 + (l.r1 - l.r0) * e;
                    if (k === 1) {
                        l.st = 2;
                        later(t);
                    }
                } else {
                    l.a.opacity = Math.max(0, 255 * (1 - l.t / FADE_S));
                    if (l.t >= FADE_S) {
                        l.st = 0;
                        l.a.visible = false;
                    }
                }
                move(l);
            }

            if (bb.x1 > bb.x0)
                cv.dirty(bb.x0, bb.y0, bb.x1, bb.y1);
            const left = cv.flush(fill, first ? FIRST_TILES : TILES);
            first &&= left > 0;
            if (saveAt && t >= saveAt)
                save();
            return busy || stroke.on || left > 0;
        },
        destroy() {
            if (saveAt)
                save();
        },
    };
}
