import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {SCENES} from './scenes/index.js';
import {makeWorld, update, fpsMs} from './world.js';
import {makeCtx, loadManifest} from './ctx.js';
import {bytesOf, scaleFor} from './render.js';
import {bgManagers, backgroundGroup, startingUp} from './shell.js';

const SLOW_TICKS = 30;  // this many over-budget ticks in a row (net) and the scene is stopped
const now = () => GLib.get_monotonic_time() / 1e6;
const count = a => a.get_children().reduce((n, c) => n + 1 + count(c), 0);

// Not shown while locked: no session-modes in metadata, so the shell disables us on lock.
export default class InteractiveWallpaper extends Extension {
    enable() {
        this._tanks = [];
        this._sigs = [];
        this._timer = 0;
        this._ms = 33;
        this._gen = 0;
        this._t0 = now();
        this._scene = null;
        this._grab = null;
        this._cache = new Map();
        this._cancel = new Gio.Cancellable();
        this.stats = {bytes: 0, k: 1, actors: 0, tickMs: 0, ticks: 0};
        this._raw = {mx: 0, my: 0, mw: 0, mh: 0, px: 0, py: 0, bare: false, down: false, rects: [],
            grabbing: null, idleMs: 0, hour: 0, dark: false, notes: 0};
        this._settings = this.getSettings();
        this._iface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        const dark = () => (this._raw.dark = this._iface.get_string('color-scheme') === 'prefer-dark');
        dark();
        const lm = Main.layoutManager, refresh = () => this._update();
        this._on(this._settings, 'changed::scene', () => this._load());
        this._on(this._iface, 'changed::color-scheme', dark);
        // ponytail: any of these re-checks every monitor and window; cheap, so no per-window tracking.
        this._on(lm, 'monitors-changed', () => this._rebuild());
        this._on(lm, 'startup-complete', () => this._load());
        this._on(global.display, 'restacked', refresh);
        this._on(global.display, 'in-fullscreen-changed', refresh);
        this._on(global.display, 'window-entered-monitor', refresh);
        this._on(global.display, 'grab-op-begin', (_d, w) => {
            this._grab = w;
            this._raw.grabbing = w?.get_stable_sequence() ?? null;
        });
        this._on(global.display, 'grab-op-end', () => {
            this._grab = this._raw.grabbing = null;
            this._update();
        });
        this._on(global.window_manager, 'size-changed', refresh);
        this._on(global.window_manager, 'minimize', refresh);
        this._on(global.window_manager, 'unminimize', refresh);
        this._on(global.workspace_manager, 'active-workspace-changed', refresh);
        this._on(Main.overview, 'showing', refresh);
        this._on(Main.overview, 'hidden', refresh);
        // Past the user's blank delay nobody can see the tank: pause, and wake on the first input.
        // Idle watches (unlike get_idletime) respect apps holding the screen awake, e.g. a video.
        this._session = new Gio.Settings({schema_id: 'org.gnome.desktop.session'});
        this._idle = global.backend.get_core_idle_monitor();
        this._blank = false;
        this._idleWatch = this._activeWatch = 0;
        const watchIdle = () => {
            const idle = this._idle, delay = this._session.get_uint('idle-delay');
            if (this._idleWatch)
                idle.remove_watch(this._idleWatch);
            this._idleWatch = delay && idle.add_idle_watch(delay * 1000, () => {
                this._blank = true;
                this._activeWatch ||= idle.add_user_active_watch(() => {
                    this._activeWatch = 0;
                    this._blank = false;
                    this._update();
                });
                this._update();
            });
        };
        watchIdle();
        this._on(this._session, 'changed::idle-delay', watchIdle);
        // Count notifications only; the objects themselves are never kept.
        const hook = src => src.connectObject('notification-added', () => this._raw.notes++, this);
        Main.messageTray.getSources().forEach(hook);
        this._on(Main.messageTray, 'source-added', (_t, src) => hook(src));
        if (!startingUp())
            this._load();
    }

