# Falling leaves: one sheet per season, 20 frames (8 cols): 0-15 a two-axis tumble that loops, 16-19 four
# poses lying on the sand (manifest extra rest = [16..19]). Maple red (autumn), maple green (summer),
# cherry petal (spring). Also holds the leaf/petal mesh + material that branch.py hangs on its twigs.
# Usage: blender -b --factory-startup -t 6 -P scenes/garden/blender/leaves.py [-- autumn summer spring]
import math, os, sys
import bpy
import numpy as np
from mathutils import Matrix, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *

TAU = math.tau
LOBES = [(90, 1.0), (35, 0.86), (145, 0.86), (-15, 0.5), (195, 0.5)]  # maple: angle (deg), length


def outline(kind, th, rng):
    """Leaf radius at angle th (rad, 90 deg = tip). Maple: five pointed lobes, deep sinuses, toothed edge.
    Petal: an oval with a notch at the tip."""
    if kind == 'petal':
        r = 0.5 / np.sqrt((np.cos(th) / 0.7) ** 2 + np.sin(th) ** 2)
        return r * (1 - 0.22 * np.exp(-((th - math.pi / 2) / 0.18) ** 2)) * (1 + 0.03 * np.sin(th * 5 + rng.uniform(0, 6)))
    r = np.full_like(th, 0.24)
    for a, L in LOBES:
        d = np.abs(np.angle(np.exp(1j * (th - math.radians(a + rng.uniform(-5, 5))))))
        r = np.maximum(r, L * rng.uniform(0.92, 1.05) * np.clip(1 - d / 0.62, 0, 1) ** 0.85)
    return r * (1 + 0.05 * np.abs(np.sin(th * 26 + rng.uniform(0, 6))) ** 0.5)  # serrated


def leaf_mesh(kind, sd, size=0.26, curl=0.1):
    """Polar fan mesh in the xy plane (tip +y, facing +z), centre at the origin; uv = (r 0..1, angle).
    Open at the base sinus so the angle uv never wraps across a face. Veins sit raised, the blade
    between them sags a touch, the whole leaf curls a little."""
    rng = np.random.default_rng(sd)
    A, R = 96, 10
    th = np.linspace(-math.pi / 2, 1.5 * math.pi, A + 1)
    rad = outline(kind, th, rng) * size
    cv = rng.uniform(-1, 1)
    verts, uv = [(0.0, 0.0, 0.0)], [(0.0, 0.5)]
    for i in range(1, R + 1):
        f = i / R
        for t, r in zip(th, rad):
            x, y = math.cos(t) * r * f, math.sin(t) * r * f
            vd = min(abs(np.angle(np.exp(1j * (t - math.radians(a))))) for a, _ in LOBES) if kind != 'petal' else 1
            z = -0.025 * size * f * min(1, vd / 0.3) + curl * size * f * f * (math.cos(t) * cv) ** 2
            if kind == 'petal':
                z = 0.25 * x * x / size  # cupped
            verts.append((x, y, z))
            uv.append((f, (t + math.pi / 2) / TAU))
    faces = [(0, 1 + j, 2 + j) for j in range(A)]
    for i in range(R - 1):
        b0, b1 = 1 + i * (A + 1), 1 + (i + 1) * (A + 1)
        faces += [(b0 + j, b1 + j, b1 + j + 1, b0 + j + 1) for j in range(A)]
    o = mesh(f'{kind}{sd}', verts, faces, uv=uv)
    if kind == 'petal':  # petal attaches at its narrow base: move that point to the origin
        o.data.transform(Matrix.Translation((0, size * 0.5, 0)))
    return o


COLS = {  # base, tip, vein, edge-scorch
    'autumn': ((0.4, 0.012, 0.01), (0.7, 0.04, 0.015), (0.72, 0.26, 0.04), (0.16, 0.04, 0.015)),
    'summer': ((0.05, 0.14, 0.02), (0.11, 0.26, 0.04), (0.28, 0.38, 0.1), (0.3, 0.26, 0.06)),
    'petal': ((0.95, 0.42, 0.58), (1.0, 0.88, 0.92), (0.9, 0.55, 0.62), (0.75, 0.5, 0.42)),
}


