import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {SCENES} from './scenes/index.js';

export default class Prefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings(), ids = Object.keys(SCENES);
        const row = new Adw.ComboRow({title: 'Scene', model: Gtk.StringList.new(ids.map(id => SCENES[id].name))});
        row.selected = Math.max(0, ids.indexOf(settings.get_string('scene')));
        row.connect('notify::selected', () => settings.set_string('scene', ids[row.selected]));
        const group = new Adw.PreferencesGroup();
        group.add(row);
        const page = new Adw.PreferencesPage();
        page.add(group);
        window.add(page);
        window._settings = settings;  // keep alive with the window
    }
}
