# Castle: three round towers and a curtain wall built block by block, arched windows and door,
# a shingled cone roof, flags, moss and grime. Renders assets/castle.png.
import math, os, random, sys
import bmesh
import bpy
from mathutils import Vector
sys.path.insert(0, os.path.dirname(__file__))
from common import *

scenery()
seed(11)
R = random.random
TAU = math.tau
SINK = 0.15     # everything starts this far under the sand


# ---- materials ----

def blockmat(name, c1, c2, moss=0.5, low=0.0, scale=2.5, rough=0.85, bump=0.8, wear=0.45, tide=0.0, jit=1.0):
    """Stone blocks: per-block tone ('blk' attribute), drips, worn edges, grime, moss, pitted bump."""
    m = new_mat(name)
    co = N(m, 'TexCoord')
    at = N(m, 'Attribute', _attribute_name='blk')
    atx = N(m, 'SeparateXYZ', Vector=(at, 'Vector'))
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=scale, Detail=8.0, Roughness=0.6)
    fine = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=scale * 12, Detail=4.0)
    tone = M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.45, M(m, 'MULTIPLY', (atx, 'X'), 0.75))
    col = (ramp(m, tone, [(0.15, c1), (0.5, c2), (0.95, (c2[0] * 0.75, c2[1] * 0.68, c2[2] * 0.6))]), 'Color')
    # green drips running down from ledges
    mp = N(m, 'Mapping', Vector=(co, 'Object'), Scale=(9.0, 9.0, 0.7))
    drip = N(m, 'TexNoise', Vector=mp, Scale=2.0, Detail=3.0)
    dm = N(m, 'MapRange', Value=(drip, 'Fac'), **{'From Min': 0.62, 'From Max': 0.78, 'To Max': 0.5})
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=(dm, 'Result'), A=col,
             B=(0.45, 0.42, 0.3, 1)), 'Result')
    # worn, lighter edges where the stone is convex; fine speckle all over
    pt = N(m, 'MapRange', Value=(N(m, 'NewGeometry'), 'Pointiness'), **{'From Min': 0.52, 'From Max': 0.62, 'To Max': wear})
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='SCREEN', Factor=(pt, 'Result'), A=col, B=(0.5, 0.47, 0.42, 1)), 'Result')
    sp = N(m, 'MapRange', Value=(fine, 'Fac'), **{'From Min': 0.35, 'From Max': 0.65, 'To Min': 0.7, 'To Max': 1.15})
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=col, B=(sp, 'Result')), 'Result')
    pos = N(m, 'SeparateXYZ', Vector=(N(m, 'NewGeometry'), 'Position'))
    if low:  # algae + silt creeping up from the sand
        lz = N(m, 'MapRange', Value=M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.5, (pos, 'Z')),
               **{'From Min': 0.1, 'From Max': 0.7, 'To Min': low, 'To Max': 0.0})
        col = (N(m, 'Mix', _data_type='RGBA', Factor=(lz, 'Result'), A=col, B=(0.12, 0.15, 0.05, 1)), 'Result')
    # per-block hue/saturation jitter, and about one block in seven darker (a replaced or stained stone)
    wn = N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(at, 'Vector'))
    wc = N(m, 'SeparateXYZ', Vector=(wn, 'Color'))
    val = M(m, 'SUBTRACT', M(m, 'MULTIPLY_ADD', (wc, 'Z'), -0.3, 1.1), M(m, 'MULTIPLY', M(m, 'GREATER_THAN', (wn, 'Value'), 0.85), 0.42))
    col = (N(m, 'HueSaturation', Hue=M(m, 'MULTIPLY_ADD', (wc, 'X'), 0.09 * jit, 0.5 - 0.045 * jit),
             Saturation=M(m, 'MULTIPLY_ADD', (wc, 'Y'), 0.9 * jit, 1 - 0.4 * jit),
             Value=val, Color=col), 'Color')
    if tide:  # old waterline: olive stain below a ragged line, darkest right at it
        tn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=3.0, Detail=6.0)
        edge = M(m, 'MULTIPLY_ADD', M(m, 'SUBTRACT', (tn, 'Fac'), 0.5), 0.35, (pos, 'Z'))
        st = N(m, 'MapRange', Value=edge, **{'From Min': tide, 'From Max': tide - 0.15, 'To Max': 0.6})
        ln = N(m, 'MapRange', Value=M(m, 'ABSOLUTE', M(m, 'SUBTRACT', edge, tide - 0.02)), **{'From Max': 0.035, 'To Min': 0.4, 'To Max': 0.0})
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=M(m, 'ADD', (st, 'Result'), (ln, 'Result')), A=col,
                 B=(0.25, 0.3, 0.12, 1)), 'Result')
    col = ao_grime(m, col, 0.12, 0.3)
    pit = N(m, 'TexVoronoi', Vector=(co, 'Object'), Scale=scale * 6, _feature='SMOOTH_F1')
    height = M(m, 'MULTIPLY_ADD', (fine, 'Fac'), 0.5, M(m, 'MULTIPLY_ADD', (pit, 'Distance'), 0.5, (nz, 'Fac')))
    r = rough
    if moss:
        up = N(m, 'SeparateXYZ', Vector=(N(m, 'NewGeometry'), 'Normal'))
        mn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=scale * 2.2, Detail=10.0)
        mask = M(m, 'MULTIPLY', M(m, 'ADD', (up, 'Z'), M(m, 'MULTIPLY', (atx, 'Y'), 0.35)), (mn, 'Fac'))
        mk = N(m, 'MapRange', Value=mask, **{'From Min': 0.55 - moss * 0.3, 'From Max': 0.62 - moss * 0.3})
        mc = ramp(m, (fine, 'Fac'), [(0.3, (0.035, 0.07, 0.012)), (0.7, (0.13, 0.2, 0.035))])
        col = (N(m, 'Mix', _data_type='RGBA', Factor=(mk, 'Result'), A=col, B=(mc, 'Color')), 'Result')
        height = M(m, 'MULTIPLY_ADD', (mk, 'Result'), 0.6, height)
        r = (N(m, 'MapRange', Value=(mk, 'Result'), **{'To Min': rough, 'To Max': 0.97}), 'Result')
    b = N(m, 'Bump', Strength=bump, Distance=0.03, Height=height)
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': r, 'Normal': b}))
    return m


