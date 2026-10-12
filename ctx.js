// The ctx a scene gets: textures (the only St.ImageContent code) and a per-scene JSON store.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {PACKAGE_VERSION} from 'resource:///org/gnome/shell/misc/config.js';
import {parseManifest, sizeAt, frameOffset, canvasBytes, tileRange, BUDGET} from './render.js';

const STORE_MAX = 64 * 1024;
const warn = msg => console.warn(`interactive-wallpaper: ${msg}`);

// One small sync read when a scene mounts. No manifest = a scene without art.
export function loadManifest(dir) {
    const f = dir.get_child('assets').get_child('manifest.json');
    if (!f.query_exists(null))
        return {ref: 1440, images: Object.freeze({})};
    return parseManifest(new TextDecoder().decode(f.load_contents(null)[1]));
}

// GNOME 48 gave set_bytes() a Cogl context as its first argument.
const COGL_ARG = parseInt(PACKAGE_VERSION) >= 48;

function upload(content, bytes, format, w, h, stride) {
    if (COGL_ARG)
        content.set_bytes(global.stage.context.get_backend().get_cogl_context(), bytes, format, w, h, stride);
    else
        content.set_bytes(bytes, format, w, h, stride);
}

const uploadPixbuf = (content, pb) => upload(content, pb.read_pixel_bytes(),
    pb.has_alpha ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888, pb.width, pb.height, pb.rowstride);

// Content is created now and stays empty (paints nothing) until the PNG decodes off the hot path.
// rec.done turns true when the decode ends either way; rec.cbs run then (they count pending decodes).
function load(sc, cancel, name) {
    const e = sc.man.images[name];
    if (!e)
        throw new Error(`no image "${name}" in scene ${sc.id}`);
    const content = St.ImageContent.new_with_preferred_size(Math.round(e.w * e.cols), Math.round(e.h * Math.ceil(e.n / e.cols)));
    const [w, h] = sizeAt(e, sc.k);
    const rec = {e: Object.freeze({...e, content}), done: false, cbs: []};
    const finish = err => {
        if (err && !err.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
            warn(`${sc.id}/${name} failed to load: ${err.message}`);
        rec.done = true;
        rec.cbs.splice(0).forEach(f => f());
    };
    sc.dir.get_child('assets').get_child(`${name}.png`).read_async(GLib.PRIORITY_LOW, cancel, (f, r1) => {
        try {
            const stream = f.read_finish(r1);
            GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(stream, w, h, false, cancel, (_s, r2) => {
                try {
                    stream.close_async(GLib.PRIORITY_LOW, null, null);
                    uploadPixbuf(content, GdkPixbuf.Pixbuf.new_from_stream_finish(r2));
                    finish();
                } catch (err) {
                    finish(err);
                }
            });
        } catch (err) {
            finish(err);
        }
    });
    return rec;
}

// Kept across disable/enable so a quick lock/unlock reads what the last session just saved, not the
// disk copy its save hasn't replaced yet. At most 64 KB per scene.
const STORES = new Map();
const storeFor = id => STORES.get(id) ?? STORES.set(id, store(id)).get(id);

function store(id) {
    const dir = GLib.build_filenamev([GLib.get_user_data_dir(), 'interactive-wallpaper']);
    const file = Gio.File.new_for_path(GLib.build_filenamev([dir, `${id}.json`]));
    let data = null;  // one in-memory copy shared by every monitor; disk is read once
    let busy = false, next = null;
    // One write in flight: two overlapping async replaces could land out of order (older save last).
    const save = bytes => {
        if (busy) {
            next = bytes;
            return;
        }
        busy = true;
        GLib.mkdir_with_parents(dir, 0o700);
        // No cancellable: a save from destroy() during disable() must still land.
        file.replace_contents_bytes_async(new GLib.Bytes(bytes), null, false,
            Gio.FileCreateFlags.REPLACE_DESTINATION, null, (f, r) => {
                try {
                    f.replace_contents_finish(r);
                } catch {
                    warn(`${id} store save failed`);
                }
                busy = false;
                if (next) {
                    const b = next;
                    next = null;
                    save(b);
                }
            });
    };
    return {
        get() {
            if (data)
                return data;
            try {
                const raw = file.load_contents(null)[1];
                const v = raw.length <= STORE_MAX ? JSON.parse(new TextDecoder().decode(raw)) : warn(`${id} store over 64 KB, ignored`);
                data = v && typeof v === 'object' && !Array.isArray(v) ? v : {};
            } catch {
                data = {};
            }
            return data;
        },
        set(obj) {
            const bytes = new TextEncoder().encode(JSON.stringify(obj));
            if (bytes.length > STORE_MAX) {
                warn(`${id} store over 64 KB, not saved`);
                return;
            }
            data = obj;
            save(bytes);
        },
    };
}

// A grid of textures the scene paints itself from bytes (see docs/writing-a-scene.md, Canvas). The
// scene keeps its own state (a height field, say) and refills only the tiles it marked dirty.
function canvas(sc, root, opts) {
    const {w, h, tile = 256, px = 1} = opts ?? {};
    const int = (v, max) => Number.isInteger(v) && v > 0 && v <= max;
    if (!int(w, 16384) || !int(h, 16384) || !int(tile, 1024) || !(px > 0 && px <= 64))
        throw new Error('canvas needs whole w, h, tile and a positive px');
    const cols = Math.ceil(w / tile), rows = Math.ceil(h / tile), bytes = canvasBytes(w, h, tile);
    if (sc.art + sc.canvas + bytes > BUDGET)
        throw new Error('canvas over budget');
    sc.canvas += bytes;
    const actor = new Clutter.Actor({width: w * px, height: h * px});
    root.connect('destroy', () => {  // freed with ctx.root, even if the scene never added it there
        sc.canvas -= bytes;
        actor.destroy();
    });
    const contents = [], dirty = new Uint8Array(cols * rows), buf = new Uint8Array(tile * tile * 4);
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const tw = Math.min(tile, w - c * tile), th = Math.min(tile, h - r * tile);
            const content = St.ImageContent.new_with_preferred_size(tw, th);
            const a = new Clutter.Actor({content, x: c * tile * px, y: r * tile * px, width: tw * px, height: th * px});
            a.set_content_scaling_filters(Clutter.ScalingFilter.LINEAR, Clutter.ScalingFilter.LINEAR);
            actor.add_child(a);
            contents.push(content);
        }
    }
    let left = 0;
    return Object.freeze({
        actor, cols, rows, tile,
        dirty(x0, y0, x1, y1) {
            const [c0, r0, c1, r1] = tileRange(x0, y0, x1, y1, tile, cols, rows);
            for (let r = r0; r < r1; r++) {
                for (let c = c0; c < c1; c++) {
                    left += 1 - dirty[r * cols + c];
                    dirty[r * cols + c] = 1;
                }
            }
        },
        // fill(buf, x, y, tw, th): write premultiplied RGBA for cells x..x+tw, y..y+th, row stride tw*4.
        flush(fill, max = Infinity) {
            for (let i = 0; i < dirty.length && left > 0 && max > 0; i++) {
                if (!dirty[i])
                    continue;
                dirty[i] = 0;
                left--;
                max--;
                const x = (i % cols) * tile, y = Math.floor(i / cols) * tile;
                const tw = Math.min(tile, w - x), th = Math.min(tile, h - y);
                fill(buf, x, y, tw, th);
                upload(contents[i], new GLib.Bytes(buf.subarray(0, tw * th * 4)),
                    Cogl.PixelFormat.RGBA_8888_PRE, tw, th, tw * 4);
            }
            return left;
        },
    });
}

