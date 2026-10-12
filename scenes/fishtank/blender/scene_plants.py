# Aquarium plants: each species is built from real curved leaf meshes (centre line + width
# profile + twist + cup) and stem tubes, rendered as one sprite with sway joints j1..jK.
# Usage: blender -b --factory-startup -P blender/scene_plants.py [-- species ...]
import math, os, random, sys
import bpy
import numpy as np
from mathutils import Vector, Matrix
sys.path.insert(0, os.path.dirname(__file__))
from common import *

V = Vector


def arc(base, az, el, length, droop=0.0, n=24, wob=0.0, curl=0.0):
    """Centre line: starts at base heading (azimuth, elevation), bends down by `droop` rad per
    unit, sideways by `curl`, with a little random wobble."""
    p, pts = V(base), []
    ds = length / (n - 1)
    for i in range(n):
        pts.append(p.copy())
        d = V((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        p = p + d * ds
        el -= droop * ds + random.uniform(-wob, wob) * ds
        az += curl * ds
    return pts


def strip(pts, width, az, twist=0.0, m=5, cup=0.15, wave=0.0, wfreq=9.0):
    """Leaf/ribbon surface along pts. width(t) = half width. Returns verts, uv (u across, v along)."""
    n = len(pts)
    side = V((-math.sin(az), math.cos(az), 0))
    verts, uv = [], []
    for i, p in enumerate(pts):
        t = i / (n - 1)
        d = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        s = Matrix.Rotation(twist * t, 3, d) @ side
        s = (s - d * s.dot(d)).normalized()
        nr = d.cross(s)
        w = width(t)
        for j in range(m):
            u = j / (m - 1) * 2 - 1
            ripple = wave * math.sin(t * wfreq * math.pi + u * 1.3) * abs(u) ** 2
            verts.append(p + s * (u * w) + nr * ((cup * u * u + ripple) * w))
            uv.append(((u + 1) / 2, t))
    return verts, uv, n, m


class Geo:
    """Accumulates many leaves into one mesh with per-vertex UV and a per-leaf random 'rnd'."""
    def __init__(self):
        self.v, self.f, self.uv, self.r = [], [], [], []

    def add(self, s, rnd=None):
        verts, uv, n, m = s
        o = len(self.v)
        self.v += verts
        self.uv += uv
        self.r += [random.random() if rnd is None else rnd] * len(verts)
        self.f += [(o + i * m + j, o + i * m + j + 1, o + (i + 1) * m + j + 1, o + (i + 1) * m + j)
                   for i in range(n - 1) for j in range(m - 1)]

    def obj(self, name, mat):
        o = mesh(name, self.v, self.f, mat, uv=self.uv)
        a = o.data.attributes.new('rnd', 'FLOAT', 'POINT')
        a.data.foreach_set('value', self.r)
        return o


def leaf_mat(name, base, tip, vein, alt=None, old=0.15, veins='net', trans=0.35, rough=0.45, coat=0.0,
             zramp=None, spots=0.0, algae=0.3):
    """Translucent leaf: base->tip colour, veins, per-leaf hue shift, old leaves brown at the
    edges with holes, algae speckles toward the tip. zramp=(height, [(pos, rgb)]) colours by
    height instead (ludwigia reddens toward the light)."""
    m = new_mat(name)
    uv = N(m, 'UVMap', _uv_map='UVMap')
    sp = N(m, 'SeparateXYZ', Vector=uv)
    co = N(m, 'TexCoord')
    rnd = N(m, 'Attribute', _attribute_name='rnd')
    du = M(m, 'MULTIPLY', M(m, 'ABSOLUTE', M(m, 'SUBTRACT', (sp, 'X'), 0.5)), 2.0)
    if zramp:
        z = N(m, 'SeparateXYZ', Vector=(co, 'Object'))
        col = ramp(m, M(m, 'DIVIDE', (z, 'Z'), zramp[0]), zramp[1])
    else:
        col = ramp(m, (sp, 'Y'), [(0.0, base), (1.0, tip)])
    col = (col, 'Color')
    if alt:
        col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (rnd, 'Fac'), 0.7), A=col, B=(*alt, 1)), 'Result')
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=9.0, Detail=6.0)
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.35, A=col, B=(nz, 'Color')), 'Result')
    # veins
    if veins == 'net':
        mid = N(m, 'MapRange', Value=du, **{'From Min': 0.0, 'From Max': 0.07, 'To Min': 1.0, 'To Max': 0.0})
        s = M(m, 'SUBTRACT', M(m, 'MULTIPLY', (sp, 'Y'), 1.0), M(m, 'MULTIPLY', du, 0.28))
        lat = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', s, 60.0))), 24.0)
        lat = M(m, 'MULTIPLY', lat, M(m, 'LESS_THAN', du, 0.93))
        vn = M(m, 'MAXIMUM', (mid, 'Result'), M(m, 'MULTIPLY', lat, 0.6))
    else:  # parallel veins along a ribbon
        vn = M(m, 'MULTIPLY', M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), 5 * math.pi))), 30.0), 0.7)
    col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', vn, 0.55), A=col, B=(*vein, 1)), 'Result')
    # algae fuzz: dull olive speckles, more toward tips
    an = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=60.0, Detail=3.0)
    am = N(m, 'MapRange', Value=M(m, 'ADD', (an, 'Fac'), M(m, 'MULTIPLY', (sp, 'Y'), 0.25)),
           **{'From Min': 0.78 - algae * 0.2, 'From Max': 0.9 - algae * 0.2, 'To Max': algae})
    col = (N(m, 'Mix', _data_type='RGBA', Factor=(am, 'Result'), A=col, B=(0.09, 0.1, 0.03, 1)), 'Result')
    if spots:  # green spot algae / spore dots
        vo = N(m, 'TexVoronoi', Vector=(co, 'Object'), Scale=40.0)
        dot = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.12, 'From Max': 0.2, 'To Min': spots, 'To Max': 0.0})
        col = (N(m, 'Mix', _data_type='RGBA', Factor=(dot, 'Result'), A=col, B=(0.22, 0.2, 0.05, 1)), 'Result')
    # old leaves: brown margins/patches and holes
    oldm = N(m, 'MapRange', Value=(rnd, 'Fac'), **{'From Min': 1 - old, 'From Max': 1 - old + 0.01})
    bn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=5.0, Detail=8.0)
    patch = N(m, 'MapRange', Value=M(m, 'ADD', M(m, 'ADD', (bn, 'Fac'), M(m, 'MULTIPLY', du, 0.35)), M(m, 'MULTIPLY', (sp, 'Y'), 0.2)),
              **{'From Min': 0.78, 'From Max': 0.9})
    brown = M(m, 'MULTIPLY', (patch, 'Result'), (oldm, 'Result'))
    col = (N(m, 'Mix', _data_type='RGBA', Factor=brown, A=col, B=(0.2, 0.11, 0.03, 1)), 'Result')
    hv = N(m, 'TexVoronoi', Vector=(co, 'Object'), Scale=14.0)
    hole = M(m, 'MULTIPLY', M(m, 'LESS_THAN', (hv, 'Distance'), 0.13), M(m, 'MULTIPLY', (oldm, 'Result'), M(m, 'GREATER_THAN', (patch, 'Result'), 0.3)))
    bump = N(m, 'Bump', Strength=0.25, Distance=0.02, Height=M(m, 'ADD', vn, M(m, 'MULTIPLY', (nz, 'Fac'), 0.3)))
    bsdf = N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': rough, 'Normal': bump, 'Coat Weight': coat,
                                    'Subsurface Weight': 0.15})
    bsdf.inputs['Subsurface Radius'].default_value = (0.3, 0.6, 0.2)
    bsdf.inputs['Subsurface Scale'].default_value = 0.02
    tr = N(m, 'BsdfTranslucent', Color=col, Normal=bump)
    leafsh = N(m, 'MixShader', Fac=trans)
    m.node_tree.links.new(bsdf.outputs[0], leafsh.inputs[1])
    m.node_tree.links.new(tr.outputs[0], leafsh.inputs[2])
    out = N(m, 'MixShader', Fac=hole)
    m.node_tree.links.new(leafsh.outputs[0], out.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], out.inputs[2])
    N(m, 'OutputMaterial', Surface=out)
    return m