def plain(name, c, rough=0.9, metal=0.0, emit=None):
    m = new_mat(name)
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (*c, 1), 'Roughness': rough, 'Metallic': metal})
    if emit:
        bs.inputs['Emission Color'].default_value = (*emit[0], 1)
        bs.inputs['Emission Strength'].default_value = emit[1]
    N(m, 'OutputMaterial', Surface=bs)
    return m


STONE = blockmat('stone', (0.2, 0.16, 0.12), (0.66, 0.55, 0.42), moss=0.55, low=0.6, tide=1.2)
ROOF = blockmat('roof', (0.16, 0.04, 0.025), (0.36, 0.12, 0.06), moss=0.35, scale=4, rough=0.7, bump=0.25, wear=0.1, jit=0.35)
MORTAR = pbr('mortar', (0.07, 0.06, 0.045), (0.14, 0.12, 0.08), rough=0.95, scale=6, grime=0.8)
VOID = plain('void', (0.005, 0.008, 0.01), rough=1.0)
GLOW = plain('glow', (0.02, 0.015, 0.01), emit=((1.0, 0.5, 0.18), 0.3))  # one lit window: somebody's home


def wood(name, c1, c2):
    m = new_mat(name)
    co = N(m, 'TexCoord')
    mp = N(m, 'Mapping', Vector=(co, 'Object'), Scale=(14.0, 14.0, 1.2))
    wv = N(m, 'TexWave', Vector=mp, _wave_type='RINGS', Scale=3.0, Distortion=8.0, Detail=6.0)
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=5.0, Detail=6.0)
    col = ramp(m, M(m, 'MULTIPLY_ADD', (wv, 'Fac'), 0.6, M(m, 'MULTIPLY', (nz, 'Fac'), 0.4)),
               [(0.2, c1), (0.8, c2)])
    c = ao_grime(m, (col, 'Color'), 0.08, 0.35)
    b = N(m, 'Bump', Strength=0.5, Distance=0.02, Height=(wv, 'Fac'))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': c, 'Roughness': 0.8, 'Normal': b}))
    return m


WOOD = wood('door', (0.12, 0.06, 0.025), (0.32, 0.17, 0.07))
IRON = pbr('iron', (0.04, 0.035, 0.03), (0.16, 0.07, 0.03), rough=0.6, metal=0.8, scale=8, bump=0.4, grime=0.6)
BRASS = pbr('brass', (0.25, 0.16, 0.05), (0.12, 0.13, 0.06), rough=0.4, metal=1.0, scale=6, bump=0.2)


