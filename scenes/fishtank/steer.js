// Fish motion: turns a brain intent into movement. Knows nothing about moods. Pure math, no gi.

// o: {x, y, cruise px/s, turn rad/s, pad px, school id, burst s, coast s, coastG: coast gait
//     (0 = stops between bursts), accel: x cruise px/s² limit, hop: bursts kick upward (mandarin)}
export function makeFish(o, rand = Math.random) {
    const coast = o.coast ?? 2, dir = rand() < 0.5 ? 0 : Math.PI;
    return {
        x: o.x, y: o.y, dir, speed: o.cruise * 0.5, vx: Math.cos(dir) * o.cruise * 0.5, vy: 0,  // v: cached from dir/speed
        cruise: o.cruise, turn: o.turn ?? 2.2, pad: o.pad ?? 20, school: o.school ?? null,
        wander: rand() * 6.283, wr: 0, burst: o.burst ?? 0.4, coast, beat: rand() * coast, beatLen: coast,
        g: 0.6, coastG: o.coastG ?? 0.6, accel: o.accel ?? 4, hop: !!o.hop, hv: 0,
        gliding: false, rev: false,
    };
}

import { clamp } from '../../engine/bend.js';
// Manifest points are untrusted: one bad point skips that sprite, not the rest of the scenery.
export const pt = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
export const FLOW = 180;  // px from a dragged window's edge its current still reaches

// How hard a dragged window's current {x, y, w, h} pushes the point (x, y): 0.35 at the window, 0 at FLOW px.
export function drift(fl, x, y) {
    const dx = Math.max(fl.x - x, 0, x - fl.x - fl.w), dy = Math.max(fl.y - y, 0, y - fl.y - fl.h);
    return Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / FLOW) * 0.35;
}

// Body crossfade weights (fish.js) for two stacked sprite frames at blend t (0..1): the lower
// frame stays solid until halfway, the upper is fully in by then, so the body never turns
// see-through mid-blend (a plain (1-t, t) split leaves it 75 % opaque at t = 0.5). Below 255 the lower
// frame gives way so the pair sums to op.
export const blend = (t, op, out) => {
    const b = op * Math.min(1, 2 * t);
    out[0] = Math.round(op < 255 ? 255 * (op - b) / (255 - b) : op * Math.min(1, 2 - 2 * t));
    out[1] = Math.round(b);
    return out;
};

