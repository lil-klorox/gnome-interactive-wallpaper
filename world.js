// Pure (no gi): the per-monitor snapshot scenes read. The host fills `raw` each tick, in global
// coords plus the monitor box (mx, my, mw, mh); update() makes everything monitor-local.
export const makeWorld = () => ({
    pointer: {x: 0, y: 0, speed: 0, over: false, down: false},
    windows: [],  // [{x, y, w, h, moving, id, vx, vy, age}]
    area: {x: 0, y: 0, w: 0, h: 0},  // the work area (no panels/docks), monitor-local
    idle: 0, hour: 0, dark: false, notifications: 0,
    lightsOn: true, warm: false,
    ready: false,  // the host sets it once this monitor's first textures have decoded (or after 3 s)
    _seen: new Map(),  // window id -> {x, y, vx, vy, age, gen}; host-private
    _gen: 0,
});

// raw = {mx, my, mw, mh, px, py, bare, down, rects:[{x,y,w,h,id}], grabbing, idleMs, hour, dark, notes,
//        lights: {on, warm}, area: {x, y, w, h} | null}
export function update(world, raw, dt) {
    const p = world.pointer, x = raw.px - raw.mx, y = raw.py - raw.my;
    const over = raw.bare && x >= 0 && y >= 0 && x < raw.mw && y < raw.mh;
    p.speed = over && p.over ? 0.5 * p.speed + 0.5 * Math.hypot(x - p.x, y - p.y) / Math.max(dt, 0.001) : 0;
    p.x = x;
    p.y = y;
    p.over = over;
    p.down = raw.down;
    // Window motion is smoothed like pointer.speed. Windows already there on this world's first update
    // count as old (age 3600), so a fresh build doesn't treat every window as just opened.
    const seen = world._seen, first = world._gen === 0, gen = ++world._gen, idt = 1 / Math.max(dt, 0.001);
    let n = 0;
    for (const r of raw.rects) {
        const rx = r.x - raw.mx, ry = r.y - raw.my;
        if (rx + r.w <= 0 || ry + r.h <= 0 || rx >= raw.mw || ry >= raw.mh)
            continue;
        let m = seen.get(r.id);
        if (!m) {
            seen.set(r.id, m = {x: rx, y: ry, vx: 0, vy: 0, age: first ? 3600 : 0, gen});
        } else {
            m.vx = 0.5 * m.vx + 0.5 * (rx - m.x) * idt;
            m.vy = 0.5 * m.vy + 0.5 * (ry - m.y) * idt;
            m.age += dt;
            m.x = rx;
            m.y = ry;
            m.gen = gen;
        }
        const o = world.windows[n] ??= {};
        o.x = rx;
        o.y = ry;
        o.w = r.w;
        o.h = r.h;
        o.id = r.id;
        o.moving = r.id === raw.grabbing;
        o.vx = m.vx;
        o.vy = m.vy;
        o.age = m.age;
        n++;
    }
    world.windows.length = n;
    if (seen.size > n) {  // a window left: forget it, so coming back counts as new
        for (const [id, m] of seen) {
            if (m.gen !== gen)
                seen.delete(id);
        }
    }
    if (raw.area) {  // kept as is while the host has none (paused, mid-hotplug)
        const a = world.area;
        a.x = raw.area.x - raw.mx;
        a.y = raw.area.y - raw.my;
        a.w = raw.area.w;
        a.h = raw.area.h;
    }
    world.idle = raw.idleMs / 1000;
    world.hour = raw.hour;
    world.dark = raw.dark;
    world.notifications = Math.max(world.notifications, raw.notes);
    world.lightsOn = raw.lights.on;
    world.warm = raw.lights.warm;
}

// True when the rects {x, y, w, h} together cover all of area a (so tiled windows count too).
// Splits a into vertical strips at every rect edge and checks each strip top to bottom.
export function covers(rects, a) {
    const r = rects.filter(q => q.x < a.x + a.w && q.x + q.w > a.x && q.y < a.y + a.h && q.y + q.h > a.y);
    const xs = [...new Set([a.x, a.x + a.w, ...r.flatMap(q => [q.x, q.x + q.w])])]
        .filter(x => x >= a.x && x <= a.x + a.w).sort((p, q) => p - q);
    for (let i = 0; i + 1 < xs.length; i++) {
        const mid = (xs[i] + xs[i + 1]) / 2;
        let y = a.y;
        for (const q of r.filter(s => s.x < mid && s.x + s.w > mid).sort((p, s) => p.y - s.y)) {
            if (q.y > y)
                break;
            y = Math.max(y, q.y + q.h);
        }
        if (y < a.y + a.h)
            return false;
    }
    return true;
}

// Did anything a sleeping scene could react to change since `last`? Copies the new values into `last`.
export function changed(raw, last) {
    const c = raw.px !== last.px || raw.py !== last.py || raw.down !== last.down || raw.notes !== last.notes ||
        raw.lights.on !== last.on || raw.lights.warm !== last.warm || raw.dark !== last.dark;
    last.px = raw.px;
    last.py = raw.py;
    last.down = raw.down;
    last.notes = raw.notes;
    last.on = raw.lights.on;
    last.warm = raw.lights.warm;
    last.dark = raw.dark;
    return c;
}