def stem_mat(name, c1, c2):
    return pbr(name, c1, c2, rough=0.5, scale=12.0, bump=0.15, grime=0.3, sss=0.2)


def roots(base, n, spread, length):
    """Fine pale roots creeping out over the sand from the crown."""
    paths = []
    for _ in range(n):
        az = random.uniform(0, math.tau)
        paths.append(arc(base + V((0, 0, 0.02)), az, -0.25, length * random.uniform(0.5, 1), droop=-0.4, n=8, wob=2.5))
    return curve('roots', paths, 1.0, radii=lambda t: 0.012 * (1 - t) + 0.003,
                 mat=stem_mat('root', (0.45, 0.4, 0.3), (0.3, 0.25, 0.17)), res=1)


def taper(W, tip=6, base=0.3, rise=20):
    return lambda t: W * (1 - t ** tip) * min(1.0, base + t * rise)


def lance(W, sharp=1.0):
    """Lanceolate blade: widest a third of the way up, pointed tip."""
    return lambda t: W * math.sin(math.pi * min(1, t ** 0.75)) ** sharp * (1 - 0.15 * t) + 0.003


def fade_shadow(name, base, R):
    """The floor catches the whole canopy's shadow; keep only a soft pool around the roots so
    the sprite has no shadow edge where it was cropped. Pure-shadow pixels are the black ones."""
    path = os.path.join(ASSETS, name + '.png')
    px = load_png(path)
    H, W = px.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.hypot(xx - base[0], (yy - base[1]) * 2.5) / R
    fall = np.clip(1 - d, 0, 1) ** 1.5
    shadow = px[:, :, :3].max(axis=2) < 0.02
    px[:, :, 3] = np.where(shadow, px[:, :, 3] * fall, px[:, :, 3])
    save_png(px, path)


