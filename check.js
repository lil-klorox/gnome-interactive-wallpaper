// `gjs -m check.js`: host math, then every scene's own check.
import {parseManifest, scaleFor, bytesOf, frameOffset, BUDGET} from './render.js';
import {makeWorld, update, fpsMs} from './world.js';

const ok = (c, msg) => { if (!c) throw new Error('FAIL: ' + msg); };

// render
ok(scaleFor(1440, 1440, 10e6, 64e6) === 1, 'k=1 at ref');
ok(scaleFor(720, 1440, 10e6, 64e6) === 0.5, 'k halves with the screen');
const big = {a: {w: 4000, h: 4000, n: 1, cols: 1, px: [4000, 4000]}, b: {w: 3000, h: 1000, n: 1, cols: 1, px: [3000, 1000]}};
ok(bytesOf(big, scaleFor(1440, 1440, bytesOf(big, 1), 64e6)) <= 64e6, 'over-budget art shrinks under budget');
ok(String(frameOffset({w: 160, h: 96, n: 64, cols: 8}, 9)) === '160,96', 'frame 9 is row 1 col 1');
const m = parseManifest('{"ref":1440,"images":{"a":{"w":"x"},"b":{"w":1,"h":1},"../c":{"w":1,"h":1},"d":{"w":1,"h":1,"n":4,"cols":5},"e":null,"f":{"w":1,"h":1,"n":5000}}}');
ok(Object.keys(m.images).join() === 'b' && m.images.b.n === 1 && m.images.b.cols === 1, 'bad entries dropped');
ok(BUDGET === 65e6, 'budget');

// world
const w = makeWorld(), raw = {mx: 100, my: 0, mw: 1000, mh: 500, px: 300, py: 200, bare: true, down: true,
    rects: [{x: 150, y: 50, w: 100, h: 100, id: 1}, {x: 2000, y: 0, w: 50, h: 50, id: 2}], grabbing: 1,
    idleMs: 0, hour: 12, dark: false, notes: 3};
update(w, raw, 0.1);
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
ok(fpsMs(61) === 100 && fpsMs(5) === 33, 'fps drops past 60 s idle');

await import('./scenes/fishtank/check.js');
console.log('check: ok');
