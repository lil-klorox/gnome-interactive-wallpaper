# Garden borders: edge-wood (two weathered cedar planks with rusty nails) and edge-bamboo (two lashed
# culms with black palm-fibre rope), each a 512x48 strip that tiles horizontally. The geometry and the
# texture repeat every L units (copies one period either side), so the strip has no seam.
# Usage: blender -b --factory-startup -t 6 -P scenes/garden/blender/edges.py [-- wood bamboo]
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *

L = 5.12  # one tile = 512 px


def strip_rig():
    s = rig()
    camera(L, 512, 48, tilt=PITCH)
    bpy.ops.mesh.primitive_plane_add(size=3 * L)  # uniform shadow catcher (ground()'s fade would not tile)
    p = bpy.context.object
    p.is_shadow_catcher = True
    m = new_mat('catch')
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfDiffuse'))
    p.data.materials.append(m)
    return s


def box(x0, x1, y0, y1, h, rz=0.0, sd=0):
    """Plank with worn rounded edges; verts kept in world place so its texture differs per plank."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, h / 2 - 0.02))
    o = bpy.context.object
    o.scale = (x1 - x0, y1 - y0, h)
    o.rotation_euler.z = rz
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mod(o, 'BEVEL', width=0.03, segments=3)
    mod(o, 'SUBSURF', levels=3, render_levels=3, subdivision_type='SIMPLE')
    t = bpy.data.textures.new(f'wear{sd}', 'CLOUDS')
    t.noise_scale, t.noise_depth = 0.12, 4
    mod(o, 'DISPLACE', texture=t, strength=0.012, texture_coords='GLOBAL')
    apply_all(o)
    return o


def cedar():
    """Weathered cedar: silver-grey sun-bleached top with brown left in the grain, dark checks."""
    m = pbr('cedar', (0.2, 0.16, 0.12), (0.42, 0.4, 0.36), rough=0.85, scale=4.0, bump=0.5, grime=0.7, cracks=0.0)
    nt, bs = m.node_tree, principled(m)
    co = (N(m, 'TexCoord'), 'Object')
    gm = N(m, 'Mapping', Vector=co)
    gm.inputs['Scale'].default_value = (0.12, 1.0, 1.0)  # grain runs long along the plank
    wv = N(m, 'TexWave', Vector=gm, _bands_direction='Y', Scale=9.0, Distortion=3.0, Detail=8.0, **{'Detail Scale': 3.0})
    grain = ramp(m, (wv, 'Fac'), [(0.2, (0.55, 0.45, 0.35)), (0.6, (1.0, 1.0, 1.0)), (0.9, (1.1, 1.08, 1.05))])
    base = bs.inputs['Base Color'].links[0].from_socket
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, B=(grain, 'Color'))
    nt.links.new(base, sock(c.inputs, 'A'))
    ck = N(m, 'TexNoise', Vector=co, Scale=3.0, Detail=2.0)  # long thin drying checks along the grain
    chk = M(m, 'MULTIPLY', M(m, 'GREATER_THAN', (N(m, 'TexWave', Vector=co, _bands_direction='Y', Scale=3.0, Distortion=2.0), 'Fac'), 0.97),
            M(m, 'GREATER_THAN', (ck, 'Fac'), 0.55))
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', chk, 0.85), A=(c, 'Result'), B=(0.03, 0.025, 0.02, 1))
    nt.links.new(sock(c.outputs, 'Result'), bs.inputs['Base Color'])
    b = N(m, 'Bump', Strength=0.6, Distance=0.02, Height=M(m, 'SUBTRACT', (wv, 'Fac'), chk),
          Normal=bs.inputs['Normal'].links[0].from_node)
    nt.links.new(b.outputs[0], bs.inputs['Normal'])
    return m


def wood():
    strip_rig()
    rng = np.random.default_rng(2)
    cm = cedar()
    rust = pbr('rust', (0.12, 0.05, 0.02), (0.3, 0.13, 0.05), rough=0.9, scale=30, bump=0.6, grime=0.3)
    objs = []
    for k, (x0, x1) in enumerate(((-L / 2 + 0.012, -0.012), (0.012, L / 2 - 0.012))):
        p = box(x0, x1, -0.2, 0.2, 0.14 + rng.uniform(-0.015, 0.015), rng.uniform(-0.004, 0.004), k)
        p.data.materials.append(cm)
        objs.append(p)
        for x in (x0 + 0.12, x1 - 0.12):  # nail pairs near each end, one a bit proud
            for y in (-0.1, 0.1):
                bpy.ops.mesh.primitive_cylinder_add(radius=0.022, depth=0.02, location=(x + rng.uniform(-0.01, 0.01), y, 0.125 + rng.uniform(0, 0.012)))
                n = bpy.context.object
                bpy.ops.object.transform_apply(location=True)
                n.data.materials.append(rust)
                objs.append(n)
    for o in objs:
        wrap(o, L)
    render('edge-wood.png')
    manifest('edge-wood', {'w': 512, 'h': 48})


def bamboo_mat():
    """Dry bamboo: straw to olive, fine streaks along the culm, waxy, weathered grey blotches."""
    m = new_mat('bamboo')
    co = N(m, 'TexCoord')
    st = N(m, 'Mapping', Vector=(co, 'Object'))
    st.inputs['Scale'].default_value = (0.5, 25.0, 25.0)  # stretched along x: streaks
    nz = N(m, 'TexNoise', Vector=st, Scale=4.0, Detail=6.0)
    big = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=1.6, Detail=3.0)
    col = ramp(m, (big, 'Fac'), [(0.35, (0.33, 0.27, 0.11)), (0.6, (0.5, 0.42, 0.2)), (0.75, (0.42, 0.42, 0.22))])
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.45, A=(col, 'Color'), B=(nz, 'Color'))
    sp = N(m, 'MapRange', Value=(N(m, 'TexNoise', Vector=(co, 'Object'), Scale=6.0, Detail=5.0), 'Fac'), **{'From Min': 0.62, 'From Max': 0.72})
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (sp, 'Result'), 0.6), A=(c, 'Result'), B=(0.25, 0.23, 0.2, 1))
    node = N(m, 'Attribute', _attribute_name='node')  # 1 at the culm nodes
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=M(m, 'MULTIPLY', (node, 'Fac'), 0.6), A=(c, 'Result'),
          B=(0.45, 0.35, 0.25, 1))
    c = ao_grime(m, (c, 'Result'), 0.15, 0.5)
    bump = N(m, 'Bump', Strength=0.2, Distance=0.01, Height=(nz, 'Fac'))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': c, 'Roughness': 0.4, 'Coat Weight': 0.15, 'Coat Roughness': 0.35, 'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    return m


def culm(y, z, r, nodes, mat):
    """Open tube along x over one period with node bulges at `nodes` (x); attribute node = 1 there."""
    nx, na = 256, 20
    verts, nd, faces = [], [], []
    for i in range(nx + 1):
        x = -L / 2 + L * i / nx
        g = max(math.exp(-((x - n) / 0.025) ** 2) for n in nodes + [n + L for n in nodes] + [n - L for n in nodes])
        for j in range(na):
            a = j / na * math.tau
            rr = r * (1 + 0.08 * g)
            verts.append((x, y + rr * math.cos(a), z + rr * math.sin(a)))
            nd.append(g)
    faces = [(i * na + j, i * na + (j + 1) % na, (i + 1) * na + (j + 1) % na, (i + 1) * na + j) for i in range(nx) for j in range(na)]
    o = mesh('culm', verts, faces, mat)
    at = o.data.attributes.new('node', 'FLOAT', 'POINT')
    at.data.foreach_set('value', nd)
    return o


def bamboo():
    strip_rig()
    rng = np.random.default_rng(5)
    bm = bamboo_mat()
    rope = pbr('rope', (0.02, 0.015, 0.012), (0.07, 0.05, 0.035), rough=0.95, scale=60, bump=0.8, grime=0.4)
    objs = []
    for y, z, r, off in ((-0.11, 0.1, 0.1, 0.0), (0.11, 0.1, 0.095, 0.3)):
        nodes = sorted(-L / 2 + (k + off + rng.uniform(-0.15, 0.15)) * L / 7 for k in range(7))
        objs.append(culm(y, z, r, nodes, bm))
    for xc in (-1.5, 1.2):  # lashings: rope wound round both culms, then a twist knot on top
        paths = []
        for strand in range(2):
            pts = []
            for i in range(80):
                t = i / 79
                a = t * 4 * math.tau + strand * math.pi
                x = xc - 0.05 + t * 0.1 + 0.012 * math.sin(a * 3)
                pts.append((x, 0.22 * math.cos(a), 0.1 + 0.13 * math.sin(a)))
            paths.append(pts)
        paths.append([(xc - 0.02, -0.05, 0.24), (xc + 0.04, -0.12, 0.25), (xc + 0.09, -0.2, 0.2)])  # loose end
        o = curve('rope', paths, 0.014, rope, res=2)
        objs.append(o)
    for o in objs:
        wrap(o, L)
    render('edge-bamboo.png')
    manifest('edge-bamboo', {'w': 512, 'h': 48})


JOBS = {'wood': wood, 'bamboo': bamboo}

if __name__ == '__main__':
    want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(JOBS)
    bad = [w for w in want if w not in JOBS]
    if bad:
        sys.exit(f'edges.py: unknown {bad}; choose from {list(JOBS)}')
    for w in want:
        JOBS[w]()
