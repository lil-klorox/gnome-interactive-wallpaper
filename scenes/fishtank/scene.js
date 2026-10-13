// Fishtank scene: tank.js (scenery, critters, food) + fish.js, wired to the host's ctx. ctx.settings
// is refreshed in place, so it is read every tick.
// Back to front: water + rays/caustics, far plates, far fish layer, decor, bubbler, sand/rocks/snail,
// near fish layer, foreground plants. A fish = brain.js (state machine -> intent), steer.js (intent ->
// motion), fish.js (frame from yaw + tail phase, pupils, puff); personality is per-species data.
// World reactions: moving/new windows -> flee; idle > 600 s -> rest, light dims; lights off on the
// engine's schedule (world.lightsOn/warm); notification -> bubbles + glance; click on bare desktop ->
// flakes, fish feed. Store {fish: {id: {born, fed}}}: fish grow over 14 days, fed fish get bolder.
import { Tank } from './tank.js';
import { School } from './fish.js';
import { hand, gesture } from './food.js';

const ACT = { calm: 0.7, normal: 1, lively: 1.3 };

export default function create(ctx) {
    const S = ctx.settings;
    const env = { act: ACT[S.activity], curiosity: S.curiosity };
    const tank = new Tank(ctx, S, env), school = new School(ctx, tank, env);
    // food falls in the far layer as often as fish live there (no far fish: all near)
    const share = () => { tank.food.farShare = school.farShare; };
    share();
    ctx.onSettings(keys => { school.onSettings(keys); share(); });
    const P = ctx.world.pointer;
    const g = hand();
    g.down = P.down;
    return {
        tick(dt, t) {
            env.act = ACT[S.activity];
            env.curiosity = S.curiosity;
            if (ctx.world.gap) tank.food.skip(ctx.world.gap);
            // on bare desktop: a click drops a pinch, holding pours
            const top = P.y < tank.swimBounds.y + 40;
            switch (gesture(g, P, dt)) {
            case 'drop':
                tank.food.drop(P.x, P.y, S.food);
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
