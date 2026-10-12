# Garden stones stone-1..5 (low flat, tall standing, round, split pair, long) and moss-1..3 cushions
# that sit at a stone's foot. Points: base (centre of the footprint) and foot [x, y, w, h] px.
# Usage: blender -b --factory-startup -t 6 -P scenes/garden/blender/stones.py [-- stone-2 moss-1 ...]
import math, os, sys
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *

# (rocks: [(size, sink, sd, loc, rot_z)], moss, granite tint)
STONES = {
    1: ([((1.35, 1.0, 0.38), 0.12, 3, (0, 0, 0), 0.3)], 0.45, (0.0, 0.0, 0.0)),
    2: ([((0.7, 0.55, 1.5), 0.25, 8, (0, 0, 0), -0.4)], 0.2, (0.02, 0.01, -0.01)),
    3: ([((0.95, 0.9, 0.78), 0.3, 5, (0, 0, 0), 0.0)], 0.6, (-0.01, 0.0, 0.01)),
    4: ([((0.78, 0.7, 0.68), 0.2, 11, (-0.62, 0.05, 0), 0.2), ((0.7, 0.66, 0.6), 0.2, 12, (0.6, -0.08, 0), -0.5)], 0.35,
        (0.015, 0.008, 0.0)),
    5: ([((1.8, 0.55, 0.48), 0.12, 14, (0, 0, 0), 0.12)], 0.3, (-0.01, -0.005, 0.005)),
}


def granite(name, moss, tint):
    """Weathered grey granite: speckled grains, pale lichen rosettes, moss on top faces."""
    c1, c2 = (np.array((0.13, 0.125, 0.12)) + tint), (np.array((0.36, 0.34, 0.31)) + tint)
    m = pbr(name, tuple(c1), tuple(c2), rough=0.85, scale=1.3, bump=0.5, vor=0.2, moss=moss, grime=0.7, strata=0.12)
    nt, bs = m.node_tree, principled(m)
    co = (N(m, 'TexCoord'), 'Object')
    base = bs.inputs['Base Color'].links[0].from_socket
    vo = N(m, 'TexVoronoi', Vector=co, Scale=55.0, Randomness=1.0)  # feldspar / mica / quartz speckle
    sp = ramp(m, (vo, 'Color'), [(0.0, (0.55, 0.55, 0.55)), (0.15, (1, 1, 1)), (0.85, (1, 1, 1)), (0.9, (1.5, 1.45, 1.38))])
    sp.color_ramp.interpolation = 'CONSTANT'
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, B=(sp, 'Color'))
    nt.links.new(base, sock(c.inputs, 'A'))
    lv = N(m, 'TexVoronoi', Vector=co, Scale=3.5)  # lichen: a few pale grey-green rosettes with fuzzy rims
    ln = N(m, 'TexNoise', Vector=co, Scale=30.0, Detail=4.0)
    pick = M(m, 'GREATER_THAN', (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(lv, 'Color')), 'Value'), 0.72)
    rim = N(m, 'MapRange', Value=M(m, 'ADD', (lv, 'Distance'), M(m, 'MULTIPLY', (ln, 'Fac'), 0.12)),
            **{'From Min': 0.22, 'From Max': 0.34, 'To Min': 1.0, 'To Max': 0.0})
    lich = M(m, 'MULTIPLY', (rim, 'Result'), pick)
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', lich, 0.55), A=(c, 'Result'), B=(0.42, 0.44, 0.35, 1))
    nt.links.new(sock(c.outputs, 'Result'), bs.inputs['Base Color'])
    return m


def stone_prop(k):
    rocks, moss, tint = STONES[k]
    mat = granite(f'granite{k}', moss, tint)
    objs = []
    for size, sink, sd, loc, rz in rocks:
        o = rock(size, sink=sink, sd=sd, facets=0.02, loc=loc)
        o.rotation_euler.z = rz
        o.data.materials.append(mat)
        objs.append(o)
    return objs


def footprint(objs, z=0.06):
    """World x/y bounds of the verts within z of the ground: where the stone meets the sand."""
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    low = [p for p in pts if abs(p.z) < z] or pts  # the ring where it meets the sand, not the buried part
    return min(p.x for p in low), max(p.x for p in low), min(p.y for p in low), max(p.y for p in low)


def stones(k):
    rig()
    seed(k)
    objs = stone_prop(k)
    ground(14, soft=2.5, power=1000)
    fp = footprint(objs)
    place(objs, margin=0.25)
    ent = sprite(f'stone-{k}', {'base': ((fp[0] + fp[1]) / 2, (fp[2] + fp[3]) / 2, 0)})
    foot(f'stone-{k}', ent, *fp)


