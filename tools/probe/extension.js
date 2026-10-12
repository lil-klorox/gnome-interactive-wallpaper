// Dev-only driver for `dev.sh --headless`: hides the overview, moves a virtual cursor, raises a
// notification, cycles the target extension off/on, freezes it for a moment, takes screenshots and writes $OUT/stats.txt.
// POSTER=1: set every `still` setting value, hide the top bar, take only s0.png at SHOT seconds (default 4), nothing else.
// RACE=1: lifecycle races (disable mid-decode, double scene switch, 3 monitors-changed in one tick,
// lock/unlock), then one `race ok` / `race FAIL ...` line: no JS errors, one root per bg actor,
// same actor count as a fresh build, poster still the wallpaper. Needs secs >= 14.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import System from 'system';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const env = GLib.getenv;

export default class Probe {
    enable() {
        // Disabling the target makes the shell disable+re-enable extensions loaded after it, the probe
        // included; a second run would cycle the target again and skew the rates. Dev-only, so the
        // timer is deliberately left running across that.
        if (this._started)
            return;
        this._started = true;
        const soak = Number(env('SOAK') || 0), out = env('OUT'), uuid = env('TARGET_UUID'), secs = Number(env('SECS') || 40);
        const lines = [], em = Main.extensionManager, start = GLib.get_monotonic_time() / 1e6;
        const rss = () => Number(/VmRSS:\s+(\d+)/.exec(new TextDecoder().decode(GLib.file_get_contents('/proc/self/status')[1]))[1]) / 1024;
        const stats = () => em.lookup(uuid)?.stateObj?.stats;
        const note = s => {
            lines.push(`${(GLib.get_monotonic_time() / 1e6 - start).toFixed(1)}s ${s}`);
            GLib.file_set_contents(`${out}/stats.txt`, `${lines.join('\n')}\n`);
        };
        const snap = label => {
            System.gc();  // RSS otherwise includes garbage GJS hasn't collected yet
            const s = stats();
            note(`${label} rss_mb=${rss().toFixed(1)}` + (s ? ` bytes=${s.bytes} k=${s.k.toFixed(3)} actors=${s.actors} tickMs=${s.tickMs.toFixed(3)} ticks=${s.ticks} notes=${em.lookup(uuid).stateObj._raw.notes}` : ' (disabled)'));
        };
        let t0 = 0;
        const rate = (label, from) => {
            const s = stats();
            if (from === undefined)
                return [s?.ticks ?? 0, GLib.get_monotonic_time()];
            note(`${label} ticks/s=${(((s?.ticks ?? 0) - from[0]) / ((GLib.get_monotonic_time() - from[1]) / 1e6)).toFixed(1)}`);
        };
        const shot = n => {
            const f = Gio.File.new_for_path(`${out}/s${n}.png`), st = f.replace(null, false, 0, null);
            new Shell.Screenshot().screenshot(false, st, (o, r) => { o.screenshot_finish(r); st.close(null); });
        };
        const dev = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        const move = (x, y) => dev.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
        note(`probe-start rss_mb=${rss().toFixed(1)}`);
        const poster = !!env('POSTER'), shotAt = Math.round(2 * Number(env('SHOT') || 4));
        let i = 0, act, idle, ov, fz;
        if (env('RACE')) {
            this._race(note, stats, em, uuid, out);
            return;
        }
        // 0.5 s steps
        GLib.timeout_add(0, 500, () => {
            i++;
            if (poster && i === 2) this._still(em.lookup(uuid), note);
            if (i === 4) Main.overview.hide();
            if (poster && i === shotAt - 1) Main.layoutManager.panelBox.hide();
            if (i === shotAt) shot(0);
            if (poster) return i < 2 * secs;
            if (i === 8) snap('mounted');
            if (i >= 10 && i < 20) move(500 + i * 20, 300 + i * 5);
            if (i === 12) act = rate();
            if (i === 20) { rate('active', act); shot(1); Main.notify('probe', 'hello'); }
            if (i === 21) shot(2);
            if (i === 22) { Main.overview.show(); ov = rate(); }  // should be 0: paused in the overview
            if (i === 23) { rate('overview', ov); Main.overview.hide(); }
            if (i === 24) { snap('before-cycle'); em.disableExtension(uuid); }
            if (i === 28) { snap('disabled'); em.enableExtension(uuid); }
            if (i === 34) { snap('re-enabled'); em.disableExtension(uuid); }
            if (i === 36) em.enableExtension(uuid);
            if (i === 42) { snap('re-enabled-2'); em.lookup(uuid).stateObj.getSettings().set_boolean('frozen', true); fz = rate(); }
            if (i === 43) { rate('frozen', fz); em.disableExtension(uuid); }  // should be 0
            if (i === 44) em.enableExtension(uuid);  // built while frozen: must still draw once and fade in
            if (i === 50) fz = rate();  // past READY_S
            if (i === 52) {
                const x = em.lookup(uuid).stateObj;
                rate(`frozen-build ready=${x._tanks.every(t => !t || t.world.ready && t.root?.opacity === 255)}`, fz);  // should be true, 0
                x.getSettings().set_boolean('frozen', false);
            }
            const k = i - 53;  // SOAK=n: n more off/on cycles, 3 s each, RSS after a GC
            if (k >= 0 && k < soak * 6) {
                if (k % 6 === 0) em.disableExtension(uuid);
                if (k % 6 === 1) em.enableExtension(uuid);
                if (k % 6 === 5) { System.gc(); snap(`soak-${k / 6 + 1 | 0}`); }
            }
            if (secs >= 80 && i === 2 * (secs - 14)) idle = rate();
            if (secs >= 80 && i === 2 * (secs - 4)) rate('idle', idle);
            return i < 2 * secs;
        });
    }

