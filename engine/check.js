// `gjs -m engine/check.js` (make check): host math, then every scene's own check.
import Gio from 'gi://Gio';
import {parseManifest, scaleFor, bytesOf, frameOffset, maxHeight, canvasBytes, tileRange, BUDGET} from './render.js';
import {spacing, heading, shear, spring} from './bend.js';
import {makeWorld, update, covers, changed} from './world.js';
import {resolve, encode, lightsAt, posterPlan, logLines, POSTER_COLOR} from './settings.js';
import {SCENES} from '../scenes/index.js';

const ok = (c, msg) => { if (!c) throw new Error('FAIL: ' + msg); };

// render
ok(scaleFor(1440, 1440, 10e6, 64e6) === 1, 'k=1 at ref');
ok(scaleFor(720, 1440, 10e6, 64e6) === 0.5, 'k halves with the screen');
const big = {a: {w: 4000, h: 4000, n: 1, cols: 1, px: [4000, 4000]}, b: {w: 3000, h: 1000, n: 1, cols: 1, px: [3000, 1000]}};
ok(bytesOf(big, scaleFor(1440, 1440, bytesOf(big, 1), 64e6)) <= 64e6, 'over-budget art shrinks under budget');
ok(String(frameOffset({w: 160, h: 96, n: 64, cols: 8}, 9)) === '160,96', 'frame 9 is row 1 col 1');
const m = parseManifest('{"ref":1440,"images":{"a":{"w":"x"},"b":{"w":1,"h":1},"../c":{"w":1,"h":1},"d":{"w":1,"h":1,"n":4,"cols":5},"e":null,"f":{"w":1,"h":1,"n":5000}}}');
ok(Object.keys(m.images).join() === 'b' && m.images.b.n === 1 && m.images.b.cols === 1, 'bad entries dropped');
const pts = parseManifest('{"ref":1,"images":{"a":{"w":1,"h":1,"base":[1,"x"],"eyes":[[1,2]],"foot":[0,0,1,1]}}}').images.a;
ok(pts.base === undefined && pts.eyes && pts.foot, 'non-numeric point dropped, numeric lists kept');
ok(String(parseManifest('{"ref":1440,"images":{"a":{"w":10.5,"h":4,"n":3,"cols":2}}}').images.a.px) === '21,8', 'px-less entry: px from w·cols × h·rows');
ok(maxHeight([], false) === 0 && maxHeight([{height: 720, geometry_scale: 2}, {height: 1080}], false) === 1440, 'no monitors = 0, not -Infinity; scale applied');

// canvas tiles
ok(canvasBytes(1000, 700, 256) === 4 * 3 * 256 * 256 * 4, 'canvas: 1000x700 / 256 = 4x3 whole tiles');
ok(String(tileRange(255, 0, 257, 1, 256, 4, 3)) === '0,0,2,1', 'dirty across a tile edge touches exactly two tiles');
ok(String(tileRange(-50, -5, 9999, 9999, 256, 4, 3)) === '0,0,4,3' && tileRange(-9, 0, -1, 5, 256, 4, 3)[2] === 0, 'dirty clamps; off-canvas is empty');
ok(bytesOf(big, 1) + canvasBytes(4096, 2304, 256) > BUDGET, 'art + canvas over budget is caught by the sum');

// bend
ok(Math.abs(spacing(100, 0.21) - 58) < 1e-9, 'pieces fading 21 % each end sit 58 % apart');
ok(heading(-1, 1) === 45 && heading(1, 1) === 45, 'mirrored sprite keeps the unmirrored angle');
{
    let got = null;
    const m = {init_from_2d: (...v) => (got = v, m)}, a = {get_transform: () => m, set_transform: x => ok(x === m, 'shear sets the matrix')};
    shear(a, 45, 10);
    ok(Math.abs(got[2] + 1) < 1e-9 && Math.abs(got[4] - 10) < 1e-9, 'shear slides rows, joint row py stays put');
    const p = {bend: 0, bv: 0}, dt = 1 / 30;
    for (let i = 0; i < 300; i++) { p.bv += 400 * dt; spring(p, dt); ok(Math.abs(p.bend) <= 1 && Math.abs(p.bv) <= 4, 'bend clamped'); }
    for (let i = 0; i < 300; i++) spring(p, dt);
    ok(p.bend === 0 && p.bv === 0, 'bend comes to rest');
}

