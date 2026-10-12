// The sand garden's settings (pure data, no gi). Each entry becomes a row in the settings window.
export const SETTINGS = [
    {key: 'teeth', type: 'int', label: 'Rake teeth', group: 'Rake', default: 5, min: 1, max: 7, step: 1},
    {key: 'settle', type: 'int', label: 'Hours until your raking smooths out (0 = never)', group: 'Rake', default: 6, min: 0, max: 48, step: 1},
    {key: 'resetSand', type: 'action', label: 'Smooth all the sand', button: 'Smooth', group: 'Rake', default: 0},
    {key: 'stones', type: 'int', label: 'Stones', group: 'Garden', default: 3, min: 0, max: 5, step: 1, rebuild: true},
    {key: 'season', type: 'choice', label: 'Season', group: 'Garden', default: 'autumn', rebuild: true,
        choices: [['autumn', 'Autumn (red maple)'], ['summer', 'Summer (green maple)'], ['spring', 'Spring (cherry blossom)'], ['none', 'No tree']]},
    {key: 'lines', type: 'bool', label: 'Raked lines across the sand', group: 'Garden', default: true, rebuild: true},
    {key: 'lantern', type: 'bool', label: 'Stone lantern', group: 'Garden', default: true, rebuild: true},
    {key: 'border', type: 'choice', label: 'Border', group: 'Garden', default: 'wood', rebuild: true,
        choices: [['none', 'None'], ['wood', 'Wood'], ['bamboo', 'Bamboo']]},
    {key: 'lights', type: 'choice', label: 'Lights', group: 'Lights', default: 'auto',
        choices: [['auto', 'On a schedule'], ['on', 'Always on'], ['off', 'Always off']]},
    {key: 'lightsOn', type: 'time', label: 'Lights on at', group: 'Lights', default: 360},
    {key: 'lightsOff', type: 'time', label: 'Lights off at', group: 'Lights', default: 1260},
];
