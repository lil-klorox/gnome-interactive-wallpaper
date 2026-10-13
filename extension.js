import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {SCENES} from './scenes/index.js';
import {makeWorld, update, covers, changed} from './engine/world.js';
import {makeCtx, loadManifest} from './engine/ctx.js';
import {bytesOf, scaleFor, maxHeight} from './engine/render.js';
import {resolve, lightsAt, posterPlan} from './engine/settings.js';
import {bgManagers, backgroundGroup, startingUp} from './engine/shell.js';

const FRAME = 0.025;     // every 2nd frame at 60 Hz with jitter slack (0.030 dropped ~4 % of ticks)
const LIMIT_MS = 66;     // slow tick
const SLOW_TICKS = 90;   // slow ticks in a row (~3 s) before a rest
const REST_S = 60;
const MAX_CRASHES = 3;   // per scene load
const REBUILD_MS = 250;  // quiet before a settings rebuild (a held spin button)
const SLEEP_S = 0.2;     // tick interval of a sleeping scene
const READY_S = 3;       // fade in even if art is still decoding
const ICON = 'preferences-desktop-wallpaper-symbolic';
const BG = [['uri', 'picture-uri'], ['dark', 'picture-uri-dark'], ['options', 'picture-options'], ['color', 'primary-color']];
const now = () => GLib.get_monotonic_time() / 1e6;
const MOVES = [Meta.GrabOp.MOVING, Meta.GrabOp.MOVING_UNCONSTRAINED, Meta.GrabOp.KEYBOARD_MOVING];
const count = a => a.get_children().reduce((n, c) => n + 1 + count(c), 0);

// Not shown while locked: no session-modes in metadata, so the shell disables us on lock. The poster
// wallpaper (a still of the scene set as GNOME's own wallpaper) covers the lock screen and overview.
export default class InteractiveWallpaper extends Extension {
    // The shell never calls disable() after a throwing enable(), so undo the half-built state here.
    enable() {
        try {
            this._enable();
        } catch (e) {
            this.disable();
            throw e;
        }
    }

