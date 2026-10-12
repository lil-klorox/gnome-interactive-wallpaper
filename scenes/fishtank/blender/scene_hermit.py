# Hermit crab in a whelk shell, facing +x, shell bottom on z=0 (`base`). Frame 0 = hidden in the shell,
# 1-6 walk, 7-9 pick/eat (claw to mouth), 10-11 half out (coming out). Banded legs, eye stalks.
# Usage: blender -b --factory-startup -P blender/scene_hermit.py   (SAMPLES env = render samples)
import math, os, sys
import bpy
import numpy as np
from mathutils import Quaternion, Vector
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig, half
from scene_eels import eye, eye_mat, outward

APEX = Vector((-0.92, 0, 0.38)).normalized()  # spire points back and a little up
SPIN = math.radians(150)  # turns the mouth to face front-low


def whelk(mat):
    """Tube swept round a cone (apex up), growing exponentially: a tall-spired whelk. uv = (t, around)."""
    n, m, turns = 240, 24, 5.0
    T = turns * math.tau
    b = math.log(1.65) / math.tau
    a = 0.15 / math.exp(b * T)
    verts, uv, faces = [], [], []
    for i in range(n):
        t = i / (n - 1)
        ph = t * T
        R = a * math.exp(b * ph)
        r = 0.62 * R * (1 + 0.04 * math.sin(ph * 9) * (t > 0.2))  # knobbly shoulders
        c = np.array([R * math.cos(ph), R * math.sin(ph), -2.0 * R])
        out = np.array([math.cos(ph), math.sin(ph), 0.0])
        for j in range(m):
            v = j / m * math.tau
            p = c + out * r * math.cos(v) + np.array([0, 0, 1.0]) * r * 1.15 * math.sin(v)
            verts.append(tuple(p))
            uv.append((t, j / m))
    for i in range(n - 1):
        for j in range(m):
            faces.append((i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j))
    o = outward(mesh('shell', verts, faces, mat, uv=uv))
    mod(o, 'SOLIDIFY', thickness=0.012)
    return o, m


def shell_mat():
    """Cream and chestnut spiral bands, fine growth lines across them, worn and a little encrusted."""
    m = new_mat('whelk')
    sp = N(m, 'SeparateXYZ', Vector=(N(m, 'UVMap', _uv_map='UVMap'), 'UV'))
    band = N(m, 'TexWave', Vector=N(m, 'CombineXYZ', X=(sp, 'Y'), Y=(sp, 'X')), _bands_direction='X', Scale=4.0,
             Distortion=4.0, Detail=3.0)
    col = ramp(m, (band, 'Fac'), [(0.2, (0.6, 0.48, 0.32)), (0.45, (0.78, 0.68, 0.5)), (0.6, (0.32, 0.15, 0.06)),
                                  (0.85, (0.55, 0.3, 0.12))])
    growth = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), 420.0))), 4.0)
    nz = N(m, 'TexNoise', Vector=(N(m, 'TexCoord'), 'Object'), Scale=25.0, Detail=6.0)
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=M(m, 'MULTIPLY', growth, 0.25),
          A=(col, 'Color'), B=(0.5, 0.4, 0.3, 1))
    crust = N(m, 'MapRange', Value=(nz, 'Fac'), **{'From Min': 0.62, 'From Max': 0.7})
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (crust, 'Result'), 0.7), A=(c, 'Result'), B=(0.62, 0.42, 0.42, 1))
    c = ao_grime(m, (c, 'Result'), 0.06, 0.35)
    bump = N(m, 'Bump', Strength=0.35, Distance=0.01, Height=M(m, 'ADD', growth, (nz, 'Fac')))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': c, 'Roughness': 0.6, 'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    return m


def crab_mat():
    """Orange-red with pale bands across the legs and a speckled carapace."""
    m = new_mat('crab')
    co = (N(m, 'TexCoord'), 'Object')
    wv = N(m, 'TexWave', Vector=co, Scale=9.0, Distortion=1.0, _bands_direction='X')
    bands = N(m, 'MapRange', Value=(wv, 'Fac'), **{'From Min': 0.75, 'From Max': 0.85})
    nz = N(m, 'TexNoise', Vector=co, Scale=30.0, Detail=4.0)
    col = ramp(m, (nz, 'Fac'), [(0.3, (0.55, 0.1, 0.03)), (0.7, (0.85, 0.28, 0.06))])
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (bands, 'Result'), 0.75), A=(col, 'Color'), B=(0.9, 0.82, 0.65, 1))
    bump = N(m, 'Bump', Strength=0.3, Distance=0.01, Height=(nz, 'Fac'))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.45,
                                                            'Subsurface Weight': 0.15, 'Normal': bump}))
    return m


def blob(loc, scale, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=loc, segments=20, ring_count=10)
    o = bpy.context.object
    o.scale, o.rotation_euler = scale, rot
    o.data.shade_smooth()
    o.data.materials.append(mat)
    return o


