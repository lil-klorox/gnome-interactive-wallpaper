// Dev-only driver for `dev.sh --headless`: hides the overview, moves a virtual cursor, raises a
// notification, cycles the target extension off/on, takes screenshots and writes $OUT/stats.txt.
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
        let i = 0, act, idle;
        // 0.5 s steps
        GLib.timeout_add(0, 500, () => {
            i++;
            if (i === 4) Main.overview.hide();
            if (i === 8) { shot(0); snap('mounted'); }
            if (i >= 10 && i < 20) move(500 + i * 20, 300 + i * 5);
            if (i === 12) act = rate();
            if (i === 20) { rate('active', act); shot(1); Main.notify('probe', 'hello'); }
            if (i === 21) shot(2);
            if (i === 24) { snap('before-cycle'); em.disableExtension(uuid); }
            if (i === 28) { snap('disabled'); em.enableExtension(uuid); }
            if (i === 34) { snap('re-enabled'); em.disableExtension(uuid); }
            if (i === 36) em.enableExtension(uuid);
            if (i === 42) snap('re-enabled-2');
            const k = i - 44;  // SOAK=n: n more off/on cycles, 3 s each, RSS after a GC
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

    disable() {}
}