    disable() {
        this._cancel.cancel();
        for (const [obj, id] of this._sigs)
            obj.disconnect(id);
        Main.messageTray.getSources().forEach(s => s.disconnectObject(this));
        this._stop();
        for (const w of [this._idleWatch, this._activeWatch].filter(Boolean))
            this._idle.remove_watch(w);
        this._clear();
        this._sigs = this._tanks = this._cache = this._cancel = this._scene = this._grab = this._session = this._idle = null;
        this._settings = this._iface = this._raw = this.stats = null;
    }

    _on(obj, sig, fn) {
        this._sigs.push([obj, obj.connect(sig, fn)]);
    }

    // Import the chosen scene (unknown id = the first one) and read its manifest, then mount it.
    async _load() {
        const gen = ++this._gen, cancel = this._cancel;
        this._clear();
        this._scene = null;
        const want = this._settings.get_string('scene');
        const id = Object.hasOwn(SCENES, want) ? want : Object.keys(SCENES)[0];
        try {
            const mod = await SCENES[id].load();
            if (cancel.is_cancelled() || gen !== this._gen)
                return;
            const dir = this.dir.get_child('scenes').get_child(id);
            this._scene = {id, dir, man: loadManifest(dir), k: 0, create: mod.default};
            this._rebuild();
        } catch (e) {
            logError(e, `interactive-wallpaper: scene ${id} failed to load`);
        }
    }

    _clear() {
        for (const t of this._tanks)
            t?.root?.destroy();
        this._tanks = [];
    }

    _rebuild() {
        this._clear();
        const sc = this._scene;
        if (!sc)
            return;
        const mons = Main.layoutManager.monitors;
        // X11 monitor geometry is already physical pixels; the optional call is for shells without X11.
        const x11 = Meta.is_wayland_compositor?.() === false;
        const physH = Math.max(...mons.map(m => m.height * (x11 ? 1 : m.geometry_scale ?? 1)));
        const k = scaleFor(physH, sc.man.ref, bytesOf(sc.man.images, 1));
        if (k !== sc.k) {  // textures are decoded at k, so a new k needs fresh ones
            sc.k = this.stats.k = k;
            this.stats.bytes = bytesOf(sc.man.images, k);
            this._cache.clear();
            console.log(`interactive-wallpaper: ${sc.id} textures ${(this.stats.bytes / 1e6).toFixed(1)} MB at k=${k.toFixed(3)}`);
        }
        bgManagers().forEach((mgr, i) => mons[i] && this._build(mgr, mons[i], i));  // lengths can differ mid-hotplug
        this._update();
    }

    _build(mgr, mon, i) {
        const sc = this._scene;
        // Non-reactive: the pointer is polled in _tick, so desktop clicks/menus are untouched.
        const root = new Clutter.Actor({width: mon.width, height: mon.height});
        const t = {root, mon, world: makeWorld(), scene: null, slow: 0, paused: false, dead: false};
        this._tanks[i] = t;
        // Also fires when the shell destroys the bg actor under us.
        root.connect('destroy', () => {
            t.dead = true;
            t.root = null;
            try {
                t.scene?.destroy?.();
            } catch (e) {
                logError(e, `interactive-wallpaper: ${sc.id} teardown`);
            }
        });
        // Wallpaper changed: shell swaps in a new bg actor, the old one fades out and dies.
        mgr.connectObject('changed', () => {
            root.destroy();
            this._build(mgr, mon, i);
            this._update();
        }, root);  // disconnected when root is destroyed
        mgr.backgroundActor.add_child(root);
        try {
            t.scene = sc.create(makeCtx(sc, this._cache, this._cancel, root, mon.width, mon.height, t.world));
            this.stats.actors = count(root);
            if (this.stats.actors > 300)
                console.warn(`interactive-wallpaper: ${sc.id} built ${this.stats.actors} actors`);
        } catch (e) {
            logError(e, `interactive-wallpaper: ${sc.id} build`);
            root.destroy();  // don't leave a half-built scene painted
        }
    }

