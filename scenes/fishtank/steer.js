// Fish motion: turns a brain intent into movement (burst-and-coast wander, seek, flee, bounds,
// depth band, separation, schooling + loose shoaling, turn limits). Knows nothing about moods.
// Pure math, no gi imports.

// o: {x, y, cruise px/s, turn rad/s, pad px, school id, burst s, coast s}
export function makeFish(o, rand = Math.random) {
    const coast = o.coast ?? 2;
    return {
        x: o.x, y: o.y, dir: rand() < 0.5 ? 0 : Math.PI, speed: o.cruise * 0.5,
        cruise: o.cruise, turn: o.turn ?? 2.2, pad: o.pad ?? 20, school: o.school ?? null,
        wander: rand() * 6.283, wr: 0, burst: o.burst ?? 0.4, coast, beat: rand() * coast, beatLen: coast,
    };
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// Advance one fish. it = intent from brain.js, b = swim bounds, all = fish sharing its layer.
export function step(f, dt, it, b, all, rand = Math.random) {
    dt = Math.min(dt, 0.1);
    const vx = Math.cos(f.dir) * f.speed, vy = Math.sin(f.dir) * f.speed, top = f.cruise * it.speed;
    const flee = it.ax !== undefined, wander = !flee && it.tx === undefined;
    let ax = 0, ay = 0;  // wanted change in velocity, summed from each behaviour

    if (flee) {  // full speed directly away
        const dx = f.x - it.ax, dy = f.y - it.ay, d = Math.hypot(dx, dy) || 1;
        ax += (dx / d * top - vx) * 2;
        ay += (dy / d * top - vy) * 2;
    } else if (!wander) {  // seek, slowing to a hover on arrival
        const dx = it.tx - f.x, dy = it.ty - f.y, d = Math.hypot(dx, dy) || 1, s = Math.min(top, d * 1.5) / d;
        ax += (dx * s - vx) * 2;
        ay += (dy * s - vy) * 2;
    } else {  // smooth noisy heading, mostly horizontal; a short tail-beat burst, then a long coast
        f.wr = f.wr * (1 - dt) + (rand() - 0.5) * 6 * dt;
        f.wander += f.wr * dt;
        f.beat += dt;
        if (f.beat > f.burst + f.beatLen) { f.beat = 0; f.beatLen = f.coast * (0.6 + rand() * 0.8); }
        const g = top * (f.beat < f.burst ? 1.6 : 0.6);
        ax += Math.cos(f.wander) * g - vx;
        ay += Math.sin(f.wander) * g * 0.3 - vy;
    }

    // soft bounds (pad keeps the whole body in; a seek target is trusted), wanderers keep to their band
    const m = 70, x0 = b.x + f.pad, x1 = b.x + b.w - f.pad, y0 = b.y + f.pad, y1 = b.y + b.h - f.pad;
    const push = d => wander || flee ? Math.max(0, d) / m * f.cruise * 3 : 0;
    ax += push(x0 + m - f.x) - push(f.x - (x1 - m));
    ay += push(y0 + m - f.y) - push(f.y - (y1 - m));
    if (wander && it.band) ay += (push(b.y + b.h * it.band[0] - f.y) - push(f.y - b.y - b.h * it.band[1])) * 0.5;

    // separation from layer-mates; tight cohesion + alignment with own school, and loose wide
    // shoaling with any species nearby, weighted by intent.shoal. Mates in the blind spot behind
    // don't pull, so leaders emerge.
    const sh = it.shoal ?? 0, school = { n: 0, x: 0, y: 0, vx: 0, vy: 0 }, shoal = { ...school };
    for (const o of all) {
        if (o === f) continue;
        const dx = f.x - o.x, dy = f.y - o.y, d = Math.hypot(dx, dy) || 1, r = f.pad + o.pad + 12;
        if (d < r) { ax += dx / d * (1 - d / r) * f.cruise * 3; ay += dy / d * (1 - d / r) * f.cruise * 3; }
        if ((-dx * Math.cos(f.dir) - dy * Math.sin(f.dir)) / d < -0.7) continue;
        const g = f.school && o.school === f.school && d < 250 ? school : sh && d < 320 ? shoal : null;
        if (!g) continue;
        g.n++; g.x += o.x; g.y += o.y; g.vx += Math.cos(o.dir) * o.speed; g.vy += Math.sin(o.dir) * o.speed;
    }
    for (const [g, c, a] of [[school, 0.5, 0.8], [shoal, 0.06 * sh, 0.25 * sh]]) {
        if (!g.n) continue;
        ax += (g.x / g.n - f.x) * c + (g.vx / g.n - vx) * a;
        ay += (g.y / g.n - f.y) * c + (g.vy / g.n - vy) * a;
    }

    // integrate with a max turn rate (quicker when dashing)
    const nvx = vx + ax * dt * 2, nvy = vy + ay * dt * 2, sp = Math.hypot(nvx, nvy);
    if (sp > 1) {  // hovering in place keeps its heading instead of jittering
        let diff = Math.atan2(nvy, nvx) - f.dir;
        diff = Math.atan2(Math.sin(diff), Math.cos(diff));
        const maxT = f.turn * Math.max(1, it.speed / 1.5) * dt;
        f.dir += clamp(diff, -maxT, maxT);
        f.dir = Math.atan2(Math.sin(f.dir), Math.cos(f.dir));
    }
    f.speed = Math.min(sp, Math.max(top, f.cruise * 0.3) * 1.6);
    f.x = clamp(f.x + Math.cos(f.dir) * f.speed * dt, x0, x1);
    f.y = clamp(f.y + Math.sin(f.dir) * f.speed * dt, y0, y1);
}
