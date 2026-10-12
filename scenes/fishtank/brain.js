// Fish brain: what each fish wants, as a small state machine. Pure logic, no gi imports.
// A state is { enter(b, c), update(b, c) }; update returns an intent for steer.js, or the name
// of the state to switch to. Adding a behavior = one entry in STATES + a transition into it.
//
// intent: { tx, ty }  swim to this point (omit both to wander)
//         { ax, ay }  swim away from this point
//         speed       x cruise speed
//         band        [top, bottom] fractions of the water to wander in
//         shoal       0..1 pull toward nearby fish of any species
//         tight       x pull toward own school (default 1)
//         noise       x wander heading noise (darting)
//         look        {x, y} the eyes follow, or null for straight ahead
//         face        turn toward the viewer (curious hover, flare)
//         chomp       mouth busy (nibbling, eating)
//         alarm       startled (puffer puffs)
//         pitch       nose angle goal (rad, + = down) while lining up a bite
//         fin         fins barely moving (hover, sit, night rest)
//         flare       betta flaring (body swells)
// c (context): { f: motion state from steer.js, p: pointer {x,y,speed}|null, b: swim bounds,
//                mates: [{f, b}] fish sharing the layer (motion + brain, includes this one), dt, rand,
//                threats: [{x,y,w,h}] rects to flee, food: food pieces in play | null, feeder: the
//                food object (bite/kick), layer: 0 far | 1 near, attn: {x,y}|null notification spot
//                (attnNew on its first tick), wake: user just came back, drowsy: rest weight
//                multiplier (night/idle), lazy: speed multiplier, night: lights off, act: activity
//                0.5..1.5, curiosity: false = ignore cursor + critters, spots: [{x,y}] critters worth
//                a look, perches: [{x,y}] plant stems, torch: the night flashlight is on the cursor }
// Brain fields other code reads: state, fed (food eaten), nods (bumps each nose-down: bite,
// sand nibble), cling (pleco on the glass), timer. fish.js sets pet (the tame favourite).

export const FAST = 1400;  // px/s cursor speed that startles a fish with nerve 1
export const SEE = 260;    // px a fish notices the cursor from
export const NEAR = 80;    // px a curious fish hovers at
export const BORING = 8;   // s a parked cursor takes to stop being interesting

