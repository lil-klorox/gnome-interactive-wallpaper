// Fish brain: what each fish wants, as a small state machine. Pure logic, no gi imports.
// A state is { enter(b, c), update(b, c) }; update returns an intent for steer.js, or the name
// of the state to switch to. Adding a behavior = one entry in STATES + a transition into it.
//
// intent: { tx, ty }  swim to this point (omit both to wander)
//         { ax, ay }  swim away from this point
//         speed       x cruise speed
//         band        [top, bottom] fractions of the water to wander in
//         shoal       0..1 pull toward nearby fish of any species
//         look        {x, y} the eyes follow, or null for straight ahead
//         face        turn toward the viewer (curious hover)
//         chomp       mouth busy (nibbling)
//         alarm       startled (puffer puffs)
// c (context): { f: motion state from steer.js, p: pointer {x,y,speed}|null, b: swim bounds,
//                mates: [{f, b}] fish sharing the layer (motion + brain, includes this one), dt, rand }

export const FAST = 1400;  // px/s cursor speed that startles a fish with nerve 1
export const SEE = 260;    // px a fish notices the cursor from
export const NEAR = 80;    // px a curious fish hovers at
export const BORING = 8;   // s a parked cursor takes to stop being interesting

// Per-species personality, plain data. curious: chance to approach instead of flee.
// nerve: x FAST it tolerates. attention: x seconds curiosity lasts. dash: flee speed.
// band: home depth. social: shoal pull. nibble/rest/follow/gulp: what idle turns into.
export const PERSONALITY = {
    clown: { curious: 0.7, nerve: 0.8, attention: 1.2, dash: 4, band: [0.35, 0.75], social: 0.3, nibble: 0.4, rest: 0.5, follow: 0.3 },
    tetra: { curious: 0.15, nerve: 0.5, attention: 0.6, dash: 6, band: [0.2, 0.55], social: 1, nibble: 0.2 },
    angel: { curious: 0.55, nerve: 1, attention: 1.4, dash: 3, band: [0.3, 0.7], social: 0.4, nibble: 0.3, rest: 0.4, follow: 0.4 },
    goldfish: { curious: 0.85, nerve: 1.3, attention: 1.6, dash: 3, band: [0.3, 0.9], social: 0.3, nibble: 1, rest: 0.3, follow: 0.2 },
    tang: { curious: 0.3, nerve: 0.7, attention: 0.8, dash: 5, band: [0.3, 0.8], social: 0.5, nibble: 0.5, rest: 0.1, follow: 0.5 },
    puffer: { curious: 0.6, nerve: 0.6, attention: 1.5, dash: 1.6, band: [0.4, 0.8], social: 0.1, nibble: 0.5, rest: 0.6, follow: 0.1 },
    cory: { curious: 0.4, nerve: 0.8, attention: 1, dash: 3, band: [0.92, 1], social: 0.7, nibble: 1.2, rest: 0.5, follow: 0.6, gulp: 0.25 },
    betta: { curious: 0.75, nerve: 1.2, attention: 2, dash: 2.5, band: [0.1, 0.45], social: 0, nibble: 0.2, rest: 0.8 },
};

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const near = c => c.p && dist(c.f, c.p) < SEE * 1.2 ? c.p : null;
const sandY = c => c.b.y + c.b.h - c.f.pad;
const mateIn = (c, state, r, same) =>
    c.mates.find(m => m.b.state === state && m.f !== c.f && (!same || m.b.pers === same) && dist(m.f, c.f) < r);
const calm = (b, c, it) => notice(b, c) ?? { shoal: b.pers.social, look: near(c), ...it };

// Calm states call this: a slow cursor close by (or a curious neighbour near it) gets a roll
// of the dice, curious or flee. A cursor parked for a while is ignored (habituation).
function notice(b, c) {
    if (!c.p || b.cool > 0 || b.still > BORING) return null;
    const d = dist(c.f, c.p);
    if (d > SEE && !(d < SEE * 2 && mateIn(c, 'curious', 200))) return null;
    b.cool = 4;
    return c.rand() < b.pers.curious ? 'curious' : 'flee';
}

// Idle gets restless after a while and picks the next thing to do, weighted by personality.
function restless(b, c) {
    const P = b.pers, alone = c.mates.length < 2;
    const w = [['nibble', P.nibble], ['rest', P.rest], ['follow', alone ? 0 : P.follow], ['gulp', P.gulp], ['idle', 1]];
    let r = c.rand() * w.reduce((s, [, x]) => s + (x ?? 0), 0);
    for (const [name, x] of w) if ((r -= x ?? 0) <= 0) return name;
    return 'idle';
}

