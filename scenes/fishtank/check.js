// Self-check for brain.js + steer.js: `gjs -m check.js` or `node check.js`.
import { makeBrain, think, PERSONALITY, NEAR, FAST } from './brain.js';
import { makeFish, step } from './steer.js';

let seed = 1;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const ok = (c, msg) => { if (!c) throw new Error('FAIL: ' + msg); };
const B = { x: 0, y: 0, w: 1600, h: 900 }, dt = 1 / 30;
const dist = (f, p) => Math.hypot(f.x - p.x, f.y - p.y);
const fish = (x, y, pers) => ({ f: makeFish({ x, y, cruise: 60 }, rand), b: makeBrain({ ...PERSONALITY.clown, ...pers }, rand) });
const run = (o, p, mates = [o]) => step(o.f, dt, think(o.b, { f: o.f, p, b: B, mates, dt, rand }), B, mates.map(m => m.f), rand);

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
console.log('brain + steer ok');