def cloth(name, c1, c2):
    m = new_mat(name)
    co = N(m, 'TexCoord')
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=7.0, Detail=6.0)
    col = ramp(m, (nz, 'Fac'), [(0.3, c1), (0.75, c2)])
    weave = N(m, 'TexWave', Vector=(co, 'Object'), Scale=180.0, _bands_direction='X')
    # algae creeping in from the edges
    uv = N(m, 'SeparateXYZ', Vector=(co, 'UV'))
    edge = M(m, 'MAXIMUM', (uv, 'X'), M(m, 'ABSOLUTE', M(m, 'MULTIPLY', M(m, 'SUBTRACT', (uv, 'Y'), 0.5), 2.0)))
    ed = N(m, 'MapRange', Value=M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.4, edge), **{'From Min': 0.95, 'From Max': 1.25, 'To Max': 0.8})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(ed, 'Result'), A=(col, 'Color'), B=(0.05, 0.07, 0.02, 1))
    b = N(m, 'Bump', Strength=0.15, Distance=0.01, Height=(weave, 'Fac'))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.85, 'Normal': b,
                                   'Sheen Weight': 0.6, 'Subsurface Weight': 0.15})
    N(m, 'OutputMaterial', Surface=bs)
    return m


# ---- block builder ----

class Batch:
    """Collects hexahedral blocks (bent along u) into one mesh with a per-block random 'blk' attribute."""

    def __init__(self):
        self.v, self.f, self.c = [], [], []

    def block(self, fn, nu=1, jit=0.012, chip=0.05):
        b = len(self.v)
        tone = (R(), R(), 0)
        pts = {}
        for i in range(nu + 1):
            for v in (0, 1):
                for w in (0, 1):
                    p = Vector(fn(i / nu, v, w)) + Vector((R() - .5, R() - .5, R() - .5)) * jit * 2
                    pts[i, v, w] = len(self.v)
                    self.v.append(p)
                    self.c.append(tone)
        # knock one corner in for a chipped edge
        if chip and R() < 0.7:
            k = pts[random.choice((0, nu)), random.choice((0, 1)), 0]
            ctr = sum((self.v[j] for j in pts.values()), Vector()) / len(pts)
            self.v[k] = self.v[k].lerp(ctr, chip * (0.5 + R()))
        q = pts
        for i in range(nu):
            self.f += [(q[i, 0, 0], q[i + 1, 0, 0], q[i + 1, 1, 0], q[i, 1, 0]),
                       (q[i, 0, 1], q[i, 1, 1], q[i + 1, 1, 1], q[i + 1, 0, 1]),
                       (q[i, 0, 0], q[i, 0, 1], q[i + 1, 0, 1], q[i + 1, 0, 0]),
                       (q[i, 1, 0], q[i + 1, 1, 0], q[i + 1, 1, 1], q[i, 1, 1])]
        self.f += [(q[0, 0, 0], q[0, 1, 0], q[0, 1, 1], q[0, 0, 1]),
                   (q[nu, 0, 0], q[nu, 0, 1], q[nu, 1, 1], q[nu, 1, 0])]

    def build(self, name, mat, bevel=0.022):
        o = mesh(name, [tuple(p) for p in self.v], self.f, mat, smooth=False)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(o.data)
        bm.free()
        a = o.data.color_attributes.new('blk', 'FLOAT_COLOR', 'POINT')
        for i, c in enumerate(self.c):
            a.data[i].color = (*c, 1)
        mod(o, 'BEVEL', width=bevel, segments=2, limit_method='ANGLE', angle_limit=math.radians(30))
        return o


def arch_hole(x, z, w, h):
    """True if (x, z) is inside an arched opening of width w, total height h, bottom at 0."""
    zs = h - w / 2
    return z > -0.1 and (abs(x) < w / 2 and z < zs or (x * x + (z - zs) ** 2) < (w / 2) ** 2)


def ring_rows(B, cx, cy, r, z0, z1, depth=0.22, rowh=0.27, bw=0.42, holes=(), gap=0.012):
    """Courses of curved blocks around a tower. holes: (theta, zb, w, h) arched openings."""
    z, row = z0, 0
    while z < z1 - 0.05:
        h = min(rowh * (0.85 + 0.3 * R()), z1 - z)
        th = R() * 0.3 + row * 0.5 * bw / r
        end = th + TAU
        while th < end - 1e-3:
            dth = min(bw * (0.75 + 0.5 * R()) / r, end - th)
            tc, zc = th + dth / 2, z + h / 2
            skip = any(arch_hole(((tc - t + math.pi) % TAU - math.pi) * r, zc - zb, w + 0.1, hh + 0.08)
                       for t, zb, w, hh in holes)
            if not skip:
                ro = r + (R() - 0.5) * 0.03
                a0, a1, zz0, zz1 = th + gap / r, th + dth - gap / r, z + gap, z + h - gap

                def fn(u, v, w, a0=a0, a1=a1, zz0=zz0, zz1=zz1, ro=ro):
                    a = a0 + (a1 - a0) * u
                    rr = ro - w * depth
                    return (cx + rr * math.cos(a), cy + rr * math.sin(a), zz0 + (zz1 - zz0) * v)
                B.block(fn, nu=3)
            th += dth
        z += h
        row += 1
    return z


