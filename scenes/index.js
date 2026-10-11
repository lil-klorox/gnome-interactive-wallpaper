// Scene registry (no gi imports: prefs.js reads it too). First entry is the default.
export const SCENES = {
    fishtank: {name: 'Fishtank', load: () => import('./fishtank/scene.js')},
    dot: {name: 'Dot (demo)', load: () => import('./dot/scene.js')},
};
