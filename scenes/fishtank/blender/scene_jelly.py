# Moon jelly: translucent bell (12-frame pulse: 0-3 contract, 4-11 relax) seen 3/4 from above,
# with radial canals, four horseshoe gonads inside and a fringe of fine marginal tentacles.
# Plus two frilly oral-arm strips (stored pointing up like a plant: base at the bottom, j1 joint)
# that tank.js hangs from the bell's `mouth` with the plant chain code.
# Usage: blender -b --factory-startup -P blender/scene_jelly.py   (SAMPLES env = render samples)
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig, half

TIP = math.radians(28)  # bell top tipped toward the camera: the 3/4 view


def contraction(f):
    """0 relaxed .. 1 fully contracted: quick squeeze over frames 0-3, slow relax over 4-11."""
    if f <= 3:
        return math.sin(f / 3 * math.pi / 2)
    return 0.5 + 0.5 * math.cos((f - 3) / 9 * math.pi)


def bell_mat():
    """Milky glass: see-through face-on, brighter and denser at grazing angles, faint radial canals."""
    m = new_mat('bell')
    co = (N(m, 'TexCoord'), 'Object')
    sep = N(m, 'SeparateXYZ', Vector=co)
    ang = M(m, 'ARCTAN2', (sep, 'Y'), (sep, 'X'))
    canal = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'COSINE', M(m, 'MULTIPLY', ang, 8.0))), 40.0)
    nz = N(m, 'TexNoise', Vector=co, Scale=6.0, Detail=4.0)
    lw = N(m, 'LayerWeight', Blend=0.35)
    dens = M(m, 'MULTIPLY_ADD', (lw, 'Facing'), 0.75, M(m, 'MULTIPLY_ADD', canal, 0.18, M(m, 'MULTIPLY', (nz, 'Fac'), 0.12)))
    dens.use_clamp = True
    col = ramp(m, (nz, 'Fac'), [(0.3, (0.72, 0.82, 0.9)), (0.7, (0.86, 0.84, 0.95))])
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (col, 'Color'), 'Roughness': 0.25, 'Subsurface Weight': 0.6,
                                  'Emission Color': (0.55, 0.75, 0.9, 1), 'Emission Strength': 0.15})
    bs.inputs['Subsurface Radius'].default_value = (0.5, 0.6, 0.8)
    bs.inputs['Subsurface Scale'].default_value = 0.1
    mx = N(m, 'MixShader', Fac=dens)
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def soft_mat(name, col, dens, emit=0.2):
    m = new_mat(name)
    nz = N(m, 'TexNoise', Vector=(N(m, 'TexCoord'), 'Object'), Scale=20.0, Detail=3.0)
    lw = N(m, 'LayerWeight', Blend=0.4)
    d = M(m, 'MULTIPLY_ADD', (lw, 'Facing'), dens * 0.5, M(m, 'MULTIPLY_ADD', (nz, 'Fac'), dens * 0.4, dens * 0.6))
    d.use_clamp = True
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (*col, 1), 'Roughness': 0.4, 'Subsurface Weight': 0.5,
                                  'Emission Color': (*col, 1), 'Emission Strength': emit})
    mx = N(m, 'MixShader', Fac=d)
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def dome(c, f):
    """Bell (r, z) profile at contraction c: saucer when relaxed, taller and narrower squeezed."""
    R, H = 1 - 0.22 * c, 0.55 + 0.32 * c
    def at(u, th):
        a = u * math.pi / 2 * (1.0 + 0.12 * c)  # squeezed: the margin curls under
        lap = 1 + 0.025 * math.cos(16 * th) * u ** 6  # lappets at the rim
        wob = 1 + 0.02 * math.sin(2 * th + f * 0.9) * u  # never perfectly round
        return R * math.sin(a) * lap * wob, H * math.cos(a) - 0.06 * u ** 4
    return at


