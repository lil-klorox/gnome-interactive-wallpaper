// Fishtank scene: scenery (tank.js) + fish (fish.js), wired to the host's ctx.
import { Tank } from './tank.js';
import { School } from './fish.js';

export default function create(ctx) {
    const tank = new Tank(ctx), school = new School(ctx, tank.fishLayers, tank.swimBounds);
    return {
        tick(dt, t) { tank.tick(dt, t); school.tick(dt, t); },
        destroy() { school.destroy(); },  // actors go with ctx.root, which the host destroys
    };
}