def moss_mat():
    """Cushion moss: olive to fresh green tufts, brown dry bits, fine bump; alpha fringe from noise."""
    m = new_mat('moss')
    co = (N(m, 'TexCoord'), 'Object')
    uv = N(m, 'SeparateXYZ', Vector=(N(m, 'UVMap', _uv_map='UVMap'), 'UV'))
    fine = N(m, 'TexVoronoi', Vector=co, Scale=90.0)
    nz = N(m, 'TexNoise', Vector=co, Scale=7.0, Detail=8.0)
    col = ramp(m, (nz, 'Fac'), [(0.35, (0.05, 0.08, 0.015)), (0.55, (0.12, 0.2, 0.03)), (0.75, (0.22, 0.3, 0.05))])
    dry = N(m, 'MapRange', Value=(N(m, 'TexNoise', Vector=co, Scale=3.0, Detail=4.0), 'Fac'), **{'From Min': 0.6, 'From Max': 0.7})
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (dry, 'Result'), 0.7), A=(col, 'Color'), B=(0.2, 0.14, 0.05, 1))
    tip = N(m, 'MapRange', Value=(fine, 'Distance'), **{'From Max': 0.4, 'To Min': 1.0, 'To Max': 0.0})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=0.6, A=(c, 'Result'), B=(tip, 'Result'))
    # fringe: radial falloff (uv.x 0 centre .. 1 rim) broken up by noise so the edge is tufty
    edge = M(m, 'ADD', (uv, 'X'), M(m, 'MULTIPLY', M(m, 'SUBTRACT', (N(m, 'TexNoise', Vector=co, Scale=14.0, Detail=6.0), 'Fac'), 0.5), 0.55))
    a = N(m, 'MapRange', Value=edge, **{'From Min': 0.82, 'From Max': 0.88, 'To Min': 1.0, 'To Max': 0.0})
    bump = N(m, 'Bump', Strength=0.9, Distance=0.03, Height=M(m, 'ADD', (tip, 'Result'), (nz, 'Fac')))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.9, 'Normal': bump, 'Subsurface Weight': 0.1})
    mx = N(m, 'MixShader', Fac=(a, 'Result'))
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m


def moss(k):
    rig()
    rng = np.random.default_rng(20 + k)
    nr, na = 14, 64
    lobes = [(rng.uniform(0, math.tau), rng.uniform(0.04, 0.13), rng.integers(2, 6)) for _ in range(3)]
    verts, uv, faces = [(0, 0, 0.09)], [(0, 0)], []
    for i in range(1, nr + 1):
        r = i / nr
        for j in range(na):
            a = j / na * math.tau
            s = 1 + sum(h * math.sin(n * a + ph) for ph, h, n in lobes)  # lumpy outline
            x, y = math.cos(a) * r * 0.5 * s, math.sin(a) * r * 0.36 * s
            verts.append((x, y, 0.09 * (1 - r ** 2.2)))
            uv.append((r, 0))
    for j in range(na):
        faces.append((0, 1 + j, 1 + (j + 1) % na))
    for i in range(nr - 1):
        b0, b1 = 1 + i * na, 1 + (i + 1) * na
        faces += [(b0 + j, b1 + j, b1 + (j + 1) % na, b0 + (j + 1) % na) for j in range(na)]
    off = k * 3.1  # verts shifted, object moved back: each patch gets its own texture noise
    o = mesh('moss', [(x + off, y, z) for x, y, z in verts], faces, moss_mat(), uv=uv)
    o.location.x = -off
    t = bpy.data.textures.new('tuft', 'CLOUDS')
    t.noise_scale = 0.05
    mod(o, 'SUBSURF', levels=2, render_levels=2)
    mod(o, 'DISPLACE', texture=t, strength=0.03, texture_coords='LOCAL')
    ground(6, soft=1.5, power=600)
    place([o], margin=0.08)
    sprite(f'moss-{k}', {'base': (0, 0, 0)})


JOBS = {f'stone-{k}': (stones, k) for k in STONES} | {f'moss-{k}': (moss, k) for k in (1, 2, 3)}

if __name__ == '__main__':
    want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(JOBS)
    bad = [w for w in want if w not in JOBS]
    if bad:
        sys.exit(f'stones.py: unknown {bad}; choose from {list(JOBS)}')
    for w in want:
        fn, k = JOBS[w]
        fn(k)