// Per-species personality, plain data. curious: chance to approach instead of flee.
// nerve: x FAST it tolerates. attention: x seconds curiosity lasts. dash: flee speed.
// band: home depth. social: shoal pull. tight: own-school pull. nibble/rest/follow/gulp/hover/sit/
// home: what idle turns into (weights). huddle: night band. Feeders: surface (sees food above
// sooner), bottom (only sunk food). glide: holds the tail still while coasting. prey: small fish
// a lionfish stalks. flare: betta display. inspect: hovers at the glass, slower.
export const PERSONALITY = {
    clown: { curious: 0.7, nerve: 0.8, attention: 1.2, dash: 4, band: [0.35, 0.75], social: 0.3, nibble: 0.4, rest: 0.5, follow: 0.3, home: 0.6, surface: true },
    tetra: { curious: 0.15, nerve: 0.5, attention: 0.6, dash: 6, band: [0.2, 0.55], social: 1, nibble: 0.2, huddle: [0.55, 0.8], prey: true },
    angel: { curious: 0.55, nerve: 1, attention: 1.4, dash: 3, band: [0.3, 0.7], social: 0.4, tight: 0.5, nibble: 0.3, rest: 0.4, follow: 0.4, glide: true },
    goldfish: { curious: 0.85, nerve: 1.3, attention: 1.6, dash: 3, band: [0.3, 0.9], social: 0.3, nibble: 1, rest: 0.3, follow: 0.2, glide: true },
    tang: { curious: 0.3, nerve: 0.7, attention: 0.8, dash: 5, band: [0.3, 0.8], social: 0.5, nibble: 0.5, rest: 0.1, follow: 0.5, glide: true },
    puffer: { curious: 0.6, nerve: 0.6, attention: 1.5, dash: 1.6, band: [0.4, 0.8], social: 0.1, nibble: 0.5, rest: 0.6, follow: 0.1, inspect: true },
    cory: { curious: 0.4, nerve: 0.8, attention: 1, dash: 3, band: [0.92, 1], social: 0.7, nibble: 1.2, rest: 0.5, follow: 0.6, gulp: 0.25, bottom: true },
    betta: { curious: 0.75, nerve: 1.2, attention: 2, dash: 2.5, band: [0.1, 0.45], social: 0, nibble: 0.2, rest: 0.8, surface: true, glide: true, flare: true },
    lionfish: { curious: 0.5, nerve: 1.3, attention: 1.5, dash: 2, band: [0.3, 0.7], social: 0, nibble: 0, rest: 0.3, hover: 0.6, glide: true, stalk: true },
    discus: { curious: 0.45, nerve: 0.9, attention: 1.2, dash: 2.5, band: [0.3, 0.7], social: 0.4, tight: 0.4, nibble: 0.3, rest: 0.4, follow: 0.3, glide: true },
    guppy: { curious: 0.5, nerve: 0.6, attention: 0.8, dash: 5, band: [0.1, 0.45], social: 0.8, tight: 0.3, nibble: 0.2, follow: 0.4, surface: true, prey: true, noise: 1.5 },
    pleco: { curious: 0.1, nerve: 0.9, attention: 0.5, dash: 2, band: [0.95, 1], social: 0, nibble: 0.4, sit: 0.9, bottom: true },
    mandarin: { curious: 0.35, nerve: 0.7, attention: 1, dash: 2, band: [0.92, 1], social: 0, nibble: 1.2, rest: 0.3, bottom: true },
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

// Best food piece for this fish, or null: own layer only, nearest wins; a piece another fish holds is
// skipped (one fish per piece, so a pinch spreads out instead of a scrum on one flake). Bottom
// feeders take only sunk food; the rest chase sinking food all the way down but leave what lies on
// the sand to them. Surface feeders notice food above.
export function flake(b, c) {
    let best = null, bs = 1e9;
    if (c.food) for (const k of c.food) {
        if (!k.live || k.layer !== c.layer) continue;
        if (k.claims > (holds(b, k) ? 1 : 0)) continue;
        let d = dist(c.f, k);
        if (b.pers.surface && k.y < c.f.y) d /= 1.5;
        if (d > SEE * 2) continue;
        if (b.pers.bottom && !k.settled && k.y < c.b.y + c.b.h * b.pers.band[0]) continue;
        if (!b.pers.bottom && k.settled && !k.perch) continue;
        if (d < bs) { bs = d; best = k; }
    }
    return best;
}
// a pool piece reused for a new drop is a new piece, not the one b claimed
const holds = (b, k) => k === b.food && k.born === b.foodBorn;
function claim(b, k) {
    if (k && holds(b, k)) return;
    release(b);
    if (!k) return;
    k.claims++;
    b.food = k;
    b.foodBorn = k.born;
}
export function release(b) {
    const k = b.food;
    if (k && k.born === b.foodBorn) k.claims = Math.max(0, k.claims - 1);  // a reused piece is not ours
    b.food = null;
}

const tame = b => Math.min(2, 1 + b.fed / 50);
export const PET = 30;  // flakes eaten before a fish can become the tame favourite
// Index of the favourite in a list of fed counts: the most fed, once it has eaten PET; else -1.
export function petOf(fed) {
    let best = -1;
    for (let i = 0; i < fed.length; i++) if (fed[i] >= PET && (best < 0 || fed[i] > fed[best])) best = i;
    return best;
}
// Lights off and a long-idle desk both make fish rest more and swim slower.
export const drowsy = (night, idle) => (night ? 3 : 1) * (idle > 600 ? 3 : 1);
export const lazy = (night, idle) => (night ? 0.7 : 1) * (idle > 600 ? 0.5 : 1);
function calm(b, c, it) {  // fills defaults into the state's own intent object
    const n = notice(b, c);
    if (n) return n;
    it.shoal ??= b.pers.social;
    it.tight ??= b.pers.tight;
    it.noise ??= b.pers.noise;
    if (it.look === undefined) it.look = near(c);
    if (b.pers.prey && it.ax === undefined) for (const m of c.mates)  // small fish slide away from a lionfish nearby
        if (m.b.pers.stalk && dist(m.f, c.f) < 110) { it.ax = m.f.x; it.ay = m.f.y; it.speed = 1.2; it.tight = 2; break; }
    return it;
}

// Calm states call this: a slow cursor close by (or a curious neighbour near it) gets a roll
// of the dice, curious or flee. A cursor parked for a while is ignored (habituation). A betta
// flares at a fish or cursor close by; a critter out in view (spot) is worth a visit.
function notice(b, c) {
    const P = b.pers;
    if (P.flare && b.flareCool <= 0) {
        for (const m of c.mates)
            if (m.f !== c.f && dist(m.f, c.f) < 120) return 'flare';
        if (c.p && dist(c.f, c.p) < NEAR) return 'flare';
    }
    if (P.stalk && b.stalkCool <= 0) for (const m of c.mates)
        if (m.b.pers.prey && dist(m.f, c.f) < 160) { b.prey = m.f; return 'stalk'; }
    if (c.curiosity === false) return null;  // owner turned curiosity off: ignore the cursor and critters
    if (c.spots?.length && b.visitCool <= 0) {
        for (const s of c.spots) if (dist(c.f, s) < SEE) {
            b.visitCool = 10;
            if (c.rand() < P.curious * 0.5 * (c.act ?? 1)) { b.spot = s; return 'visit'; }  // half a cursor's pull
            break;
        }
    }
    // night torch: small fish drift into the light like moths, bottom dwellers slip out of it
    const moth = c.torch && P.prey;
    if (!c.p || b.cool > 0 || (b.still > BORING && !moth)) return null;
    const d = dist(c.f, c.p);
    if (d > SEE && !(d < SEE * 2 && mateIn(c, 'curious', 200))) return null;
    b.cool = 4;
    if (b.pet || c.rand() < (moth ? 0.9 : c.torch && P.bottom ? 0 : 1 - (1 - P.curious) / tame(b))) return 'curious';  // fed fish are tamer
    b.fx = c.p.x; b.fy = c.p.y;
    b.fright = c.torch && P.bottom ? 0.4 : 1;
    return 'flee';
}

// Idle gets restless after a while and picks the next thing to do, weighted by personality.
// Activity scales the lazy picks down and the busy ones up.
function restless(b, c) {
    const P = b.pers, alone = c.mates.length < 2, act = c.act ?? 1, slow = (c.drowsy ?? 1) / act;
    const w = [['nibble', (P.nibble ?? 0) * act], ['rest', (P.rest ?? 0) * slow], ['follow', alone ? 0 : (P.follow ?? 0) * act],
        ['gulp', P.gulp], ['hover', (P.hover ?? 0) * slow], ['sit', (P.sit ?? 0) * slow],
        ['home', c.perches?.length ? P.home : 0], ['idle', 1]];
    let r = c.rand() * w.reduce((s, [, x]) => s + (x ?? 0), 0);
    for (const [name, x] of w) if ((r -= x ?? 0) <= 0) return name;
    return 'idle';
}

// One intent object per brain, cleared and refilled each think (no allocation per tick).
const KEYS = ['tx', 'ty', 'ax', 'ay', 'speed', 'band', 'shoal', 'tight', 'noise', 'look', 'face', 'chomp', 'alarm', 'pitch', 'fin', 'flare'];
function I(b, speed, look) {
    const it = b.it;
    for (const k of KEYS) it[k] = undefined;
    it.speed = speed;
    if (look !== undefined) it.look = look;
    return it;
}
const to = (it, x, y) => { it.tx = x; it.ty = y; return it; };
// Hang about at (x, y), swaying a pixel or two.
const sway = (b, x, y, speed) => { const it = to(I(b, speed), x + Math.sin(b.timer * 0.9) * 2, y + Math.sin(b.timer * 0.6) * 1.5); it.shoal = 0; return it; };

export const STATES = {
    idle: {
        enter: (b, c) => { b.timer = 4 + c.rand() * 6; },
        update: (b, c) => {
            // air gulps are catching: a nearby gulper of the same kind sets this one off now and then
            if (b.pers.gulp && mateIn(c, 'gulp', 250, b.pers) && c.rand() < c.dt) return 'gulp';
            if (b.timer <= 0) return notice(b, c) ?? restless(b, c);
            const it = I(b, 0.6, c.attn ?? undefined);
            it.band = b.pers.band;
            return calm(b, c, it);
        },
    },
    curious: {
        enter: (b, c) => { b.timer = b.pers.attention * (3 + c.rand() * 3); b.greet = b.pet ? 0.6 : 0; },
        update: (b, c) => {
            if (!c.p || b.timer <= 0) return 'bored';
            const { f, p } = c, d = dist(f, p) || 1, insp = b.pers.inspect, moth = c.torch && b.pers.prey;
            const r = NEAR * (b.pet ? 0.6 : moth ? 1.5 : 1);  // the favourite comes closest
            const it = to(I(b, moth ? 0.5 : insp ? 1 : 1.5, p), p.x + (f.x - p.x) / d * r, p.y + (f.y - p.y) / d * r);
            it.face = d < r + (insp ? 60 : 40);
            it.chomp = (b.greet -= c.dt) > 0;  // the favourite says hello with a mouth wiggle
            it.shoal = b.pers.social * 0.5;
            return it;
        },
    },
    visit: {  // a critter out in view (moray, jelly, seahorse): drift over, look, move on
        enter: (b, c) => { b.timer = 3 + c.rand() * 3; b.visitCool = 60; },
        update: (b, c) => {
            // b.spot is the critter's own spot object (critters.js keeps one per critter), so
            // "still in c.spots" means that critter is still out
            const s = b.spot;
            if (!s || b.timer <= 0 || !c.spots?.includes(s)) return 'idle';
            const { f } = c, d = dist(f, s) || 1;
            const it = to(I(b, 0.9, s), s.x + (f.x - s.x) / d * NEAR, s.y + (f.y - s.y) / d * NEAR);
            it.face = d < NEAR + 30;
            return calm(b, c, it);
        },
    },
    flee: {  // whoever sends a fish here sets b.fx/fy, the point to flee from
        enter: b => { b.panic = b.fright || 1; b.fright = 0; },  // fright: a softer scare (torch)
        update: (b, c) => {
            const r = threat(c);
            if (r) { b.fx = r.x + r.w / 2; b.fy = r.y + r.h / 2; } else if (c.p && dist(c.f, c.p) < SEE * 1.5) { b.fx = c.p.x; b.fy = c.p.y; }
            b.panic -= c.dt * 0.4;
            if (b.panic < 0.1) return 'bored';
            const it = I(b, 1 + b.pers.dash * b.panic, null);
            it.ax = b.fx; it.ay = b.fy; it.alarm = true; it.shoal = 1;
            return it;
        },
    },
    bored: {  // wary cool-down: ignores the cursor unless it startles; a school stays packed tight a while
        enter: (b, c) => { b.timer = 5 + c.rand() * 3; b.cool = b.timer + 2; b.since = 0; },
        update: (b, c) => {
            b.since += c.dt;
            if (b.timer <= 0) return b.pers.home && c.perches?.length ? 'home' : 'idle';  // clowns head home after a scare
            const it = I(b, 0.6, null);
            it.band = b.pers.band; it.shoal = b.pers.social; it.tight = 1 + 1.5 * Math.max(0, 1 - b.since / 6);
            return it;
        },
    },
    nibble: {  // ponytail: spots are random points on the sand; use real plant spots if Scene ever exports them
        enter: (b, c) => { b.tx = c.b.x + c.f.pad + c.rand() * (c.b.w - 2 * c.f.pad); b.ty = sandY(c); b.timer = 12; b.got = false; },
        update: (b, c) => {
            const at = Math.abs(c.f.x - b.tx) + Math.abs(c.f.y - b.ty) < 18;
            if (at && !b.got) { b.got = true; b.timer = 3 + c.rand() * 4; b.nod = 0; }
            if (b.timer <= 0) return 'idle';
            if (at && (b.nod -= c.dt) <= 0) { b.nod = 1.2; b.nods++; }  // noses the sand
            b.pt.x = b.tx + 9; b.pt.y = b.ty + 20;
            const it = to(I(b, at ? 0.3 : 0.9, b.pt), b.tx, b.ty);
            it.chomp = at;
            return calm(b, c, it);
        },
    },
    rest: {  // hang still low down near the glass ends, where the decor sits; fins barely move at night
        enter: (b, c) => {
            const side = c.rand() < 0.5 ? 0.12 : 0.88;
            b.tx = c.b.x + c.b.w * (side + (c.rand() - 0.5) * 0.15); b.ty = sandY(c) - 20 - c.rand() * 60; b.timer = 8 + c.rand() * 8;
            b.yawn = 0;
        },
        update: (b, c) => {
            if (b.timer <= 0) return 'idle';
            if (c.rand() < c.dt / 40) b.yawn = 0.6;  // a slow gape now and then
            b.yawn -= c.dt;
            const it = to(I(b, 0.6), b.tx, b.ty);
            it.shoal = 0; it.fin = c.night; it.chomp = b.yawn > 0;
            return calm(b, c, it);
        },
    },
    hover: {  // lionfish: hang in mid water, fins fanned, turning to show off now and then
        enter: (b, c) => { b.tx = c.f.x; b.ty = c.f.y; b.timer = 8 + c.rand() * 12; b.show = c.rand() < 0.4; },
        update: (b, c) => {
            if (b.timer <= 0) return 'idle';
            const it = sway(b, b.tx, b.ty, 0.3);
            it.fin = true; it.face = b.show && b.timer < 4;
            return calm(b, c, it);
        },
    },
    sit: {  // pleco: parked on the sand for minutes, now and then clinging to the front glass instead
        enter: (b, c) => { b.tx = c.f.x; b.ty = sandY(c); b.timer = 60 + c.rand() * 180; b.cling = c.rand() < 0.1 ? 20 + c.rand() * 40 : 0; },
        update: (b, c) => {
            b.cling = Math.max(0, b.cling - c.dt);
            if (b.timer <= 0) { b.cling = 0; return 'idle'; }
            const it = to(I(b, 0.2, null), b.tx, b.ty);
            it.shoal = 0; it.fin = true;
            return calm(b, c, it);
        },
    },
    home: {  // clownfish: hang at its own plant (its anemone stand-in)
        enter: (b, c) => { b.timer = 8 + c.rand() * 12; },
        update: (b, c) => {
            const p = c.perches?.[b.homeIdx % (c.perches?.length || 1)];
            return !p || b.timer <= 0 ? 'idle' : calm(b, c, sway(b, p.x, p.y, 0.5));
        },
    },
    flare: {  // betta: stops, faces the rival, swells
        enter: (b, c) => { b.timer = 3; b.flareCool = 40; },
        update: (b, c) => {
            if (b.timer <= 0) return 'idle';
            const it = to(I(b, 0, c.p), c.f.x, c.f.y);
            it.face = true; it.flare = true; it.shoal = 0;
            return it;
        },
    },
    stalk: {  // lionfish: creeps after a small fish for a while (never catches it)
        enter: (b, c) => { b.timer = 6; b.stalkCool = 30; },
        update: (b, c) => {
            const m = b.prey;
            if (!m || !c.mates.some(o => o.f === m) || b.timer <= 0) return 'idle';
            const it = to(I(b, 0.4, m), m.x, m.y);
            it.fin = true;
            return calm(b, c, it);
        },
    },
    follow: {
        enter: (b, c) => {
            let n = 0;
            for (const m of c.mates) if (m.f !== c.f) n++;
            let k = Math.floor(c.rand() * n);
            b.buddy = null;
            for (const m of c.mates) if (m.f !== c.f && k-- === 0) b.buddy = m.f;
            b.timer = 6 + c.rand() * 6;
        },
        update: (b, c) => {
            const m = b.buddy;
            if (!m || !c.mates.some(o => o.f === m) || b.timer <= 0) return 'idle';
            const behind = 30 + c.f.pad + m.pad;  // trail just behind the buddy's tail
            return calm(b, c, to(I(b, 1.3, m), m.x - Math.cos(m.dir) * behind, m.y - Math.sin(m.dir) * behind));
        },
    },
    feed: {  // claim a piece, ease in, line up the mouth, snap; a miss carries the fish past and it loops back
        enter: (b, c) => { b.timer = 15; b.retarget = 1; b.over = 0; b.eat = 0; claim(b, flake(b, c)); },
        update: (b, c) => {
            if (b.timer <= 0) { b.foodCool = 2; return 'idle'; }  // no endless chases
            if ((b.retarget -= c.dt) <= 0 || !b.food?.live) { b.retarget = 1; claim(b, flake(b, c)); }
            const k = b.food, { f, b: w } = c;
            if (!k) return 'idle';
            if (b.over > 0) {
                b.over -= c.dt;
                const it = to(I(b, 1.2, k), f.x + Math.cos(f.dir) * 80, f.y + Math.sin(f.dir) * 80);
                it.shoal = 0;
                return it;
            }
            // bug fix: fish aimed their middle at the flake (ate with it in the belly) and trailed a sinking
            // one forever. Now the body stops beside it with the mouth on the flake, aiming 0.7 s ahead of its
            // fall; clamped to where steer lets the fish's centre go, so food by the glass or the sand stays in reach.
            // ponytail: mouth = 0.8 pad ahead of the centre; read a mouth point from the manifest if fish look off
            const side = f.x <= k.x ? 1 : -1, mo = 0.8 * f.pad, at = b.pt;
            at.x = Math.max(w.x + f.pad, Math.min(w.x + w.w - f.pad, k.x - side * mo));
            at.y = Math.max(w.y + f.pad, Math.min(sandY(c), k.y + (k.settled ? 0 : (k.vy || 0) * 0.7)));
            const d = dist(f, at), mx = f.x + (Math.cos(f.dir) >= 0 ? mo : -mo) - k.x, my = f.y - k.y;
            const it = to(I(b, 0.3, k), at.x, at.y);
            it.shoal = 0;
            if (b.eat > 0) { b.eat -= c.dt; it.chomp = true; return it; }
            if (mx * mx + my * my < (10 + 0.2 * f.pad) ** 2) {
                if (c.rand() < (b.fed >= 50 ? 0.1 : 0.2)) {  // missed: knocks it, overshoots, comes round again
                    c.feeder?.kick(k, Math.cos(f.dir) * 12);
                    b.over = 0.3;
                } else if (c.feeder ? c.feeder.bite(k) : (k.live = false, true)) {
                    b.fed++;
                    b.nods++;
                    b.eat = 0.4;
                    b.timer = 15;
                    if (!k.live) release(b);
                }
                b.retarget = 0.4;
                it.chomp = true;
                return it;
            }
            const fast = (1.6 + 0.3 * Math.min(1, b.fed / 50)) * (b.pers.curious < 0.3 ? 0.8 : 1);
            it.speed = d > 120 ? fast : Math.min(fast, 0.6 + d / 120);
            it.chomp = d < 40;
            if (d < 80) it.pitch = Math.max(-0.45, Math.min(0.45, Math.atan2(k.y - f.y, Math.abs(k.x - f.x) + 1)));
            return it;
        },
    },
    gulp: {  // corydoras dart up for a gulp of air, then sink back home
        enter: (b, c) => { b.tx = c.f.x + (c.rand() - 0.5) * 120; b.ty = c.b.y + c.f.pad; b.timer = 6; },
        update: (b, c) => b.timer <= 0 || c.f.y < b.ty + 12 ? 'idle' : to(I(b, 2.5, null), b.tx, b.ty),
    },
};

export function makeBrain(pers, rand = Math.random) {
    return { pers, state: 'idle', timer: 4 + rand() * 6, cool: 0, still: 0, panic: 0, fx: 0, fy: 0, fed: 0, dart: 0, food: null,
        foodBorn: -1, foodCool: 0, react: -1, startle: -1, flareCool: 10, stalkCool: 10, visitCool: 20, nods: 0, cling: 0, homeIdx: 0,
        pet: false, greet: 0, fright: 0,
        it: Object.fromEntries(KEYS.map(k => [k, undefined])), pt: { x: 0, y: 0 } };
}

function enter(b, name, c) {
    if (b.state === 'feed' && name !== 'feed') release(b);
    b.state = name;
    STATES[name].enter(b, c);
}

// One tick of thinking: returns this tick's intent.
export function think(b, c) {
    const dt = c.dt;
    b.timer -= dt; b.cool -= dt; b.dart -= dt; b.foodCool -= dt; b.flareCool -= dt; b.stalkCool -= dt; b.visitCool -= dt;
    b.still = c.p && c.p.speed < 30 ? b.still + dt : 0;
    // a fast cursor or a moving window nearby startles every fish whatever it was doing; panic
    // spreads to calm neighbours a beat later (a ripple through the school)
    const p = c.p, calmNow = b.state !== 'flee';
    const scare = calmNow && p && p.speed > FAST * b.pers.nerve * tame(b) && dist(c.f, p) < SEE * 1.5;
    const th = calmNow && !scare && threat(c);
    const spooked = calmNow && !scare && !th && b.cool <= 0 && b.startle < 0 && mateIn(c, 'flee', 220);
    if (spooked) { b.startle = 0.08 + c.rand() * 0.25; b.fx = spooked.b.fx; b.fy = spooked.b.fy; }
    // food: a short reaction delay first (bold fish get there before shy ones)
    const food = calmNow && b.state !== 'feed' && b.foodCool <= 0 && c.food ? flake(b, c) : null;
    if (!food) b.react = -1;
    else if (b.react < 0) b.react = (1 - b.pers.curious) * 1.2 + c.rand() * 0.5;
    let r = null;
    if (scare) { b.fx = p.x; b.fy = p.y; r = 'flee'; b.startle = -1; }
    else if (th) { b.fx = th.x + th.w / 2; b.fy = th.y + th.h / 2; r = 'flee'; b.startle = -1; }
    else if (b.startle >= 0 && (b.startle -= dt) < 0) r = calmNow ? 'flee' : null;
    else if (food && (b.react -= dt) < 0) r = 'feed';
    else if (c.wake && p && calmNow && c.curiosity !== false && (b.pet || dist(c.f, p) < SEE * 3)) r = 'curious';
    if (c.attnNew && c.f.y < c.b.y + c.b.h * 0.35) b.dart = 0.5;  // surface fish dart at a notification
    r ??= STATES[b.state].update(b, c);
    for (let i = 0; typeof r === 'string' && i < 4; i++) {
        enter(b, r, c);
        r = STATES[r].update(b, c);
    }
    if (typeof r === 'string') r = I(b, 0.6, null);
    if (c.night && b.pers.huddle && r.band) { r.band = b.pers.huddle; r.tight = 3; r.speed *= 0.8; }
    if (b.dart > 0) r.speed *= 2.5;
    else if (b.state !== 'flee') r.speed *= c.lazy ?? 1;
    return r;
}
