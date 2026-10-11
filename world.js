// Pure (no gi): the per-monitor snapshot scenes read. The host fills `raw` each tick, in global
// coords plus the monitor box (mx, my, mw, mh); update() makes everything monitor-local.
export const makeWorld = () => ({
    pointer: {x: 0, y: 0, speed: 0, over: false, down: false},
    windows: [],  // [{x, y, w, h, moving, id}]
    idle: 0, hour: 0, dark: false, notifications: 0,
});

// raw = {mx, my, mw, mh, px, py, bare, down, rects:[{x,y,w,h,id}], grabbing, idleMs, hour, dark, notes}
export function update(world, raw, dt) {
    const p = world.pointer, x = raw.px - raw.mx, y = raw.py - raw.my;
    const over = raw.bare && x >= 0 && y >= 0 && x < raw.mw && y < raw.mh;
    p.speed = over && p.over ? 0.5 * p.speed + 0.5 * Math.hypot(x - p.x, y - p.y) / Math.max(dt, 0.001) : 0;
    p.x = x;
    p.y = y;
    p.over = over;
    p.down = raw.down;
    let n = 0;
    for (const r of raw.rects) {
        const rx = r.x - raw.mx, ry = r.y - raw.my;
        if (rx + r.w <= 0 || ry + r.h <= 0 || rx >= raw.mw || ry >= raw.mh)
            continue;
        const o = world.windows[n] ??= {};
        o.x = rx;
        o.y = ry;
        o.w = r.w;
        o.h = r.h;
        o.id = r.id;
        o.moving = r.id === raw.grabbing;
        n++;
    }
    world.windows.length = n;
    world.idle = raw.idleMs / 1000;
    world.hour = raw.hour;
    world.dark = raw.dark;
    world.notifications = Math.max(world.notifications, raw.notes);
}

// Frame interval: 10 fps once the user has been away a minute.
export const fpsMs = idle => idle > 60 ? 100 : 33;
