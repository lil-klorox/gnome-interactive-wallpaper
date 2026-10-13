// `make uninstall` runs this after disabling, as a net: enable() never runs again after an uninstall, so a poster left as
// GNOME's wallpaper would point at a deleted file. Puts the saved wallpaper back, only if ours shows.
// Usage: gjs -m tools/restore-wallpaper.js <schemas dir> <uuid>
import Gio from 'gi://Gio';
import System from 'system';
import {posterPlan} from '../settings.js';

const [dir, uuid] = System.programArgs;
const src = Gio.SettingsSchemaSource.new_from_directory(dir, Gio.SettingsSchemaSource.get_default(), false);
const ours = new Gio.Settings({settings_schema: src.lookup('org.gnome.shell.extensions.interactive-wallpaper', false)});
const bg = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
const BG = [['uri', 'picture-uri'], ['dark', 'picture-uri-dark'], ['options', 'picture-options'], ['color', 'primary-color']];
const cur = Object.fromEntries(BG.map(([k, key]) => [k, bg.get_string(key)]));
const p = posterPlan(cur, ours.get_string('saved-background'), null, `/${uuid}/scenes/`);  // same rules as disable()
for (const [k, key] of BG) {
    if (p.reset)
        bg.reset(key);
    else if (p.apply && bg.get_string(key) !== p.apply[k])
        bg.set_string(key, p.apply[k]);
}
ours.reset('saved-background');
Gio.Settings.sync();
if (p.reset || p.apply)
    print('wallpaper put back');