def crab(out, walk, pick, cm, em, A):
    """Crab parts at emergence `out` (0 hidden .. 1 out); walk = leg phase or None; pick 0..1 claw up.
    A = shell mouth centre; the parts are laid out with the mouth at (0.06, 0, 0.15)."""
    d = 0.1 * (1 - out)  # pulled back into the mouth (toward -x, up the coil)
    P = lambda x, y, z: (x - d + A[0] - 0.06, y, z + d * 0.4 + A[2] - 0.15)  # noqa: E731
    claw = [curve('arm', [[P(0.12, -0.05, 0.14), P(0.2, -0.08, 0.12), P(0.25, -0.08, 0.1)]], 0.025, cm),
            blob(P(0.29, -0.08, 0.1), (0.07, 0.035, 0.05), cm, (0, math.radians(-15), 0)),
            curve('finger', [[P(0.34, -0.08, 0.12), P(0.4, -0.08, 0.1)], [P(0.34, -0.08, 0.08), P(0.39, -0.08, 0.075)]],
                  0.012, cm, radii=lambda t: 1 - 0.6 * t)]
    if out <= 0:  # hidden: only the big claw shows, plugging the shell mouth
        return claw
    objs = claw + [blob(P(0.12, 0, 0.17), (0.08, 0.07, 0.06), cm)]
    # eye stalks + eyes, antennae
    for s in (-1, 1):
        top = P(0.21, s * 0.03, 0.31)
        objs.append(curve('stalk', [[P(0.15, s * 0.02, 0.2), top]], 0.012, cm))
        objs.append(eye(top, 0.02, em))
    objs.append(curve('ant', [[P(0.17, s * 0.02, 0.2), P(0.32, s * 0.05, 0.3), P(0.42, s * 0.06, 0.24)] for s in (-1, 1)], 0.004, cm))
    # the small claw lifts to the mouth when picking
    up = pick or 0.0
    objs.append(curve('arm2', [[P(0.13, 0.05, 0.14), P(0.24, 0.07, 0.14 + 0.06 * up), P(0.28 - 0.08 * up, 0.06, 0.12 + 0.1 * up)]],
                      0.014, cm))
    objs.append(blob(P(0.29 - 0.08 * up, 0.06, 0.12 + 0.1 * up), (0.03, 0.02, 0.022), cm))
    # two walking legs per side, stepping in turn
    legs = []
    if out > 0.3:
        for k in range(2):
            for s in (-1, 1):
                ph = (walk or 0) - k * math.pi / 2 + (math.pi if s > 0 else 0)
                step = 0.04 * math.sin(ph) if walk is not None else 0
                lift = 0.025 * max(0, math.cos(ph)) if walk is not None else 0
                reach = out
                hip, knee = P(0.12 - k * 0.04, s * 0.05, 0.15), P(0.26 - k * 0.04, s * 0.13, 0.22 + lift)
                foot = (0.3 - k * 0.06 + step - d + A[0] - 0.06, s * 0.12, lift + (1 - reach) * 0.1)
                legs.append([hip, knee, foot])
        objs.append(curve('legs', legs, 0.016, cm, radii=lambda t: 1 - 0.55 * t))
    return objs


def hermit():
    rig(200, 200, 150, cx=-0.05, cz=0.2)
    sm, cm, em = shell_mat(), crab_mat(), eye_mat((0.25, 0.22, 0.15))
    shell, m = whelk(sm)
    piv = bpy.data.objects.new('piv', None)
    bpy.context.scene.collection.objects.link(piv)
    shell.parent = piv
    shell.rotation_mode = 'QUATERNION'  # spin about the shell's own axis (mouth to front-low), then lean back
    shell.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(APEX) @ Quaternion((0, 0, 1), SPIN)
    bpy.context.view_layer.update()
    w = [shell.matrix_world @ v.co for v in shell.data.vertices]
    shell.location = (-0.12 - (min(p.x for p in w) + max(p.x for p in w)) / 2, 0, -min(p.z for p in w))  # resting on z=0
    bpy.context.view_layer.update()
    A = sum((shell.matrix_world @ v.co for v in shell.data.vertices[-m:]), Vector()) / m  # mouth centre
    live = []
    # frame: (out, walk phase or None, pick, shell bob)
    F = [(0, None, 0, 0)] + [(1, k / 6 * math.tau, 0, 0.012 * abs(math.sin(k / 6 * math.tau))) for k in range(6)] + \
        [(1, None, p, 0) for p in (0.5, 1.0, 0.5)] + [(0.45, None, 0, 0), (0.75, None, 0, 0)]

    def pose_for(o, w, p, bob):
        def pose():
            for q in live:
                bpy.data.objects.remove(q)
            piv.location.z = bob
            piv.rotation_euler.y = math.radians(-3) * (bob > 0)
            live[:] = crab(o, w, p, cm, em, A)
        return pose
    sheet('hermit', [pose_for(*f) for f in F], 12, {'base': (-0.12, 0, 0)}, pad=3)
    half('hermit')


if __name__ == '__main__':
    hermit()
