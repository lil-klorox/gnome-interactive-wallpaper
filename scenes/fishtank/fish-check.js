// Fish-side asserts (brain feeding/startle, steer limits, body blend): `node fish-check.js`,
// `gjs -m fish-check.js`, or imported by check.js. No gi.
import { makeBrain, think, flake, PERSONALITY, petOf, PET, NEAR, SEE } from './brain.js';
import { makeFish, step, blend } from './steer.js';

let seed = 7;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const ok = (c, msg) => { if (!c) throw new Error('FAIL fish: ' + msg); };
const B = { x: 0, y: 0, w: 1600, h: 900 }, dt = 1 / 15;
const fish = (x, y, name, o = {}) => ({ f: makeFish({ x, y, cruise: 60, pad: 20, ...o }, rand), b: makeBrain(PERSONALITY[name], rand) });
const ctx = (o, mates, w = {}) => ({ f: o.f, p: null, b: B, mates, dt, rand, layer: 1, perches: [], spots: [], ...w });
const tick = (all, w) => { for (const o of all) step(o.f, dt, think(o.b, ctx(o, all, w)), B, all.map(m => m.f), rand); };

// food stub with the food.js shape: 3 bites finish a piece
const piece = (x, y, o = {}) => ({ live: true, layer: 1, x, y, claims: 0, bites: 0, settled: false, born: seed++, ...o });
const feeder = { bite: k => k.live && (++k.bites >= 3 && (k.live = false), true), kick: () => {} };

// claims: never more than 2 fish on a piece, and a pinch gets eaten within 20 s
{
    const pieces = [0, 1, 2, 3, 4, 5].map(i => piece(700 + i * 30, 300 + (i % 2) * 40));
    const all = [0, 1, 2, 3, 4, 5, 6, 7].map(i => fish(500 + i * 60, 450, i % 2 ? 'clown' : 'goldfish'));
    let t = 0;
    for (; t < 20 && pieces.some(k => k.live); t += dt) {
        tick(all, { food: pieces, feeder });
        for (const k of pieces) ok(k.claims >= 0 && k.claims <= 2, 'claims stay 0..2 (' + k.claims + ')');
    }
    ok(pieces.every(k => !k.live), 'pinch eaten within 20 s');
    ok(all.reduce((n, o) => n + o.b.fed, 0) === 18, 'every bite counted');
}

// bottom feeders ignore falling food until it sinks; others ignore food lying on the sand far off
{
    const cory = fish(800, 860, 'cory'), c = ctx(cory, [cory]);
    ok(flake(cory.b, { ...c, food: [piece(820, 300)] }) === null, 'cory ignores a falling piece');
    ok(flake(cory.b, { ...c, food: [piece(820, 880, { settled: true })] }) !== null, 'cory takes a settled piece');
    const tetra = fish(800, 300, 'tetra');
    ok(flake(tetra.b, { ...ctx(tetra, [tetra]), food: [piece(1100, 880, { settled: true })] }) === null, 'mid feeder leaves far sand food');
    ok(flake(tetra.b, { ...ctx(tetra, [tetra]), food: [piece(820, 300, { layer: 0 })] }) === null, 'other layer ignored');
}

// startle ripple: a calm neighbour of a fleeing fish waits a beat before it bolts
{
    const a = fish(800, 450, 'tetra'), b = fish(860, 450, 'tetra'), duo = [a, b];
    a.b.state = 'flee'; a.b.panic = 1; a.b.fx = 700; a.b.fy = 450;
    think(b.b, ctx(b, duo));
    ok(b.b.state !== 'flee' && b.b.startle > 0, 'startle delay > 0');
    for (let i = 0; i < 6; i++) think(b.b, ctx(b, duo));
    ok(b.b.state === 'flee', 'neighbour flees after the delay');
}

// crowd at n = 0 and n = 1 (school species alone), no perches or spots: stays in the water
for (const n of [0, 1]) {
    const all = [];
    for (let i = 0; i < n; i++) all.push(fish(800, 450, 'tetra', { school: 'tetra' }));
    for (let i = 0; i < 4000; i++) {
        tick(all, { p: i % 200 < 100 ? { x: 790, y: 450, speed: 3000 } : null });
        for (const o of all) ok(o.f.x >= 20 && o.f.x <= 1580 && o.f.y >= 20 && o.f.y <= 880 && Number.isFinite(o.f.dir + o.f.speed), `n=${n} stays in bounds`);
    }
}

