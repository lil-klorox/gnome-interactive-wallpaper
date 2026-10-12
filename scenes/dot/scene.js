// Demo scene: the whole contract in one file. A dot eases toward the cursor, pops on each new
// notification and dims at night or in dark mode.
import Graphene from 'gi://Graphene';
import St from 'gi://St';

export default function create(ctx) {
    const r = ctx.h / 20;
    const dot = new St.Widget({width: 2 * r, height: 2 * r, pivot_point: new Graphene.Point({x: 0.5, y: 0.5}),
        style: `background-color: #ffbe3c; border-radius: ${r}px;`});
    ctx.root.add_child(dot);
    let x = ctx.w / 2, y = ctx.h / 2, notes = ctx.world.notifications, pop = 0;
    return {
        tick(dt) {
            const {pointer: p, hour, dark} = ctx.world;
            if (p.over) {
                const f = 1 - Math.exp(-3 * dt);
                x += (p.x - x) * f;
                y += (p.y - y) * f;
            }
            if (ctx.world.notifications !== notes) {
                notes = ctx.world.notifications;
                pop = 1;
            }
            pop = Math.max(0, pop - 2 * dt);
            dot.set_translation(x - r, y - r, 0);
            dot.set_scale(1 + pop, 1 + pop);
            dot.opacity = hour >= 21 || hour < 6 || dark ? 120 : 255;
        },
    };
}
