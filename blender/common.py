# Shared render setup so scenery and fish share one camera, light rig and look.
# Run scripts as: ~/opt/blender/blender -b --factory-startup -P blender/<script>.py
import math
import os
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets')


def reset(samples=128):
    """Empty scene, Cycles, transparent film, Standard view (no filmic wash-out)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.film_transparent = True
    s.render.image_settings.file_format = 'PNG'
    s.render.image_settings.color_mode = 'RGBA'
    s.view_settings.view_transform = 'Standard'
    s.view_settings.look = 'None'
    world = bpy.data.worlds.new('water')
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.05, 0.22, 0.32, 1)  # blue-green ambient bounce
    bg.inputs['Strength'].default_value = 0.6
    s.world = world
    return s


def camera(width_m, px_w, px_h, y=-10.0, z=0.0):
    """Orthographic side view looking down +Y; width_m world units map to px_w pixels."""
    s = bpy.context.scene
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = width_m * max(1, px_h / px_w)
    cam.location = (0, y, z)
    cam.rotation_euler = (math.radians(90), 0, 0)
    s.collection.objects.link(cam)
    s.camera = cam
    s.render.resolution_x, s.render.resolution_y = px_w, px_h
    s.render.resolution_percentage = 100
    return cam


def lights():
    """Warm soft key from the surface, cool fill from the front, rim from behind."""
    s = bpy.context.scene

    def add(name, kind, energy, color, loc, rot, size):
        l = bpy.data.lights.new(name, kind)
        l.energy, l.color = energy, color
        if kind == 'AREA':
            l.size = size
        else:
            l.angle = size
        o = bpy.data.objects.new(name, l)
        o.location, o.rotation_euler = loc, [math.radians(a) for a in rot]
        s.collection.objects.link(o)
        return o

    return [
        add('key', 'SUN', 3.2, (1.0, 0.95, 0.82), (0, 0, 10), (-15, 10, 0), math.radians(8)),
        add('fill', 'AREA', 250, (0.55, 0.8, 1.0), (0, -8, 1), (80, 0, 0), 12),
        add('rim', 'AREA', 180, (0.6, 0.95, 1.0), (0, 6, 4), (-120, 0, 0), 8),
    ]


def render(path):
    """Render the current scene to assets/<path> (PNG, RGBA)."""
    out = os.path.join(ASSETS, path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    return out