// acceleration limit: wander speed never jumps by more than cruise*4 px/s per second
{
    const o = fish(800, 450, 'clown');
    let last = o.f.speed;
    for (let i = 0; i < 3000; i++) {
        step(o.f, dt, { speed: i % 300 < 150 ? 2 : 0.3 }, B, [o.f], rand);
        ok(Math.abs(o.f.speed - last) <= 60 * 4 * dt + 1e-6, 'acceleration clamped');
        last = o.f.speed;
    }
}

// body crossfade: near, lower frame solid to halfway, upper fully in from halfway; far, the stack always adds up to op
{
    const w = [0, 0];
    ok(String(blend(0, 255, w)) === '255,0' && String(blend(1, 255, w)) === '0,255', 'blend ends');
    for (let t = 0; t <= 1; t += 0.05) {
        blend(t, 165, w);
        ok(Math.abs(255 - (255 - w[0]) * (255 - w[1]) / 255 - 165) < 1.5 && w.every(v => v >= 0 && v <= 165), 'far stack always reads as op');
    }
}
// the tame favourite: the most fed once past PET; never flees a slow cursor, hovers closest, ignores taps
{
    ok(petOf([3, PET - 1]) === -1 && petOf([PET, PET + 5, PET + 5, 2]) === 1, 'pet = first most-fed past PET');
    let fled = 0, close = 1e9;
    for (let k = 0; k < 200; k++) {
        const o = fish(800, 450, 'tetra');
        o.b.pet = true;
        think(o.b, ctx(o, [o], { p: { x: 760, y: 450, speed: 0 } }));
        fled += o.b.state === 'flee';
    }
    const o = fish(900, 450, 'clown'), p = { x: 700, y: 450, speed: 0 };
    o.b.pet = true;
    for (let i = 0; i < 15 * 6; i++) { tick([o], { p }); if (o.b.state === 'curious') close = Math.min(close, Math.hypot(o.f.x - p.x, o.f.y - p.y)); }
    ok(fled === 0 && close < NEAR * 0.6 + 15, `pet comes, never flees (${fled}, ${close | 0} px)`);
    tick([o], { p, tap: { x: o.f.x + 30, y: o.f.y, age: 0, n: 1 } });
    ok(o.b.state !== 'flee', 'a tap does not scare the pet');
}

// a glass tap: calm fish nearby jump (half a scare, once per tap), fish far off don't
{
    const near = fish(800, 450, 'goldfish'), far = fish(100, 100, 'goldfish'), tap = { x: 820, y: 450, age: 0, n: 1 };
    tick([near], { tap }); tick([far], { tap });
    ok(near.b.state === 'flee' && near.b.panic <= 0.5 && far.b.state !== 'flee', 'tap startles fish close by only');
    for (let i = 0; i < 15 * 3; i++) tick([near], { tap: { ...tap, age: 0.1 } });
    ok(near.b.state !== 'flee', 'one jump per tap, then it calms');
}

// night torch: small fish come into the light, bottom dwellers slip out of it
{
    const p = { x: 760, y: 450, speed: 0 };
    let moth = 0, shy = 0;
    for (let k = 0; k < 200; k++) {
        const t = fish(800, 450, 'tetra'), c = fish(800, 450, 'cory');
        think(t.b, ctx(t, [t], { p, torch: true, night: true }));
        think(c.b, ctx(c, [c], { p, torch: true, night: true }));
        moth += t.b.state === 'curious'; shy += c.b.state === 'flee' && c.b.panic <= 0.4;
    }
    ok(moth > 160 && shy === 200, `torch: tetras come (${moth}/200), corys leave (${shy}/200)`);
}

// small fish slide away from a lionfish close by
{
    const t = fish(800, 450, 'tetra'), l = fish(880, 450, 'lionfish'), duo = [t, l];
    const it = think(t.b, ctx(t, duo));
    ok(it.ax === l.f.x && it.speed >= 1.2 || t.b.state !== 'idle', 'tetra keeps away from the lionfish');
}
console.log('fish ok');
