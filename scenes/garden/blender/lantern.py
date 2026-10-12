# Stone lantern (toro): base, pole, platform, fire box with windows, upturned roof, jewel finial, all
# hexagonal, chipped and lichened. Points: base, foot [x, y, w, h], light (fire box centre, where the
# night glow goes). Also `glow`: a 256 px warm radial still for that light.
# Usage: blender -b --factory-startup -t 6 -P scenes/garden/blender/lantern.py
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *
from stones import granite


def frustum(name, rings, mat):
    """Closed hex solid through rings [(r, z, corner_lift)], bottom to top."""
    verts = []
    for r, z, lift in rings:
        verts += [(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3), z + lift)  # a flat face toward -y
                  for k in range(6)]
    n = len(rings)
    faces = [tuple(range(5, -1, -1)), tuple(range((n - 1) * 6, n * 6))]
    faces += [(i * 6 + k, i * 6 + (k + 1) % 6, (i + 1) * 6 + (k + 1) % 6, (i + 1) * 6 + k) for i in range(n - 1) for k in range(6)]
    o = mesh(name, verts, faces, mat, smooth=False)
    mod(o, 'BEVEL', width=0.025, segments=2)
    mod(o, 'SUBSURF', levels=2, render_levels=2, subdivision_type='SIMPLE')
    t = bpy.data.textures.new(name, 'CLOUDS')
    t.noise_scale, t.noise_depth = 0.25, 3
    mod(o, 'DISPLACE', texture=t, strength=0.025, texture_coords='GLOBAL')  # weathered, slightly lumpy
    return o


def chip(o, at, r):
    """Knock a chip out of o: boolean away a small displaced sphere at `at`."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r, location=at)
    c = bpy.context.object
    mod(o, 'BOOLEAN', object=c, operation='DIFFERENCE')
    c.hide_render = c.hide_viewport = True


def lantern():
    rig()
    seed(4)
    st = granite('toro', 0.5, (0.01, 0.005, -0.005))
    dark = new_mat('inside')
    N(dark, 'OutputMaterial', Surface=N(dark, 'BsdfDiffuse', Color=(0.025, 0.02, 0.015, 1)))
    z = 0.0
    parts = [frustum('kiso', [(0.62, -0.05, 0), (0.6, 0.18, 0), (0.42, 0.28, 0)], st)]
    z = 0.28
    parts.append(frustum('sao', [(0.2, z - 0.02, 0), (0.18, z + 0.55, 0), (0.22, z + 0.6, 0), (0.22, z + 0.66, 0),
                                 (0.17, z + 0.71, 0), (0.16, z + 1.25, 0)], st))
    z += 1.25
    parts.append(frustum('chudai', [(0.24, z - 0.02, 0), (0.6, z + 0.2, 0), (0.62, z + 0.3, 0)], st))
    z += 0.3
    box = frustum('hibukuro', [(0.44, z - 0.01, 0), (0.44, z + 0.85, 0)], st)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.4, z + 0.3))  # front window, toward the viewer
    win = bpy.context.object
    win.scale = (0.3, 0.4, 0.36)
    mod(box, 'BOOLEAN', object=win, operation='DIFFERENCE')
    win.hide_render = True
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.4 * math.cos(-0.5236), 0.4 * math.sin(-0.5236), z + 0.3),
                                    rotation=(0, 0, math.radians(60)))  # a smaller round-ish side window, front-right face
    side = bpy.context.object
    side.scale = (0.18, 0.4, 0.2)
    mod(box, 'BOOLEAN', object=side, operation='DIFFERENCE')
    side.hide_render = True
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.36, depth=0.8, location=(0, 0, z + 0.42))
    inner = bpy.context.object  # dark inside behind the window
    inner.data.materials.append(dark)
    light = (0, -0.3, z + 0.3)
    parts.append(box)
    z += 0.85
    # roof: wide hexagonal kasa, eaves turned up at the six corners (warabite), stepped top
    parts.append(frustum('kasa', [(0.7, z - 0.02, 0.06), (0.8, z + 0.06, 0.1), (0.78, z + 0.12, 0.1),
                                  (0.5, z + 0.3, 0.0), (0.22, z + 0.46, 0.0)], st))
    z += 0.5
    parts.append(frustum('collar', [(0.2, z - 0.02, 0), (0.17, z + 0.1, 0)], st))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, 0, z + 0.27))
    hoju = bpy.context.object  # jewel finial, a little pointed
    hoju.data.materials.append(st)
    hoju.data.shade_smooth()
    hoju.scale = (1, 1, 1.15)
    t = bpy.data.textures.new('hoju', 'CLOUDS')
    t.noise_scale = 0.2
    mod(hoju, 'DISPLACE', texture=t, strength=0.02)
    parts.append(hoju)
    chip(parts[4], (0.62, -0.42, z - 0.4), 0.12)  # a bite out of the roof eave
    chip(parts[0], (-0.5, -0.3, 0.2), 0.1)     # and the base
    for o in parts:
        o.rotation_euler.z = 0.12  # not dead square to the camera
    inner.rotation_euler.z = 0.12
    ground(10, soft=2.5, power=1000)
    place(parts, margin=0.2)
    ent = sprite('lantern', {'base': (0, 0, 0), 'light': light})
    foot('lantern', ent, -0.62, 0.62, -0.62, 0.62)


def glow():
    def fn(x, y):
        r = np.sqrt(x * x + y * y)
        a = 0.9 * np.exp(-(r / 0.42) ** 2) + 0.25 * np.exp(-(r / 0.8) ** 2) * (r < 1)
        a = a * np.clip((1 - r) * 6, 0, 1)
        hot = np.exp(-(r / 0.2) ** 2)[..., None]  # whiter at the flame
        return (1 - hot) * np.array([1.0, 0.745, 0.43]) + hot * np.array([1.0, 0.88, 0.66]), a
    still('glow', 256, 256, fn)


if __name__ == '__main__':
    glow()
    lantern()