def wall_rows(B, x0, x1, y, z0, z1, thick=0.45, rowh=0.25, bw=0.5, holes=(), gap=0.012):
    """Straight courses; front face at y, holes (xc, zb, w, h)."""
    z, row = z0, 0
    while z < z1 - 0.05:
        h = min(rowh * (0.85 + 0.3 * R()), z1 - z)
        x = x0 - (row % 2) * bw * 0.5
        while x < x1 - 1e-3:
            dx = bw * (0.7 + 0.6 * R())
            a, b = max(x, x0), min(x + dx, x1)
            if b - a > 0.08 and not any(arch_hole((a + b) / 2 - xc, z + h / 2 - zb, w + 0.1, hh + 0.08)
                                        for xc, zb, w, hh in holes):
                yy = y + (R() - 0.5) * 0.025

                def fn(u, v, w, a=a + gap, b=b - gap, zz0=z + gap, zz1=z + h - gap, yy=yy):
                    return (a + (b - a) * u, yy + w * thick, zz0 + (zz1 - zz0) * v)
                B.block(fn, nu=1)
            x += dx
        z += h
        row += 1


def merlons(B, cx, cy, r, z, n, h=0.32, depth=0.2, skip=()):
    """Crenellated parapet ring: alternating tall merlons and low crenels."""
    for k in range(n):
        a0, a1 = TAU * k / n, TAU * (k + 1) / n
        tall = k % 2 == 0
        if tall and k in skip:  # a broken merlon
            tall = False
        hh = (h if tall else h * 0.3) * (0.9 + 0.2 * R())

        def fn(u, v, w, a0=a0 + 0.01, a1=a1 - 0.01, hh=hh):
            a = a0 + (a1 - a0) * u
            rr = r - w * depth
            return (cx + rr * math.cos(a), cy + rr * math.sin(a), z + 0.01 + hh * v)
        B.block(fn, nu=2, chip=0.12)


def corbels(B, cx, cy, r, z, n):
    for k in range(n):
        a = TAU * k / n

        def fn(u, v, w, a=a):
            aa = a + (u - 0.5) * 0.09 / r * 1.4
            rr = r - 0.05 + (1 - w) * 0.17 * (0.5 + 0.5 * v)
            return (cx + rr * math.cos(aa), cy + rr * math.sin(aa), z - 0.22 + 0.22 * v)
        B.block(fn, nu=1, jit=0.006, chip=0)


def ring_band(B, cx, cy, r, z, h, n, depth=0.18):
    """A projecting band of stones (parapet base) all the way round."""
    for k in range(n):
        a0, a1 = TAU * k / n, TAU * (k + 1) / n

        def fn(u, v, w, a0=a0 + 0.008, a1=a1 - 0.008):
            a = a0 + (a1 - a0) * u
            rr = r - w * depth
            return (cx + rr * math.cos(a), cy + rr * math.sin(a), z + h * v)
        B.block(fn, nu=3, jit=0.008)


def arch_stones(B, cx, cy, r, theta, zb, w, h, n=7, d=0.14):
    """Voussoirs round the arch top of an opening on a tower (r>0) or a wall (r=None, cx=x, cy=y)."""
    zs, rad = zb + h - w / 2, w / 2
    for k in range(n):
        p0, p1 = math.pi * k / n, math.pi * (k + 1) / n

        def fn(u, v, ww, p0=p0 + 0.02, p1=p1 - 0.02):
            p = p0 + (p1 - p0) * u
            rr = rad + 0.02 + v * d
            s, z = -rr * math.cos(p), zs + rr * math.sin(p)
            out = 0.04 - ww * 0.2
            if r is None:
                return (cx + s, cy - out, z)
            a = theta + s / r
            return (cx + (r + out) * math.cos(a), cy + (r + out) * math.sin(a), z)
        B.block(fn, nu=2, jit=0.006, chip=0.06)
    # sill below
    def fn(u, v, ww):
        s, z = (u - 0.5) * (w + 0.18), zb - 0.08 + 0.08 * v
        out = 0.06 - ww * 0.25
        if r is None:
            return (cx + s, cy - out, z)
        a = theta + s / r
        return (cx + (r + out) * math.cos(a), cy + (r + out) * math.sin(a), z)
    B.block(fn, nu=3, jit=0.006, chip=0.08)


