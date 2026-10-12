# Rocks, the air-stone bubbler and the bubble sprite.
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *


def tentacles(rnd, at, mat, n=26, r=0.16, ln=0.35):
    """Sea anemone: a squat column topped with a ring of fat tapering tentacles."""
    out = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=0.18, location=(at[0], at[1], at[2] + 0.06))
    col = bpy.context.object
    mod(col, 'SUBSURF', levels=2, render_levels=2)
    col.data.materials.append(mat)
    out.append(col)
    for i in range(n):
        a = i / n * 2 * math.pi + rnd.uniform(-0.1, 0.1)
        ring = r * (0.65 if i % 2 else 0.9)
        cu = bpy.data.curves.new('tent', 'CURVE')
        cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', 0.028, 3, True
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(3)
        L = ln * rnd.uniform(0.7, 1.15)
        for k, bp in enumerate(sp.bezier_points):
            t = k / 3
            out_r = ring + t * L * 0.75
            bp.co = (at[0] + out_r * math.cos(a), at[1] + out_r * math.sin(a), at[2] + 0.15 + t * L * 0.8 - t * t * L * 0.5)
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
            bp.radius = 1.0 - 0.75 * t
        o = bpy.data.objects.new('tent', cu)
        bpy.context.scene.collection.objects.link(o)
        cu.materials.append(mat)
        out.append(o)
    return out


def arch(mat):
    """Rock arch: a bent, lumpy tube faceted like the boulders."""
    cu = bpy.data.curves.new('arch', 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', 0.45, 6, True
    sp = cu.splines.new('BEZIER')
    pts = [(-1.5, 0, -0.4), (-1.3, 0, 0.9), (-0.4, 0.1, 1.75), (0.6, -0.1, 1.6), (1.35, 0, 0.7), (1.5, 0.1, -0.4)]
    sp.bezier_points.add(len(pts) - 1)
    for bp, p, rr in zip(sp.bezier_points, pts, (1.6, 1.25, 0.95, 0.85, 1.15, 1.5)):
        bp.co, bp.radius = p, rr
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new('arch', cu)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    mod(o, 'REMESH', mode='VOXEL', voxel_size=0.05)
    for kind, s, st in (('VORONOI', 0.6, 0.25), ('CLOUDS', 0.35, 0.18)):
        t = bpy.data.textures.new('ar', kind)
        t.noise_scale = s
        mod(o, 'DISPLACE', texture=t, strength=st, texture_coords='GLOBAL')
    mod(o, 'DECIMATE', ratio=0.04)
    apply_all(o)
    mod(o, 'BEVEL', width=0.04, segments=3, limit_method='ANGLE', angle_limit=math.radians(25))
    mod(o, 'SUBSURF', levels=1, render_levels=1)
    apply_all(o)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    o.data.materials.append(mat)
    return o


def air_stone(mat, tube_mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.22, depth=0.5, location=(0, 0, 0.12), rotation=(0, math.radians(90), 0.25))
    st = bpy.context.object
    mod(st, 'BEVEL', width=0.05, segments=4)
    mod(st, 'SUBSURF', levels=2, render_levels=2)
    st.data.materials.append(mat)
    # airline: clear tubing from the stone's end, arching over and diving into the sand
    cu = bpy.data.curves.new('tube', 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution = '3D', 0.045, 6
    sp = cu.splines.new('BEZIER')
    pts = [(0.3, -0.07, 0.15), (0.6, 0.05, 0.32), (1.0, 0.25, 0.3), (1.35, 0.4, -0.05)]
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    tube = bpy.data.objects.new('tube', cu)
    bpy.context.scene.collection.objects.link(tube)
    cu.materials.append(tube_mat)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.06, depth=0.08, location=(0.27, -0.065, 0.14), rotation=(0, math.radians(90), 0.25))
    nip = bpy.context.object  # plastic nipple the tube pushes onto
    nip.data.materials.append(pbr('nipple', (0.02, 0.02, 0.02), rough=0.35, scale=20, bump=0.05))
    return [st, tube, nip]


def build():
    scenery()
    rnd = np.random.default_rng(4)
    ground(30)
    a = rock((1.5, 1.1, 0.95), 0.35, 1)
    a.data.materials.append(stone('rock_a', moss=0.6))
    b = rock((0.8, 0.7, 1.7), 0.3, 5, facets=0.02)
    b.data.materials.append(stone('rock_b', moss=0.45, c1=(0.09, 0.075, 0.06), c2=(0.24, 0.19, 0.14)))
    c = [rock((s, s * 0.85, s * 0.7), 0.15 * s, 11 + i, facets=0.08, loc=(x, y, 0))
         for i, (s, x, y) in enumerate(((0.55, 0, 0), (0.38, 0.75, -0.25), (0.3, -0.62, 0.15), (0.2, 0.42, -0.5)))]
    river = pbr('river', (0.1, 0.075, 0.05), (0.3, 0.22, 0.15), rough=0.45, coat=0.15, scale=2.5, bump=0.15, moss=0.3, strata=0.3)
    for o in c:
        o.data.materials.append(river)
    anem = pbr('anemone', (0.65, 0.12, 0.3), (0.95, 0.45, 0.55), rough=0.4, scale=6, bump=0.2, sss=0.5, grime=0.2)
    c += tentacles(rnd, (0.05, -0.05, 0.36), anem)
    d = arch(stone('rock_d', moss=0.55, c1=(0.06, 0.06, 0.055), c2=(0.18, 0.16, 0.13)))
    porous = pbr('airstone', (0.35, 0.38, 0.42), (0.6, 0.62, 0.65), rough=0.95, scale=12, bump=0.8, vor=1.0, grime=0.8)
    glass = new_mat('tubing')
    N(glass, 'OutputMaterial', Surface=N(glass, 'BsdfGlass', Color=(0.85, 0.95, 0.9, 1), Roughness=0.08, IOR=1.4))
    bub = air_stone(porous, glass)
    sets = {'rock_a': [a], 'rock_b': [b], 'rock_c': c, 'rock_d': [d], 'bubbler': bub}
    for name, objs in sets.items():
        for o in [o for v in sets.values() for o in v]:
            o.hide_render = o not in objs
        fit([o for o in objs if o.type in ('MESH', 'CURVE')], margin=0.35)
        pts = {'base': (0, 0, 0)}
        if name == 'bubbler':
            pts['outlet'] = (0, 0, 0.36)
        sprite(name, pts)
    # bubble: an air pocket in water (IOR < 1 gives the bright total-reflection rim)
    reset(256)
    bpy.context.scene.cycles.film_transparent_glass = True
    lights()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1)
    o = bpy.context.object
    o.scale.z = 0.93
    o.data.shade_smooth()
    m = new_mat('bubble')
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfGlass', Color=(0.9, 1, 1, 1), Roughness=0.0, IOR=0.75))
    o.data.materials.append(m)
    camera(2.3, 56, 56)
    sprite('bubble', pad=0, crop=False)


build()
