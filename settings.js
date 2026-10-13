// Pure (no gi, prefs loads it too): scene settings, lights schedule, poster plan, store parsing.
export const STORE_MAX = 64 * 1024;  // also caps the scene-settings JSON
const WARM = 45;  // minutes either side of an automatic light switch that get the warm tint
export const POSTER_COLOR = '#031a26';  // shown before the poster decodes, instead of GNOME's blue

const isObj = v => !!v && typeof v === 'object' && !Array.isArray(v);
const parse = text => {
    try {
        const v = typeof text === 'string' && text.length <= STORE_MAX ? JSON.parse(text) : null;
        return isObj(v) ? v : {};
    } catch {
        return {};
    }
};

// A scene's store file bytes -> object; too big or bad = {}.
export const parseStore = raw => (raw.length <= STORE_MAX ? parse(new TextDecoder().decode(raw)) : {});

// The checked value, or undefined when it doesn't fit the declaration.
function valid(d, v) {
    switch (d.type) {
    case 'bool':
        return typeof v === 'boolean' ? v : undefined;
    case 'int':
    case 'double': {
        if (typeof v !== 'number' || !Number.isFinite(v))
            return undefined;
        const lo = d.min ?? -Infinity, hi = d.max ?? Infinity, step = d.step ?? (d.type === 'int' ? 1 : 0);
        const o = Number.isFinite(lo) ? lo : 0;
        let x = Math.min(hi, Math.max(lo, v));
        if (step > 0)
            x = Math.min(hi, Number((o + Math.round((x - o) / step) * step).toFixed(6)));
        return d.type === 'int' ? Math.round(x) : x;
    }
    case 'choice':
        return d.choices?.some(c => c[0] === v) ? v : undefined;
    case 'time':  // minutes since midnight
        return Number.isInteger(v) && v >= 0 && v < 1440 ? v : undefined;
    case 'action':  // how many times its button was pressed
        return Number.isInteger(v) && v >= 0 ? v : undefined;
    }
    return undefined;
}

// Trust boundary for `scene-settings`: every declared key valid (clamped/snapped/default). Never throws.
export function resolve(decl, json, id) {
    const all = parse(json), src = Object.hasOwn(all, id) && isObj(all[id]) ? all[id] : {}, out = {};
    for (const d of decl) {
        if (d.type !== 'log')  // read-only, nothing stored
            out[d.key] = valid(d, src[d.key]) ?? d.default;
    }
    return out;
}

// New JSON with this scene's block replaced by its non-default values; other scenes are kept.
export function encode(decl, json, id, values) {
    const all = parse(json), block = {};
    for (const d of decl) {
        const v = valid(d, values[d.key]);
        if (v !== undefined && v !== d.default)
            block[d.key] = v;
    }
    if (Object.keys(block).length)
        all[id] = block;
    else
        delete all[id];
    return JSON.stringify(all);
}

// A `log` row's lines from the store (outside input: odd entries skipped), newest first. Never throws.
export function logLines(d, store) {
    let v = store;
    for (const k of d.path ?? [])
        v = isObj(v) && Object.hasOwn(v, k) ? v[k] : undefined;
    if (!Array.isArray(v))
        return [];
    const kinds = isObj(d.kinds) ? d.kinds : {};
    return v.filter(e => isObj(e) && typeof e.day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(e.day) &&
            typeof e.kind === 'string' && Object.hasOwn(kinds, e.kind) && typeof kinds[e.kind] === 'string')
        .sort((a, b) => b.day.localeCompare(a.day)).slice(0, d.max ?? 7)
        .map(e => ({day: e.day, text: kinds[e.kind]}));
}

// Lights at `min` (minutes since midnight); on === off = always on. Reuse `out` to stay allocation-free.
export function lightsAt(min, mode, on, off, out = {on: true, warm: false}) {
    const auto = mode !== 'on' && mode !== 'off', span = (off - on + 1440) % 1440;
    const near = m => Math.min((min - m + 1440) % 1440, (m - min + 1440) % 1440) < WARM;
    out.on = mode === 'on' || (auto && (span === 0 || (min - on + 1440) % 1440 < span));
    out.warm = auto && span !== 0 && (near(on) || near(off));
    return out;
}

const BG = ['uri', 'dark', 'options', 'color'];

// What to do with GNOME's wallpaper keys; poster null = turning off; base = a path piece only our scenes have.
// Turning on saves+applies; off restores only if ours is showing (reset if nothing valid was saved).
export function posterPlan(cur, saved, poster, base) {
    const ours = u => typeof u === 'string' && u.includes(base);
    // Someone set only picture-uri while we ran: their uri stands in for our leftover dark one.
    const theirs = ours(cur.dark) ? {...cur, dark: cur.uri} : cur;
    if (poster) {
        const save = !ours(cur.uri) && JSON.stringify(theirs) !== saved ? theirs : null;
        return {save, apply: {uri: poster.uri, dark: poster.dark ?? poster.uri, options: 'zoom', color: POSTER_COLOR},
            reset: false, clear: false};
    }
    let back = null;
    try {
        const v = JSON.parse(saved);
        if (BG.every(k => typeof v?.[k] === 'string') && !ours(v.uri))
            back = Object.fromEntries(BG.map(k => [k, v[k]]));
    } catch {}
    const showing = ours(cur.uri);
    return {save: null, apply: showing ? back : theirs !== cur ? theirs : null, reset: showing && !back, clear: saved !== ''};
}
