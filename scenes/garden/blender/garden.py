# Garden render setup: reuses the fishtank helpers (scenes/fishtank/blender/common.py) but writes to
# scenes/garden/assets and swaps the wet blue-green tank rig for a dry, mostly top-down sunlit one.
# Scripts: blender -b --factory-startup -t 6 -P scenes/garden/blender/<script>.py   (SAMPLES env = samples)
import math, os, sys
import bpy
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'fishtank', 'blender'))
import common  # noqa: E402
from common import *  # noqa: E402,F401  helpers read common.ASSETS at call time

common.ASSETS = os.path.join(os.path.dirname(HERE), 'assets')
ASSETS = common.ASSETS
PITCH = 60   # camera pitch from horizontal: mostly top-down, a bit of side
PPU = 100    # px per world unit at the 1440 px reference height


def rig(samples=None):
    """reset + dry daylight: warm sun from the top-left (the runtime groove shading assumes it), neutral
    grey sky fill, a soft overhead area so the shadow side is not dead. No fog, no backdrop."""
    s = reset(samples or int(os.environ.get('SAMPLES', 128)))
    bg = s.world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.42, 0.43, 0.45, 1)
    bg.inputs['Strength'].default_value = 0.5
    sun = bpy.data.objects.new('key', bpy.data.lights.new('key', 'SUN'))
    sun.data.energy, sun.data.color, sun.data.angle = 3.2, (1.0, 0.94, 0.84), math.radians(6)
    sun.rotation_euler = [math.radians(a) for a in (-35, -25, 0)]  # from the screen top-left (+y = up the screen, -x = left)
    s.collection.objects.link(sun)
    fill = bpy.data.objects.new('fill', bpy.data.lights.new('fill', 'AREA'))
    fill.data.energy, fill.data.size, fill.data.color = 120, 10, (0.85, 0.88, 0.95)
    fill.location = (2, -3, 7)
    s.collection.objects.link(fill)
    s.view_settings.exposure = -0.3
    return s


def place(objs, margin=0.15):
    """fit() at the garden pitch and density."""
    return fit(objs, margin=margin, tilt=PITCH, ppu=PPU)


def foot(name, ent, x0, x1, y0, y1):
    """Add foot = [x, y, w, h] px (the prop's ground footprint, z = 0 rect) to a cropped sprite entry."""
    pts = [project((x, y, 0)) for x in (x0, x1) for y in (y0, y1)]
    xs, ys = [p[0] - ent.get('ox', 0) for p in pts], [p[1] - ent.get('oy', 0) for p in pts]
    ent['foot'] = [round(min(xs), 1), round(min(ys), 1), round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1)]
    manifest(name, ent)
    return ent


def still(name, w, h, fn, ss=2):
    """Numpy still: fn(x, y) -> (rgb, alpha), x/y in -1..1 on an ss-times supersampled grid."""
    y, x = np.mgrid[0:h * ss, 0:w * ss].astype(np.float32)
    x, y = (x + 0.5) / (w * ss) * 2 - 1, (y + 0.5) / (h * ss) * 2 - 1
    rgb, a = fn(x, y)
    px = np.zeros((h * ss, w * ss, 4), np.float32)
    px[..., :3], px[..., 3] = np.asarray(rgb, np.float32) * a[..., None], a
    px = px.reshape(h, ss, w, ss, 4).mean((1, 3))
    px[..., :3] /= np.maximum(px[..., 3:], 1e-6)
    save_png(np.clip(px, 0, 1), os.path.join(ASSETS, name + '.png'))
    manifest(name, {'w': w, 'h': h})