def arch_plug(name, w, h, depth, mat, loc, rot_z=0.0):
    """Dark arched prism set into a wall: the hole's inside."""
    pts = [(-w / 2, 0), (w / 2, 0)]
    zs = h - w / 2
    pts += [(w / 2 * math.cos(math.pi * k / 12), zs + w / 2 * math.sin(math.pi * k / 12)) for k in range(13)]
    n = len(pts)
    v = [(x, y0, z) for y0 in (0, depth) for x, z in pts]
    f = [tuple(range(n))[::-1], tuple(range(n, 2 * n))] + [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    o = mesh(name, v, f, mat, smooth=False)
    o.location = loc
    o.rotation_euler.z = rot_z
    return o


def cyl(name, r, z0, z1, mat, loc=(0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=z1 - z0, vertices=verts, location=(*loc, (z0 + z1) / 2))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    return o


# ---- layout ----
# Towers: (x, y, radius, top of body). Keep stands behind the wall, left tower is the fat one.
TOWERS = [(-1.62, 0.15, 0.78, 3.55), (1.6, 0.25, 0.64, 2.95), (0.15, 0.95, 0.9, 4.55)]
WALL = (-1.0, 1.05, -0.05, 2.35)  # x0, x1, front y, top

B = Batch()
parts = []
for i, (cx, cy, r, top) in enumerate(TOWERS):
    front = -math.pi / 2 + (0.12 if i == 0 else -0.1)
    if i == 0:
        holes = [(front + 0.15, 1.35, 0.34, 0.66), (front - 0.35, 2.55, 0.3, 0.55)]
    elif i == 1:
        holes = [(front, 1.6, 0.3, 0.58)]
    else:
        holes = [(front - 0.25, 2.75, 0.36, 0.7), (front + 0.45, 3.65, 0.3, 0.55)]
    ring_rows(B, cx, cy, r, -SINK, top, holes=holes)
    corbels(B, cx, cy, r, top, int(TAU * r / 0.2))
    ring_band(B, cx, cy, r + 0.13, top, 0.18, int(TAU * r / 0.45), depth=0.16)
    if i != 2:
        merlons(B, cx, cy, r + 0.13, top + 0.18, 2 * int(TAU * r / 0.55), depth=0.16, skip=(4,) if i == 1 else ())
    else:
        ring_band(B, cx, cy, r + 0.04, top + 0.18, 0.2, int(TAU * r / 0.45), depth=0.14)
    parts.append(cyl(f'core{i}', r - 0.12, -SINK, top + 0.1, MORTAR, (cx, cy)))
    # floor of the tower top, seen thanks to the tilted camera
    parts.append(cyl(f'deck{i}', r + 0.05, top + 0.1, top + 0.2, MORTAR, (cx, cy)))
    for k, (t, zb, w, h) in enumerate(holes):
        arch_stones(B, cx, cy, r, t, zb, w, h, n=6)
        lit = i == 2 and k == 0
        p = arch_plug(f'win{i}{k}', w, h, 0.5, GLOW if lit else VOID,
                      (cx + (r - 0.12) * math.cos(t), cy + (r - 0.12) * math.sin(t), zb), t + math.pi / 2)
        parts.append(p)
        # iron bars in the windows
        for b in (-0.33, 0, 0.33):
            bx, by = cx + (r - 0.06) * math.cos(t + b * w / r), cy + (r - 0.06) * math.sin(t + b * w / r)
            parts.append(cyl(f'bar{i}{k}{b}', 0.012, zb, zb + h - 0.05, IRON, (bx, by), 8))

x0, x1, wy, wtop = WALL
DOOR = (0.0, -SINK + 0.1, 0.62, 1.15)
wall_rows(B, x0, x1, wy, -SINK, wtop, holes=[DOOR])
arch_stones(B, DOOR[0], wy, None, 0, DOOR[1], DOOR[2], DOOR[3], n=9, d=0.17)
# walkway band + crenellations along the wall top
for k in range(9):
    a, b = x0 + (x1 - x0) * k / 9, x0 + (x1 - x0) * (k + 1) / 9
    B.block(lambda u, v, w, a=a, b=b: (a + 0.01 + (b - a - 0.02) * u, wy - 0.06 + w * 0.5, wtop + 0.16 * v), nu=1)
    if k % 2 == 0:
        h = 0.3 * (0.85 + 0.3 * R())
        B.block(lambda u, v, w, a=a, b=b, h=h: (a + 0.02 + (b - a - 0.04) * u, wy - 0.05 + w * 0.18, wtop + 0.17 + h * v),
                nu=1, chip=0.12)
bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, wy + 0.25, (wtop - SINK) / 2))
core = bpy.context.object
core.scale = (x1 - x0, 0.36, wtop + SINK)
core.data.materials.append(MORTAR)
parts.append(core)

