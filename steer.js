// Reynolds-style steering for one fish. Pure math, no gi imports (check.js runs it headless).
export const FAST = 1400;  // px/s cursor speed that scares every fish
export const SEE = 260;    // px a fish notices the cursor from
export const NEAR = 80;    // px a curious fish hovers at

export function makeFish(o, rand = Math.random) {
    return {
        x: o.x, y: o.y, dir: rand() < 0.5 ? 0 : Math.PI, speed: o.cruise * 0.5,
        cruise: o.cruise, turn: o.turn ?? 2.2, pad: o.pad ?? 20,
        curious: o.curious ?? 0.5, school: o.school ?? null, bottom: !!o.bottom,
        wander: rand() * 6.283, panic: 0, fx: 0, fy: 0, mode: 'idle', timer: 0, bend: 0,
    };
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// Advance one fish. b = swim bounds, all = fish sharing its layer, p = {x,y,speed} or null.
export function step(f, dt, p, b, all, rand = Math.random) {
    dt = Math.min(dt, 0.1);
    const vx = Math.cos(f.dir) * f.speed, vy = Math.sin(f.dir) * f.speed;
    let ax = 0, ay = 0;  // wanted change in velocity, summed from each behaviour

    // wander: slowly drifting desired heading, mostly horizontal
    f.wander += (rand() - 0.5) * 3 * dt;
    const w = f.mode === 'curious' ? 0.1 : 1;
    ax += (Math.cos(f.wander) * f.cruise - vx) * w;
    ay += ((f.bottom ? 0 : Math.sin(f.wander) * f.cruise * 0.3) - vy) * w;

    // soft bounds (pad keeps the whole body in), bottom dwellers hug the floor
    const m = 70, x0 = b.x + f.pad, x1 = b.x + b.w - f.pad, y0 = b.y + f.pad, y1 = b.y + b.h - f.pad;
    const push = d => Math.max(0, d) / m * f.cruise * 3;
    ax += push(x0 + m - f.x) - push(f.x - (x1 - m));
    ay += push(y0 + m - f.y) - (f.bottom ? 0 : push(f.y - (y1 - m)));
    if (f.bottom) ay += (y1 - 6 - f.y) * 0.8;

    // separation from layer-mates, alignment + cohesion with own school
    let n = 0, cx = 0, cy = 0, avx = 0, avy = 0;
    for (const o of all) {
        if (o === f) continue;
        const dx = f.x - o.x, dy = f.y - o.y, d = Math.hypot(dx, dy) || 1, r = f.pad + o.pad + 12;
        if (d < r) { ax += dx / d * (1 - d / r) * f.cruise * 3; ay += dy / d * (1 - d / r) * f.cruise * 3; }
        if (f.school && o.school === f.school && d < 250) {
            n++; cx += o.x; cy += o.y;
            avx += Math.cos(o.dir) * o.speed; avy += Math.sin(o.dir) * o.speed;
        }
    }
    if (n) {
        ax += (cx / n - f.x) * 0.5 + (avx / n - vx) * 0.8;
        ay += (cy / n - f.y) * 0.5 + (avy / n - vy) * 0.8;
    }

    // cursor: notice -> roll curious vs flee once; fast cursor scares everyone
    if (p) {
        const d = Math.hypot(f.x - p.x, f.y - p.y);
        if (p.speed > FAST && d < SEE * 1.5) {
            f.panic = 1; f.mode = 'bored'; f.timer = 3;
        } else if (f.mode === 'idle' && d < SEE) {
            if (rand() < f.curious) { f.mode = 'curious'; f.timer = 3 + rand() * 3; } else { f.panic = 1; f.mode = 'bored'; f.timer = 4; }
        }
        if (f.panic > 0.05 && d < SEE * 1.5) { f.fx = p.x; f.fy = p.y; }
        if (f.mode === 'curious') {
            const dx = f.x - p.x, dy = f.y - p.y, dd = Math.hypot(dx, dy) || 1;
            const tx = p.x + dx / dd * NEAR - f.x, ty = p.y + dy / dd * NEAR - f.y;
            const s = Math.min(1.5 * f.cruise, Math.hypot(tx, ty) * 1.5) / (Math.hypot(tx, ty) || 1);
            ax += (tx * s - vx) * 2; ay += (ty * s - vy) * 2;
        }
    }
    if (f.mode !== 'idle' && (f.timer -= dt) <= 0) {
        if (f.mode === 'curious') { f.mode = 'bored'; f.timer = 6; } else f.mode = 'idle';
    }

    // flee: fast burst away from where the cursor was, decaying over ~2.5s
    if (f.panic > 0.05) {
        const dx = f.x - f.fx, dy = f.y - f.fy, d = Math.hypot(dx, dy) || 1;
        ax += (dx / d * f.cruise * 5 - vx) * f.panic * 2;
        ay += (dy / d * f.cruise * 5 - vy) * f.panic * 2;
    }
    f.panic = Math.max(0, f.panic - dt * 0.4);

    // integrate with a max turn rate; bend = normalized turn rate for the body curl
    const nvx = vx + ax * dt * 2, nvy = vy + ay * dt * 2;
    let diff = Math.atan2(nvy, nvx) - f.dir;
    diff = Math.atan2(Math.sin(diff), Math.cos(diff));
    const maxT = f.turn * (1 + 2 * f.panic) * dt, turn = clamp(diff, -maxT, maxT);
    f.dir = Math.atan2(Math.sin(f.dir + turn), Math.cos(f.dir + turn));
    f.bend += (turn / (f.turn * dt) - f.bend) * Math.min(1, dt * 6);
    f.speed = Math.min(Math.hypot(nvx, nvy), f.cruise * (1.6 + 4 * f.panic));
    f.x = clamp(f.x + Math.cos(f.dir) * f.speed * dt, x0, x1);
    f.y = clamp(f.y + Math.sin(f.dir) * f.speed * dt, y0, y1);
}
