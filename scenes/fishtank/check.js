// Self-check for brain.js + steer.js, food.js and critters.js: `gjs -m check.js` or `node check.js`.
import { Food, POOL, hand, gesture, TAP_S, HOLD_S, POUR_S } from './food.js';
import { Critters, plan, readTank, dayOf, EVENTS, LOG } from './critters.js';
import { makeBrain, think, PERSONALITY, NEAR, FAST, SEE, drowsy, lazy } from './brain.js';
import { makeFish, step, drift, FLOW } from './steer.js';

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
for (let i = 0; i < 15; i++) { run(scared, p, duo); run(calm, p, duo); }  // the neighbour bolts after a short startle delay
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

// feeding is checked in fish-check.js (claims, bites, bottom feeders) against food.js's piece shape

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
        run(q, null, duo, { drowsy: drowsy(hour >= 21, 0), lazy: lazy(hour >= 21, 0) });
        n += q.b.state === 'rest';
    }
    return n;
};
const day = restTime(12), nightRest = restTime(23);
ok(nightRest > day * 1.5, `rests more at night (${day} -> ${nightRest})`);

// night huddle: a tetra school wanders lower and packs tighter than by day (median of fixed seeds)
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
// median over fixed seeds: one school's two minutes is noisy, and a school that splits makes one huge spread
const avg = night => {
    const r = [];
    for (let k = 1; k <= 12; k++) { seed = k * 7919; r.push(school(night)); }
    const med = i => r.map(v => v[i]).sort((x, y) => x - y)[6];
    return [med(0), med(1)];
};
const [dayY, daySpread] = avg(false), [nightY, nightSpread] = avg(true);
// the night pull (tight 2) is small next to wander noise, so only a school scattering apart fails here
ok(nightY > dayY + 100 && nightSpread < daySpread * 0.85, `tetras huddle low and tight at night (y ${dayY | 0} -> ${nightY | 0}, spread ${daySpread | 0} -> ${nightSpread | 0})`);
console.log('brain + steer ok');

// ---- food + critters, on stub actors (any method is a no-op) ----
const stub = o => new Proxy(o, { get: (t, k) => k in t ? t[k] : () => {} });
const actor = () => {
    const a = { visible: true, _c: stub({}), parent: null, add_child(k) { k.parent = a; }, remove_child(k) { k.parent = null; },
        get_parent() { return a.parent; }, get_first_child() { return a._c; } };
    return stub(a);
};
const img = (w, h, extra = {}) => ({ w, h, n: 1, cols: 1, ...extra });
const IMAGES = {
    food: img(20, 20, { n: 32, cols: 8, anchor: [10, 10] }), crumb: img(8, 8),
    jelly: img(70, 80, { n: 12, cols: 12, anchor: [35, 2], mouth: [35, 50] }), jelly_tent_0: img(20, 140, { base: [10, 138], j1: [10, 70] }),
    garden_eel: img(20, 130, { n: 12, cols: 12, base: [10, 128] }),
    moray_head: img(60, 30, { n: 6, cols: 6, anchor: [4, 15] }), moray_seg: img(28, 26), moray_tail: img(50, 20, { anchor: [2, 10] }),
    seahorse: img(30, 60, { n: 24, cols: 12, anchor: [20, 10] }), shrimp: img(35, 20, { n: 12, cols: 12, base: [18, 19] }),
    hermit: img(60, 50, { n: 12, cols: 12, base: [30, 48] }),
    shrimp_shell: img(57, 16, { base: [26, 13] }), egg_cluster: img(20, 26, { base: [8, 25] }),
    turtle: img(200, 90, { n: 12, cols: 12, anchor: [100, 45] }), shark: img(520, 160), fry: img(18, 8, { n: 8, cols: 8, anchor: [9, 4] }),
};
const world = { pointer: { x: 0, y: 0, speed: 0, over: false, down: false }, windows: [], hour: 12, idle: 0, lightsOn: true };
let saved = {};
const store = { get: () => saved, set: o => { saved = o; } };
const ctxOf = images => ({ w: 1600, h: 900, ref: 1440, images, world, store, sheet: n => ({ ...images[n], make: actor, show() {} }) });
// same shape as tank.js: near band from the swim box's bottom down, far band on a wavy back edge
const tankOf = () => {
    const b = { x: 0, y: 54, w: 1600, h: 720 };
    return { swimBounds: b, ground: (l, x, z) => l ? 774 + z * 72 : 700 + 10 * Math.sin(x / 100) + z * 20,
        tops: [{ x0: 1100, x1: 1200, y: 600 }], fishLayers: [actor(), actor()], mid: actor(), far: [actor(), actor(), actor()],
        spots: [], perches: [{ x: 300, y: 700 }, { x: 900, y: 690 }], plants: [{ x: 300, y: 780, h: 200 }], chain: () => [actor(), actor()],
        ship: { hole: { x: 700, y: 760 }, actor: actor() } };
};
const ON = { jelly: true, gardenEels: true, moray: true, seahorse: true, shrimp: true, hermit: true, visitors: true };