// world
const w = makeWorld(), raw = {mx: 100, my: 0, mw: 1000, mh: 500, px: 300, py: 200, bare: true, down: true,
    rects: [{x: 150, y: 50, w: 100, h: 100, id: 1}, {x: 2000, y: 0, w: 50, h: 50, id: 2}], grabbing: 1,
    idleMs: 0, hour: 12, dark: false, notes: 3, lights: {on: false, warm: true}};
update(w, raw, 0.1);
ok(!w.lightsOn && w.warm && !w.ready, 'lights copied, not ready yet');
ok(w.pointer.x === 200 && w.pointer.over && w.pointer.speed === 0 && w.pointer.down, 'pointer local, no speed on entry');
ok(w.windows.length === 1 && w.windows[0].x === 50 && w.windows[0].moving, 'grabbed rect moving, off-monitor dropped');
raw.px += 10;
raw.down = false;
update(w, raw, 0.1);
ok(w.pointer.speed === 50 && !w.pointer.down, 'speed smooths, down follows the button');
raw.bare = false;
raw.notes = 1;
update(w, raw, 0.1);
ok(w.pointer.speed === 0 && !w.pointer.over, 'speed zero when not over');
ok(w.notifications === 3, 'notifications only climb');
// window motion: monitor-local, smoothed like pointer.speed; present at the first update = old
const wm = makeWorld(), rw = {...raw, rects: [{x: 200, y: 10, w: 50, h: 50, id: 7}], grabbing: null,
    area: {x: 100, y: 30, w: 900, h: 470}};
update(wm, rw, 0.1);
ok(wm.windows[0].age >= 3600 && wm.windows[0].vx === 0, 'window present at the first update is old');
ok(JSON.stringify(wm.area) === '{"x":0,"y":30,"w":900,"h":470}', 'work area made monitor-local');
rw.rects = [rw.rects[0], {x: 300, y: 10, w: 50, h: 50, id: 8}];
update(wm, rw, 0.1);
rw.rects[1].x += 10;
update(wm, rw, 0.1);
ok(wm.windows[1].vx === 50 && wm.windows[1].vy === 0, 'new window: x +10 in 0.1 s gives vx 50');
update(wm, {...rw, area: null}, 0.1);
ok(wm.windows[1].vx === 25 && Math.abs(wm.windows[1].age - 0.2) < 1e-9 && wm.area.y === 30, 'unmoved halves vx, age counts, null area kept');
update(wm, {...rw, rects: [rw.rects[0]]}, 0.1);
update(wm, rw, 0.1);
ok(wm.windows[1].age === 0 && wm.windows[0].age > 3600, 'missing for one update, then back = new');
// sleepy-tick wake test
const last = {}, cr = {px: 1, py: 2, down: false, notes: 0, dark: false, lights: {on: true, warm: false}};
changed(cr, last);
ok(!changed(cr, last), 'nothing changed = stay asleep');
cr.px++;
ok(changed(cr, last) && !changed(cr, last), 'pointer move wakes once');
cr.notes++;
ok(changed(cr, last), 'a notification wakes');
cr.lights.on = false;
ok(changed(cr, last), 'lights flip wakes');
const A = {x: 0, y: 32, w: 1000, h: 500};
ok(covers([{x: 0, y: 32, w: 500, h: 500}, {x: 500, y: 0, w: 600, h: 600}], A), 'two tiles cover');
ok(!covers([{x: 0, y: 32, w: 499, h: 500}, {x: 500, y: 32, w: 500, h: 500}], A), 'a 1 px gap does not');
ok(!covers([{x: 0, y: 32, w: 1000, h: 250}, {x: 0, y: 283, w: 1000, h: 250}], A), 'a horizontal gap does not');
ok(!covers([], A) && covers([{x: -5, y: 0, w: 2000, h: 900}], A), 'nothing / one big window');

// settings
const D = [{key: 'b', type: 'bool', default: true}, {key: 'i', type: 'int', default: 3, min: 0, max: 8},
    {key: 'd', type: 'double', default: 0.5, min: 0, max: 1, step: 0.1},
    {key: 'c', type: 'choice', default: 'x', choices: [['x', 'X'], ['y', 'Y']]}, {key: 't', type: 'time', default: 360}];
const DEF = '{"b":true,"i":3,"d":0.5,"c":"x","t":360}';
for (const bad of ['nope', '[1]', 'null', '{"s":5}', '{"s":{"b":"yes","i":"4","d":null,"c":"z","t":1500}}', '{"other":{"b":false}}'])
    ok(JSON.stringify(resolve(D, bad, 's')) === DEF, `bad settings fall back to defaults: ${bad}`);
