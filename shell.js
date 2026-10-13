// The only private shell fields we read; no public API exposes them.
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const bgManagers = () => Main.layoutManager._bgManagers ?? [];
export const backgroundGroup = () => Main.layoutManager._backgroundGroup;
export const startingUp = () => Main.layoutManager._startingUp ?? false;
