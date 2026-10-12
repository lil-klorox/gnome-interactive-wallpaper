// The dot scene's settings (pure data, no gi). Each entry becomes a row in the settings window.
export const SETTINGS = [
    {key: 'color', type: 'choice', label: 'Colour', group: 'Dot', default: 'amber',
        choices: [['amber', 'Amber'], ['mint', 'Mint'], ['rose', 'Rose']]},
    // rebuild: the scene is built again when this changes, because the dot's size is set in create().
    {key: 'size', type: 'int', label: 'Size', group: 'Dot', default: 5, min: 1, max: 10, step: 1, rebuild: true},
    // Reserved keys: declare them and the engine's lights schedule (world.lightsOn) follows them.
    {key: 'lights', type: 'choice', label: 'Lights', group: 'Lights', default: 'auto',
        choices: [['auto', 'On a schedule'], ['on', 'Always on'], ['off', 'Always off']]},
    {key: 'lightsOn', type: 'time', label: 'Lights on at', group: 'Lights', default: 360},
    {key: 'lightsOff', type: 'time', label: 'Lights off at', group: 'Lights', default: 1260},
];