// food: a pinch sinks in its own layer, rocks, lands at its own depth in that layer's sand band (no
// ruler-straight line of leftovers), sinks in a touch, then fades away
let tk = tankOf(), food = tk.food = new Food(ctxOf(IMAGES), tk, rand);
food.drop(800, 100, 9);
ok(food.pieces.filter(q => q.live).length === 9, 'drop makes n pieces');
let fallX = 0, landed = new Set(), dropped = food.pieces.filter(q => q.live);
for (let i = 0; i < 30 * 150; i++) {
    food.tick(dt);
    for (const q of dropped) {
        if (q.live && !q.settled) fallX = Math.max(fallX, Math.abs(q.x - 800));
        if (q.settled && !landed.has(q)) { ok(Math.abs(q.y - tk.ground(q.layer, q.x, q.z) - 2) < 1e-6, 'lands on the floor at its own depth'); landed.add(q); }
    }
}
const ys = dropped.filter(q => q.layer).map(q => q.y);
ok(landed.size === 9 && new Set(dropped.map(q => q.layer)).size === 2, 'every piece lands, in both depths');
ok(Math.max(...ys) - Math.min(...ys) > 15, 'near leftovers spread over the sand, not one line');
ok(fallX < 60, `flakes rock in place, no runaway drift (${fallX | 0} px)`);
food.drop(800, 840, 4);  // click on the front sand: food stays where it was dropped
ok(food.pieces.filter(q => q.live && !q.settled).every(q => q.layer === 1 && q.z > 0.5), 'front-sand click drops near, low in the band');
for (let i = 0; i < 5; i++) food.tick(dt);
ok(food.pieces.filter(q => q.live && q.born >= 9).every(q => q.settled && q.y > 800), 'and it lies there, no jump up to the floor line');
food.farShare = 0;
food.drop(400, 100, 6);
ok(food.pieces.filter(q => q.live && q.born >= 13).every(q => q.layer === 1), 'no far fish: all food falls near');
// a piece over the rock top rests there, then slides off and falls on to the sand
food.drop(1150, 400, 1);
const pr = food.pieces.find(q => q.live && q.born === 19);
pr.x = 1150; pr.layer = 1; pr.kind = 3;
let perched = false;
for (let i = 0; i < 30 * 40; i++) { food.tick(dt); perched ||= pr.perch > 0 && pr.y === 600; }
ok(perched && pr.settled && pr.y > 770, 'food rests on a rock top, then slides off onto the sand');
for (let i = 0; i < 30 * 100; i++) food.tick(dt);
food.drop(800, 700, 1);
for (let i = 0; i < 30 * 10; i++) food.tick(dt);
const p0 = food.pieces.find(q => q.live);
ok(food.bite(p0) && food.bite(food.pieces.indexOf(p0)) && p0.live && food.bite(p0) && !p0.live && !food.bite(p0), 'third bite finishes a piece, a dead one cannot be bitten');
for (let i = 0; i < 30 * 46; i++) food.tick(dt);
ok(!food.any && food.pieces.every(q => !q.live), 'settled food fades away');
food.drop(800, 760, POOL);
for (let i = 0; i < 30 * 10; i++) food.tick(dt);
const oldest = food.pieces.reduce((a, q) => q.born < a.born ? q : a);
oldest.claims = 2;
food.drop(400, 100, 1);
ok(food.pieces.every(q => q.live) && oldest.x < 500 && oldest.claims === 0 && !oldest.settled, 'full pool reuses the oldest settled piece, fresh');
food = new Food(ctxOf({}), tk, rand);  // no art: still drops and fades, nothing to draw
food.drop(800, 760, 3);
for (let i = 0; i < 30 * 90; i++) food.tick(dt);
ok(!food.any, 'food without art still runs');

