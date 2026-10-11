// Self-check for steer.js: `gjs -m check.js` or `node check.js`.
import { makeFish, step, NEAR, FAST } from './steer.js';

let seed = 1;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const ok = (c, msg) => { if (!c) throw new Error('FAIL: ' + msg); };
const B = { x: 0, y: 0, w: 1600, h: 900 }, dt = 1 / 30;
const dist = (f, p) => Math.hypot(f.x - p.x, f.y - p.y);

// flee: a skittish fish next to the cursor ends up well away from it
let f = makeFish({ x: 800, y: 450, cruise: 60, curious: 0 }, rand), p = { x: 760, y: 450, speed: 0 };
for (let i = 0; i < 60; i++) step(f, dt, p, B, [f], rand);
ok(dist(f, p) > 200, 'flee moves away');

// curious: approaches to about NEAR, then loses interest
f = makeFish({ x: 830, y: 450, cruise: 60, curious: 1 }, rand); p = { x: 600, y: 450, speed: 0 };
let closest = 1e9, bored = false;
for (let i = 0; i < 30 * 20; i++) {
    step(f, dt, p, B, [f], rand);
    if (f.mode === 'curious') closest = Math.min(closest, dist(f, p));
    bored ||= f.mode === 'bored';
}
ok(closest < NEAR + 30, 'curious ends near cursor (' + closest.toFixed(0) + ')');
ok(bored, 'curious loses interest');

// bounds: a crowd under random cursors (some fast) never leaves the water
const all = [];
for (let i = 0; i < 18; i++) all.push(makeFish({ x: rand() * 1600, y: rand() * 900, cruise: 30 + rand() * 50, pad: 20, curious: rand(), school: i < 8 ? 't' : null, bottom: i === 17 }, rand));
for (let i = 0; i < 20000; i++) {
    if (i % 90 === 0) p = rand() < 0.3 ? null : { x: rand() * 1600, y: rand() * 900, speed: rand() < 0.2 ? FAST * 2 : 100 };
    for (const g of all) {
        step(g, dt, p, B, all, rand);
        ok(g.x >= 20 && g.x <= 1580 && g.y >= 20 && g.y <= 880 && Number.isFinite(g.dir), 'stays in bounds');
    }
}
console.log('steer ok');
