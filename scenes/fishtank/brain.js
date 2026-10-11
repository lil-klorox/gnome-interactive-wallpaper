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
//                mates: [{f, b}] fish sharing the layer (motion + brain, includes this one), dt, rand,
//                threats: [{x,y,w,h}] rects to flee, food: [{x,y,live}] flakes, attn: {x,y}|null
//                notification spot (attnNew on its first tick), wake: user just came back,
//                drowsy: rest weight multiplier (night/idle), lazy: speed multiplier }

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

const dist = (a, b) => { const x = a.x - b.x, y = a.y - b.y; return Math.sqrt(x * x + y * y); };
const near = c => c.p && dist(c.f, c.p) < SEE * 1.2 ? c.p : null;
const sandY = c => c.b.y + c.b.h - c.f.pad;
function mateIn(c, state, r, same) {
    for (const m of c.mates)
        if (m.b.state === state && m.f !== c.f && (!same || m.b.pers === same) && dist(m.f, c.f) < r) return m;
    return null;
}
// Nearest point of any threat rect within SEE, as its centre; null when none.
function threat(c) {
    if (c.threats) for (const r of c.threats) {
        const dx = Math.max(r.x - c.f.x, 0, c.f.x - r.x - r.w), dy = Math.max(r.y - c.f.y, 0, c.f.y - r.y - r.h);
        if (dx * dx + dy * dy < SEE * SEE) return r;
    }
    return null;
}
function flake(c) {
    let best = null, bd = SEE;
    if (c.food) for (const k of c.food) if (k.live) { const d = dist(c.f, k); if (d < bd) { bd = d; best = k; } }
    return best;
}
const tame = b => Math.min(2, 1 + b.fed / 50);
// Night (21-6, ponytail: fixed bands, sunrise math when location is wired) and a long-idle desk both
// make fish rest more and swim slower.
export const night = hour => hour >= 21 || hour < 6;
export const drowsy = (hour, idle) => (night(hour) ? 3 : 1) * (idle > 600 ? 3 : 1);
export const lazy = (hour, idle) => (night(hour) ? 0.7 : 1) * (idle > 600 ? 0.5 : 1);
function calm(b, c, it) {  // fills defaults into the state's own intent object
    const n = notice(b, c);
    if (n) return n;
    it.shoal ??= b.pers.social;
    if (it.look === undefined) it.look = near(c);
    return it;
}

// Calm states call this: a slow cursor close by (or a curious neighbour near it) gets a roll
// of the dice, curious or flee. A cursor parked for a while is ignored (habituation).
function notice(b, c) {
    if (!c.p || b.cool > 0 || b.still > BORING) return null;
    const d = dist(c.f, c.p);
    if (d > SEE && !(d < SEE * 2 && mateIn(c, 'curious', 200))) return null;
    b.cool = 4;
    if (c.rand() < 1 - (1 - b.pers.curious) / tame(b)) return 'curious';  // fed fish are tamer
    b.fx = c.p.x; b.fy = c.p.y;
    return 'flee';
}

// Idle gets restless after a while and picks the next thing to do, weighted by personality.
function restless(b, c) {
    const P = b.pers, alone = c.mates.length < 2;
    const w = [['nibble', P.nibble], ['rest', (P.rest ?? 0) * (c.drowsy ?? 1)], ['follow', alone ? 0 : P.follow], ['gulp', P.gulp], ['idle', 1]];
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
            return b.timer <= 0 ? notice(b, c) ?? restless(b, c) : calm(b, c, { speed: 0.6, band: b.pers.band, look: c.attn ?? undefined });
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
    flee: {  // whoever sends a fish here sets b.fx/fy, the point to flee from
        enter: b => { b.panic = 1; },
        update: (b, c) => {
            const r = threat(c);
            if (r) { b.fx = r.x + r.w / 2; b.fy = r.y + r.h / 2; } else if (c.p && dist(c.f, c.p) < SEE * 1.5) { b.fx = c.p.x; b.fy = c.p.y; }
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
    feed: {  // swim to the flake, chomp it; it vanishes for everyone
        enter: (b, c) => { b.food = flake(c); b.timer = 15; },
        update: (b, c) => {
            const k = b.food;
            if (!k?.live || b.timer <= 0) return 'idle';
            // bug fix: a flake on the sand or by the glass sat outside where steer lets the fish's
            // centre go, so it was never in reach; aim at (and measure to) the nearest reachable spot
            const { f, b: w } = c, x = Math.max(w.x + f.pad, Math.min(w.x + w.w - f.pad, k.x));
            const at = { x, y: Math.max(w.y + f.pad, Math.min(sandY(c), k.y)) }, d = dist(f, at);
            if (d < 14 + f.pad * 0.3) { k.live = false; b.fed++; b.food = null; return 'idle'; }
            return { tx: at.x, ty: at.y, speed: 1.6, look: k, chomp: d < 40, shoal: 0 };
        },
    },
    gulp: {  // corydoras dart up for a gulp of air, then sink back home
        enter: (b, c) => { b.tx = c.f.x + (c.rand() - 0.5) * 120; b.ty = c.b.y + c.f.pad; b.timer = 6; },
        update: (b, c) => b.timer <= 0 || c.f.y < b.ty + 12 ? 'idle' : { tx: b.tx, ty: b.ty, speed: 2.5, look: null },
    },
};

export function makeBrain(pers, rand = Math.random) {
    return { pers, state: 'idle', timer: 4 + rand() * 6, cool: 0, still: 0, panic: 0, fx: 0, fy: 0, fed: 0, dart: 0, food: null };
}

function enter(b, name, c) {
    b.state = name;
    STATES[name].enter(b, c);
}

// One tick of thinking: returns this tick's intent.
export function think(b, c) {
    b.timer -= c.dt;
    b.cool -= c.dt;
    b.dart -= c.dt;
    b.still = c.p && c.p.speed < 30 ? b.still + c.dt : 0;
    // a fast cursor or a moving window nearby startles every fish whatever it was doing; panic
    // spreads to calm neighbours
    const p = c.p, calmNow = b.state !== 'flee';
    const scare = calmNow && p && p.speed > FAST * b.pers.nerve * tame(b) && dist(c.f, p) < SEE * 1.5;
    const th = calmNow && !scare && threat(c);
    const spooked = calmNow && !scare && !th && b.cool <= 0 && mateIn(c, 'flee', 220);
    let r = null;
    if (scare) { b.fx = p.x; b.fy = p.y; r = 'flee'; }
    else if (th) { b.fx = th.x + th.w / 2; b.fy = th.y + th.h / 2; r = 'flee'; }
    else if (spooked) { b.fx = spooked.b.fx; b.fy = spooked.b.fy; r = 'flee'; }
    else if (calmNow && b.state !== 'feed' && flake(c)) r = 'feed';
    else if (c.wake && p && calmNow && dist(c.f, p) < SEE * 3) r = 'curious';
    if (c.attnNew && c.f.y < c.b.y + c.b.h * 0.35) b.dart = 0.5;  // surface fish dart at a notification
    r ??= STATES[b.state].update(b, c);
    for (let i = 0; typeof r === 'string' && i < 4; i++) {
        enter(b, r, c);
        r = STATES[r].update(b, c);
    }
    if (typeof r === 'string') r = { speed: 0.6, look: null };
    if (b.dart > 0) r.speed *= 2.5;
    else if (b.state !== 'flee') r.speed *= c.lazy ?? 1;
    return r;
}
