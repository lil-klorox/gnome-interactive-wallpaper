# Snail: log-spiral shell with growth ridges and colour bands, wet bumpy foot, eye stalks.
# 8 uncropped frames of a creeping cycle (foot stretches/contracts, stalks bob), facing +x.
import math, os, sys
import bpy
from mathutils import Vector as V
sys.path.insert(0, os.path.dirname(__file__))
from common import *


def shell_mesh():
    """Tube swept along a logarithmic spiral in the XZ plane (facing the camera)."""
    b, turns, n, m = math.log(2.2) / math.tau, 3.1, 260, 28
    T = turns * math.tau
    a = 0.215 / math.exp(b * T)                      # final whorl radius
    verts, uvs, faces = [], [], []
    for i in range(n):
        t = i / (n - 1)
        th = t * T
        R = a * math.exp(b * th)
        r = 0.43 * R * (1 + 0.025 * math.sin(th * 34)) * (1 + 0.04 * t ** 8)   # growth ridges, flared lip
        phi = -th + 0.1                               # coil clockwise seen from the front
        c = V((R * math.cos(phi), -0.18 * R * (1 - t), R * math.sin(phi)))   # slight cone toward camera
        out = V((math.cos(phi), 0, math.sin(phi)))
        for j in range(m):
            v = j / m * math.tau
            p = c + out * (r * math.cos(v)) + V((0, 1, 0)) * (r * 1.05 * math.sin(v))
            verts.append(p)
            uvs.append((t, j / m))
    for i in range(n - 1):
        for j in range(m):
            faces.append((i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j))
    return verts, faces, uvs


def shell_mat():
    m = new_mat('shell')
    uv = N(m, 'UVMap', _uv_map='UVMap')
    sp = N(m, 'SeparateXYZ', Vector=uv)
    # bands run along the coil (around-tube coordinate), ridges across it
    band = N(m, 'TexWave', Vector=N(m, 'CombineXYZ', X=(sp, 'Y'), Y=(sp, 'X')), _bands_direction='X', Scale=1.3,
             Distortion=1.5, Detail=3.0)
    col = ramp(m, (band, 'Fac'), [(0.0, (0.08, 0.025, 0.006)), (0.3, (0.75, 0.25, 0.03)), (0.5, (1.0, 0.65, 0.2)),
                                  (0.7, (0.7, 0.24, 0.03)), (1.0, (0.12, 0.04, 0.01))])
    ridge = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), 260.0))), 3.0)
    nz = N(m, 'TexNoise', Vector=uv, Scale=30.0, Detail=6.0)
    apex = N(m, 'MapRange', Value=(sp, 'X'), **{'From Min': 0.0, 'From Max': 0.25, 'To Min': 0.55, 'To Max': 1.0})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(col, 'Color'), B=(apex, 'Result'))
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.3, A=(c, 'Result'), B=(nz, 'Color'))
    bump = N(m, 'Bump', Strength=0.35, Distance=0.01, Height=M(m, 'ADD', ridge, M(m, 'MULTIPLY', (nz, 'Fac'), 0.4)))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.35, 'Coat Weight': 0.35,
                                  'Coat Roughness': 0.08, 'Subsurface Weight': 0.0, 'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    return m


def skin_mat():
    m = pbr('skin', (0.22, 0.1, 0.035), (0.55, 0.33, 0.16), rough=0.3, scale=14.0, bump=0.5, vor=0.6,
            grime=0.5, sss=0.35, coat=0.25)
    principled(m).inputs['Coat Roughness'].default_value = 0.05
    return m


def body(ph, mat):
    """Foot lofted along x: flat sole, domed back, head lifting at the front. ph = creep phase."""
    stretch = 1 + 0.09 * math.sin(ph)
    n, m = 40, 20
    verts, faces = [], []
    for i in range(n):
        t = i / (n - 1)                         # 0 tail .. 1 head
        x = (-0.42 + 0.82 * t) * stretch + 0.03 * math.sin(ph - t * 3) * t
        w = 0.1 * math.sin(math.pi * min(1, (t * 0.92 + 0.04))) ** 0.6 * (1 - 0.25 * t)
        hgt = 0.06 + 0.07 * math.sin(math.pi * t) ** 0.7 + 0.05 * max(0, t - 0.75) / 0.25
        lift = 0.05 * max(0, t - 0.72) / 0.28 * (1 + 0.15 * math.sin(ph * 2))
        for j in range(m):
            v = j / m * math.tau
            y = w * math.cos(v)
            z = max(-0.2, math.sin(v)) * hgt if math.sin(v) > 0 else math.sin(v) * 0.012
            verts.append((x, y, z + 0.012 + lift))
    for i in range(n - 1):
        for j in range(m):
            faces.append((i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j))
    verts.append((-0.43 * stretch, 0, 0.02))
    verts.append((0.42 * stretch + 0.03, 0, 0.07))
    faces += [(len(verts) - 2, (j + 1) % m, j) for j in range(m)]
    faces += [(len(verts) - 1, (n - 1) * m + j, (n - 1) * m + (j + 1) % m) for j in range(m)]
    o = mesh('foot', verts, faces, mat)
    mod(o, 'SUBSURF', levels=2, render_levels=2)
    return o, 0.42 * stretch


def stalks(head_x, ph, mat, eye):
    objs = []
    cu = bpy.data.curves.new('stalks', 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', 1.0, 3, True
    hz = 0.17
    for side in (-1, 1):
        for long_, ln, el, r0 in ((True, 0.2, 1.05, 0.015), (False, 0.08, 0.25, 0.012)):
            bob = 0.12 * math.sin(ph * 2 + side) if long_ else 0.2 * math.sin(ph + side)
            sp = cu.splines.new('POLY')
            k = 7
            sp.points.add(k - 1)
            p = V((head_x - 0.05, side * 0.03, hz - (0 if long_ else 0.06)))
            a = el + bob
            for i in range(k):
                sp.points[i].co = (*p, 1)
                sp.points[i].radius = r0 * (1 - 0.45 * i / (k - 1))
                p = p + V((math.cos(a), side * 0.18, math.sin(a))).normalized() * (ln / (k - 1))
                a -= 0.12 if long_ else 0.05
            if long_:
                bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, location=p, segments=24, ring_count=12)
                e = bpy.context.object
                e.data.shade_smooth()
                e.data.materials.append(eye)
                objs.append(e)
    o = bpy.data.objects.new('stalks', cu)
    bpy.context.scene.collection.objects.link(o)
    cu.materials.append(mat)
    return objs + [o]


def eye_mat():
    m = new_mat('eye')
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (0.01, 0.01, 0.012, 1),
                                                            'Roughness': 0.1, 'Coat Weight': 1.0}))
    return m


scenery()
skin, eye = skin_mat(), eye_mat()
sv, sf, suv = shell_mesh()
shell = mesh('shell', sv, sf, shell_mat(), uv=suv)
shell.rotation_euler = (0, math.radians(-12), 0)
ground(4)
for f in range(8):
    ph = f / 8 * math.tau
    foot, hx = body(ph, skin)
    parts = stalks(hx, ph, skin, eye) + [foot]
    shell.location = (-0.07 + 0.015 * math.sin(ph - 0.6), 0, 0.27 + 0.006 * math.cos(ph))
    if f == 0:
        fit([shell, foot] + parts, margin=0.1)
    sprite(f'snail_{f}', {'base': (0, 0, 0)}, crop=False)
    for o in parts:
        bpy.data.objects.remove(o)
crop_frames([f'snail_{f}' for f in range(8)])
