// Demo scene: the whole contract in one file. A dot eases toward the cursor, pops on each new
// notification, dims when the lights are off or in dark mode, and follows its settings.
import Graphene from 'gi://Graphene';
import St from 'gi://St';

const COLORS = {amber: '#ffbe3c', mint: '#5fd8a8', rose: '#ff7a9c'};

export default function create(ctx) {
    // A plain backdrop: the scene paints the whole screen, so its poster can stand in for it.
    ctx.root.add_child(new St.Widget({width: ctx.w, height: ctx.h, style: 'background-color: #1b2a33;'}));
    const r = ctx.h * ctx.settings.size / 100;
    const dot = new St.Widget({width: 2 * r, height: 2 * r, pivot_point: new Graphene.Point({x: 0.5, y: 0.5})});
    const paint = () => (dot.style = `background-color: ${COLORS[ctx.settings.color]}; border-radius: ${r}px;`);
    paint();
    ctx.onSettings(paint);  // colour changes live; size is `rebuild`, so create() runs again instead
    ctx.root.add_child(dot);
    let x = ctx.w / 2, y = ctx.h / 2, notes = ctx.world.notifications, pop = 0;
    return {
        tick(dt) {
            const {pointer: p, lightsOn, dark} = ctx.world;
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
            dot.opacity = lightsOn && !dark ? 255 : 120;
            return p.over || pop > 0;  // false = nothing moves: the engine ticks it slowly until something changes
        },
    };
}