export const STATES = {
    idle: {
        enter: (b, c) => { b.timer = 4 + c.rand() * 6; },
        update: (b, c) => {
            // air gulps are catching: a nearby gulper of the same kind sets this one off now and then
            if (b.pers.gulp && mateIn(c, 'gulp', 250, b.pers) && c.rand() < c.dt) return 'gulp';
            return b.timer <= 0 ? notice(b, c) ?? restless(b, c) : calm(b, c, { speed: 0.6, band: b.pers.band });
        },
    },
    curious: {
        enter: (b, c) => { b.timer = b.pers.attention * (3 + c.rand() * 3); },
        update: (b, c) => {
            if (!c.p || b.timer <= 0) return 'bored';
            const { f, p } = c, d = dist(f, p) || 1;
            return {
                tx: p.x + (f.x - p.x) / d * NEAR, ty: p.y + (f.y - p.y) / d * NEAR,
                speed: 1.5, look: p, face: d < NEAR + 40, shoal: b.pers.social * 0.5,
            };
        },
    },
    flee: {
        enter: (b, c) => { b.panic = 1; b.fx = c.p?.x ?? b.fx; b.fy = c.p?.y ?? b.fy; },
        update: (b, c) => {
            if (c.p && dist(c.f, c.p) < SEE * 1.5) { b.fx = c.p.x; b.fy = c.p.y; }
            b.panic -= c.dt * 0.4;
            if (b.panic < 0.1) return 'bored';
            return { ax: b.fx, ay: b.fy, speed: 1 + b.pers.dash * b.panic, look: null, alarm: true, shoal: 1 };
        },
    },
    bored: {  // wary cool-down: ignores the cursor unless it startles
        enter: (b, c) => { b.timer = 5 + c.rand() * 3; b.cool = b.timer + 2; },
        update: b => b.timer <= 0 ? 'idle' : { speed: 0.6, band: b.pers.band, shoal: b.pers.social, look: null },
    },
    nibble: {  // ponytail: spots are random points on the sand; use real plant spots if Scene ever exports them
        enter: (b, c) => { b.tx = c.b.x + c.f.pad + c.rand() * (c.b.w - 2 * c.f.pad); b.ty = sandY(c); b.timer = 12; b.got = false; },
        update: (b, c) => {
            const at = dist(c.f, { x: b.tx, y: b.ty }) < 14;
            if (at && !b.got) { b.got = true; b.timer = 3 + c.rand() * 4; }
            if (b.timer <= 0) return 'idle';
            return calm(b, c, { tx: b.tx, ty: b.ty, speed: at ? 0.3 : 0.9, look: { x: b.tx + 9, y: b.ty + 20 }, chomp: at });
        },
    },
    rest: {  // hang still low down near the glass ends, where the decor sits
        enter: (b, c) => {
            const side = c.rand() < 0.5 ? 0.12 : 0.88;
            b.tx = c.b.x + c.b.w * (side + (c.rand() - 0.5) * 0.15); b.ty = sandY(c) - 20 - c.rand() * 60; b.timer = 8 + c.rand() * 8;
        },
        update: (b, c) => b.timer <= 0 ? 'idle' : calm(b, c, { tx: b.tx, ty: b.ty, speed: 0.6, shoal: 0 }),
    },
    follow: {
        enter: (b, c) => {
            const mates = c.mates.filter(m => m.f !== c.f);
            b.buddy = mates[Math.floor(c.rand() * mates.length)]?.f ?? null; b.timer = 6 + c.rand() * 6;
        },
        update: (b, c) => {
            const m = b.buddy;
            if (!m || !c.mates.some(o => o.f === m) || b.timer <= 0) return 'idle';
            const behind = 30 + c.f.pad + m.pad;  // trail just behind the buddy's tail
            return calm(b, c, { tx: m.x - Math.cos(m.dir) * behind, ty: m.y - Math.sin(m.dir) * behind, speed: 1.3, look: m });
        },
    },
    gulp: {  // corydoras dart up for a gulp of air, then sink back home
        enter: (b, c) => { b.tx = c.f.x + (c.rand() - 0.5) * 120; b.ty = c.b.y + c.f.pad; b.timer = 6; },
        update: (b, c) => b.timer <= 0 || c.f.y < b.ty + 12 ? 'idle' : { tx: b.tx, ty: b.ty, speed: 2.5, look: null },
    },
};

export function makeBrain(pers, rand = Math.random) {
    return { pers, state: 'idle', timer: 4 + rand() * 6, cool: 0, still: 0, panic: 0, fx: 0, fy: 0 };
}

function enter(b, name, c) {
    b.state = name;
    STATES[name].enter(b, c);
}

// One tick of thinking: returns this tick's intent.
export function think(b, c) {
    b.timer -= c.dt;
    b.cool -= c.dt;
    b.still = c.p && c.p.speed < 30 ? b.still + c.dt : 0;
    // a fast cursor nearby startles every fish whatever it was doing; panic spreads to calm neighbours
    const p = c.p, scare = p && b.state !== 'flee' && p.speed > FAST * b.pers.nerve && dist(c.f, p) < SEE * 1.5;
    const spooked = !scare && b.state !== 'flee' && b.cool <= 0 && mateIn(c, 'flee', 220);
    if (spooked) { b.fx = spooked.b.fx; b.fy = spooked.b.fy; }
    let r = scare || spooked ? 'flee' : STATES[b.state].update(b, c);
    for (let i = 0; typeof r === 'string' && i < 4; i++) {
        enter(b, r, c);
        r = STATES[r].update(b, c);
    }
    return typeof r === 'string' ? { speed: 0.6, look: null } : r;
}
