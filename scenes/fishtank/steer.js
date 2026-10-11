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
        const dx = f.x - it.ax, dy = f.y - it.ay, d = Math.sqrt(dx * dx + dy * dy) || 1;
        ax += (dx / d * top - vx) * 2;
        ay += (dy / d * top - vy) * 2;
    } else if (!wander) {  // seek, slowing to a hover on arrival
        const dx = it.tx - f.x, dy = it.ty - f.y, d = Math.sqrt(dx * dx + dy * dy) || 1, s = Math.min(top, d * 1.5) / d;
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
    const sh = it.shoal ?? 0, cd = Math.cos(f.dir), sd = Math.sin(f.dir);
    let sn = 0, sx = 0, sy = 0, svx = 0, svy = 0, hn = 0, hx = 0, hy = 0, hvx = 0, hvy = 0;  // school, shoal sums
    for (const o of all) {
        if (o === f) continue;
        const dx = f.x - o.x, dy = f.y - o.y, d2 = dx * dx + dy * dy;
        if (d2 > 102400) continue;  // 320 px: past every radius below
        const d = Math.sqrt(d2) || 1, r = f.pad + o.pad + 12;
        if (d < r) { ax += dx / d * (1 - d / r) * f.cruise * 3; ay += dy / d * (1 - d / r) * f.cruise * 3; }
        if ((-dx * cd - dy * sd) / d < -0.7) continue;
        const ovx = Math.cos(o.dir) * o.speed, ovy = Math.sin(o.dir) * o.speed;
        if (f.school && o.school === f.school && d < 250) { sn++; sx += o.x; sy += o.y; svx += ovx; svy += ovy; }
        else if (sh) { hn++; hx += o.x; hy += o.y; hvx += ovx; hvy += ovy; }
    }
    if (sn) {
        ax += (sx / sn - f.x) * 0.5 + (svx / sn - vx) * 0.8;
        ay += (sy / sn - f.y) * 0.5 + (svy / sn - vy) * 0.8;
    }
    if (hn) {
        ax += (hx / hn - f.x) * 0.06 * sh + (hvx / hn - vx) * 0.25 * sh;
        ay += (hy / hn - f.y) * 0.06 * sh + (hvy / hn - vy) * 0.25 * sh;
    }

    // integrate with a max turn rate (quicker when dashing)
    const nvx = vx + ax * dt * 2, nvy = vy + ay * dt * 2, sp = Math.sqrt(nvx * nvx + nvy * nvy);
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