// critters: all present, jellies stay in the top part, the moray goes out and comes home, eels hide
tk = tankOf();
tk.food = new Food(ctxOf(IMAGES), tk, rand);
let cr = new Critters(ctxOf(IMAGES), tk, ON, { act: 1 }, rand);
ok(cr.list.length === 8, `every critter with art is built (${cr.list.length})`);
const vis = cr.list.find(k => k.V);
for (const v of vis.V) v.due = 0;
let crossed = 0;
for (let i = 0; i < 30 * 120; i++) { cr.tick(dt, i * dt); crossed += vis.V.filter(v => !v.on && v.due > 500).length; }
ok(vis.V.length === 3 && crossed > 0 && vis.V.every(v => v.on || v.due > 0), 'visitors cross and get rescheduled');
const jel = cr.list.find(k => k.all?.[0]?.bell), mor = cr.list.find(k => k.M), eel = cr.list.find(k => k.all?.[0]?.mir);
const b0 = tk.swimBounds;
let jLow = 0, wentOut = false, home = false, maxSpots = 0, jSpot = null, sameSpot = true;
mor.M.timer = 1;
for (let i = 0; i < 30 * 600; i++) {
    cr.tick(dt, i * dt);
    for (const J of jel.all) { jLow = Math.max(jLow, J.y); ok(Number.isFinite(J.x + J.y) && J.y >= b0.y + 40, 'jelly in the water'); }
    wentOut ||= mor.M.st === 'out' && mor.M.L > 100;
    home ||= wentOut && mor.M.st === 'peek';
    ok(Number.isFinite(mor.M.L + mor.M.x + mor.M.y) && mor.M.L >= 0, 'moray path sane');
    maxSpots = Math.max(maxSpots, tk.spots.length);
    const js = jel.all[0].spot;
    sameSpot &&= !jSpot || js === jSpot;
    jSpot = js;
}
ok(sameSpot && tk.spots.includes(jSpot) && jSpot.on, 'a critter keeps one spot object');
ok(jLow <= b0.y + 0.6 * b0.h, 'jellies stay above mid-tank');
ok(wentOut && home, 'moray goes out and returns home');
ok(maxSpots >= 4 && tk.spots.every(q => Number.isFinite(q.x + q.y)), 'visible critters become spots');
ok(eel.all.every(E => E.st === 'out'), 'eels come out');
world.pointer = { x: eel.all[0].x * 900 / 1440, y: (eel.all[0].y - 60) * 900 / 1440, speed: FAST, over: true, down: false };
for (let i = 0; i < 15; i++) cr.tick(dt, 0);
ok(eel.all.every(E => E.st === 'wait' && E.f === 0), 'a fast cursor sends the eels into the sand');
world.pointer.over = false;
for (let i = 0; i < 30 * 15; i++) cr.tick(dt, 0);
ok(eel.all.every(E => E.st === 'out'), 'and they come back out');
// shrimp and the hermit eat food lying on the front sand near them, never far-layer food
tk.food.farShare = 1;
tk.food.drop(tk.plants[0].x, 300, 3);  // falls in the far layer: left alone
tk.food.drop(tk.plants[0].x, 790, 3);  // front sand by the shrimp
for (let i = 0; i < 30 * 40; i++) { tk.food.tick(dt); cr.tick(dt, i * dt); }
const fresh = tk.food.pieces.filter(q => q.born >= tk.food._seq - 6);
ok(fresh.filter(q => q.layer === 0).every(q => q.bites === 0), 'far-layer food is not theirs');
ok(fresh.some(q => q.layer === 1 && (q.bites > 0 || !q.live)), 'shrimp eat food on the sand by them');
// nothing on: no art, no perches, no ship
cr = new Critters(ctxOf({}), { ...tankOf(), perches: [], plants: [], ship: null }, ON, { act: 1 }, rand);
cr.tick(dt, 0);
ok(cr.list.length === 0, 'missing art skips critters without throwing');
// jellies turn back before the side glass instead of sliding along it
cr = new Critters(ctxOf(IMAGES), tk, ON, { act: 1 }, rand);
{
    const J = cr.list.find(k => k.all?.[0]?.bell).all[1];
    J.x = tk.swimBounds.x + 25; J.px = 0;
    let minX = J.x;
    for (let i = 0; i < 30 * 30; i++) { cr.tick(dt, i * dt); minX = Math.min(minX, J.x); }
    ok(minX > tk.swimBounds.x + 15 && J.x > tk.swimBounds.x + 100, `jelly pushed off the wall (${J.x | 0})`);
}
// seahorse at rest snatches a piece sinking past its snout
{
    const sea = cr.list.find(k => k.all?.[0]?.pi !== undefined), H = sea.all[0];
    for (const p of tk.food.pieces) p.live = false;
    tk.food.drop(0, 0, 1);
    const q = tk.food.pieces.find(p => p.live);
    H.st = 'rest'; H.timer = 99; H.scan = 0; q.layer = 1; q.x = H.x + 10; q.y = H.y + 10; q.settled = true;
    tk.food.tick(dt);
    let snapped = false;
    for (let i = 0; i < 20; i++) { cr.tick(dt, 0); snapped ||= H.st === 'snap'; }
    ok(snapped && q.bites === 1 && H.st === 'rest', `seahorse snaps up passing food`);
}