# ---------------- species ----------------

def vallisneria(h):
    g = Geo()
    for i in range(random.randint(15, 19)):
        az = random.uniform(0, math.tau)
        L = h * random.uniform(0.55, 1.0)
        pts = arc((random.uniform(-0.06, 0.06), random.uniform(-0.06, 0.06), -0.05), az,
                  math.radians(random.uniform(78, 88)), L, droop=random.uniform(0.02, 0.2),
                  n=48, wob=0.25, curl=random.uniform(-0.15, 0.15))
        g.add(strip(pts, taper(random.uniform(0.04, 0.06)), az + math.pi / 2, twist=random.uniform(-3, 3), m=4, cup=0.25))
    mat = leaf_mat('valli', (0.12, 0.2, 0.04), (0.28, 0.45, 0.1), (0.4, 0.55, 0.2), alt=(0.25, 0.32, 0.06),
                   old=0.2, veins='par', trans=0.5)
    return [g.obj('valli', mat), roots(V((0, 0, 0)), 9, 0.4, 0.45)]


def sword(h):
    g = Geo()
    petioles = []
    k = random.randint(13, 17)
    for i in range(k):
        az = random.uniform(0, math.tau)
        inner = i / k
        el = math.radians(80 - 45 * inner + random.uniform(-6, 6))
        pl = h * random.uniform(0.18, 0.3) * (1.1 - 0.4 * inner)
        pp = arc((0, 0, -0.03), az, el, pl, droop=0.15, n=8)
        petioles.append(pp)
        d = (pp[-1] - pp[-2]).normalized()
        L = h * random.uniform(0.45, 0.65) * (1.1 - 0.3 * inner)
        pts = arc(pp[-1], az, math.asin(max(-1, min(1, d.z))), L, droop=random.uniform(0.25, 0.6), n=30, wob=0.1)
        g.add(strip(pts, lance(random.uniform(0.15, 0.2), 0.8), az + math.pi / 2, twist=random.uniform(-0.6, 0.6),
                    m=9, cup=0.22, wave=0.06))
    mat = leaf_mat('sword', (0.09, 0.22, 0.04), (0.2, 0.42, 0.08), (0.45, 0.6, 0.22), alt=(0.16, 0.3, 0.03),
                   old=0.18, trans=0.35, coat=0.2)
    st = curve('swordstem', petioles, 1.0, radii=lambda t: 0.028 * (1 - 0.5 * t),
               mat=stem_mat('swst', (0.15, 0.28, 0.06), (0.25, 0.35, 0.1)), res=3)
    return [g.obj('sword', mat), st, roots(V((0, 0, 0)), 10, 0.5, 0.55)]


