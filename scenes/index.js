// Scene registry (no gi imports: prefs.js reads it too). First entry is the default.
// settings = the scene's knob list (pure data), shown in the settings window.
import {SETTINGS as fishtank} from './fishtank/settings.js';
import {SETTINGS as garden} from './garden/settings.js';
import {SETTINGS as dot} from './dot/settings.js';

export const SCENES = {
    fishtank: {name: 'Fishtank', load: () => import('./fishtank/scene.js'), settings: fishtank},
    garden: {name: 'Sand garden', load: () => import('./garden/scene.js'), settings: garden},
    dot: {name: 'Dot (demo)', load: () => import('./dot/scene.js'), settings: dot},
};