const v = resolve(D, '{"s":{"b":false,"i":99,"d":0.33,"c":"y","t":1439,"zz":1},"other":{"q":1}}', 's');
ok(JSON.stringify(v) === '{"b":false,"i":8,"d":0.3,"c":"y","t":1439}', 'clamped, snapped, unknown key dropped');
ok(resolve(D, '{"s":{"i":2.6,"t":-1}}', 's').i === 3 && resolve(D, '{"s":{"t":-1}}', 's').t === 360, 'int rounds, time range');
const enc = encode(D, '{"other":{"q":1},"s":{"zz":1}}', 's', {...v, i: 3});
ok(enc === '{"other":{"q":1},"s":{"b":false,"d":0.3,"c":"y","t":1439}}', 'encode: declared non-defaults only, others kept');
ok(encode(D, enc, 's', {}) === '{"other":{"q":1}}' && encode(D, 'junk', 's', {i: 4}) === '{"s":{"i":4}}', 'reset / bad json');
// A declaration the settings window can draw: known type, real choices, sane range, default that
// survives resolve() unchanged (a sentinel default shows a clamped or unlisted one), unique keys.
const declBad = decl => {
    const keys = new Set();
    for (const d of decl) {
        if (d.type === 'log') {  // read-only: needs a store path and a kind -> sentence map
            if (!d.key || keys.has(d.key) || !d.label || !Array.isArray(d.path) || !d.kinds || typeof d.kinds !== 'object')
                return d.key ?? '?';
            keys.add(d.key);
            continue;
        }
        const lo = d.min ?? -Infinity, hi = d.max ?? Infinity;
        const back = v => resolve([{...d, default: Symbol.for('x')}], JSON.stringify({s: {[d.key]: v}}), 's')[d.key];
        if (!d.key || keys.has(d.key) || !d.label || !['bool', 'int', 'double', 'choice', 'time', 'action'].includes(d.type) ||
            (d.type === 'choice' && !d.choices?.length) || (d.type === 'action' && d.rebuild) || lo > hi || (d.step !== undefined && !(d.step > 0)) ||
            back(d.default) !== d.default || ('still' in d && back(d.still) !== d.still))
            return d.key ?? '?';
        keys.add(d.key);
    }
    return null;
};
for (const bad of [[{key: 'c', type: 'choice', label: 'C', default: 'x'}], [{key: 'i', type: 'int', label: 'I', default: 1, min: 5, max: 2}],
    [{key: 'i', type: 'int', label: 'I', default: 9, min: 0, max: 8}], [D[0], {...D[0]}].map(d => ({...d, label: 'B'}))])
    ok(declBad(bad), `bad declaration caught: ${JSON.stringify(bad)}`);
ok(declBad([{key: 'l', type: 'log', label: 'L', kinds: {}}]), 'log without a path caught');
ok(declBad([{...D[1], label: 'I', still: 9}]), 'a still value outside the range caught');
const ACT = {key: 'a', type: 'action', label: 'Go', default: 0};
ok(!declBad([ACT]) && resolve([ACT], '{"s":{"a":2}}', 's').a === 2 && encode([ACT], '', 's', {a: 1}) === '{"s":{"a":1}}', 'action: 0 fits, a press round-trips');
ok(resolve([ACT], '{"s":{"a":true}}', 's').a === 0 && resolve([ACT], '{"s":{"a":-1}}', 's').a === 0, 'action: bool / negative rejected');
const LOG = {key: 'l', type: 'log', label: 'Log', path: ['tank', 'log'], kinds: {fry: 'Baby fish', yawn: 'A yawn'}};
ok(!declBad([LOG]) && !('l' in resolve([LOG], '{"s":{"l":5}}', 's')), 'log is valid and stores nothing');
const days = Array.from({length: 9}, (_, i) => ({day: `2026-10-0${i + 1}`, kind: i % 2 ? 'fry' : 'yawn'}));
const lines = logLines(LOG, {tank: {log: [...days, {day: 'x', kind: 'fry'}, {day: '2026-10-10', kind: 'toString'}, null, 7]}});
ok(lines.length === 7 && lines[0].day === '2026-10-09' && lines[0].text === 'A yawn' && lines[6].day === '2026-10-03', 'log: newest 7, bad entries skipped');
ok([null, {}, {tank: 5}, {tank: {log: 'no'}}, JSON.parse('{"__proto__":{"log":[]}}')].every(st => logLines(LOG, st).length === 0), 'log: missing/odd store = no lines');
for (const [id, s] of Object.entries(SCENES))
    ok(!declBad(s.settings ?? []), `${id}.${declBad(s.settings ?? [])}: declaration the settings window can draw`);