def javafern(h):
    g = Geo()
    rh = [V((x, random.uniform(-0.03, 0.03), 0.01 + 0.02 * math.sin(x * 7))) for x in [i * 0.06 - 0.3 for i in range(11)]]
    leaves = random.randint(13, 17)
    for i in range(leaves):
        b = rh[random.randint(1, len(rh) - 2)]
        az = random.uniform(0, math.tau)
        L = h * random.uniform(0.55, 1.0)
        pts = arc(b, az, math.radians(random.uniform(55, 85)), L, droop=random.uniform(0.3, 0.7), n=34, wob=0.2)
        g.add(strip(pts, lance(random.uniform(0.07, 0.1), 1.2), az + math.pi / 2, twist=random.uniform(-0.8, 0.8),
                    m=7, cup=0.3, wave=0.25, wfreq=random.uniform(10, 16)))
        if random.random() < 0.35:  # plantlet sprouting from the leaf tip
            tip = pts[-1]
            for _ in range(3):
                a2 = random.uniform(0, math.tau)
                p2 = arc(tip, a2, math.radians(random.uniform(20, 70)), 0.12, droop=1, n=6)
                g.add(strip(p2, lance(0.025), a2 + math.pi / 2, m=3, cup=0.2), rnd=0.3)
    mat = leaf_mat('jfern', (0.04, 0.12, 0.03), (0.1, 0.25, 0.05), (0.18, 0.32, 0.08), alt=(0.08, 0.16, 0.02),
                   old=0.15, trans=0.25, rough=0.4, spots=0.6)
    stem = stem_mat('jfrh', (0.03, 0.02, 0.012), (0.08, 0.05, 0.025))
    rhz = curve('rhizome', [rh], 1.0, radii=lambda t: 0.035, mat=stem, res=3)
    hair = [arc(p, random.uniform(0, math.tau), random.uniform(-0.6, -0.1), random.uniform(0.08, 0.2), n=5, wob=3)
            for p in rh for _ in range(3)]
    return [g.obj('jfern', mat), rhz, curve('jfroots', hair, 1.0, radii=lambda t: 0.006, mat=stem, res=1)]


