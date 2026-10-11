// Self-check for brain.js + steer.js: `gjs -m check.js` or `node check.js`.
import { makeBrain, think, PERSONALITY, NEAR, FAST, SEE, drowsy, lazy } from './brain.js';
import { frameOffset } from '../../render.js';
import { makeFish, step } from './steer.js';

let seed = 1;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const ok = (c, msg) => { if (!c) throw new Error('FAIL: ' + msg); };
const B = { x: 0, y: 0, w: 1600, h: 900 }, dt = 1 / 30;
const dist = (f, p) => Math.hypot(f.x - p.x, f.y - p.y);
const fish = (x, y, pers) => ({ f: makeFish({ x, y, cruise: 60 }, rand), b: makeBrain({ ...PERSONALITY.clown, ...pers }, rand) });
const run = (o, p, mates = [o], w = {}) => step(o.f, dt, think(o.b, { f: o.f, p, b: B, mates, dt, rand, ...w }), B, mates.map(m => m.f), rand);

// flee: a skittish fish next to the cursor ends up well away from it, then calms down
let o = fish(800, 450, { curious: 0 }), p = { x: 760, y: 450, speed: 0 };
run(o, p);
ok(o.b.state === 'flee', 'slow cursor close by scares a skittish fish');
for (let i = 0; i < 60; i++) run(o, p);
ok(dist(o.f, p) > 200, 'flee moves away');
for (let i = 0; i < 30 * 8; i++) run(o, null);
ok(o.b.state !== 'flee', 'panic wears off');

// a fast cursor scares even the most curious fish
o = fish(800, 450, { curious: 1 });
run(o, { x: 700, y: 450, speed: FAST * 3 });
ok(o.b.state === 'flee', 'fast cursor scares');

// panic spreads: a calm neighbour that can't see the cursor flees along with a scared fish
const scared = fish(800, 450, { curious: 0 }), calm = fish(900, 450, { curious: 1 }), duo = [scared, calm];
p = { x: 700, y: 450, speed: 0 };
run(scared, p, duo); run(calm, p, duo);
ok(scared.b.state === 'flee' && calm.b.state === 'flee', 'scare spreads to neighbours');

// habituation: a cursor parked for a while stops being interesting until it moves again
o = fish(800, 450, { curious: 1 });
for (let i = 0; i < 30 * 9; i++) run(o, { x: o.f.x + 600, y: 450, speed: 0 });
run(o, { x: o.f.x + 60, y: o.f.y, speed: 0 });
ok(o.b.state !== 'curious' && o.b.state !== 'flee', 'parked cursor ignored');
run(o, { x: o.f.x + 60, y: o.f.y, speed: 100 });
ok(o.b.state === 'curious', 'moving cursor noticed again');

// curious: approaches to about NEAR, faces the viewer, then gets bored
o = fish(830, 450, { curious: 1 }); p = { x: 600, y: 450, speed: 0 };
let closest = 1e9, faced = false, bored = false;
for (let i = 0; i < 30 * 20; i++) {
    run(o, p);
    if (o.b.state === 'curious') closest = Math.min(closest, dist(o.f, p));
    faced ||= o.b.state === 'curious' && dist(o.f, p) < NEAR + 40;
    bored ||= o.b.state === 'bored';
}
ok(closest < NEAR + 30, 'curious ends near cursor (' + closest.toFixed(0) + ')');
ok(faced && bored, 'curious hovers then loses interest');

// idle restlessness reaches every new behavior; nibbling fish reach the sand and chomp
const seen = new Set();
let chomped = false;
const pair = [fish(400, 300, { gulp: 0.5 }), fish(900, 500, { gulp: 0.5 })];
for (let i = 0; i < 30 * 600; i++) for (const q of pair) {
    const it = think(q.b, { f: q.f, p: null, b: B, mates: pair, dt, rand });
    step(q.f, dt, it, B, pair.map(m => m.f), rand);
    seen.add(q.b.state);
    chomped ||= !!it.chomp && q.f.y > 800;
}
for (const s of ['idle', 'nibble', 'rest', 'follow', 'gulp']) ok(seen.has(s), 'reaches ' + s);
ok(chomped, 'nibble reaches the sand and chomps');