// lights
const L = (m, mode = 'auto', on = 360, off = 1260) => { const r = lightsAt(m, mode, on, off); return `${+r.on}${+r.warm}`; };
ok(L(720) === '10' && L(1290) === '01' && L(1320) === '00' && L(60) === '00', 'day on, evening warm, night off');
ok(L(359) === '01' && L(360) === '11' && L(404) === '11' && L(405) === '10', 'on at the switch, warm 45 min either side');
ok(L(23 * 60, 'auto', 1320, 360) === '10' && L(3 * 60, 'auto', 1320, 360) === '10' && L(720, 'auto', 1320, 360) === '00', 'lit span wraps midnight');
ok(L(5, 'auto', 1420, 360) === '11', 'warm window wraps midnight');
ok(L(100, 'auto', 500, 500) === '10' && L(60, 'on') === '10' && L(720, 'off') === '00', 'on == off, always on/off');

// poster
const BASE = '/ext/scenes/', P = {uri: `file://${BASE}fishtank/poster.jpg`, dark: null};
const mine = {uri: 'file:///me.jpg', dark: 'file:///me-d.jpg', options: 'zoom', color: '#023c88'};
const ourBg = {uri: P.uri, dark: P.uri, options: 'zoom', color: POSTER_COLOR};
let pp = posterPlan(mine, '', P, BASE);
ok(pp.save === mine && pp.apply.uri === P.uri && pp.apply.dark === P.uri && pp.apply.color === POSTER_COLOR, 'fresh install saves and applies');
pp = posterPlan(ourBg, JSON.stringify(mine), P, BASE);
ok(!pp.save && pp.apply.uri === P.uri, 're-enable after lock: poster already up, nothing saved twice');
pp = posterPlan(ourBg, JSON.stringify(mine), {uri: `${BASE}dot/poster.jpg`, dark: `${BASE}dot/poster-dark.jpg`}, BASE);
ok(!pp.save && pp.apply.dark.endsWith('dot/poster-dark.jpg'), 'scene switch keeps the saved wallpaper');
pp = posterPlan(mine, '', {uri: `${BASE}dot/poster-dark.jpg`}, BASE);
ok(pp.apply.uri === pp.apply.dark && pp.apply.uri.endsWith('poster-dark.jpg'), 'lights off: the night poster for both styles');
ok(!posterPlan(mine, JSON.stringify(mine), P, BASE).save, 'same wallpaper is not saved again');
pp = posterPlan(ourBg, JSON.stringify(mine), null, BASE);
ok(JSON.stringify(pp.apply) === JSON.stringify(mine) && pp.clear && !pp.reset, 'turn off restores');
pp = posterPlan(ourBg, '{bad', null, BASE);
ok(!pp.apply && pp.reset && pp.clear, 'corrupt saved + ours showing: reset to GNOME defaults');
ok(!posterPlan(ourBg, '{bad', P, BASE).save, 'corrupt saved + ours showing: our poster never saved');
pp = posterPlan(mine, JSON.stringify({...mine, uri: 'file:///old.jpg'}), null, BASE);
ok(!pp.apply && !pp.reset && pp.clear, 'user changed the wallpaper meanwhile: leave theirs');
ok(!posterPlan(ourBg, JSON.stringify(ourBg), null, BASE).apply, 'a saved poster is never restored');
const half = {...mine, dark: ourBg.dark};  // someone set only picture-uri while we ran
pp = posterPlan(half, '', P, BASE);
ok(pp.save?.dark === mine.uri, 'half-ours wallpaper saved with their uri for dark');
pp = posterPlan(half, JSON.stringify(mine), null, BASE);
ok(pp.apply?.dark === mine.uri && pp.apply.uri === mine.uri && !pp.reset, 'turn off clears our leftover dark poster');

// Each scene's own check.js, when it has one.
for (const id of Object.keys(SCENES)) {
    if (Gio.File.new_for_uri(import.meta.url).get_parent().resolve_relative_path(`../scenes/${id}/check.js`).query_exists(null))
        await import(`../scenes/${id}/check.js`);
}
console.log('check: ok');
