# Cherry shrimp, facing +x, feet on z=0 (`base`). Frames 0-5 walk, 6-9 pick (claws to mouth),
# 10-11 tail flick. See-through red body with a darker saddle, ringed tail, long antennae.
# Usage: blender -b --factory-startup -P blender/scene_shrimp.py   (SAMPLES env = render samples)
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig, half
from scene_eels import tube, skin_coords, eye, eye_mat


def shell():
    """Translucent cherry red: mottled, darker saddle over the back, pale specks, rings on the tail."""
    m = new_mat('shrimp')
    co, sp = skin_coords(m)
    nz = N(m, 'TexNoise', Vector=co, Scale=9.0, Detail=5.0)
    col = ramp(m, (nz, 'Fac'), [(0.3, (0.55, 0.03, 0.02)), (0.7, (0.85, 0.12, 0.05))])
    back = N(m, 'MapRange', Value=M(m, 'COSINE', M(m, 'MULTIPLY', (sp, 'Y'), math.tau)), **{'To Min': 1.0, 'To Max': 0.55})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(col, 'Color'), B=(back, 'Result'))
    vo = N(m, 'TexVoronoi', Vector=co, Scale=50.0)
    sp_ = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.08, 'From Max': 0.14, 'To Min': 0.6, 'To Max': 0.0})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(sp_, 'Result'), A=(c, 'Result'), B=(1.0, 0.75, 0.6, 1))
    ring = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), math.pi / 0.075))), 0.3)
    bump = N(m, 'Bump', Strength=0.3, Distance=0.01, Height=ring)
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.3, 'Subsurface Weight': 0.5,
                                  'Coat Weight': 0.3, 'Coat Roughness': 0.15, 'Normal': bump})
    bs.inputs['Subsurface Radius'].default_value = (1.0, 0.25, 0.15)
    bs.inputs['Subsurface Scale'].default_value = 0.03
    lw = N(m, 'LayerWeight', Blend=0.3)
    mx = N(m, 'MixShader', Fac=M(m, 'MULTIPLY_ADD', (lw, 'Facing'), 0.3, 0.72))  # edges denser, middle see-through
    m.node_tree.links.new(N(m, 'BsdfTransparent', Color=(1.0, 0.5, 0.45, 1)).outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def limb_mat():
    m = new_mat('limb')
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (0.75, 0.12, 0.06, 1), 'Roughness': 0.4, 'Subsurface Weight': 0.4})
    mx = N(m, 'MixShader', Fac=0.75)
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def spine(flick):
    """Head first: rostrum base, humped carapace, abdomen arching down to the tail; flick 0..1 curls
    the tail under the body."""
    pts = [(0.27, 0, 0.1), (0.18, 0, 0.13), (0.07, 0, 0.14), (-0.02, 0, 0.135)]
    p, th = np.array(pts[-1], float), math.pi - 0.05
    for i in range(14):
        th += (0.025 + 0.22 * flick) * (0.5 + i / 14)
        p = p + np.array([math.cos(th), 0, math.sin(th)]) * 0.026
        pts.append(tuple(p))
    return pts


def radius(t):
    """t 0 head .. 1 tail: deep carapace, then the abdomen tapering to the fan."""
    if t < 0.42:
        return 0.035 + 0.04 * math.sin(math.pi * min(1, (t + 0.1) / 0.55)) ** 0.6
    return 0.012 + 0.045 * (1 - (t - 0.42) / 0.58)


def tailfan(p, d, mat):
    """Five-lobed tail fan at p, pointing along d (xz)."""
    paths = []
    for k in range(5):
        a = math.atan2(d[2], d[0]) + (k - 2) * 0.32
        paths.append([tuple(p), tuple(p + np.array([math.cos(a), 0, math.sin(a)]) * 0.075)])
    return curve('fan', paths, 0.016, mat, radii=lambda t: 0.6 + 0.9 * math.sin(math.pi * min(1, t * 0.8)))


def shrimp():
    rig(100, 110, 70, cx=-0.02, cz=0.1)
    body, limb, em = shell(), limb_mat(), eye_mat((0.2, 0.05, 0.03))
    live = []

    def pose_for(f):
        def pose():
            for o in live:
                bpy.data.objects.remove(o)
            flick = {10: 0.4, 11: 0.75}.get(f, 0.0)
            walk = f / 6 * math.tau if f < 6 else 0.0
            pick = (f - 6) / 4 * math.tau if 6 <= f < 10 else None
            pts = spine(flick)
            objs = [tube('body', pts, radius, body, m=20, sq=0.75)]
            end, pre = np.array(pts[-1]), np.array(pts[-3])
            objs.append(tailfan(end, (end - pre) / np.linalg.norm(end - pre), body))
            for s in (-1, 1):
                objs.append(eye((0.26, s * 0.04, 0.135), 0.017, em))
            # walking legs: 4 pairs under the carapace; each foot steps in turn
            legs = []
            for k in range(4):
                hx = 0.17 - k * 0.055
                for s in (-1, 1):
                    ph = walk - k * 1.1 + (math.pi if s > 0 else 0)
                    fx = hx + 0.02 + (0.025 * math.sin(ph) if f < 6 else 0)
                    lift = 0.012 * max(0, math.cos(ph)) if f < 6 else 0
                    legs.append([(hx, s * 0.025, 0.08), (hx + 0.035, s * 0.06, 0.06 + lift), (fx + 0.02, s * 0.06, lift)])
            # claws: small front legs, reaching to the mouth when picking
            for s in (-1, 1):
                up = 0.5 + 0.5 * math.sin(pick + (0 if s < 0 else math.pi)) if pick is not None else 0
                legs.append([(0.22, s * 0.025, 0.08), (0.27 + 0.02 * (1 - up), s * 0.045, 0.04 + 0.03 * up),
                             (0.31 - 0.04 * up, s * 0.035, 0.015 + 0.07 * up)])
            # swimmerets under the abdomen
            for k in range(4):
                q = np.array(pts[5 + k * 2])
                legs.append([tuple(q - [0, 0, 0.03]), tuple(q + [0.012 * math.sin(walk + k), 0, -0.06])])
            objs.append(curve('legs', legs, 0.006, limb, radii=lambda t: 1 - 0.5 * t))
            # long antennae arch back over the body, short antennules forward
            ant = [[(0.27, s * 0.02, 0.12), (0.36, s * 0.03, 0.16), (0.22, s * 0.05, 0.2), (-0.08, s * 0.06, 0.19),
                    (-0.32, s * 0.07, 0.12 + 0.015 * math.sin(walk + s))] for s in (-1, 1)]
            ant += [[(0.28, s * 0.015, 0.11), (0.36, s * 0.02, 0.14), (0.41, s * 0.02, 0.13)] for s in (-1, 1)]
            objs.append(curve('ant', ant, 0.004, limb))
            objs.append(curve('rostrum', [[(0.24, 0, 0.13), (0.33, 0, 0.135)]], 0.012, body, radii=lambda t: 1 - 0.85 * t))
            live[:] = objs
        return pose
    sheet('shrimp', [pose_for(f) for f in range(12)], 12, {'base': (0.05, 0, 0)}, pad=3)
    half('shrimp')


if __name__ == '__main__':
    shrimp()
