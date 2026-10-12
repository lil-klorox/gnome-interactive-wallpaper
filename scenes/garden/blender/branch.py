# Overhanging branch, one still per season, entering from the top-right corner of a 900x500 frame (not
# cropped: the runtime pins it to the screen corner). Maple with red leaves (autumn) or green leaves and
# seed wings (summer); cherry with pink blossom and a few young leaves (spring). Worn bark with lichen.
# Usage: blender -b --factory-startup -t 6 -P scenes/garden/blender/branch.py [-- autumn summer spring]
import math, os, sys
import bpy
import numpy as np
from mathutils import Matrix, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *
from leaves import leaf, leaf_mat, stem_mat, leaf_mesh

W, H = 9.0, 5.0  # frame in world units (PPU 100 -> 900x500 px)


def bark(season):
    """Bark: cracked, grimy, moss on the tops; pale lichen rosettes. Cherry is redder and smoother."""
    if season == 'spring':
        m = pbr('bark', (0.09, 0.04, 0.035), (0.24, 0.12, 0.09), rough=0.7, scale=5, bump=0.35, grime=0.6,
                cracks=0.15, strata=0.3, moss=0.1)
    else:
        m = pbr('bark', (0.06, 0.05, 0.042), (0.2, 0.17, 0.13), rough=0.88, scale=4, bump=0.6, vor=0.2, grime=0.65,
                cracks=0.5, strata=0.12, moss=0.25)
    nt, bs = m.node_tree, principled(m)
    co = (N(m, 'TexCoord'), 'Object')
    lv = N(m, 'TexVoronoi', Vector=co, Scale=7.0)
    ln = N(m, 'TexNoise', Vector=co, Scale=30.0, Detail=4.0)
    pick = M(m, 'GREATER_THAN', (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(lv, 'Color')), 'Value'), 0.7)
    blob = M(m, 'MULTIPLY', M(m, 'LESS_THAN', M(m, 'MULTIPLY_ADD', (ln, 'Fac'), 0.12, (lv, 'Distance')), 0.3), pick)
    lc = ramp(m, (ln, 'Fac'), [(0.4, (0.36, 0.4, 0.3)), (0.6, (0.55, 0.58, 0.45))])
    base = bs.inputs['Base Color'].links[0].from_socket
    mix = N(m, 'Mix', _data_type='RGBA', Factor=blob, B=(lc, 'Color'))
    nt.links.new(base, sock(mix.inputs, 'A'))
    nt.links.new(sock(mix.outputs, 'Result'), bs.inputs['Base Color'])
    return m


def path(p, ang, L, rng, n=10, bend=0.0, zv=0.0):
    """Wobbly limb centre line from p heading ang (rad, screen plane), bending `bend` rad per unit."""
    pts, p = [np.array(p, float)], np.array(p, float)
    for i in range(1, n):
        ang += (bend + rng.uniform(-0.5, 0.5)) * L / n
        p = p + np.array([math.cos(ang), math.sin(ang), zv + rng.uniform(-0.15, 0.15)]) * L / n
        pts.append(p)
    return pts, ang


def inside(p, m=0.35):
    return -W / 2 + m < p[0] and -H / 2 + 0.95 < p[1]  # leaves hang ~0.7 below a tip: keep them in frame