// Advance one fish. it = intent from brain.js, b = swim bounds, all = fish sharing its layer.
export function step(f, dt, it, b, all, rand = Math.random) {
    dt = Math.min(dt, 0.1);
    const vx = f.vx, vy = f.vy, top = f.cruise * it.speed;
    const flee = it.ax !== undefined, wander = !flee && it.tx === undefined;
    let ax = 0, ay = 0, coast = false;  // wanted change in velocity, summed from each behaviour

    if (flee) {  // full speed directly away
        const dx = f.x - it.ax, dy = f.y - it.ay, d = Math.sqrt(dx * dx + dy * dy) || 1;
        ax += (dx / d * top - vx) * 2;
        ay += (dy / d * top - vy) * 2;
    } else if (!wander) {  // seek, slowing to a hover on arrival
        const dx = it.tx - f.x, dy = it.ty - f.y, d = Math.sqrt(dx * dx + dy * dy) || 1, s = Math.min(top, d * 1.5) / d;
        ax += (dx * s - vx) * 2;
        ay += (dy * s - vy) * 2;
    } else {  // smooth noisy heading, mostly horizontal; a short tail-beat burst, then a long coast
        f.wr = f.wr * (1 - dt) + (rand() - 0.5) * 6 * (it.noise ?? 1) * dt;
        f.wander += f.wr * dt;
        f.beat += dt;
        if (f.beat > f.burst + f.beatLen) {
            f.beat = 0;
            f.beatLen = f.coast * (0.6 + rand() * 0.8);
            if (f.hop) f.hv -= f.cruise * 0.85;  // a hop off the sand
        }
        coast = f.beat >= f.burst;
        // gait eases between burst and coast instead of switching (0.25 s), so nothing snaps
        f.g += ((coast ? f.coastG : 1.6) - f.g) * (1 - Math.exp(-dt / 0.25));
        const g = top * f.g;
        ax += Math.cos(f.wander) * g - vx;
        ay += Math.sin(f.wander) * g * 0.3 - vy;
    }

    // soft bounds (pad keeps the whole body in; a seek target is trusted), wanderers keep to their band
    const m = 70, x0 = b.x + f.pad, x1 = b.x + b.w - f.pad, y0 = b.y + f.pad, y1 = b.y + b.h - f.pad;
    const push = d => wander || flee ? Math.max(0, d) / m * f.cruise * 3 : 0;
    const px = push(x0 + m - f.x) - push(f.x - (x1 - m)), py = push(y0 + m - f.y) - push(f.y - (y1 - m));
    ax += px;
    ay += py;
    if (wander && it.band) ay += (push(b.y + b.h * it.band[0] - f.y) - push(f.y - b.y - b.h * it.band[1])) * 0.5;

    // separation, school cohesion + alignment, loose shoaling (intent.shoal); mates in the blind spot
    // behind don't pull, so leaders emerge
    const sh = it.shoal ?? 0, cd = Math.cos(f.dir), sd = Math.sin(f.dir);
    let sn = 0, sx = 0, sy = 0, svx = 0, svy = 0, hn = 0, hx = 0, hy = 0, hvx = 0, hvy = 0;  // school, shoal sums
    for (const o of all) {
        if (o === f) continue;
        const dx = f.x - o.x, dy = f.y - o.y, d2 = dx * dx + dy * dy;
        if (d2 > 102400) continue;  // 320 px: past every radius below
        const d = Math.sqrt(d2) || 1, r = f.pad + o.pad + 12;
        if (d < r) { ax += dx / d * (1 - d / r) * f.cruise * 3; ay += dy / d * (1 - d / r) * f.cruise * 3; }
        if (wander && !(f.school && o.school === f.school)) {  // a faint nudge apart so idle fish spread over the tank
            const k = (1 - d / 320) * f.cruise * 0.08;  // ponytail: tune vs shoal pull if fish look lonely or still bunch
            ax += dx / d * k; ay += dy / d * k;
        }
        if ((it.tight ?? 1) <= 1 && (-dx * cd - dy * sd) / d < -0.7) continue;  // a packed school (tight > 1) feels mates behind too
        const ovx = o.vx, ovy = o.vy;
        if (f.school && o.school === f.school) { sn++; sx += o.x; sy += o.y; svx += ovx; svy += ovy; }
        else if (sh) { hn++; hx += o.x; hy += o.y; hvx += ovx; hvy += ovy; }
    }
    if (sn) {
        const k = 0.5 * (it.tight ?? 1);
        ax += (sx / sn - f.x) * k + (svx / sn - vx) * 0.8;
        ay += (sy / sn - f.y) * k + (svy / sn - vy) * 0.8;
    }
    if (hn) {
        ax += (hx / hn - f.x) * 0.06 * sh + (hvx / hn - vx) * 0.25 * sh;
        ay += (hy / hn - f.y) * 0.06 * sh + (hvy / hn - vy) * 0.25 * sh;
    }

    // acceleration limit: starts and stops ramp over ~0.4 s instead of snapping (a dash gets 2x)
    const amax = f.cruise * f.accel * (flee ? 2 : 1) / 2, a = Math.sqrt(ax * ax + ay * ay);
    if (a > amax) { ax *= amax / a; ay *= amax / a; }

    // integrate with a max turn rate: wide lazy arcs in open water, a quick U-turn at the glass,
    // quicker still when dashing
    const nvx = vx + ax * dt * 2, nvy = vy + ay * dt * 2, sp = Math.sqrt(nvx * nvx + nvy * nvy);
    let cap = Math.max(top, f.cruise * 0.3) * 1.6;
    if (sp > 1) {  // hovering in place keeps its heading instead of jittering
        let diff = Math.atan2(nvy, nvx) - f.dir;
        diff = Math.atan2(Math.sin(diff), Math.cos(diff));
        const wall = clamp(Math.max(Math.abs(px), Math.abs(py)) / (f.cruise * 3), 0, 1);
        // (a fish keeping station in its school turns as before, or the school frays)
        const k = wander ? (sn ? 1 : 0.5) + 2.5 * wall : Math.max(1, it.speed / 1.5);
        const maxT = f.turn * k * dt;
        f.dir += clamp(diff, -maxT, maxT);
        f.dir = Math.atan2(Math.sin(f.dir), Math.cos(f.dir));
        // a big reversal brakes into the turn, then bursts out of it
        const rev = wander && Math.abs(diff) > 2.4;
        if (rev) cap *= 0.6;
        else if (f.rev) f.beat = 0;
        f.rev = rev;
    }
    f.speed = Math.min(sp, Math.max(cap, f.speed - amax * 2 * dt));  // a lower speed cap eases in too
    f.gliding = coast && f.g < 0.9 && f.speed > 0.25 * f.cruise;
    f.vx = Math.cos(f.dir) * f.speed;
    f.vy = Math.sin(f.dir) * f.speed;
    f.x = clamp(f.x + f.vx * dt, x0, x1);
    f.y = clamp(f.y + f.vy * dt, y0, y1);
    if (f.hop) {  // the hop rises then sinks back to the sand under its own weight
        f.hv = f.y >= y1 && f.hv > 0 ? 0 : f.hv + f.cruise * 2 * dt;
        f.y = clamp(f.y + f.hv * dt, y0, y1);
    }
}

// Saved fish spot {x, y (fractions of the swim box), dir, at (epoch ms)}: store data is untrusted,
// so anything not a finite number gives null and fractions are clamped.
export const spotOf = r => [r?.x, r?.y, r?.dir, r?.at].every(Number.isFinite)
    ? { x: clamp(r.x, 0, 1), y: clamp(r.y, 0, 1), dir: r.dir, at: r.at } : null;
export const here = (f, b, at) => ({ x: Math.round((f.x - b.x) / b.w * 1e3) / 1e3, y: Math.round((f.y - b.y) / b.h * 1e3) / 1e3,
    dir: Math.round(f.dir * 100) / 100, at });
// Puts f at a saved spot, then on for the time it was away. False (f untouched) when r is odd.
export function resume(f, r, b, now) {
    const p = spotOf(r);
    if (!p) return false;
    f.x = b.x + p.x * b.w;
    f.y = b.y + p.y * b.h;
    f.dir = Math.atan2(Math.sin(p.dir), Math.cos(p.dir));
    coast(f, (now - p.at) / 1000, b);
    return true;
}
// Unseen for sec s: swim on along the heading at a slow cruise (at most 20 s worth), turning off the glass.
const fold = (v, lo, hi) => { const w = Math.max(1, hi - lo), u = ((v - lo) % (2 * w) + 2 * w) % (2 * w); return lo + (u > w ? 2 * w - u : u); };
export function coast(f, sec, b) {
    const d = clamp(sec, 0, 20) * f.cruise * 0.3;
    f.x = fold(f.x + Math.cos(f.dir) * d, b.x + f.pad, b.x + b.w - f.pad);
    f.y = fold(f.y + Math.sin(f.dir) * d, b.y + f.pad, b.y + b.h - f.pad);
    f.vx = Math.cos(f.dir) * f.speed;
    f.vy = Math.sin(f.dir) * f.speed;
}