    // Poster runs: the scene's settings with a `still` value use it (fish counts 0, critters off).
    async _still(ext, note) {
        try {
            const {SCENES} = await import(ext.dir.get_child('scenes').get_child('index.js').get_uri());
            const set = ext.stateObj.getSettings(), id = set.get_string('scene');
            const vals = Object.fromEntries((SCENES[id]?.settings ?? []).filter(d => 'still' in d).map(d => [d.key, d.still]));
            set.set_string('scene-settings', JSON.stringify({[id]: vals}));
            note(`still ${Object.keys(vals).join() || 'none'}`);
        } catch (e) {
            note(`still FAIL ${e.message}`);
        }
    }

    // 0.1 s steps; the shell is up and the scene mounted by step 40.
    _race(note, stats, em, uuid, out) {
        const ext = () => em.lookup(uuid);
        let i = 0, base = 0, first = '';
        GLib.timeout_add(0, 100, () => {
            i++;
            if (i === 30) Main.overview.hide();
            if (i === 44) base = stats()?.actors ?? -1;
            if (i === 45) em.disableExtension(uuid);
            if (i === 46) em.enableExtension(uuid);
            if (i === 48) em.disableExtension(uuid);  // decodes still in flight
            if (i === 50) em.enableExtension(uuid);
            if (i === 52) {
                const set = ext().stateObj.getSettings();
                first = set.get_string('scene');
                set.set_string('scene', first === 'dot' ? 'fishtank' : 'dot');
            }
            if (i === 53) ext().stateObj.getSettings().set_string('scene', first);
            if (i === 60) [0, 1, 2].forEach(() => Main.layoutManager.emit('monitors-changed'));
            if (i === 70) Main.sessionMode.pushMode('unlock-dialog');
            if (i === 80) Main.sessionMode.popMode('unlock-dialog');
            if (i >= 90 && i <= 92)  // a held spin button: rebuild keys coalesce into one rebuild (dot's size)
                ext().stateObj.getSettings().set_string('scene-settings', JSON.stringify({dot: {size: i - 84}}));
            if (i === 100) ext().stateObj.getSettings().set_string('scene-settings', '{}');
            if (i === 130) {
                const fail = [];
                const log = new TextDecoder().decode(GLib.file_get_contents(`${out}/log`)[1]);
                // Ours only: a JS ERROR whose stack names our folder (the shell's own calendar etc. don't count),
                // or a logError line (printed as CRITICAL, not JS ERROR).
                const ls = log.split('\n');
                const errs = ls.filter((l, j) => (l.includes('JS ERROR') && ls.slice(j, j + 9).some(q => q.includes(uuid))) ||
                    /CRITICAL.*interactive-wallpaper/.test(l)).length;
                if (errs) fail.push(`${errs} error lines`);
                const kids = (Main.layoutManager._bgManagers ?? []).map(m => m.backgroundActor.get_n_children());
                if (!kids.length || kids.some(n => n !== 1)) fail.push(`bg children ${kids}`);
                if (stats()?.actors !== base) fail.push(`actors ${stats()?.actors} vs fresh ${base}`);
                const dir = ext().dir.get_child('scenes').get_child(first), poster = dir.get_child('poster.jpg');
                const uri = new Gio.Settings({schema_id: 'org.gnome.desktop.background'}).get_string('picture-uri');
                const ours = [poster, dir.get_child('poster-dark.jpg')].map(f => f.get_uri());  // day or night poster
                if (poster.query_exists(null) ? !ours.includes(uri) : uri.includes(`/${uuid}/scenes/`))
                    fail.push(`picture-uri ${uri}`);
                note(fail.length ? `race FAIL ${fail.join('; ')}` : `race ok (scene ${first}, actors ${base}, ${uri.split('/').pop()})`);
            }
            return i < 130;
        });
    }

    disable() {}
}