// bounds: a crowd under random cursors (some fast) never leaves the water
const all = [];
for (let i = 0; i < 18; i++) {
    const q = fish(rand() * 1600, rand() * 900, { curious: rand() });
    Object.assign(q.f, { pad: 20, cruise: 30 + rand() * 80, school: i < 8 ? 't' : null });
    if (i === 17) q.b.pers.band = [0.92, 1];
    all.push(q);
}
for (let i = 0; i < 20000; i++) {
    if (i % 90 === 0) p = rand() < 0.3 ? null : { x: rand() * 1600, y: rand() * 900, speed: rand() < 0.2 ? FAST * 2 : 100 };
    for (const q of all) {
        run(q, p, all);
        const g = q.f;
        ok(g.x >= 20 && g.x <= 1580 && g.y >= 20 && g.y <= 880 && Number.isFinite(g.dir + g.speed), 'stays in bounds');
    }
}
// a dragged window over a fish: it flees away from the window's centre
o = fish(800, 450, { curious: 1 });
const win = { x: 700, y: 400, w: 200, h: 100, moving: true };
run(o, null, [o], { threats: [win] });
ok(o.b.state === 'flee', 'moving window scares');
for (let i = 0; i < 60; i++) run(o, null, [o], { threats: [win] });
ok(dist(o.f, { x: 800, y: 450 }) > 150, 'flees the window');

// food: a flake within SEE pulls a fish in and gets eaten within 10 s
o = fish(800, 450, {});
const flake = { x: 800 + SEE * 0.8, y: 500, live: true };
run(o, null, [o], { food: [flake] });
ok(o.b.state === 'feed', 'flake noticed');
for (let i = 0; i < 300 && flake.live; i++) run(o, null, [o], { food: [flake] });
ok(!flake.live && o.b.fed === 1, 'flake eaten');
o = fish(800, 700, {});
const sunk = { x: 805, y: B.h, live: true };  // lying on the floor, below where a fish's centre can go
for (let i = 0; i < 300 && sunk.live; i++) run(o, null, [o], { food: [sunk] });
ok(!sunk.live, 'flake on the floor eaten');

// tameness: 100 flakes eaten halves the chance a slow cursor spooks a fish
const fleeRate = fed => {
    let n = 0;
    for (let i = 0; i < 4000; i++) {
        const q = fish(800, 450, { curious: 0.5 });
        q.b.fed = fed;
        think(q.b, { f: q.f, p: { x: 760, y: 450, speed: 0 }, b: B, mates: [q], dt, rand });
        n += q.b.state === 'flee';
    }
    return n / 4000;
};
const r0 = fleeRate(0), r1 = fleeRate(100);
ok(Math.abs(r1 / r0 - 0.5) < 0.1, `fed fish half as skittish (${r0} -> ${r1})`);

// night: more time resting than by day
const restTime = hour => {
    const duo = [fish(400, 300, {}), fish(900, 500, {})];
    let n = 0;
    for (let i = 0; i < 30 * 600; i++) for (const q of duo) {
        run(q, null, duo, { drowsy: drowsy(hour, 0), lazy: lazy(hour, 0) });
        n += q.b.state === 'rest';
    }
    return n;
};
const day = restTime(12), nightRest = restTime(23);
ok(nightRest > day * 1.5, `rests more at night (${day} -> ${nightRest})`);

// night huddle: a tetra school wanders lower and packs tighter than by day
const school = night => {
    const ts = [];
    for (let i = 0; i < 7; i++) ts.push({ f: makeFish({ x: 700 + i * 30, y: 300, cruise: 60, school: 't' }, rand), b: makeBrain(PERSONALITY.tetra, rand) });
    let y = 0, spread = 0, n = 0;
    for (let i = 0; i < 30 * 120; i++) {
        for (const q of ts) run(q, null, ts, { night });
        if (i < 30 * 30) continue;
        const my = ts.reduce((s, q) => s + q.f.y, 0) / 7, mx = ts.reduce((s, q) => s + q.f.x, 0) / 7;
        y += my; spread += ts.reduce((s, q) => s + Math.hypot(q.f.x - mx, q.f.y - my), 0) / 7; n++;
    }
    return [y / n, spread / n];
};
const [dayY, daySpread] = school(false), [nightY, nightSpread] = school(true);
ok(nightY > dayY + 100 && nightSpread < daySpread, `tetras huddle low and tight at night (y ${dayY | 0} -> ${nightY | 0}, spread ${daySpread | 0} -> ${nightSpread | 0})`);

// sprite frame i = yaw row * cols + phase col, row-major in the sheet, as fish.js indexes it
ok(String(frameOffset({ w: 116, h: 165, cols: 12 }, 3 * 12 + 5)) === String([5 * 116, 3 * 165]), 'frame index is row-major');
console.log('brain + steer ok');