    _enable() {
        const group = backgroundGroup();
        if (!group) {
            logError(new Error('no background group; GNOME Shell changed?'), 'interactive-wallpaper');
            return;
        }
        this._tanks = [];
        this._rebuildId = 0;
        this._nextMin = 0;
        this._sigs = [];
        this._gen = 0;
        this._t0 = this._last = now();
        this._scene = null;
        this._grab = null;
        this._restacked = true;
        this._cache = new Map();
        this._cancel = new Gio.Cancellable();
        this.stats = {bytes: 0, k: 1, actors: 0, tickMs: 0, ticks: 0};
        this._raw = {mx: 0, my: 0, mw: 0, mh: 0, px: 0, py: 0, bare: false, down: false, rects: [],
            grabbing: null, idleMs: 0, hour: 0, dark: false, notes: 0, lights: {on: true, warm: false}, area: null, event: true};
        this._prev = {};  // last values changed() compared against
        this._poke = false;  // a settings change wakes sleeping scenes
        this._posterOn = true;  // lights.on the poster on screen was picked for
        this._settings = this.getSettings();
        this._bg = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
        this._bg.delay();  // _wallpaper applies all keys as one change
        this._iface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._idle = global.backend.get_core_idle_monitor();
        this._clock = new Clutter.Timeline({actor: group, duration: 1000, repeat_count: -1});
        const dark = () => (this._raw.dark = this._iface.get_string('color-scheme') === 'prefer-dark');
        dark();
        const lm = Main.layoutManager, refresh = () => this._update();
        this._on(this._clock, 'new-frame', () => now() - this._last >= FRAME && this._tick());
        this._on(this._settings, 'changed::scene', () => this._load());
        this._on(this._settings, 'changed::live', () => this._live());
        this._on(this._settings, 'changed::frozen', refresh);
        this._on(this._settings, 'changed::scene-settings', () => this._sceneSettings());
        this._on(this._iface, 'changed::color-scheme', dark);
        // ponytail: any of these re-checks every monitor and window; cheap, so no per-window tracking.
        this._on(lm, 'monitors-changed', () => this._rebuild());
        this._on(lm, 'startup-complete', () => this._live());  // off still clears a stranded poster
        this._on(global.display, 'restacked', refresh);
        this._on(global.display, 'in-fullscreen-changed', refresh);
        this._on(global.display, 'window-entered-monitor', refresh);
        this._on(global.display, 'workareas-changed', refresh);
        this._on(global.display, 'grab-op-begin', (_d, w, op) => {
            if (!MOVES.includes(op))  // resizes are tracked by size-changed
                return;
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
        // Mutter 16 can't report monitor power-save state; the shield comes up before blanking.
        if (Main.screenShield)
            this._on(Main.screenShield, 'active-changed', refresh);
        const hook = src => src.connectObject('notification-added', () => this._raw.notes++, this);
        Main.messageTray.getSources().forEach(hook);
        this._on(Main.messageTray, 'source-added', (_t, src) => hook(src));
        this._tile();
        if (!startingUp())
            this._live();  // off while we were disabled still clears a leftover poster
    }

    disable() {
        if (!this._clock)  // enable() bailed out
            return;
        this._cancel.cancel();
        for (const [obj, id] of this._sigs)
            obj.disconnect(id);
        Main.messageTray.getSources().forEach(s => s.disconnectObject(this));
        this._clock.stop();
        this._clear();
        try {
            if (!Main.sessionMode.isLocked)  // locking disables us too: keep the poster for the lock screen
                this._wallpaper(null);
        } catch (e) {  // still tear down the tile below
            logError(e, 'interactive-wallpaper: wallpaper restore failed');
        }
        if (this._toggle) {
            Gio.Settings.unbind(this._toggle, 'checked');
            this._toggle.menu.destroy();  // not destroyed with the toggle
            this._toggle.destroy();
        }
        this._indicator?.destroy();
        this._sigs = this._tanks = this._cache = this._cancel = this._scene = this._grab = this._clock = null;
        this._settings = this._bg = this._iface = this._idle = this._raw = this.stats = null;
        this._toggle = this._indicator = null;
    }

    _on(obj, sig, fn) {
        this._sigs.push([obj, obj.connect(sig, fn)]);
    }

    _sceneId() {
        const want = this._settings.get_string('scene');
        return Object.hasOwn(SCENES, want) ? want : Object.keys(SCENES)[0];
    }

    _tile() {
        const ids = Object.keys(SCENES);
        const tog = this._toggle = new QuickSettings.QuickMenuToggle({title: 'Wallpaper', icon_name: ICON, toggle_mode: true});
        this._settings.bind('live', tog, 'checked', Gio.SettingsBindFlags.DEFAULT);
        tog.menu.setHeader(ICON, 'Live wallpaper', 'A moving scene instead of your own wallpaper');
        const frz = new PopupMenu.PopupSwitchMenuItem('Freeze motion (keeps a still picture)', false);
        frz.connect('toggled', (_i, on) => this._settings.set_boolean('frozen', on));
        frz.activate = () => frz.toggle();  // skip 'activate', which closes the menu
        const sync = () => {
            frz.setToggleState(this._settings.get_boolean('frozen'));
            frz.setSensitive(this._settings.get_boolean('live'));  // freezing only means something while live
        };
        sync();
        this._on(this._settings, 'changed::frozen', sync);
        this._on(this._settings, 'changed::live', sync);
        tog.menu.addMenuItem(frz);
        tog.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        if (ids.length > 1) {
            const items = ids.map(id => {
                const it = new PopupMenu.PopupMenuItem(SCENES[id].name);
                it.activate = () => this._settings.set_string('scene', id);
                tog.menu.addMenuItem(it);
                return [id, it];
            });
            const mark = () => {
                const cur = this._sceneId();
                tog.subtitle = SCENES[cur].name;
                items.forEach(([id, it]) => it.setOrnament(id === cur ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE));
            };
            mark();
            this._on(this._settings, 'changed::scene', mark);
            tog.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        }
        tog.menu.addAction('Wallpaper settings…', () => {
            Main.panel.closeQuickSettings();
            this.openPreferences();
        });
        this._indicator = new QuickSettings.SystemIndicator();  // no panel icon: it stays hidden
        this._indicator.quickSettingsItems.push(tog);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
    }

    // Set the scene's poster as GNOME's wallpaper (id), or put the user's wallpaper back (null).
    // The night poster (lights off) when the scene's lights are off, for both light and dark style.
    _wallpaper(id) {
        const scenes = this.dir.get_child('scenes'), file = n => scenes.get_child(id).get_child(n);
        const has = n => id && file(n).query_exists(null);
        this._posterOn = this._raw.lights.on;
        const name = !this._posterOn && has('poster-dark.jpg') ? 'poster-dark.jpg' : 'poster.jpg';
        const poster = has(name) ? {uri: file(name).get_uri()} : null;
        const cur = Object.fromEntries(BG.map(([k, key]) => [k, this._bg.get_string(key)]));
        const p = posterPlan(cur, this._settings.get_string('saved-background'), poster, `/${this.uuid}/scenes/`);
        if (p.save)
            this._settings.set_string('saved-background', JSON.stringify(p.save));
        for (const [k, key] of BG) {
            if (p.reset)
                this._bg.reset(key);
            else if (p.apply && this._bg.get_string(key) !== p.apply[k])
                this._bg.set_string(key, p.apply[k]);
        }
        this._bg.apply();
        if (p.clear)
            this._settings.set_string('saved-background', '');
    }

    _live() {
        if (this._settings.get_boolean('live')) {
            this._load();
            return;
        }
        this._gen++;  // drops a load still in flight
        this._clear();
        this._scene = null;
        this._drop();
        this._clock.stop();
        this._wallpaper(null);
    }

    // Cancels in-flight decodes and frees the textures.
    _drop() {
        this._cancel.cancel();
        this._cancel = new Gio.Cancellable();
        this._cache.clear();
    }

    async _load() {
        if (this._scene?.id === this._sceneId())  // re-picked the running scene: keep it and its textures
            return;
        this._clear();
        this._scene = null;
        this._drop();
        const gen = ++this._gen, cancel = this._cancel;
        if (!this._settings.get_boolean('live'))
            return;
        const id = this._sceneId(), decl = SCENES[id].settings ?? [];
        try {
            const mod = await SCENES[id].load();
            if (cancel.is_cancelled() || gen !== this._gen)
                return;
            const dir = this.dir.get_child('scenes').get_child(id);
            const man = loadManifest(dir);
            this._nextMin = 0;
            this._scene = {id, dir, decl, man, k: 0, art: 0, canvas: 0, create: mod.default, crashes: 0, warned: false,
                settings: resolve(decl, this._settings.get_string('scene-settings'), id)};
            this._rebuild();
            this._poster(true);  // after the build, so a poster failure can't strand a scene with no tanks
        } catch (e) {
            logError(e, `interactive-wallpaper: scene ${id} failed to load`);
        }
    }

    _sceneSettings() {
        const sc = this._scene;
        if (!sc)
            return;
        const next = resolve(sc.decl, this._settings.get_string('scene-settings'), sc.id);
        const keys = Object.keys(next).filter(k => next[k] !== sc.settings[k]);
        if (!keys.length)
            return;
        Object.assign(sc.settings, next);
        this._nextMin = 0;
        this._poke = true;
        if (sc.decl.some(d => d.rebuild && keys.includes(d.key))) {
            if (this._rebuildId)
                GLib.Source.remove(this._rebuildId);
            this._rebuildId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, REBUILD_MS, () => {
                this._rebuildId = 0;
                this._rebuild(true);
                return GLib.SOURCE_REMOVE;
            });
            return;
        }
        for (const t of this._tanks) {
            try {
                t?.onSettings?.(keys);
            } catch (e) {
                logError(e, `interactive-wallpaper: ${sc.id} settings`);
            }
        }
    }

    _clear() {
        if (this._rebuildId)
            GLib.Source.remove(this._rebuildId);
        this._rebuildId = 0;
        for (const t of this._tanks)
            t?.root?.destroy();
        this._tanks = [];
    }

    // keep: show at once, no fade from the poster (a settings rebuild).
    _rebuild(keep = false) {
        this._clear();
        const sc = this._scene, mons = Main.layoutManager.monitors;
        if (!sc || !mons.length)  // lid closed, no screen: keep k and the textures for when one returns
            return;
        if (!bgManagers().length && !sc.warned) {
            sc.warned = true;
            logError(new Error('no background managers; GNOME Shell changed?'), 'interactive-wallpaper');
        }
        // X11 geometry is already physical px; the ?. is for shells built without X11.
        const x11 = Meta.is_wayland_compositor?.() === false;
        const k = scaleFor(maxHeight(mons, x11), sc.man.ref, bytesOf(sc.man.images, 1));
        keep &&= k === sc.k;
        if (k !== sc.k) {  // textures are decoded at k
            sc.k = this.stats.k = k;
            sc.art = bytesOf(sc.man.images, k);
            this._drop();
            console.log(`interactive-wallpaper: ${sc.id} textures ${(sc.art / 1e6).toFixed(1)} MB at k=${k.toFixed(3)}`);
        }
        bgManagers().forEach((mgr, i) => mons[i] && this._build(mgr, mons[i], i, keep));  // lengths can differ mid-hotplug
        this._update();
    }

    _build(mgr, mon, i, keep = false) {
        const sc = this._scene;
        if (sc.crashes >= MAX_CRASHES)
            return;
        // Non-reactive (the pointer is polled), so desktop clicks/menus are untouched.
        const root = new Clutter.Actor({width: mon.width, height: mon.height, opacity: keep ? 255 : 0});
        const t = {root, mon, world: makeWorld(), scene: null, slow: 0, rest: 0, paused: false, dead: false, drawn: false,
            pending: 0, born: now(), last: now(), wake: 0, onSettings: null,
            area: {x: mon.x, y: mon.y, w: mon.width, h: mon.height}};  // work area, global; the real one comes in _update
        t.world.ready = keep;
        this._tanks[i] = t;
        root.connect('destroy', () => {
            t.dead = true;
            t.root = t.onSettings = null;
            try {
                t.scene?.destroy?.();
            } catch (e) {
                logError(e, `interactive-wallpaper: ${sc.id} teardown`);
            }
        });
        // Wallpaper changed: the shell puts a new bg actor under the old one and fades the old one out.
        // The live scene moves into the new one and a clone of it stays in the old one, so the fade
        // shows the scene over itself instead of the old poster.
        mgr.connectObject('changed', () => {
            const old = root.get_parent();
            old?.remove_child(root);
            mgr.backgroundActor.add_child(root);
            if (t.world.ready) {  // a clone ignores the root's opacity, so never clone a half-loaded scene
                root.opacity = 255;  // remove_child stopped any running fade-in
                old?.add_child(new Clutter.Clone({source: root}));
            }
        }, root);  // disconnected when root is destroyed
        mgr.backgroundActor.add_child(root);
        try {
            const lm = Main.layoutManager;
            const monitor = Object.freeze({index: mon.index, count: lm.monitors.length, primary: mon.index === lm.primaryIndex});
            t.scene = sc.create(makeCtx(sc, this._cache, this._cancel, t, mon.width, mon.height, monitor));
            this.stats.actors = count(root);
            if (this.stats.actors > 1000)
                console.warn(`interactive-wallpaper: ${sc.id} built ${this.stats.actors} actors`);
        } catch (e) {
            this._crash(e, 'build');
            root.destroy();  // don't leave a half-built scene painted
        }
        this.stats.bytes = sc.art + sc.canvas;
    }

    _crash(e, what) {
        const sc = this._scene;
        logError(e, `interactive-wallpaper: ${sc.id} ${what}`);
        if (sc.crashes++ === 0) {
            Main.notify('Interactive Wallpaper', `The ${SCENES[sc.id].name} scene ran into a problem. ` +
                'If it keeps happening it stops; turning the live wallpaper off and on tries again.');
        }
    }

    // Desktop topmost under the cursor. Polled: desktop-icons/blur extensions eat motion events.
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

    // Refresh window rects; pause what nobody can see (all of it while `frozen`, once drawn).
    _update() {
        const rects = [], lm = Main.layoutManager;
        const unseen = Main.overview.visible || !!Main.screenShield?.active, frozen = this._settings.get_boolean('frozen');
        for (const w of global.workspace_manager.get_active_workspace().list_windows()) {
            if (!w.showing_on_its_workspace() || w.get_window_type() === Meta.WindowType.DESKTOP)
                continue;
            const r = w.get_frame_rect();
            rects.push({x: r.x, y: r.y, w: r.width, h: r.height, id: w.get_stable_sequence()});
        }
        this._raw.rects = rects;
        this._restacked = true;
        let live = false;
        for (const t of this._tanks) {
            if (!t || t.dead)
                continue;
            const a = unseen ? null : lm.getWorkAreaForMonitor(t.mon.index);
            if (a)  // null mid-hotplug, before monitors-changed rebuilds us
                t.area = {x: a.x, y: a.y, w: a.width, h: a.height};
            t.paused = (frozen && t.drawn) || !a || covers(rects, t.area);  // the resume tick gets world.gap
            live ||= !t.paused;
        }
        if (live && !this._clock.is_playing()) {
            this._last = now();
            this._clock.start();
        } else if (!live) {
            this._clock.stop();
        }
        if (this._scene)  // last: a poster failure must not skip the pause/clock logic
            this._poster();
    }

    _fill() {
        const r = this._raw, [x, y, mods] = global.get_pointer();
        const restacked = this._restacked;
        if (x !== r.px || y !== r.py || restacked)  // a stage pick is most of the host's tick
            r.bare = this._bare(x, y);
        this._restacked = false;
        r.px = x;
        r.py = y;
        r.down = !!(mods & Clutter.ModifierType.BUTTON1_MASK);
        r.idleMs = this._idle.get_idletime();
        if (this._grab) {
            const g = this._grab.get_frame_rect(), o = r.rects.find(q => q.id === r.grabbing);
            if (o)
                Object.assign(o, {x: g.x, y: g.y, w: g.width, h: g.height});
        }
        // changed() first: it must always copy the new values.
        r.event = changed(r, this._prev) || restacked || !!this._grab || this._poke;
        this._poke = false;
    }

    // ponytail: follows the lights on ticks and window changes only; add a minute timer if a paused desktop lags.
    _poster(force = false) {
        this._hour();
        if (!force && this._raw.lights.on === this._posterOn)
            return;
        try {  // _posterOn is set first, so a dconf failure logs once, not every tick
            this._wallpaper(this._scene.id);
        } catch (e) {
            logError(e, 'interactive-wallpaper: poster update failed');
        }
    }

    // Recomputed once a minute (or after the clock jumps back).
    _hour() {
        const r = this._raw, s = this._scene.settings, ms = Date.now();
        if (ms < this._nextMin && ms >= this._nextMin - 60000)
            return;
        const d = new Date(ms);
        this._nextMin = ms - d.getSeconds() * 1000 - d.getMilliseconds() + 60000;
        r.hour = d.getHours() + d.getMinutes() / 60;
        // Reserved setting keys; undeclared = lights 06:00-21:00.
        lightsAt(d.getHours() * 60 + d.getMinutes(), s.lights ?? 'auto', s.lightsOn ?? 360, s.lightsOff ?? 1260, r.lights);
    }

    _tick() {
        const t0 = now(), raw = this._raw;
        this._last = t0;
        if (!this._scene)
            return;
        try {
            this._fill();
        } catch (e) {  // e.g. the dragged window died mid-grab
            this._grab = this._raw.grabbing = null;
            logError(e, 'interactive-wallpaper: world fill');
        }
        this._poster();
        let live = false;
        for (const t of this._tanks) {
            if (!t || t.dead || t.paused)
                continue;
            if (t.rest) {  // keep the clock running so it resumes on time
                live = true;
                if (t0 - t.rest < REST_S)
                    continue;
                t.rest = 0;
            }
            if (t.wake && t0 < t.wake && !raw.event) {
                live = true;
                continue;
            }
            const gap = t0 - t.last;
            t.world.gap = gap > 1 ? gap : 0;
            const dt = Math.min(gap, t.wake ? 0.3 : 0.1);
            t.last = t0;
            raw.area = t.area;
            raw.mx = t.mon.x;
            raw.my = t.mon.y;
            raw.mw = t.mon.width;
            raw.mh = t.mon.height;
            const s = now();
            try {
                update(t.world, raw, dt);
                t.wake = t.scene.tick(dt, t0 - this._t0) === false ? t0 + SLEEP_S : 0;
                t.slow = (now() - s) * 1000 > LIMIT_MS ? t.slow + 1 : 0;
                if (t.slow >= SLOW_TICKS) {
                    t.slow = 0;
                    t.rest = t0;
                    throw new Error(`ticks kept taking over ${LIMIT_MS} ms; resting ${REST_S} s`);
                }
                if (!t.world.ready && (t.pending <= 0 || t0 - t.born > READY_S)) {
                    t.world.ready = true;
                    t.root.ease({opacity: 255, duration: 300});
                }
                // Built while frozen: this first ready frame is the one that stays.
                if (t.world.ready && !t.drawn) {
                    t.drawn = true;
                    if (this._settings.get_boolean('frozen'))
                        this._update();
                }
                live = true;
            } catch (e) {
                if (t.rest) {  // slow machine: rest, never a strike
                    console.warn(`interactive-wallpaper: ${this._scene.id} ${e.message}`);
                    live = true;
                } else {
                    this._crash(e, 'stopped');
                    t.root.destroy();
                }
            }
        }
        const st = this.stats;
        st.tickMs = 0.95 * st.tickMs + 0.05 * (now() - t0) * 1000;
        st.ticks++;
        if (!live)
            this._clock.stop();
    }
}
