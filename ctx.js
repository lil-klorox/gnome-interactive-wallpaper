// The ctx a scene gets: textures (the only St.ImageContent code) and a per-scene JSON store.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {parseManifest, sizeAt, frameOffset} from './render.js';

const STORE_MAX = 64 * 1024;
const warn = msg => console.warn(`interactive-wallpaper: ${msg}`);

// One small sync read when a scene mounts. No manifest = a scene without art.
export function loadManifest(dir) {
    const f = dir.get_child('assets').get_child('manifest.json');
    if (!f.query_exists(null))
        return {ref: 1440, images: Object.freeze({})};
    return parseManifest(new TextDecoder().decode(f.load_contents(null)[1]));
}

function upload(content, pb) {
    const args = [pb.read_pixel_bytes(), pb.has_alpha ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
        pb.width, pb.height, pb.rowstride];
    // GNOME 48+ takes the Cogl context first. Try the old form first: too few args throws before
    // doing anything, while too many (old shell, new form) logs a GJS warning on every image.
    try {
        content.set_bytes(...args);
    } catch {
        content.set_bytes(global.stage.context.get_backend().get_cogl_context(), ...args);
    }
}

// Content is created now and stays empty (paints nothing) until the PNG decodes off the hot path.
function load(sc, cancel, name) {
    const e = sc.man.images[name];
    if (!e)
        throw new Error(`no image "${name}" in scene ${sc.id}`);
    const content = St.ImageContent.new_with_preferred_size(Math.round(e.w * e.cols), Math.round(e.h * Math.ceil(e.n / e.cols)));
    const [w, h] = sizeAt(e, sc.k);
    const fail = err => {
        if (!err.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
            warn(`${sc.id}/${name} failed to load: ${err.message}`);
    };
    sc.dir.get_child('assets').get_child(`${name}.png`).read_async(GLib.PRIORITY_LOW, cancel, (f, r1) => {
        try {
            const stream = f.read_finish(r1);
            GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(stream, w, h, false, cancel, (_s, r2) => {
                try {
                    stream.close_async(GLib.PRIORITY_LOW, null, null);
                    upload(content, GdkPixbuf.Pixbuf.new_from_stream_finish(r2));
                } catch (err) {
                    fail(err);
                }
            });
        } catch (err) {
            fail(err);
        }
    });
    return Object.freeze({...e, content});
}

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

// sc = {id, dir, man, k} (one per mounted scene); cache + cancel live on the extension instance,
// so every monitor and every sprite of a sheet share one texture.
export function makeCtx(sc, cache, cancel, root, w, h, world) {
    const image = name => {
        const key = `${sc.id}/${name}`;
        let e = cache.get(key);
        if (!e)
            cache.set(key, e = load(sc, cancel, name));
        return e;
    };
    const sheet = name => {
        const e = image(name);
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
    // ponytail: store is per scene load, so a quick off/on can overlap the old save with the new read; share by id if that bites.
    return Object.freeze({root, w, h, ref: sc.man.ref, images: sc.man.images, world, image, sheet, store: (sc.store ??= store(sc.id))});
}
