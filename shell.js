// The only file that reads private shell fields. No public API exposes the per-monitor
// background actors or whether startup is still running, so these three are read here.
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const bgManagers = () => Main.layoutManager._bgManagers ?? [];
export const backgroundGroup = () => Main.layoutManager._backgroundGroup;
export const startingUp = () => Main.layoutManager._startingUp ?? false;