// sc = {id, dir, man, k, art, canvas, settings} (one per mounted scene; art/canvas = texture bytes);
// cache + cancel live on the extension instance, so every monitor and every sprite of a sheet share one
// texture. t = the host's per-monitor record: {root, world, pending, onSettings}. monitor = {index, count, primary}.
export function makeCtx(sc, cache, cancel, t, w, h, monitor) {
    const image = (name, fallback) => {
        if (!sc.man.images[name] && fallback !== undefined && sc.man.images[fallback]) {
            if (!(sc.swapped ??= new Set()).has(name))
                warn(`${sc.id}: no usable "${name}", using "${fallback}"`);
            sc.swapped.add(name);
            name = fallback;
        }
        const key = `${sc.id}/${name}`;
        let rec = cache.get(key);
        if (!rec)
            cache.set(key, rec = load(sc, cancel, name));
        if (!rec.done && !t.world.ready) {  // the host keeps the root hidden until these land
            t.pending++;
            rec.cbs.push(() => t.pending--);
        }
        return rec.e;
    };
    const sheet = (name, fallback) => {
        const e = image(name, fallback);
        const rows = Math.ceil(e.n / e.cols), xy = [0, 0];
        return {
            ...e,
            // e.w × e.h clip box; the child is the whole sheet, a frame change is one translation.
            make() {
                const a = new Clutter.Actor({width: e.w, height: e.h, clip_to_allocation: true});
                const c = new Clutter.Actor({content: e.content, width: e.w * e.cols, height: e.h * rows});
                c.set_content_scaling_filters(Clutter.ScalingFilter.LINEAR, Clutter.ScalingFilter.LINEAR);
                a.add_child(c);
                a._c = c;  // cached: show() runs per frame
                return a;
            },
            show(a, i) {
                if (a._f === i)
                    return;
                a._f = i;
                frameOffset(e, i, xy);
                a._c.set_translation(-xy[0], -xy[1], 0);
            },
        };
    };
    return Object.freeze({root: t.root, w, h, ref: sc.man.ref, images: sc.man.images, world: t.world, image, sheet,
        monitor, canvas: opts => canvas(sc, t.root, opts),
        store: (sc.store ??= storeFor(sc.id)), settings: sc.settings, onSettings: fn => (t.onSettings = fn)});
}