// daily events: the pick is seeded by the day (every monitor agrees), varies across days, stays in range
{
    const a = plan(20000, EVENTS), b = plan(20000, EVENTS), kinds = new Set();
    ok(JSON.stringify(a) === JSON.stringify(b), 'same day, same pick');
    for (let d = 20000; d < 20028; d++) {
        const p = plan(d, EVENTS);
        kinds.add(p.event);
        ok(p.at >= 480 && p.at < 1200 && p.t === 0, 'due 8:00-20:00');
    }
    ok(kinds.size === EVENTS.length, 'every kind turns up within four weeks');
    ok(plan(1, []).event === '' && plan(1, ['yawn']).event === 'yawn', 'picks only from what this tank has');
    ok(readTank({ day: 1, event: 'nope', at: 0, t: 0, x: 0, log: [] }) === null && readTank('x') === null, 'odd store data dropped');
    const long = readTank({ day: 9, event: 'fry', at: 600, t: 0, x: 0, log: [...Array(12).keys()].map(d => ({ day: `2026-10-${String(d + 10)}`, kind: 'fry' })).concat([{ day: 9, kind: 'fry' }]) });
    ok(long.log.length === LOG && long.log[LOG - 1].day === '2026-10-21', 'log keeps the last week');
    // due now: the shrimp moults, the event is logged once, and a second monitor shows the shell too
    const today = dayOf(Date.now());
    saved = { fish: { clown0: { born: 1, fed: 3 } }, tank: { day: today, event: 'moult', at: 0, t: 0, x: 0, log: [] } };
    cr._shown = -1;  // the 2 s timer may already have fired today's real pick during the ticks above
    cr._daily();
    const R0 = cr.list.find(k => k.all?.[0]?.y0 !== undefined).all[0];
    ok(R0.st === 'moult' && saved.tank.t > 0 && saved.tank.log.length === 1 && saved.tank.log[0].kind === 'moult' && saved.fish.clown0, 'event fires, logged, other keys kept');
    cr._daily();
    ok(saved.tank.log.length === 1, 'fires once a day');
    for (let i = 0; i < 30 * 6; i++) cr.tick(dt, 0);
    ok(R0.st !== 'moult', 'shrimp walks off after its moult');
    const cr2 = new Critters(ctxOf(IMAGES), tk, ON, { act: 1 }, rand);
    cr2._daily();
    ok(cr2._shown === today && saved.tank.log.length === 1, 'second monitor shows it without logging again');
    ok(new Critters(ctxOf(IMAGES), tk, { ...ON, events: false }, { act: 1 }, rand)._daily() === undefined, 'events off: nothing');
}

// pointer gestures: click drops, a quick second click close by taps, holding pours at a steady rate
{
    const g = hand(), P = { x: 500, y: 300, down: false, over: true }, seq = [];
    const run = (down, s) => { P.down = down; for (let t = 0; t < s - 1e-9; t += dt) { const e = gesture(g, P, dt); if (e) seq.push(e); } };
    run(true, dt); run(false, 0.2); run(true, dt); run(false, 1);
    ok(String(seq) === 'drop,tap', `double click taps (${seq})`);
    seq.length = 0; run(true, dt); run(false, TAP_S + 0.1); run(true, dt); run(false, 1);
    ok(String(seq) === 'drop,drop', 'two slow clicks are two drops');
    seq.length = 0; run(true, dt); run(false, 0.1); P.x += 40; run(true, dt); run(false, 1);
    ok(String(seq) === 'drop,drop', 'two clicks far apart are two drops');
    seq.length = 0; run(true, 2); run(false, 0.5);
    const pours = seq.filter(e => e === 'pour').length, want = (2 - HOLD_S) / POUR_S;
    ok(seq[0] === 'drop' && Math.abs(pours - want) <= 1.5, `hold pours ~${want | 0} pieces in 2 s (${pours})`);
    seq.length = 0; P.over = false; run(true, 2);
    ok(seq.length === 0, 'button held off the desktop (window drag) does nothing');
}

// window current: full push at the window, fading to nothing FLOW px away
{
    const w = { x: 100, y: 100, w: 200, h: 100 };
    ok(drift(w, 150, 150) === 0.35 && Math.abs(drift(w, 300 + FLOW / 2, 150) - 0.175) < 1e-9 && drift(w, 300 + FLOW, 150) === 0 && drift(w, 150, 200 + FLOW + 5) === 0, 'current falloff');
}
console.log('food + critters ok');
await import('./fish-check.js');
