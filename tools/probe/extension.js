import GLib from 'gi://GLib'; import Gio from 'gi://Gio'; import Shell from 'gi://Shell'; import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const OUT = GLib.getenv('SHOT_DIR');
export default class P { enable() {
  const shot = n => { const f = Gio.File.new_for_path(`${OUT}/s${n}.png`), st = f.replace(null, false, 0, null);
    new Shell.Screenshot().screenshot(false, st, (o, r) => { o.screenshot_finish(r); st.close(null); }); };
  const dev = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
  let i = 0;
  GLib.timeout_add(0, 500, () => { i++;
    if (i === 4) Main.overview.hide();
    if (i === 8) shot(0);
    if (i >= 10 && i < 20) dev.notify_absolute_motion(GLib.get_monotonic_time(), 700 + i * 5, 450);
    if (i === 20) shot(1);
    if (i === 24) shot(2);
    return i < 26; });
}; disable() {} }