def cabomba(h):
    g = Geo()
    stems = []
    for s in range(random.randint(4, 5)):
        az = random.uniform(0, math.tau)
        L = h * random.uniform(0.6, 1.0)
        base = (random.uniform(-0.2, 0.2), random.uniform(-0.1, 0.1), -0.05)
        pts = arc(base, az, math.radians(random.uniform(80, 88)), L, droop=0.0, n=60, wob=0.5)
        stems.append(pts)
        z = 0.12
        while z < L - 0.05:
            p = pts[min(int(z / L * 59), 59)]
            up = z / L
            size = 0.34 + 0.12 * math.sin(up * math.pi) - 0.14 * up
            rot = random.uniform(0, math.tau)
            for k in range(6):  # whorl of fan-shaped leaves, each split into needles
                a = rot + k * math.tau / 6
                el = math.radians(-5 + 45 * up ** 2)
                for nd in range(5):
                    a2 = a + (nd - 2) * 0.3
                    q = arc(p, a2, el + (nd - 2) * 0.08, size * random.uniform(0.7, 1.0), droop=1.0 - 2.5 * up, n=6)
                    g.add(strip(q, lambda t: 0.009 * (1 - t * 0.6), a2 + math.pi / 2, m=2, cup=0), rnd=up)
            z += 0.15 + random.uniform(-0.01, 0.03)
    mat = leaf_mat('cabomba', (0.12, 0.3, 0.05), (0.22, 0.48, 0.1), (0.3, 0.5, 0.12), old=0.05, veins='par',
                   trans=0.5, zramp=(h, [(0.0, (0.08, 0.22, 0.04)), (0.5, (0.2, 0.48, 0.08)), (1.0, (0.45, 0.7, 0.15))]))
    st = curve('cabst', stems, 1.0, radii=lambda t: 0.018 * (1 - 0.5 * t), mat=stem_mat('cabs', (0.1, 0.2, 0.05), (0.2, 0.32, 0.08)), res=3)
    return [g.obj('cabomba', mat), st, roots(V((0, 0, 0)), 8, 0.3, 0.35)]


def ludwigia(h):
    g = Geo()
    stems = []
    for s in range(random.randint(4, 6)):
        az = random.uniform(0, math.tau)
        L = h * random.uniform(0.6, 1.0)
        base = (random.uniform(-0.18, 0.18), random.uniform(-0.1, 0.1), -0.05)
        pts = arc(base, az, math.radians(random.uniform(76, 88)), L, droop=0.0, n=50, wob=0.35)
        stems.append(pts)
        z, rot = 0.15, random.uniform(0, math.pi)
        while z < L:
            p = pts[min(int(z / L * 49), 49)]
            up = z / L
            ln = 0.38 * (1 - 0.3 * up) * random.uniform(0.85, 1.1)
            for side in (0, math.pi):  # opposite pair, each node turned 90 degrees (decussate)
                a = rot + side
                q = arc(p, a, math.radians(25 + 45 * up), ln, droop=0.9 - 0.8 * up, n=14)
                g.add(strip(q, lambda t: 0.11 * math.sin(math.pi * min(1, t ** 0.8 + 0.04)) + 0.004, a + math.pi / 2,
                            m=7, cup=0.25, twist=random.uniform(-0.3, 0.3)))
            rot += math.pi / 2
            z += 0.16 * (1 - 0.3 * up)
    mat = leaf_mat('ludwigia', (0.1, 0.2, 0.04), (0.3, 0.08, 0.06), (0.5, 0.25, 0.2), alt=(0.35, 0.1, 0.12),
                   old=0.12, trans=0.45, coat=0.15, algae=0.15,
                   zramp=(h, [(0.0, (0.12, 0.26, 0.05)), (0.4, (0.35, 0.32, 0.06)), (0.7, (0.7, 0.16, 0.1)), (1.0, (0.9, 0.22, 0.2))]))
    st = curve('ludst', stems, 1.0, radii=lambda t: 0.022 * (1 - 0.4 * t), mat=stem_mat('luds', (0.25, 0.1, 0.06), (0.35, 0.16, 0.1)), res=3)
    return [g.obj('ludwigia', mat), st, roots(V((0, 0, 0)), 8, 0.3, 0.35)]