# a few loose blocks tumbled into the sand
for x, y, rz in ((-0.75, -0.55, 0.4), (1.05, -0.5, -0.3), (-0.55, -0.75, 1.2)):
    def fn(u, v, w, x=x, y=y, rz=rz):
        lx, ly = (u - 0.5) * 0.42, (w - 0.5) * 0.3
        return (x + lx * math.cos(rz) - ly * math.sin(rz), y + lx * math.sin(rz) + ly * math.cos(rz), -0.08 + 0.24 * v + 0.05 * u)
    B.block(fn, nu=1, chip=0.15)

parts.append(B.build('castle_stone', STONE))

# door: vertical planks, iron straps with studs, a ring pull
dx, dz, dw, dh = DOOR
door_y = wy + 0.07
plug = arch_plug('doorway', dw, dh, 0.4, VOID, (dx, door_y + 0.02, dz))
parts.append(plug)
P = Batch()
n = 5
for k in range(n):
    a, b = dx - dw / 2 + dw * k / n, dx - dw / 2 + dw * (k + 1) / n
    xc = (a + b) / 2 - dx
    hh = dh - dw / 2 + math.sqrt(max(0, (dw / 2) ** 2 - xc * xc)) - 0.02

    def fn(u, v, w, a=a, b=b, hh=hh):
        return (a + 0.006 + (b - a - 0.012) * u, door_y - 0.02 + 0.06 * w, dz + hh * v)
    P.block(fn, nu=1, jit=0.004, chip=0.05)
parts.append(P.build('door', WOOD, bevel=0.008))
for zz in (0.25, 0.75):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, door_y - 0.035, dz + zz))
    s = bpy.context.object
    s.scale = (dw * 0.94, 0.02, 0.06)
    s.data.materials.append(IRON)
    parts.append(s)
    for k in range(6):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.018, location=(dx - dw * 0.4 + dw * 0.8 * k / 5, door_y - 0.05, dz + zz),
                                             segments=10, ring_count=6)
        bpy.context.object.data.materials.append(IRON)
        parts.append(bpy.context.object)
bpy.ops.mesh.primitive_torus_add(major_radius=0.06, minor_radius=0.012, location=(dx + 0.14, door_y - 0.07, dz + 0.5),
                                 rotation=(math.radians(90), 0, 0))
bpy.context.object.data.materials.append(BRASS)
parts.append(bpy.context.object)

# painted crest over the door: quartered shield with a brass rim
def crest(x, y, z, w, h):
    pts = []
    for k in range(25):
        t = k / 24
        if t < 0.5:  # left side top-down
            u = t * 2
            pts.append((-w / 2 * (1 - u ** 3 * 0.9), z + h / 2 - h * u))
        else:
            u = (t - 0.5) * 2
            pts.append((w / 2 * (1 - (1 - u) ** 3 * 0.9), z - h / 2 + h * u))
    pts[12] = (0, z - h / 2)
    n = len(pts)
    for name, sc, dy, mat in (('rim', 1.0, 0.0, BRASS), ('field', 0.84, -0.012, None)):
        v = [(x + px * sc, y + dy + d, z + (pz - z) * sc) for d in (0, 0.03) for px, pz in pts]
        f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, i + n, (i + 1) % n + n, (i + 1) % n) for i in range(n)]
        if mat is None:
            mat = new_mat('paint')
            co = N(mat, 'TexCoord')
            sep = N(mat, 'SeparateXYZ', Vector=(co, 'Object'))
            q = M(mat, 'MULTIPLY', M(mat, 'SIGN', M(mat, 'SUBTRACT', (sep, 'X'), x)), M(mat, 'SIGN', M(mat, 'SUBTRACT', (sep, 'Z'), z)))
            qq = M(mat, 'MULTIPLY_ADD', q, 0.5, 0.5)
            nz = N(mat, 'TexNoise', Vector=(co, 'Object'), Scale=30.0, Detail=6.0)
            flake = N(mat, 'MapRange', Value=(nz, 'Fac'), **{'From Min': 0.58, 'From Max': 0.62})
            c = N(mat, 'Mix', _data_type='RGBA', Factor=qq, A=(0.06, 0.12, 0.35, 1), B=(0.6, 0.45, 0.12, 1))
            c = N(mat, 'Mix', _data_type='RGBA', Factor=(flake, 'Result'), A=(c, 'Result'), B=(0.35, 0.3, 0.24, 1))
            N(mat, 'OutputMaterial', Surface=N(mat, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.6}))
        o = mesh('crest_' + name, v, f, mat, smooth=False)
        parts.append(o)