def leaf_mat(kind):
    """Leaf blade: base->tip colour, raised main veins + faint net, per-leaf hue shift (Object Info
    random), backlight through it, browned/bitten edges and a few holes on some leaves. Autumn adds tar
    spots (black blotches with a yellow halo, the classic maple fungus)."""
    base, tip, vein, scorch = COLS[kind]
    m = new_mat(f'leaf_{kind}')
    sp = N(m, 'SeparateXYZ', Vector=N(m, 'UVMap', _uv_map='UVMap'))
    co = (N(m, 'TexCoord'), 'Object')
    rnd = (N(m, 'ObjectInfo'), 'Random')
    col = (ramp(m, (sp, 'X'), [(0.0, base), (1.0, tip)]), 'Color')
    nz = N(m, 'TexNoise', Vector=co, Scale=18.0, Detail=6.0)
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.3, A=col, B=(nz, 'Color')), 'Result')
    col = (N(m, 'HueSaturation', Hue=M(m, 'MULTIPLY_ADD', rnd, {'autumn': 0.05, 'summer': 0.06, 'petal': 0.03}[kind],
                                                 {'autumn': 0.455, 'summer': 0.47, 'petal': 0.485}[kind]),
             Value=M(m, 'MULTIPLY_ADD', M(m, 'FRACT', M(m, 'MULTIPLY', rnd, 7.3)), 0.2, 0.9), Color=col), 'Color')
    th = M(m, 'MULTIPLY_ADD', (sp, 'Y'), TAU, -math.pi / 2)
    vn = None
    for a, _ in (LOBES if kind != 'petal' else [(90, 1)]):
        d = M(m, 'MULTIPLY', M(m, 'ABSOLUTE', M(m, 'WRAP', M(m, 'SUBTRACT', th, math.radians(a)), math.pi, -math.pi)), (sp, 'X'))
        v = N(m, 'MapRange', Value=d, **{'From Max': 0.05 if kind != 'petal' else 0.03, 'To Min': 1.0, 'To Max': 0.0})
        vn = (v, 'Result') if vn is None else M(m, 'MAXIMUM', vn, (v, 'Result'))
    net = N(m, 'TexVoronoi', Vector=co, Scale=60.0, _feature='DISTANCE_TO_EDGE')
    netm = N(m, 'MapRange', Value=(net, 'Distance'), **{'From Max': 0.06, 'To Min': 0.45, 'To Max': 0.0})
    vn = M(m, 'MAXIMUM', vn, (netm, 'Result'))
    col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', vn, 0.55), A=col, B=(*vein, 1)), 'Result')
    gate = M(m, 'GREATER_THAN', M(m, 'FRACT', M(m, 'MULTIPLY', rnd, 13.7)), 0.45)  # about half the leaves are worn
    en = N(m, 'TexNoise', Vector=co, Scale=7.0, Detail=5.0)
    burn = N(m, 'MapRange', Value=M(m, 'ADD', (sp, 'X'), M(m, 'MULTIPLY', (en, 'Fac'), 0.3)), **{'From Min': 0.95, 'From Max': 1.05})
    col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (burn, 'Result'), gate), A=col, B=(*scorch, 1)), 'Result')
    if kind == 'autumn':
        tv = N(m, 'TexVoronoi', Vector=co, Scale=9.0)
        pick = M(m, 'GREATER_THAN', (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(tv, 'Color')), 'Value'), 0.8)
        halo = M(m, 'MULTIPLY', M(m, 'LESS_THAN', (tv, 'Distance'), 0.16), pick)
        tar = M(m, 'MULTIPLY', M(m, 'LESS_THAN', M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.06, (tv, 'Distance')), 0.12), pick)
        col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', halo, 0.8), A=col, B=(0.75, 0.45, 0.04, 1)), 'Result')
        col = (N(m, 'Mix', _data_type='RGBA', Factor=tar, A=col, B=(0.025, 0.018, 0.012, 1)), 'Result')
    bump = N(m, 'Bump', Strength=0.3, Distance=0.005, Height=M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.2, vn))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': 0.6, 'Normal': bump, 'Sheen Weight': 0.15})
    mx = N(m, 'MixShader', Fac=0.35 if kind == 'petal' else 0.25)
    m.node_tree.links.new(bs.outputs[0], mx.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTranslucent', Color=col).outputs[0], mx.inputs[2])
    # holes (insect bites inside, nibbles at the rim), only on the worn leaves
    hv = N(m, 'TexVoronoi', Vector=co, Scale=14.0)
    hp = M(m, 'GREATER_THAN', (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(hv, 'Color')), 'Value'), 0.88)
    hole = M(m, 'MULTIPLY', M(m, 'MULTIPLY', M(m, 'LESS_THAN', (hv, 'Distance'), 0.12), hp), M(m, 'LESS_THAN', (sp, 'X'), 0.8))
    bite = M(m, 'GREATER_THAN', M(m, 'ADD', (sp, 'X'), M(m, 'MULTIPLY', M(m, 'MAXIMUM', M(m, 'SUBTRACT', (en, 'Fac'), 0.55), 0.0), 2.0)), 1.0)
    cut = M(m, 'MULTIPLY', M(m, 'MAXIMUM', hole, bite), gate) if kind != 'petal' else M(m, 'MULTIPLY', bite, 0.0)
    out = N(m, 'MixShader', Fac=cut)
    m.node_tree.links.new(mx.outputs[0], out.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], out.inputs[2])
    N(m, 'OutputMaterial', Surface=out)
    return m