def anubias(h):
    g = Geo()
    rh = [V((x, random.uniform(-0.03, 0.03), 0.02 + 0.015 * math.sin(x * 9))) for x in [i * 0.06 - 0.42 for i in range(15)]]
    pets = []
    for i in range(random.randint(7, 10)):
        b = rh[random.randint(2, len(rh) - 3)]
        az = random.uniform(0, math.tau)
        pp = arc(b, az, math.radians(random.uniform(45, 80)), h * random.uniform(0.25, 0.45), droop=0.6, n=8)
        pets.append(pp)
        d = (pp[-1] - pp[-2]).normalized()
        pts = arc(pp[-1], az, math.asin(d.z) - 0.2, h * random.uniform(0.45, 0.6), droop=0.7, n=22)
        W = random.uniform(0.17, 0.23)
        g.add(strip(pts, lambda t, W=W: W * math.sin(math.pi * min(1, t ** 0.85 + 0.02)) ** 0.7 + 0.003,
                    az + math.pi / 2, m=9, cup=0.25, twist=random.uniform(-0.4, 0.4)))
    mat = leaf_mat('anubias', (0.03, 0.1, 0.02), (0.06, 0.18, 0.04), (0.12, 0.22, 0.06), alt=(0.05, 0.14, 0.02),
                   old=0.12, trans=0.12, rough=0.3, coat=0.5, spots=0.8, algae=0.4)
    stem = stem_mat('anrh', (0.04, 0.07, 0.02), (0.1, 0.12, 0.04))
    hair = [arc(p, random.uniform(0, math.tau), random.uniform(-0.7, -0.2), random.uniform(0.15, 0.35), n=6, wob=2)
            for p in rh[::2] for _ in range(2)]
    return [g.obj('anubias', mat), curve('anrh', [rh], 1.0, radii=lambda t: 0.06 - 0.02 * t, mat=stem, res=3),
            curve('anpet', pets, 1.0, radii=lambda t: 0.018, mat=stem, res=3),
            curve('anroot', hair, 1.0, radii=lambda t: 0.01 * (1 - t) + 0.003,
                  mat=stem_mat('anr', (0.4, 0.37, 0.28), (0.28, 0.24, 0.16)), res=1)]


def hairgrass(h):
    g = Geo()
    for c in range(5):
        cx = random.uniform(-0.6, 0.6)
        for i in range(random.randint(14, 22)):
            az = random.uniform(0, math.tau)
            pts = arc((cx + random.uniform(-0.05, 0.05), random.uniform(-0.15, 0.15), -0.03), az,
                      math.radians(random.uniform(55, 88)), h * random.uniform(0.45, 1.0),
                      droop=random.uniform(0.2, 0.9), n=12, wob=0.5)
            g.add(strip(pts, lambda t: 0.009 * (1 - t ** 3) + 0.001, az + math.pi / 2, m=2, cup=0))
    mat = leaf_mat('hair', (0.08, 0.2, 0.04), (0.3, 0.5, 0.12), (0.3, 0.5, 0.12), alt=(0.18, 0.3, 0.05),
                   old=0.1, veins='par', trans=0.5)
    return [g.obj('hair', mat)]


# name: (builder, [height variant 0, 1], joints)
SPECIES = {
    'valli': (vallisneria, [7.5, 5.5], 4),
    'sword': (sword, [3.4, 2.6], 1),
    'jfern': (javafern, [2.6, 2.0], 1),
    'cabomba': (cabomba, [5.0, 3.8], 3),
    'ludwigia': (ludwigia, [4.0, 3.0], 2),
    'anubias': (anubias, [1.5, 1.2], 1),
    'hair': (hairgrass, [1.3, 0.9], 0),
}

want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(SPECIES)
bad = [a for a in want if a not in SPECIES]
if bad:
    sys.exit(f'scene_plants.py: unknown species {bad}; choose from {list(SPECIES)}')
for sp_name in want:
    build, heights, K = SPECIES[sp_name]
    for n, h in enumerate(heights):
        scenery()
        seed(sum(map(ord, sp_name)) + n * 17)
        objs = build(h)
        ground(12)
        bpy.context.view_layer.update()
        top = max((o.matrix_world @ V(c)).z for o in objs for c in o.bound_box)
        pts = {'base': (0, 0, 0)}
        pts.update({f'j{k}': (0, 0, top * k / (K + 1)) for k in range(1, K + 1)})
        fit(objs, margin=0.12)
        ent = sprite(f'plant_{sp_name}_{n}', pts)
        fade_shadow(f'plant_{sp_name}_{n}', ent['base'], 0.5 * PPU)