def branch(season):
    rng = np.random.default_rng({'autumn': 1, 'summer': 2, 'spring': 3}[season])
    s = rig()
    cam = camera(W, 900, 500, tilt=PITCH)
    bpy.context.view_layer.update()
    root = bpy.data.objects.new('root', None)  # local x = screen right, y = screen up, z = toward the camera
    s.collection.objects.link(root)
    root.matrix_world = cam.matrix_world @ Matrix.Translation((0, 0, -6))
    bm = bark(season)
    kind = 'summer' if season != 'autumn' else 'autumn'
    lm, sm = leaf_mat(kind), stem_mat(kind)
    objs, tips, nodes = [], [], []

    def limb(pts, r0, r1):
        o = curve('limb', [[tuple(q) for q in pts]], 1.0, bm, res=4, radii=lambda t: r0 + (r1 - r0) * t)
        o.parent = root
        objs.append(o)

    main, _ = path((5.6, 3.2, 0), math.radians(205), 8.2, rng, n=24, bend=0.06)
    main = [q for q in main if q[0] > -3.3] or main
    limb(main, 0.2, 0.05)
    for i in range(3, len(main) - 1, 3):  # side limbs, alternating sides
        side = 1 if (i // 3) % 2 else -1
        a0 = math.atan2(*(main[i + 1] - main[i])[1::-1]) + side * rng.uniform(0.5, 0.9)
        L = rng.uniform(1.2, 2.4) * (1 - i / len(main) * 0.5)
        pts, a = path(main[i], a0, L, rng, n=10, bend=-side * 0.25, zv=rng.uniform(-0.1, 0.15))
        pts = [q for q in pts if inside(q)]
        if len(pts) < 3:
            continue
        limb(pts, 0.07 * (1 - i / len(main) * 0.5), 0.02)
        for j in range(2, len(pts) - 1, 3):  # twigs in opposite pairs (maple)
            for sd2 in (-1, 1):
                b = math.atan2(*(pts[j + 1] - pts[j])[1::-1]) + sd2 * rng.uniform(0.6, 1.0)
                tw, ta = path(pts[j], b, rng.uniform(0.3, 0.6), rng, n=5, bend=-0.4 * sd2)
                if inside(tw[-1]):
                    limb(tw, 0.018, 0.008)
                    tips.append((tw[-1], ta))
            nodes.append((pts[j], a))
        tips.append((pts[-1], a))
    tips.append((main[-1], math.radians(205)))

    def put(o, p, rot, sc=1.0):
        o.parent = root
        o.location, o.rotation_euler, o.scale = Vector(p), rot, (sc, sc, sc)
        objs.append(o)

    k = 0
    for p, a in tips:
        if season == 'spring':
            for f in range(rng.integers(3, 6)):  # blossom clusters on short stalks
                q = p + np.array([rng.uniform(-0.18, 0.18), rng.uniform(-0.2, 0.05), rng.uniform(0, 0.15)])
                flower(q, rng, root, objs)
            if rng.random() < 0.5:
                k += 1
                put(leaf('summer', 100 + k, 0.16, lm, sm), p, (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), a - math.pi / 2 + rng.uniform(-0.8, 0.8)))
            continue
        for d in (-1, 0, 1):  # a terminal leaf and an opposite pair, hanging off the tip
            if season == 'autumn' and rng.random() < 0.25:  # some already fell
                continue
            k += 1
            yaw = a - math.pi / 2 + d * rng.uniform(0.7, 1.1) + rng.uniform(-0.25, 0.25) - 0.35
            put(leaf(kind, 10 + k, rng.uniform(0.27, 0.36), lm, sm), p,
                (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), yaw))
        if season == 'summer' and rng.random() < 0.3:
            samaras(p, rng, root, objs)
    sprite(f'branch-{season}', crop=False)


def flower(p, rng, root, objs):
    """Five notched petals round a green-yellow eye with stamens; tilted a little toward or away."""
    pm = bpy.data.materials.get('leaf_petal') or leaf_mat('petal')
    eye = bpy.data.materials.get('eye') or pbr('eye', (0.35, 0.4, 0.08), (0.6, 0.5, 0.1), rough=0.6, scale=60, grime=0.3)
    stm = bpy.data.materials.get('stamen') or pbr('stamen', (0.85, 0.75, 0.6), (0.95, 0.9, 0.8), rough=0.5, grime=0)
    fl = bpy.data.objects.new('flower', None)
    fl.parent = root
    bpy.context.scene.collection.objects.link(fl)
    fl.location, fl.rotation_euler = Vector(p), (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(0, math.tau))
    sz = rng.uniform(0.11, 0.14)
    for i in range(5):
        o = leaf_mesh('petal', int(rng.integers(1000)), sz)
        o.data.materials.append(pm)
        o.parent = fl
        o.rotation_euler = (0.25, 0, i * math.tau / 5 + rng.uniform(-0.15, 0.15) - math.pi / 2)
        objs.append(o)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=sz * 0.18, segments=12, ring_count=6)
    c = bpy.context.object
    c.data.materials.append(eye)
    c.parent = fl
    st = [[(0, 0, 0), (sz * 0.35 * math.cos(t), sz * 0.35 * math.sin(t), sz * 0.25)] for t in rng.uniform(0, math.tau, 9)]
    sc = curve('stamens', st, sz * 0.025, stm, radii=lambda t: 0.6 + 1.6 * t ** 4)
    sc.parent = fl


def samaras(p, rng, root, objs):
    """A hanging pair of maple seed wings (helicopters)."""
    wm = bpy.data.materials.get('wing') or pbr('wing', (0.35, 0.36, 0.12), (0.55, 0.48, 0.2), rough=0.6, scale=30, grime=0.2)
    pr = bpy.data.objects.new('samara', None)
    pr.parent = root
    bpy.context.scene.collection.objects.link(pr)
    pr.location = Vector(p + np.array([0, -0.12, 0.05]))
    pr.rotation_euler = (0.3, rng.uniform(-0.4, 0.4), rng.uniform(-0.3, 0.3))
    for sgn in (-1, 1):
        o = leaf_mesh('petal', int(rng.integers(1000)), 0.13)
        o.data.materials.append(wm)
        o.parent = pr
        o.scale = (0.45, 1.0, 1.0)
        o.rotation_euler = (0, 0, math.pi + sgn * 0.6)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, segments=12, ring_count=6)
        sd = bpy.context.object
        sd.data.materials.append(wm)
        sd.parent = pr
        sd.location = (sgn * 0.012, 0, 0)
        objs.append(o)


if __name__ == '__main__':
    want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['autumn', 'summer', 'spring']
    for w in want:
        if w not in ('autumn', 'summer', 'spring'):
            sys.exit(f'branch.py: unknown season {w}')
        branch(w)