def stem_mat(kind):
    c = {'autumn': (0.5, 0.12, 0.04), 'summer': (0.35, 0.3, 0.08), 'petal': (0.5, 0.35, 0.15)}[kind]
    return pbr(f'stem_{kind}', c, tuple(x * 1.3 for x in c), rough=0.6, scale=40, bump=0.1, grime=0.2)


def leaf(kind, sd, size=0.26, mat=None, smat=None):
    """Leaf object (+ petiole joined in): petiole base at the origin pointing -y from the blade."""
    o = leaf_mesh(kind, sd, size)
    o.data.materials.append(mat or leaf_mat(kind))
    if kind == 'petal':
        return o
    o.location.y = size * 0.9  # blade sits beyond its stalk
    st = curve('petiole', [[(0, 0, 0), (0.01, size * 0.45, 0.01), (0, size * 0.92, 0)]], size * 0.025,
               smat or stem_mat(kind), radii=lambda t: 1 - 0.3 * t)
    o.data.transform(Matrix.Translation(o.location))
    o.location = (0, 0, 0)
    st.parent = o
    return o


def leaf_sheet(season):
    kind = {'autumn': 'autumn', 'summer': 'summer', 'spring': 'petal'}[season]
    s = rig()
    camera(0.8, 160, 160, tilt=PITCH)  # 2x: 200 px per unit, halved by hidpi()
    o = leaf(kind, 3 if kind != 'petal' else 5, 0.26 if kind != 'petal' else 0.3)
    piv = bpy.data.objects.new('piv', None)
    s.collection.objects.link(piv)
    bpy.context.view_layer.update()
    c = sum((o.matrix_world @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)
    for q in [o] + list(o.children):  # spin about the blade centre, not the stalk end
        q.parent = piv if q is o else q.parent
    o.location = -c
    catcher = ground(3, z=-0.012, soft=1.0, power=500)
    rest = [(0.3, 0.02), (2.1, -0.03), (3.7, 0.04), (5.2, 0.0)]  # yaw, roll for the four rest poses

    def pose(k):
        def f():
            catcher.hide_render = k < 16
            if k < 16:  # two full turns about two axes: loops seamlessly
                a = TAU * k / 16
                piv.rotation_euler = (a + 0.4, 0.6 * math.sin(a), a)
                piv.location = (0, 0, 0.2)
            else:
                yaw, roll = rest[k - 16]
                piv.rotation_euler = (roll, roll * 0.5, yaw)
                piv.location = (0, 0, 0.0)
        return f
    sheet(f'leaf-{season}', [pose(k) for k in range(20)], 8, {'anchor': (0, 0, 0)}, pad=3,
          extra={'rest': [16, 17, 18, 19]})
    hidpi(f'leaf-{season}')


if __name__ == '__main__':
    want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['autumn', 'summer', 'spring']
    for w in want:
        if w not in ('autumn', 'summer', 'spring'):
            sys.exit(f'leaves.py: unknown season {w}')
        leaf_sheet(w)