def bell(mat, gm, fm, f):
    c = contraction(f)
    at = dome(c, f)
    n, m = 40, 96
    verts, faces = [(0, 0, at(0, 0)[1])], []
    for i in range(1, n + 1):
        for j in range(m):
            th = j / m * math.tau
            r, z = at(i / n, th)
            verts.append((r * math.cos(th), r * math.sin(th), z))
    faces += [(0, 1 + j, 1 + (j + 1) % m) for j in range(m)]
    for i in range(n - 1):
        for j in range(m):
            a, b = 1 + i * m, 1 + (i + 1) * m
            faces.append((a + j, b + j, b + (j + 1) % m, a + (j + 1) % m))
    o = mesh('bell', verts, faces, mat)
    mod(o, 'SOLIDIFY', thickness=0.07)
    objs = [o]
    # four horseshoe gonads under the dome top
    paths = []
    for k in range(4):
        ca = k * math.pi / 2 + 0.3
        cx, cy, rr = 0.32 * math.cos(ca), 0.32 * math.sin(ca), 0.15
        pts = []
        for t in np.linspace(0.9, math.tau - 0.9, 20):  # open horseshoe, gap toward the centre
            x, y = cx - rr * math.cos(t + ca), cy - rr * math.sin(t + ca)
            rho = math.hypot(x, y) / (1 - 0.22 * c)
            pts.append((x, y, at(min(1, rho), 0)[1] - 0.12))
        paths.append(pts)
    objs.append(curve('gonads', paths, 0.05, gm, res=3, radii=lambda t: 0.6 + 0.4 * math.sin(math.pi * t)))
    # marginal tentacles: short fine hairs hanging off the rim, curling with the pulse
    hairs = []
    rng = np.random.default_rng(f)
    for j in range(72):
        th = j / 72 * math.tau + rng.uniform(-0.03, 0.03)
        r, z = at(1, th)
        L = 0.16 + rng.uniform(0, 0.08)
        pts = []
        for t in np.linspace(0, 1, 6):
            rr = r * (1 - 0.1 * t * (0.5 + c)) + 0.02 * math.sin(t * 4 + j)
            pts.append((rr * math.cos(th), rr * math.sin(th), z - L * t))
        hairs.append(pts)
    objs.append(curve('fringe', hairs, 0.009, fm, radii=lambda t: 1 - 0.7 * t))
    for q in objs:
        q.rotation_euler = (TIP, 0, 0)
    return objs, at


def tip(p):
    x, y, z = p
    return (x, y * math.cos(TIP) - z * math.sin(TIP), y * math.sin(TIP) + z * math.cos(TIP))


def jelly():
    rig(70, 200, 170, cz=0.25)  # 2x: bell 2 units = 140 px -> 70 px on screen
    bm, gm, fm = bell_mat(), soft_mat('gonad', (0.78, 0.55, 0.8), 0.55, 0.2), soft_mat('fringe', (0.8, 0.88, 0.95), 0.6)
    live = []
    state = {}

    def pose_for(f):
        def pose():
            for o in live:
                bpy.data.objects.remove(o)
            live[:], state['at'] = bell(bm, gm, fm, f)
        return pose
    poses = [pose_for(f) for f in range(12)]
    pts = {'anchor': lambda: tip((0, 0, state['at'](0, 0)[1] + 0.035)),
           'mouth': lambda: tip((0, 0, state['at'](1, 0)[1] + 0.05))}
    sheet('jelly', poses, 12, pts, pad=4)
    half('jelly')


def arm(L, sd, mat):
    """Frilly oral arm hanging down from (0,0,0): a tapering ribbon with ruffled, curling edges."""
    rng = np.random.default_rng(sd)
    n, m = 90, 9
    verts, faces = [], []
    for i in range(n):
        t = i / (n - 1)
        w = 0.3 * (1 - 0.7 * t) * (1 + 0.2 * math.sin(t * 9 + sd))
        cx = 0.12 * math.sin(t * 3.2 + sd) * t
        tw = t * 5 + sd  # the ribbon twists, so edges and faces alternate down its length
        for j in range(m):
            u = j / (m - 1) * 2 - 1
            ruffle = 0.16 * abs(u) ** 1.5 * math.sin(t * 70 + u * 4 + rng.uniform(0, 0.5))
            a, b = u * w, ruffle + 0.08 * u * u
            verts.append((cx + a * math.cos(tw) - b * math.sin(tw), a * math.sin(tw) + b * math.cos(tw), -L * t))
    for i in range(n - 1):
        for j in range(m - 1):
            a = i * m + j
            faces.append((a, a + 1, a + m + 1, a + m))
    o = mesh('arm', verts, faces, mat)
    mod(o, 'SOLIDIFY', thickness=0.02)
    threads = [[(0.1 * k - 0.1 + 0.06 * math.sin(t * 11 + k), 0.05, -L * 1.05 * t) for t in np.linspace(0, 1, 30)] for k in range(3)]
    return [o, curve('threads', threads, 0.012, mat, radii=lambda t: 1 - 0.6 * t)]


def tentacles():
    for name, L, sd in (('jelly_tent_0', 4.0, 1), ('jelly_tent_1', 5.7, 2)):
        rig(70, 60, int(L * 70) + 30, cz=-L / 2)
        objs = arm(L, sd, soft_mat('arm', (0.88, 0.84, 0.95), 0.6, 0.3))
        sheet(name, [lambda: None], 1, {'base': (0, 0, 0), 'j1': (0, 0, -0.45 * L)}, pad=4)
        flip(name)
        half(name)


def flip(name):
    """Stored pointing up: flip the strip vertically and mirror its points."""
    import json
    path = os.path.join(ASSETS, name + '.png')
    save_png(load_png(path)[::-1], path)
    with open(os.path.join(ASSETS, 'manifest.json')) as fh:
        ent = json.load(fh)['images'][name]
    for k in ('base', 'j1'):
        ent[k] = [ent[k][0], round(ent['h'] - ent[k][1], 1)]
    ent.pop('px', None)
    manifest(name, ent)


jelly()
tentacles()
