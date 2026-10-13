import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {SCENES} from './scenes/index.js';
import {resolve, encode, logLines, parseStore} from './engine/settings.js';

const KEY = 'scene-settings';

// The scene's save file (ctx.js store), read-only; missing or bad = {}.
function readStore(id) {
    try {
        const path = GLib.build_filenamev([GLib.get_user_data_dir(), 'interactive-wallpaper', `${id}.json`]);
        return parseStore(Gio.File.new_for_path(path).load_contents(null)[1]);
    } catch {
        return {};
    }
}

// '2026-10-11' -> 'Sunday 11 October', localized; the raw day if invalid.
function dayName(day) {
    const [y, m, d] = day.split('-').map(Number);
    return GLib.DateTime.new_local(y, m, d, 12, 0, 0)?.format('%A %-d %B') ?? day;
}

function row(d, v, edit, store) {
    switch (d.type) {
    case 'log': {
        const r = new Adw.ExpanderRow({title: d.label, expanded: true});
        const lines = logLines(d, store());
        for (const l of lines)
            r.add_row(new Adw.ActionRow({title: l.text, subtitle: dayName(l.day)}));
        if (!lines.length)
            r.add_row(new Adw.ActionRow({title: d.empty ?? 'Nothing yet'}));
        return r;
    }
    case 'bool': {
        const r = new Adw.SwitchRow({title: d.label, active: v});
        r.connect('notify::active', () => edit(r.active));
        return r;
    }
    case 'int':
    case 'double': {
        const r = Adw.SpinRow.new_with_range(d.min ?? -1e6, d.max ?? 1e6, d.step ?? (d.type === 'int' ? 1 : 0.1));
        r.set({title: d.label, value: v});
        r.connect('notify::value', () => edit(d.type === 'int' ? Math.round(r.value) : r.value));
        return r;
    }
    case 'choice': {
        const ids = d.choices.map(c => c[0]);
        const r = new Adw.ComboRow({title: d.label, model: Gtk.StringList.new(d.choices.map(c => c[1]))});
        r.selected = Math.max(0, ids.indexOf(v));
        r.connect('notify::selected', () => edit(ids[r.selected]));
        return r;
    }
    case 'time': {
        const r = new Adw.ActionRow({title: d.label});
        const spin = (max, val) => {
            const s = Gtk.SpinButton.new_with_range(0, max, 1);
            s.set({value: val, wrap: true, numeric: true, width_chars: 2, valign: Gtk.Align.CENTER});
            s.connect('output', () => {
                s.text = String(s.value).padStart(2, '0');
                return true;
            });
            r.add_suffix(s);
            return s;
        };
        const h = spin(23, Math.floor(v / 60)), m = spin(59, v % 60);
        const set = () => edit(h.value * 60 + m.value);
        h.connect('value-changed', set);
        m.connect('value-changed', set);
        return r;
    }
    case 'action': {  // each press stores count + 1
        const b = new Gtk.Button({label: d.button ?? d.label, valign: Gtk.Align.CENTER});
        const r = new Adw.ActionRow({title: d.label, activatable_widget: b});
        let n = v;
        b.connect('clicked', () => edit(++n));
        r.add_suffix(b);
        return r;
    }
    }
    return new Adw.ActionRow({title: d.label});
}

export default class Prefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings(), ids = Object.keys(SCENES);
        const page = new Adw.PreferencesPage();
        const top = new Adw.PreferencesGroup();
        const live = new Adw.SwitchRow({title: 'Live wallpaper',
            subtitle: 'Show the moving scene instead of your normal wallpaper. Off puts your own wallpaper back.'});
        settings.bind('live', live, 'active', Gio.SettingsBindFlags.DEFAULT);
        const frozen = new Adw.SwitchRow({title: 'Freeze motion',
            subtitle: 'Stop the scene where it is and keep it as a still picture. Uses no CPU until you turn it off.'});
        settings.bind('frozen', frozen, 'active', Gio.SettingsBindFlags.DEFAULT);
        settings.bind('live', frozen, 'sensitive', Gio.SettingsBindFlags.GET);
        const scene = new Adw.ComboRow({title: 'Scene', model: Gtk.StringList.new(ids.map(id => SCENES[id].name))});
        const pick = () => (scene.selected = Math.max(0, ids.indexOf(settings.get_string('scene'))));
        pick();
        top.add(live);
        top.add(frozen);
        top.add(scene);
        page.add(top);

        // The scene's own rows, one box per `group`.
        let groups = [];
        const fill = () => {
            groups.forEach(g => page.remove(g));
            groups = [];
            const id = ids[scene.selected], decl = SCENES[id].settings ?? [];
            // Re-read on every write so another writer's keys are kept.
            const now = () => resolve(decl, settings.get_string(KEY), id), vals = now();
            const add = title => {
                const g = new Adw.PreferencesGroup({title});
                page.add(g);
                groups.push(g);
                return g;
            };
            const byName = new Map();
            let store;
            const getStore = () => (store === undefined ? (store = readStore(id)) : store);
            for (const d of decl) {
                const name = d.group ?? '';
                if (!byName.has(name))
                    byName.set(name, add(name));
                byName.get(name).add(row(d, vals[d.key], val => {
                    const cur = now();
                    cur[d.key] = val;
                    settings.set_string(KEY, encode(decl, settings.get_string(KEY), id, cur));
                }, getStore));
            }
            if (!decl.length)
                return;
            const reset = new Adw.ActionRow({title: 'Reset to defaults', activatable: true});
            reset.connect('activated', () => {  // keeps press counts, so a reset presses no button
                const cur = now();
                const counts = Object.fromEntries(decl.filter(d => d.type === 'action').map(d => [d.key, cur[d.key]]));
                settings.set_string(KEY, encode(decl, settings.get_string(KEY), id, counts));
                fill();
            });
            add('').add(reset);
        };
        fill();
        scene.connect('notify::selected', () => {
            settings.set_string('scene', ids[scene.selected]);
            fill();
        });
        const id = settings.connect('changed::scene', pick);  // Quick Settings can change it too
        window.connect('close-request', () => settings.disconnect(id));
        window.add(page);
        window._settings = settings;  // keep alive with the window
    }
}