    // "Bare" = desktop is topmost under the cursor. Polled: a desktop-icons/blur extension eats motion events.
    _bare(x, y) {
        if (Main.overview.visible)
            return false;
        const a = global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
        let w = a;
        while (w && !(w instanceof Meta.WindowActor))
            w = w.get_parent();
        return !!a && (a === global.stage || backgroundGroup()?.contains(a) ||
            w?.meta_window?.get_window_type() === Meta.WindowType.DESKTOP);
    }

    // On window/overview changes: refresh window rects and which monitors are covered.
    _update() {
        const covered = new Set(), rects = [];
        const ov = Main.overview.visible || this._blank;
        for (const w of global.workspace_manager.get_active_workspace().list_windows()) {
            if (!w.showing_on_its_workspace() || w.get_window_type() === Meta.WindowType.DESKTOP)
                continue;
            const r = w.get_frame_rect();
            rects.push({x: r.x, y: r.y, w: r.width, h: r.height, id: w.get_stable_sequence()});
            const max = w.is_maximized?.() ?? w.get_maximized() === Meta.MaximizeFlags.BOTH;
            if (max || w.is_fullscreen())
                covered.add(w.get_monitor());
        }
        this._raw.rects = rects;
        this._restacked = true;
        let live = false;
        for (const t of this._tanks) {
            if (!t)
                continue;
            t.paused = ov || covered.has(t.mon.index);
            live ||= !t.dead && !t.paused;
        }
        if (live && !this._timer) {
            this._last = now();
            this._arm(this._ms);
        } else if (!live) {
            this._stop();
        }
    }

    _arm(ms) {
        this._ms = ms;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT_IDLE, ms, () => this._tick());
    }

    _stop() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
    }

    _fill() {
        const r = this._raw, [x, y, mods] = global.get_pointer(), d = new Date();
        if (x !== r.px || y !== r.py || this._restacked)  // a stage pick is most of the host's tick
            r.bare = this._bare(x, y);
        this._restacked = false;
        r.px = x;
        r.py = y;
        r.down = !!(mods & Clutter.ModifierType.BUTTON1_MASK);
        r.idleMs = this._idle.get_idletime();
        r.hour = d.getHours() + d.getMinutes() / 60;
        if (this._grab) {  // one rect per tick while a window is dragged
            const g = this._grab.get_frame_rect(), o = r.rects.find(q => q.id === r.grabbing);
            if (o)
                Object.assign(o, {x: g.x, y: g.y, w: g.width, h: g.height});
        }
    }

    _tick() {
        const t0 = now(), dt = Math.min(t0 - this._last, 0.1), raw = this._raw, limit = 2 * this._ms;
        this._last = t0;
        try {
            this._fill();
        } catch (e) {  // e.g. the dragged window died mid-grab; drop it and keep ticking
            this._grab = this._raw.grabbing = null;
            logError(e, 'interactive-wallpaper: world fill');
        }
        let live = false;
        for (const t of this._tanks) {
            if (!t || t.dead || t.paused)
                continue;
            raw.mx = t.mon.x;
            raw.my = t.mon.y;
            raw.mw = t.mon.width;
            raw.mh = t.mon.height;
            const s = now();
            try {
                update(t.world, raw, dt);
                t.scene.tick(dt, t0 - this._t0);
                t.slow = (now() - s) * 1000 > limit ? t.slow + 1 : Math.max(0, t.slow - 1);
                if (t.slow > SLOW_TICKS)
                    throw new Error(`ticks keep taking over ${limit} ms`);
                live = true;
            } catch (e) {
                logError(e, `interactive-wallpaper: ${this._scene.id} stopped`);
                t.root.destroy();
            }
        }
        const st = this.stats;
        st.tickMs = 0.95 * st.tickMs + 0.05 * (now() - t0) * 1000;
        st.ticks++;
        if (!live || this._blank) {  // blanked: _update() re-arms on the first input
            this._timer = 0;
            return GLib.SOURCE_REMOVE;
        }
        const ms = fpsMs(raw.idleMs / 1000);
        if (ms === this._ms)
            return GLib.SOURCE_CONTINUE;
        this._arm(ms);  // fps policy changed: a new source replaces this one
        return GLib.SOURCE_REMOVE;
    }
}
