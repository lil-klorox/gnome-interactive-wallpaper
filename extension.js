import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {Scene} from './scene.js';
import {School} from './fish.js';

const FRAME_MS = 33;

// Not shown while locked: no session-modes in metadata, so the shell disables us on lock.
export default class FishtankExtension extends Extension {
    enable() {
        this._tanks = [];
        this._sigs = [];
        this._timer = 0;
        this._t0 = GLib.get_monotonic_time() / 1e6;
        const lm = Main.layoutManager;
        const rebuild = () => this._rebuild();
        const update = () => this._update();
        // ponytail: any of these re-checks every monitor; cheap, so no per-window tracking.
        this._on(lm, 'monitors-changed', rebuild);
        this._on(lm, 'startup-complete', rebuild);
        this._on(global.display, 'restacked', update);
        this._on(global.display, 'in-fullscreen-changed', update);
        this._on(global.display, 'window-entered-monitor', update);
        this._on(global.window_manager, 'size-changed', update);
        this._on(global.window_manager, 'minimize', update);
        this._on(global.window_manager, 'unminimize', update);
        this._on(global.workspace_manager, 'active-workspace-changed', update);
        this._on(Main.overview, 'showing', update);
        this._on(Main.overview, 'hidden', update);
        if (!lm._startingUp)
            this._rebuild();
    }

    disable() {
        for (const [obj, id] of this._sigs)
            obj.disconnect(id);
        this._stop();
        this._clear();
        this._sigs = this._tanks = null;
    }

    _on(obj, sig, fn) {
        this._sigs.push([obj, obj.connect(sig, fn)]);
    }

    _clear() {
        for (const t of this._tanks)
            t.widget?.destroy();
        this._tanks = [];
    }

    _rebuild() {
        this._clear();
        Main.layoutManager._bgManagers.forEach((_, i) => this._build(i));
        this._update();
    }

    _build(i) {
        const mgr = Main.layoutManager._bgManagers[i];
        const mon = Main.layoutManager.monitors[i];
        // Non-reactive: the pointer is polled in _tick, so desktop clicks/menus are untouched.
        const widget = new St.Widget({width: mon.width, height: mon.height});
        const t = {widget, monitor: mon.index, pointer: {x: 0, y: 0, speed: 0}, over: false};
        this._tanks[i] = t;
        // Fires on disable, on rebuild, and when the shell destroys the bg actor under us.
        widget.connect('destroy', () => {
            mgr.disconnect(t.mgrId);
            t.dead = true;
            t.widget = null;
            try {
                t.school?.destroy();
                t.scene?.destroy();
            } catch (e) {
                logError(e, 'fishtank: teardown');
            }
        });
        // Wallpaper changed: shell swaps in a new bg actor, the old one fades out and dies.
        t.mgrId = mgr.connect('changed', () => {
            widget.destroy();
            this._build(i);
            this._update();
        });
        mgr.backgroundActor.add_child(widget);
        try {
            t.scene = new Scene(widget, mon.width, mon.height);
            t.school = new School(t.scene.fishLayers, t.scene.swimBounds);
        } catch (e) {
            logError(e, 'fishtank: build');
            t.dead = true;
        }
    }

    // Polled, not event-driven: motion events never reach the background when a desktop-icons
    // or blur extension sits above it. "Over" = the topmost thing under the cursor is the desktop.
    _pointer(dt) {
        const [x, y] = global.get_pointer();
        const a = Main.overview.visible ? null : global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
        let w = a;
        while (w && !(w instanceof Meta.WindowActor))
            w = w.get_parent();
        const bare = !!a && (a === global.stage || Main.layoutManager._backgroundGroup.contains(a) ||
            w?.meta_window?.get_window_type() === Meta.WindowType.DESKTOP);
        for (const t of this._tanks) {
            const m = Main.layoutManager.monitors[t.monitor], p = t.pointer;
            const lx = x - m.x, ly = y - m.y;
            const over = bare && lx >= 0 && ly >= 0 && lx < m.width && ly < m.height;
            p.speed = over && t.over ? 0.5 * p.speed + 0.5 * Math.hypot(lx - p.x, ly - p.y) / dt : 0;
            p.x = lx;
            p.y = ly;
            t.over = over;
        }
    }

    _update() {
        const covered = new Set();
        if (!Main.overview.visible) {
            for (const w of global.workspace_manager.get_active_workspace().list_windows()) {
                if (!w.showing_on_its_workspace())
                    continue;
                const max = w.is_maximized?.() ?? w.get_maximized() === Meta.MaximizeFlags.BOTH;
                if (max || w.is_fullscreen())
                    covered.add(w.get_monitor());
            }
        }
        let live = false;
        for (const t of this._tanks) {
            t.paused = covered.has(t.monitor);
            live ||= !t.dead && !t.paused;
        }
        if (live && !this._timer) {
            this._last = GLib.get_monotonic_time() / 1e6;
            this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT_IDLE, FRAME_MS, () => this._tick());
        } else if (!live) {
            this._stop();
        }
    }

    _stop() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
    }

    _tick() {
        const now = GLib.get_monotonic_time() / 1e6;
        const dt = Math.min(now - this._last, 0.1);
        this._last = now;
        let live = false;
        this._pointer(Math.max(dt, 0.001));
        for (const t of this._tanks) {
            if (t.dead || t.paused)
                continue;
            try {
                t.scene.tick(dt, now - this._t0);
                t.school.tick(dt, now - this._t0, t.over ? t.pointer : null);
                live = true;
            } catch (e) {
                logError(e, 'fishtank: tank stopped');
                t.dead = true;
            }
        }
        if (!live)
            this._timer = 0;
        return live ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
    }
}
