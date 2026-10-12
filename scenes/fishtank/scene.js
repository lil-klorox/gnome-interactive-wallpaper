// Fishtank scene: scenery + critters + food (tank.js) and fish (fish.js), wired to the host's ctx.
// Settings are read fresh every tick from ctx.settings (the host refreshes it in place); fish counts and
// colours change live through onSettings; critters and decor rebuild the scene.
import { Tank } from './tank.js';
import { School } from './fish.js';
import { SETTINGS } from './settings.js';
import { hand, gesture } from './food.js';

const ACT = { calm: 0.7, normal: 1, lively: 1.3 };

export default function create(ctx) {
    const S = ctx.settings ?? Object.fromEntries(SETTINGS.map(d => [d.key, d.default]));  // older host: stock tank
    const env = { act: ACT[S.activity] ?? 1, curiosity: S.curiosity !== false };
    const tank = new Tank(ctx, S, env), school = new School(ctx, tank, env);
    // food falls in the far layer as often as fish live there (no far fish: all near)
    const share = () => {
        const [far, near] = school._mates;  // ponytail: School's per-layer lists; use a public count if fish.js ever exposes one
        tank.food.farShare = far.length / Math.max(1, far.length + near.length);
    };
    share();
    ctx.onSettings?.(keys => { school.onSettings(keys); share(); });
    const P = ctx.world.pointer;
    const g = hand();
    g.down = P.down;
    return {
        tick(dt, t) {
            env.act = ACT[S.activity] ?? 1;
            env.curiosity = S.curiosity !== false;
            // unseen a while: food that had landed is gone by now
            if (ctx.world.gap) for (const p of tank.food.pieces) if (p.settled) p.fade += ctx.world.gap;
            // on bare desktop: a click drops a pinch, holding pours
            const top = P.y < tank.swimBounds.y + 40;
            switch (gesture(g, P, dt)) {
            case 'drop':
                tank.food.drop(P.x, P.y, S.food ?? 7);
                if (top) tank.splash(P.x);
                break;
            case 'pour':
                tank.food.drop(P.x, P.y, 1);
                if (top && g.n % 3 === 0) tank.splash(P.x);
                break;
            }
            tank.tick(dt, t);
            school.tick(dt, t);
        },
        destroy() { school.destroy(); },  // actors go with ctx.root, which the host destroys
    };
}
