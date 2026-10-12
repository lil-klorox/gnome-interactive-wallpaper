// Fishtank settings (pure data: prefs.js imports this, so no gi). Defaults = the stock tank.
// Fish count keys are the species names, so School reads ctx.settings[species] directly.
// rebuild: true = changing it rebuilds the tank (counts, critters, decor); the rest apply live.
const fish = (key, label, def, max = 3) => ({key, type: 'int', label, group: 'Fish', default: def, min: 0, max, step: 1, rebuild: true});
const morph = (key, label, id, name) => ({key, type: 'choice', label, group: 'Fish', default: 'normal',
    choices: [['normal', 'Normal'], [id, name]], rebuild: true});
const critter = (key, label, def = true) => ({key, type: 'bool', label, group: 'Critters', default: def, rebuild: true});
const decor = (key, label, choices) => ({key, type: 'choice', label, group: 'Decorations', default: choices[0][0], choices, rebuild: true});

export const SETTINGS = [
    {key: 'lights', type: 'choice', label: 'Tank lights', group: 'Lights', default: 'auto',
        choices: [['auto', 'On a schedule'], ['on', 'Always on'], ['off', 'Always off']]},
    {key: 'lightsOn', type: 'time', label: 'Lights on at', group: 'Lights', default: 360},
    {key: 'lightsOff', type: 'time', label: 'Lights off at', group: 'Lights', default: 1260},

    fish('clown', 'Clownfish', 2), fish('tetra', 'Neon tetras', 6, 8), fish('angel', 'Angelfish', 2),
    fish('goldfish', 'Goldfish', 2), fish('tang', 'Blue tang', 1), fish('puffer', 'Pufferfish', 1),
    fish('cory', 'Cory catfish', 3, 4), fish('betta', 'Betta', 1), fish('lionfish', 'Lionfish', 1),
    fish('discus', 'Discus', 2), fish('guppy', 'Guppies', 5, 8), fish('pleco', 'Pleco', 1),
    fish('mandarin', 'Mandarin dragonet', 1),
    morph('coryMorph', 'Cory colour', 'albino', 'Albino'),
    morph('bettaMorph', 'Betta colour', 'koi', 'Koi'),
    morph('angelMorph', 'Angelfish colour', 'gold', 'Gold'),

    critter('jelly', 'Jellyfish'), critter('gardenEels', 'Garden eels'), critter('moray', 'Moray eel'),
    critter('seahorse', 'Seahorses'), critter('shrimp', 'Cherry shrimp'), critter('hermit', 'Hermit crab'),
    critter('visitors', 'Rare visitors (turtle, shark, baby fish)', false),

    {key: 'activity', type: 'choice', label: 'How busy the fish are', group: 'Behaviour', default: 'normal',
        choices: [['calm', 'Calm'], ['normal', 'Normal'], ['lively', 'Lively']]},
    {key: 'curiosity', type: 'bool', label: 'Fish come to look at the cursor', group: 'Behaviour', default: true},
    {key: 'flashlight', type: 'bool', label: 'Cursor is a flashlight when the lights are off', group: 'Behaviour', default: true},
    {key: 'events', type: 'bool', label: 'Now and then something special happens (baby fish, a shrimp moult...)', group: 'Behaviour', default: true},
    {key: 'tankLog', type: 'log', label: 'Special moments this week', group: 'Behaviour', path: ['tank', 'log'], empty: 'Nothing yet',
        kinds: {fry: 'Baby fish hatched', moult: 'The shrimp shed its shell', eggs: 'The snail laid eggs on the glass', yawn: 'The moray eel yawned'}},
    {key: 'food', type: 'int', label: 'Food pieces per click', group: 'Behaviour', default: 7, min: 1, max: 12, step: 1},

    {key: 'bubbler', type: 'bool', label: 'Air stone bubbles', group: 'Decorations', default: true, rebuild: true},
    {key: 'decor', type: 'choice', label: 'Decorations', group: 'Decorations', default: 'full', rebuild: true,
        choices: [['full', 'Full'], ['minimal', 'Just plants and rocks']]},
    decor('castle', 'Castle', [['castle', 'Castle'], ['temple', 'Sunken temple']]),
    decor('ship', 'Shipwreck', [['ship', 'Pirate ship'], ['plane', 'Sunken plane']]),
    decor('diver', 'Diver', [['diver', 'Diver'], ['skeleton', 'Treasure skeleton']]),
    decor('substrate', 'Floor', [['sand', 'Sand'], ['gravel', 'Dark gravel']]),
];