crest(DOOR[0], WALL[2] - 0.08, 1.75, 0.34, 0.4)

# keep roof: cone of overlapping shingles, finial, flagpole
cx, cy, r, top = TOWERS[2]
rz0 = top + 0.38
RH, RR = 1.65, r + 0.2
S = Batch()
rows = 13
for k in range(rows):
    t0, t1 = k / rows, (k + 1.35) / rows  # fraction from apex; rows overlap
    rr = RR * (t0 + t1) / 2
    n = max(5, int(TAU * rr / 0.2))
    off = R() * TAU
    for j in range(n):
        a0, a1 = off + TAU * j / n, off + TAU * (j + 1) / n

        def fn(u, v, w, a0=a0, a1=a1, t0=t0, t1=t1):
            a = a0 + (a1 - a0) * u
            t = t0 + (t1 - t0) * v
            bulge = 0.025 * math.sin(math.pi * u)
            rr = RR * t + 0.035 * w + 0.03 * v + bulge
            return (cx + rr * math.cos(a), cy + rr * math.sin(a), rz0 + RH * (1 - t) - 0.05 * v)
        S.block(fn, nu=3, jit=0.006, chip=0.25)
parts.append(S.build('roof', ROOF, bevel=0.01))
parts.append(cyl('roofcore', RR * 0.98, rz0 - 0.02, rz0 + 0.02, MORTAR, (cx, cy)))
bpy.ops.mesh.primitive_cone_add(radius1=RR * 0.97, depth=RH, location=(cx, cy, rz0 + RH / 2), vertices=48)
bpy.context.object.data.materials.append(MORTAR)
parts.append(bpy.context.object)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.09, location=(cx, cy, rz0 + RH + 0.05))
bpy.context.object.data.materials.append(BRASS)
parts.append(bpy.context.object)


def flag(name, pole_base, pole_h, size, mat, phase, swallow=False):
    px, py, pz = pole_base
    parts.append(cyl(name + 'pole', 0.022, pz, pz + pole_h, BRASS, (px, py), 12))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.04, location=(px, py, pz + pole_h + 0.03), segments=12, ring_count=8)
    bpy.context.object.data.materials.append(BRASS)
    parts.append(bpy.context.object)
    w, h = size
    nu, nv = 16, 8
    v, f, uv = [], [], []
    for i in range(nu + 1):
        u = i / nu
        for j in range(nv + 1):
            t = j / nv
            uu = u
            if swallow and i == nu:
                uu = 1 - 0.28 * (1 - abs(t - 0.5) * 2)
            x = px + 0.02 + w * uu
            y = py + 0.09 * uu * math.sin(uu * 7.5 + phase) + 0.02 * math.sin(t * 5)
            z = pz + pole_h - 0.05 - h * t - 0.12 * uu * uu + 0.02 * math.sin(uu * 9 + t * 3)
            v.append((x, y, z))
            uv.append((uu, t))
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            f.append((a, a + nv + 1, a + nv + 2, a + 1))
    o = mesh(name, v, f, mat, uv=uv)
    mod(o, 'SOLIDIFY', thickness=0.012)
    parts.append(o)


flag('flag_keep', (cx, cy, rz0 + RH + 0.08), 0.75, (0.62, 0.36), cloth('red', (0.4, 0.05, 0.03), (0.6, 0.14, 0.07)), 0.3, True)
lx, ly, lr, lt = TOWERS[0]
flag('flag_left', (lx - 0.2, ly + 0.1, lt + 0.2), 0.8, (0.5, 0.3), cloth('gold', (0.5, 0.3, 0.04), (0.7, 0.5, 0.12)), 2.0)
rx, ry, rr_, rt = TOWERS[1]
flag('flag_right', (rx + 0.1, ry + 0.1, rt + 0.2), 0.6, (0.42, 0.26), cloth('teal', (0.04, 0.2, 0.3), (0.12, 0.35, 0.4)), 4.1, True)


# ---- little lives on the stones: a starfish, barnacles, algae tufts ----
def on_tower(t, th, z, out):
    cx, cy, r, _ = TOWERS[t]
    return Vector((cx + (r + out) * math.cos(th), cy + (r + out) * math.sin(th), z))


