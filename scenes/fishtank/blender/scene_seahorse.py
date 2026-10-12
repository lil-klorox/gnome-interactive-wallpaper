# Seahorse, upright, facing +x. Row 0 swim: tail loose and swaying, dorsal fin fluttering; row 1 rest:
# tail curled tight, slower (smaller) flutter. Ringed bony trunk, snout, coronet, set-in eye.
# Usage: blender -b --factory-startup -P blender/scene_seahorse.py   (SAMPLES env = render samples)
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig, half
from scene_eels import tube, skin_coords, eye, eye_mat

H = np.array([0.04, 0.0, 1.05])  # head centre
EYE = H + np.array([0.035, -0.07, 0.015])


def skin():
    """Ochre with fine pale freckles, darker along the back, dark grooves between the bony rings."""
    m = new_mat('seahorse')
    co, sp = skin_coords(m)
    nz = N(m, 'TexNoise', Vector=co, Scale=6.0, Detail=5.0)
    col = ramp(m, (nz, 'Fac'), [(0.3, (0.8, 0.42, 0.07)), (0.7, (1.0, 0.66, 0.18))])
    vo = N(m, 'TexVoronoi', Vector=co, Scale=40.0)
    fr = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.1, 'From Max': 0.18, 'To Min': 0.85, 'To Max': 0.0})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(fr, 'Result'), A=(col, 'Color'), B=(0.95, 0.85, 0.6, 1))
    ring = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), math.pi / 0.055))), 0.35)
    groove = N(m, 'MapRange', Value=ring, **{'To Min': 0.7, 'To Max': 1.0})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(c, 'Result'), B=(groove, 'Result'))
    bump = N(m, 'Bump', Strength=0.35, Distance=0.02, Height=M(m, 'ADD', ring, M(m, 'MULTIPLY', (nz, 'Fac'), 0.3)))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.55, 'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    return m


def fin_mat():
    m = new_mat('fin')
    sep = N(m, 'SeparateXYZ', Vector=(N(m, 'UVMap', _uv_map='UVMap'), 'UV'))
    ray = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sep, 'X'), math.pi * 9))), 6.0)
    a = M(m, 'MULTIPLY_ADD', ray, 0.3, 0.5)
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (0.9, 0.6, 0.22, 1), 'Roughness': 0.4, 'Subsurface Weight': 0.3})
    mx = N(m, 'MixShader', Fac=a)
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def spine(curl, sway):
    """Centre line from the neck down: chest, belly, then a tail spiralling forward by `curl` rad."""
    pts = [(0.0, 0, 0.95), (0.06, 0, 0.85), (0.11, 0, 0.72), (0.12, 0, 0.6), (0.1, 0, 0.48), (0.05, 0, 0.38)]
    p, th, ds = np.array(pts[-1], float), -math.pi / 2 - 0.25, 0.022
    n = 24
    for i in range(n):
        u = (i + 1) / n
        th += curl * ds / 0.42 * (0.3 + 1.7 * u ** 1.5) + sway * 0.04 * math.sin(u * 4)
        p = p + np.array([math.cos(th), 0, math.sin(th)]) * ds
        pts.append(tuple(p))
    return pts


def radius(t):
    """t 0 neck .. 1 tail tip (trunk is the first ~53 % of the line): thin neck, deep belly, long tail."""
    if t < 0.07:
        return 0.05
    if t < 0.53:
        return 0.05 + 0.065 * math.sin(math.pi * (t - 0.07) / 0.46) ** 0.7
    return 0.008 + 0.042 * (1 - (t - 0.53) / 0.47) ** 1.2


def fan(name, base0, base1, out, mat, ph, amp, rays=10):
    """Fin membrane on the line base0 -> base1, reaching `out`; a travelling ripple flutters it."""
    b0, b1, o = map(np.array, (base0, base1, out))
    verts, uv, faces = [], [], []
    m = 6
    for i in range(rays + 1):
        t = i / rays
        b = b0 + (b1 - b0) * t
        tip = b + o * (0.6 + 0.4 * math.sin(math.pi * t))
        for j in range(m):
            v = j / (m - 1)
            q = b + (tip - b) * v
            q[1] += amp * v ** 1.3 * math.sin(math.tau * ph - t * 5)
            verts.append(tuple(q))
            uv.append((t, v))
    for i in range(rays):
        for j in range(m - 1):
            a = i * m + j
            faces.append((a, a + m, a + m + 1, a + 1))
    o = mesh(name, verts, faces, mat, uv=uv)
    mod(o, 'SOLIDIFY', thickness=0.004)
    return o


def head(mat, em):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=tuple(H), segments=32, ring_count=16)
    sk = bpy.context.object
    sk.scale = (0.1, 0.075, 0.085)
    sk.rotation_euler = (0, math.radians(-15), 0)
    sk.data.shade_smooth()
    sk.data.materials.append(mat)
    objs = [sk]
    # snout, with a slight flare at the mouth; coronet knobs on the crown; cheek spine
    objs.append(curve('snout', [[tuple(H + [0.06, 0, -0.02]), tuple(H + [0.17, 0, -0.045]), tuple(H + [0.25, 0, -0.06])]],
                      0.03, mat, res=3, radii=lambda t: 1 - 0.25 * t + 0.4 * max(0, t - 0.85) / 0.15))
    for k, (dx, dz, r) in enumerate(((-0.03, 0.09, 0.022), (-0.01, 0.115, 0.016), (-0.05, 0.1, 0.014), (0.01, 0.13, 0.01))):
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r * 0.35, depth=0.05, location=tuple(H + [dx, 0, dz]), vertices=10)
        c = bpy.context.object
        c.rotation_euler = (0, math.radians(-12 + 8 * k), 0)
        c.data.materials.append(mat)
        objs.append(c)
    objs.append(eye(tuple(EYE), 0.024, em))
    return objs


def seahorse():
    rig(100, 90, 160, cx=0.08, cz=0.62)
    body, fm, em = skin(), fin_mat(), eye_mat((0.85, 0.6, 0.15))
    hm = pbr('shead', (0.5, 0.26, 0.05), (0.78, 0.48, 0.12), rough=0.55, scale=25, bump=0.3, vor=0.3, grime=0.5)
    head(hm, em)
    live = []

    def pose_for(row, f):
        def pose():
            for o in live:
                bpy.data.objects.remove(o)
            ph = f / 12
            curl = (2.3 if row else 1.0) * math.pi + (0 if row else 0.35 * math.sin(math.tau * ph))
            pts = spine(curl, 0 if row else math.sin(math.tau * ph))
            amp = 0.012 if row else 0.03
            live[:] = [tube('trunk', pts, radius, body, m=24, sq=0.8),
                       fan('dorsal', (0.01, -0.01, 0.63), (-0.01, -0.01, 0.43), (-0.1, 0, 0.02), fm, ph, amp),
                       fan('pec', tuple(H + [-0.07, -0.05, -0.05]), tuple(H + [-0.06, -0.05, -0.1]), (-0.05, -0.02, 0), fm, ph * 2, amp, rays=6)]
        return pose
    poses = [pose_for(r, f) for r in (0, 1) for f in range(12)]
    sheet('seahorse', poses, 12, {'anchor': tuple(EYE)}, pad=3)
    half('seahorse')


if __name__ == '__main__':
    seahorse()