def starfish(t, th0, z0, size, spin):
    v, f = [], []
    K, A = 8, 80
    for k in range(K + 1):
        tt = k / K
        for j in range(A):
            a = TAU * j / A + spin
            prof = 0.32 + 0.68 * (0.5 + 0.5 * math.cos(5 * (a - spin))) ** 1.6
            rr = size * prof * tt
            x, z = rr * math.cos(a), rr * math.sin(a)
            dome = size * 0.22 * (1 - tt ** 2) * (0.6 + 0.4 * prof) + 0.01
            th = th0 + x / TOWERS[t][2]
            v.append(tuple(on_tower(t, th, z0 + z, dome)))
    for k in range(K):
        for j in range(A):
            a, b = k * A + j, k * A + (j + 1) % A
            f.append((a, b, b + A, a + A))
    o = mesh('starfish', v, f, pbr('star', (0.85, 0.22, 0.04), (1.0, 0.45, 0.1), rough=0.55, scale=40,
                                   bump=0.9, vor=0.8, sss=0.2, grime=0.3))
    parts.append(o)


starfish(0, -math.pi / 2 - 0.5, 1.05, 0.3, 0.4)

BARN = pbr('barnacle', (0.35, 0.33, 0.28), (0.6, 0.57, 0.5), rough=0.7, scale=30, bump=0.6, grime=0.8)
for k in range(22):
    t = 1 if k < 14 else 0
    th = -math.pi / 2 + (R() - 0.5) * (0.9 if t else 1.2) + (0.3 if t else -0.2)
    z = -0.05 + R() ** 2 * 0.55
    rr = 0.035 + R() * 0.035
    p0 = on_tower(t, th, z, 0.0)
    bpy.ops.mesh.primitive_cone_add(radius1=rr, radius2=rr * 0.45, depth=rr * 1.1, vertices=10, end_fill_type='NOTHING')
    b = bpy.context.object
    nrm = (p0 - Vector((TOWERS[t][0], TOWERS[t][1], z))).normalized()
    b.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
    b.location = p0 + nrm * rr * 0.4
    b.data.materials.append(BARN)
    parts.append(b)

ALGAE = pbr('algae', (0.05, 0.12, 0.02), (0.18, 0.3, 0.05), rough=0.6, scale=10, bump=0.2, sss=0.4, grime=0.3)


def tuft(base, n, hmax):
    v, f = [], []
    for _ in range(n):
        h = hmax * (0.5 + 0.5 * R())
        a, lean, ph = R() * TAU, 0.15 + 0.25 * R(), R() * TAU
        w = 0.012 + 0.01 * R()
        st = 8
        b0 = len(v)
        ox, oy = (R() - 0.5) * 0.12, (R() - 0.5) * 0.12
        for i in range(st + 1):
            u = i / st
            x = base.x + ox + math.cos(a) * lean * u * h + 0.04 * math.sin(u * 5 + ph)
            y = base.y + oy + math.sin(a) * lean * u * h
            z = base.z + u * h
            ww = w * (1 - u * 0.85)
            v += [(x - ww, y, z), (x + ww, y, z)]
        for i in range(st):
            q = b0 + 2 * i
            f.append((q, q + 1, q + 3, q + 2))
    o = mesh('tuft', v, f, ALGAE)
    mod(o, 'SOLIDIFY', thickness=0.006)
    parts.append(o)


for t, th in ((0, -2.0), (0, -1.0), (1, -1.3), (1, -2.4)):
    tuft(on_tower(t, th, TOWERS[t][3] + 0.5, 0.05), 7, 0.28)
tuft(Vector((0.55, WALL[2] + 0.05, WALL[3] + 0.48)), 6, 0.22)
tuft(Vector((-0.6, -0.35, -0.02)), 12, 0.35)
tuft(Vector((1.0, -0.3, -0.02)), 9, 0.25)

# scale the whole model to the target sprite size (~650 px tall at the reference height)
SCALE = 0.8
for o in parts:
    if o.parent is None:
        o.location *= SCALE
        o.scale *= SCALE

ground(14, soft=7, power=12000)
bpy.data.objects['contact'].location = (0, 0.3, 5.0)  # above the castle, not inside it
# fit on the castle plus a strip of sand around it so the contact shadow fades out in frame
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -0.1, 0))
foot = bpy.context.object
foot.scale = (5.0, 3.0, 1)
fit(parts + [foot], margin=0.05)
bpy.data.objects.remove(foot)
sprite('castle', {'base': (0, 0.3 * SCALE, 0)})
