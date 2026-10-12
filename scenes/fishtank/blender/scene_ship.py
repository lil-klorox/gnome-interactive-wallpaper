# Sunken galleon: plank-built hull listing in the sand, hole with exposed ribs, portholes,
# stern cabin, broken masts, torn sail, sagging rigging, barnacles, anchor and chain.
import math, os, random, sys
import bpy
from mathutils import Vector
sys.path.insert(0, os.path.dirname(__file__))
from common import *

scenery()
seed(7)
R = random.uniform
HL = 4.0  # half length; bow at +x, stern at -x, port side (camera side) at -y


def B(u):  # half beam at the deck line
    return 1.15 * max(0, 1 - max(u, 0) ** 2.4) ** 0.55 * (1 - 0.3 * max(-u, 0) ** 4)


def zt(u):  # sheer: deck edge rises toward bow and stern
    return 2.0 + 0.25 * u * u + 0.4 * max(u, 0) ** 3 + 0.25 * max(-u, 0) ** 3


def zb(u):  # keel line
    return 0.25 * u ** 4 + 0.2 * max(u, 0) ** 2


def shape(t):  # cross-section: round bilge, slight tumblehome at the top
    return math.sin(min(t, 0.88) / 0.88 * math.pi / 2) ** 0.55 * (1 - 0.1 * max(0, t - 0.88) / 0.12)


def P(u, t, side, out=0.0):  # hull surface; the bow rakes forward toward the top
    rake = 0.7 * max(0, u - 0.6) / 0.4 * t * t
    return Vector((u * HL + rake, side * (B(u) * shape(t) + out), zb(u) + (zt(u) - zb(u)) * t))


def normal(u, t, side):
    du = P(min(u + 0.01, 0.99), t, side) - P(u - 0.01, t, side)
    dt = P(u, min(t + 0.01, 1), side) - P(u, max(t - 0.01, 0), side)
    n = du.cross(dt).normalized()
    return n if n.y * side > 0 else -n


def wood(name, dark, light, moss=0.5, paint=None):
    """pbr wood: grain = noise stretched along the planks, per-plank tone, optional peeling paint."""
    m = pbr(name, dark, light, rough=0.82, scale=1.4, bump=0.35, moss=moss, grime=0.75)
    nt = m.node_tree
    r = next(n for n in nt.nodes if n.type == 'VALTORGB')
    users = [l.to_socket for l in r.outputs['Color'].links]
    co = N(m, 'TexCoord')
    grain = N(m, 'TexNoise', Vector=N(m, 'Mapping', Vector=(co, 'Object'), Scale=(0.6, 9.0, 9.0)), Scale=2.0,
              Detail=9.0, Roughness=0.7, Distortion=0.4)
    nt.links.new(grain.outputs['Fac'], r.inputs['Fac'])
    tone = N(m, 'Attribute', _attribute_name='tone')
    stain = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=0.7, Detail=3.0)
    k = M(m, 'MULTIPLY', N(m, 'MapRange', Value=(tone, 'Fac'), **{'To Min': 0.55, 'To Max': 1.25}),
          N(m, 'MapRange', Value=(stain, 'Fac'), **{'From Min': 0.35, 'From Max': 0.65, 'To Min': 0.45, 'To Max': 1.1}))
    col = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(r, 'Color'), B=k)
    if paint:
        pa = N(m, 'Attribute', _attribute_name='paint')
        peel = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=3.0, Detail=12.0, Roughness=0.7)
        pm = M(m, 'MULTIPLY', (pa, 'Fac'), N(m, 'MapRange', Value=(peel, 'Fac'), **{'From Min': 0.47, 'From Max': 0.5}))
        col = N(m, 'Mix', _data_type='RGBA', Factor=pm, A=(col, 'Result'),
                B=N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=0.6, A=(*paint, 1), B=(r, 'Color')))
    for u in users:
        nt.links.new(sock(col.outputs, 'Result'), u)
    return m


def build(name, V, F, attrs, mat):
    o = mesh(name, V, F, mat)
    for k, vals in attrs.items():
        a = o.data.attributes.new(k, 'FLOAT', 'POINT')
        a.data.foreach_set('value', vals)
    return o


# ---- hull planks ----
V, F, tone, paint = [], [], [], []
NS = 12
HOLE = (0.18, 0.55, 0.19, 0.24)  # u, t, radius in u, radius in t (port side)
breaks = []  # broken plank ends at the hole: (u, t, direction)


def plank(u0, u1, t0, t1, side, out, tn, pt):
    nu = max(3, int((u1 - u0) * 40))
    base = len(V)
    for i in range(nu + 1):
        for j in range(3):
            V.append(P(u0 + (u1 - u0) * i / nu, t0 + (t1 - t0) * j / 2, side, out))
            tone.append(tn)
            paint.append(pt)
    for i in range(nu):
        for j in range(2):
            a = base + i * 3 + j
            F.append((a, a + 3, a + 4, a + 1))


for side in (-1, 1):
    for i in range(NS):
        t0, t1 = i / NS + 0.004, (i + 1) / NS - 0.004
        tm = (t0 + t1) / 2
        wale = i in (7, 8)
        cuts = []
        if side < 0 and abs(tm - HOLE[1]) < HOLE[3]:
            du = HOLE[2] * math.sqrt(1 - ((tm - HOLE[1]) / HOLE[3]) ** 2) * R(0.7, 1.25)
            cuts = [HOLE[0] - du, HOLE[0] + du * R(0.8, 1.2)]
        u = -1.0
        while u < 0.995:
            u1 = min(0.995, u + R(0.3, 0.6))
            if u1 > 0.93:
                u1 = 0.995
            segs = [(u, u1)]
            if cuts and u < cuts[1] and u1 > cuts[0]:
                segs = [(a, b) for a, b in ((u, cuts[0]), (cuts[1], u1)) if b - a > 0.02]
                breaks += [(cuts[0], tm, 1), (cuts[1], tm, -1)]
            for a, b in segs:
                plank(a + 0.003, b - 0.003, t0, t1, side, (0.035 if wale else 0) + R(-0.006, 0.006),
                      R(0.25, 0.6) if wale else R(0.4, 1.0), 1.0 if 9 <= i <= 10 else 0.0)
            u = u1
# transom: horizontal planks closing the stern
for k in range(9):
    z0, z1 = zb(-1) + (zt(-1) - zb(-1)) * k / 9 + 0.004, zb(-1) + (zt(-1) - zb(-1)) * (k + 1) / 9 - 0.004
    base = len(V)
    for j, z in enumerate((z0, z1)):
        t = (z - zb(-1)) / (zt(-1) - zb(-1))
        w = B(-1) * shape(t)
        for i in range(9):
            V.append(Vector((-HL - 0.02, -w + 2 * w * i / 8, z)))
            tone.append(R(0.4, 1.0) if j == 0 else tone[-9])
            paint.append(0.0)
    # overwrites the per-vertex tones above, but those R() draws feed the seeded stream: keep them
    tone[base:base + 9] = [tone[base]] * 9
    tone[base + 9:base + 18] = [tone[base]] * 9
    for i in range(8):
        F.append((base + i, base + i + 1, base + 10 + i, base + 9 + i))
hull_mat = wood('hull', (0.2, 0.08, 0.025), (0.55, 0.27, 0.08), moss=0.35, paint=(0.42, 0.1, 0.05))
hull = build('hull', V, F, {'tone': tone, 'paint': paint}, hull_mat)
mod(hull, 'SOLIDIFY', thickness=0.05, offset=0)
mod(hull, 'BEVEL', width=0.012, segments=2, limit_method='ANGLE')
parts = [hull]

# ---- deck planks (with a hatch gap) ----
V, F, tone = [], [], []
for k in range(10):
    f0, f1 = -1 + 2 * k / 10 + 0.01, -1 + 2 * (k + 1) / 10 - 0.01
    u = -1.0
    while u < 0.97:
        u1 = min(0.97, u + R(0.25, 0.5))
        if not (-0.35 < (u + u1) / 2 < -0.1 and -0.4 < f0 < 0.4):
            nu, base = max(2, int((u1 - u) * 30)), len(V)
            tn = R(0.4, 1.0)
            for i in range(nu + 1):
                uu = u + 0.004 + (u1 - u - 0.008) * i / nu
                w = B(uu) * shape(1) * 0.97
                for f in (f0, f1):
                    V.append(Vector((uu * HL, f * w, zt(uu) - 0.06 + R(-0.004, 0.004))))
                    tone.append(tn)
            for i in range(nu):
                a = base + i * 2
                F.append((a, a + 2, a + 3, a + 1))
        u = u1
deck = build('deck', V, F, {'tone': tone}, wood('deck', (0.17, 0.1, 0.045), (0.46, 0.3, 0.14), moss=0.45))
mod(deck, 'SOLIDIFY', thickness=0.04, offset=-1)
parts.append(deck)

# ---- timbers: ribs (seen through the hole), keel, stem, gunwale caps, railing, masts, rigging ----
dark = wood('timber', (0.1, 0.055, 0.025), (0.3, 0.17, 0.07), moss=0.3)


ribs = [[P(u, t / 12, s, -0.06) for s in (-1, 1) for t in (range(12, -1, -1) if s < 0 else range(13))]
        for u in [x / 10 for x in range(-9, 10)]]
parts.append(curve('ribs', ribs, 0.045, dark))
parts.append(curve('keel', [[P(u / 20, 0, 1, 0) - Vector((0, 0, 0.06)) for u in range(-20, 21)]], 0.09, dark))
parts.append(curve('stem', [[P(0.995, t / 10, 1, 0) + Vector((0.05, 0, 0)) for t in range(11)]], 0.08, dark))
parts.append(curve('caps', [[P(u / 30, 1, s, 0.01) + Vector((0, 0, 0.03)) for u in range(-30, 30)] for s in (-1, 1)],
                   0.05, dark))
posts, rails = [], []
for s in (-1, 1):
    rail = []
    for i in range(-15, 15):
        u = i / 16
        p = P(u, 1, s, -0.02)
        if 0.05 < u < 0.4 and s < 0:  # broken run of railing over the hole
            if R(0, 1) < 0.4:
                posts.append([p, p + Vector((R(-0.1, 0.1), 0, R(0.08, 0.2)))])
            if rail:
                rails.append(rail)
                rail = []
            continue
        posts.append([p, p + Vector((0, 0, 0.38))])
        rail.append(p + Vector((0, 0, 0.38)))
    rails.append(rail)
parts.append(curve('posts', posts, 0.025, dark))
parts.append(curve('rail', rails, 0.03, dark))
# bowsprit, snapped
bs0 = P(0.99, 1, 1) + Vector((0.1, 0, 0.1))
parts.append(curve('bowsprit', [[bs0, bs0 + Vector((1.1, 0, 0.55))]], 0.07, dark, 2))


def mast(name, u, height, lean, r=0.11):
    """Cylinder from the keel up through the deck, snapped off: jagged splintered top."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=height, end_fill_type='TRIFAN',
                                        location=(0, 0, height / 2))
    o = bpy.context.object
    o.name = name
    for v in o.data.vertices:
        v.co.z += height / 2
    top = max(v.co.z for v in o.data.vertices)
    for v in o.data.vertices:
        if v.co.z > top - 1e-4:
            v.co.z += R(-0.35, 0.12) if (v.co.x or v.co.y) else -0.25
    base = P(u, 0.3, 1)
    o.location = (base.x, 0, base.z)
    o.rotation_euler = (math.radians(lean[0]), math.radians(lean[1]), 0)
    o.data.materials.append(dark)
    mod(o, 'BEVEL', width=0.01, segments=1)
    shards = []
    for k in range(6):  # splinters standing up from the break
        a = k / 6 * math.tau + R(-0.3, 0.3)
        h = R(0.15, 0.45)
        sp = Vector((math.cos(a) * r * 0.8, math.sin(a) * r * 0.8, top - 0.25))
        shards.append([sp, sp + Vector((math.cos(a) * 0.04, math.sin(a) * 0.04, h))])
    sh = curve(name + 'shards', shards, 0.022, dark, radii=lambda f: 1 - f * 0.95)
    sh.parent = o
    return o


main = mast('mainmast', 0.02, 4.2, (-6, 7))
fore = mast('foremast', 0.62, 2.9, (4, -10), 0.09)
parts += [main, fore]
bpy.context.view_layer.update()
mtop = main.matrix_world @ Vector((0, 0, 3.6))

# yard hanging askew, torn sail draped from it
y0 = main.matrix_world @ Vector((0, -0.14, 3.1))
yard_a, yard_b = y0 + Vector((-1.25, -0.25, -0.15)), y0 + Vector((1.2, -0.3, -1.05))
parts.append(curve('yard', [[yard_a, yard_b]], 0.055, dark, 2))
cloth = bpy.data.materials.new('sail')
cloth.use_nodes = True
cloth.node_tree.nodes.clear()
m = cloth
co = N(m, 'TexCoord')
holes = N(m, 'TexNoise', Vector=(co, 'Generated'), Scale=4.0, Detail=6.0, Roughness=0.7)
sep = N(m, 'SeparateXYZ', Vector=(co, 'Generated'))
tatter = M(m, 'ADD', (holes, 'Fac'), M(m, 'MULTIPLY', M(m, 'SUBTRACT', 0.3, (sep, 'Z')), 0.9))
keep = N(m, 'MapRange', Value=tatter, **{'From Min': 0.57, 'From Max': 0.55})
stain = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=2.0, Detail=8.0)
sc = ramp(m, (stain, 'Fac'), [(0.25, (0.16, 0.15, 0.06)), (0.5, (0.5, 0.38, 0.2)), (0.75, (0.8, 0.66, 0.42))])
weave = N(m, 'TexWave', Vector=(co, 'UV'), Scale=180.0, _bands_direction='X')
bs = N(m, 'BsdfPrincipled', **{'Base Color': (sc, 'Color'), 'Roughness': 0.95, 'Subsurface Weight': 0.2,
                               'Normal': N(m, 'Bump', Strength=0.15, Height=(weave, 'Fac'))})
tr = N(m, 'BsdfTranslucent', Color=(sc, 'Color'))
body = N(m, 'MixShader', Fac=0.35)
m.node_tree.links.new(bs.outputs[0], body.inputs[1])
m.node_tree.links.new(tr.outputs[0], body.inputs[2])
cut = N(m, 'MixShader', Fac=(keep, 'Result'))
m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], cut.inputs[1])
m.node_tree.links.new(body.outputs[0], cut.inputs[2])
N(m, 'OutputMaterial', Surface=cut)
sV, sF, NU, NV = [], [], 40, 30
for j in range(NV + 1):
    for i in range(NU + 1):
        a, b = i / NU, j / NV
        top = yard_a.lerp(yard_b, 0.1 + 0.8 * a)
        drop = 1.6 * b * (1.0 - 0.45 * a)
        fold = 0.2 * math.sin(a * 9 + b * 3) * (0.3 + b) + 0.05 * math.sin(a * 27 - b * 9)
        sV.append(top + Vector((0.35 * b * b * (1 - a), -0.35 * math.sin(math.pi * b) - fold - 0.2 * b * b, -drop)))
for j in range(NV):
    for i in range(NU):
        a = j * (NU + 1) + i
        sF.append((a, a + 1, a + NU + 2, a + NU + 1))
sail = mesh('sail', sV, sF, cloth)
sail.data.uv_layers.new()
for poly in sail.data.polygons:
    for li in poly.loop_indices:
        vi = sail.data.loops[li].vertex_index
        sail.data.uv_layers[0].data[li].uv = ((vi % (NU + 1)) / NU, 1 - (vi // (NU + 1)) / NV)
mod(sail, 'SOLIDIFY', thickness=0.008)
parts.append(sail)

# rigging: shrouds from the mast to the gunwales (one snapped, trailing), sagging
rope = pbr('rope', (0.06, 0.045, 0.025), (0.17, 0.13, 0.07), rough=0.95, scale=30, bump=0.4, grime=0.3)


def sag(a, b, d, n=16):
    return [a.lerp(b, i / n) - Vector((0, 0, d * math.sin(math.pi * i / n))) for i in range(n + 1)]


lines = []
for s in (-1, 1):
    for u in (-0.22, -0.1, 0.12, 0.24):
        lines.append(sag(mtop, P(u, 1, s, 0.05), R(0.05, 0.18)))
ftop = fore.matrix_world @ Vector((0, 0, 2.4))
lines.append(sag(ftop, bs0 + Vector((1.0, 0, 0.5)), 0.12))
lines.append(sag(mtop, ftop, 0.35))
lines.append([mtop + Vector((0.05, -0.1, -0.1))] + [mtop + Vector((0.1 + 0.08 * math.sin(i), -0.15, -0.3 * i)) for i in range(1, 9)])
parts.append(curve('rigging', lines, 0.014, rope, 2))

# ---- stern cabin with windows, and a lantern ----
cab = wood('cabin', (0.15, 0.08, 0.035), (0.42, 0.24, 0.1), moss=0.3, paint=(0.12, 0.3, 0.27))
cx0, cx1 = -HL - 0.05, -HL * 0.62
czb = zt(-0.8) - 0.05
bpy.ops.mesh.primitive_cube_add(size=1, location=((cx0 + cx1) / 2, 0, czb + 0.45))
cabin = bpy.context.object
cabin.scale = (cx1 - cx0, B(-0.8) * 1.85, 0.9)
cabin.data.materials.append(cab)
a = cabin.data.attributes.new('tone', 'FLOAT', 'POINT')
a.data.foreach_set('value', [0.8] * len(cabin.data.vertices))
a = cabin.data.attributes.new('paint', 'FLOAT', 'POINT')
a.data.foreach_set('value', [1.0] * len(cabin.data.vertices))
mod(cabin, 'BEVEL', width=0.04, segments=2)
parts.append(cabin)
# plank cladding on the camera side, and a planked quarterdeck roof with a taffrail
wb = B(-0.8) * 0.925
V, F, tone, paint = [], [], [], []
for k in range(7):
    z0, z1 = czb + 0.9 * k / 7 + 0.006, czb + 0.9 * (k + 1) / 7 - 0.006
    base, tn = len(V), R(0.45, 1.0)
    V += [Vector((cx0, -wb - 0.03, z0)), Vector((cx1, -wb - 0.03, z0)), Vector((cx1, -wb - 0.03, z1)), Vector((cx0, -wb - 0.03, z1))]
    tone += [tn] * 4
    paint += [1.0] * 4
    F.append((base, base + 1, base + 2, base + 3))
for k in range(8):
    y0_, y1_ = -wb - 0.1 + (2 * wb + 0.2) * k / 8 + 0.008, -wb - 0.1 + (2 * wb + 0.2) * (k + 1) / 8 - 0.008
    base, tn = len(V), R(0.45, 1.0)
    V += [Vector((cx0 - 0.15, y0_, czb + 0.93)), Vector((cx1 + 0.12, y0_, czb + 0.93)),
          Vector((cx1 + 0.12, y1_, czb + 0.93)), Vector((cx0 - 0.15, y1_, czb + 0.93))]
    tone += [tn] * 4
    paint += [0.0] * 4
    F.append((base, base + 1, base + 2, base + 3))
clad = build('clad', V, F, {'tone': tone, 'paint': paint}, cab)
mod(clad, 'SOLIDIFY', thickness=0.04)
mod(clad, 'BEVEL', width=0.008, segments=1)
parts.append(clad)
tp = []
for i in range(9):
    x = cx0 - 0.1 + (cx1 - cx0 + 0.15) * i / 8
    tp.append([Vector((x, -wb - 0.05, czb + 0.93)), Vector((x, -wb - 0.05, czb + 1.2 + (0.0 if i != 6 else -0.15)))])
tp += [[Vector((cx0 - 0.1, y, czb + 0.93)), Vector((cx0 - 0.1, y, czb + 1.2))] for y in (-0.3, 0.1, 0.5)]
parts.append(curve('taffposts', tp, 0.022, dark))
parts.append(curve('taffrail', [[Vector((cx1 + 0.05, -wb - 0.05, czb + 1.2)), Vector((cx0 - 0.1, -wb - 0.05, czb + 1.2)),
                                 Vector((cx0 - 0.1, wb, czb + 1.2))]], 0.03, dark))
glass = new_mat('glass')
N(glass, 'OutputMaterial', Surface=N(glass, 'BsdfPrincipled', **{
    'Base Color': (0.02, 0.06, 0.04, 1), 'Roughness': 0.08, 'Coat Weight': 1.0, 'Specular IOR Level': 0.8}))
brass = pbr('brass', (0.32, 0.19, 0.05), (0.2, 0.26, 0.14), rough=0.4, metal=0.85, scale=5, bump=0.15, grime=0.85)
wins = []
yw = -wb - 0.06
for k in range(3):
    x = cx0 + 0.3 + k * (cx1 - cx0 - 0.5) / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, yw, czb + 0.48))
    w = bpy.context.object
    w.scale = (0.34, 0.06, 0.42)
    w.data.materials.append(glass)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, yw - 0.02, czb + 0.48))
    fr = bpy.context.object
    fr.scale = (0.4, 0.04, 0.48)
    fr.data.materials.append(dark)
    mod(fr, 'BOOLEAN', object=w, operation='DIFFERENCE')
    mod(fr, 'BEVEL', width=0.01, segments=1)
    wins += [w, fr]
    for sx, sz in ((0.03, 0.4), (0.32, 0.03)):  # mullions
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, yw - 0.025, czb + 0.48))
        mu = bpy.context.object
        mu.scale = (sx, 0.02, sz)
        mu.data.materials.append(dark)
        wins.append(mu)
parts += wins
lp = Vector((cx1 - 0.15, yw - 0.3, czb + 0.95))
parts.append(curve('lanternarm', [[lp + Vector((-0.25, 0.25, 0.05)), lp + Vector((0, 0, 0.05)), lp + Vector((0, 0, -0.1))]],
                   0.015, brass))
bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.09, depth=0.2, location=lp + Vector((0, 0, -0.22)))
lan = bpy.context.object
lan.data.materials.append(glass)
bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.12, radius2=0.02, depth=0.1, location=lp + Vector((0, 0, -0.08)))
lc = bpy.context.object
lc.data.materials.append(brass)
parts += [lan, lc]

# ---- portholes along the port side ----
for u in (-0.55, -0.32, -0.08, 0.5, 0.7):
    t = 0.74
    c, n = P(u, t, -1, 0.03), normal(u, t, -1)
    q = n.to_track_quat('Z', 'Y')
    bpy.ops.mesh.primitive_torus_add(major_radius=0.13, minor_radius=0.035, major_segments=32, minor_segments=10,
                                     location=c, rotation=q.to_euler())
    ring = bpy.context.object
    ring.data.materials.append(brass)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.12, depth=0.02, location=c - n * 0.02, rotation=q.to_euler())
    g = bpy.context.object
    g.data.materials.append(glass)
    parts += [ring, g]
    for k in range(8):  # bolts round the rim
        a = k / 8 * math.tau
        off = q @ Vector((math.cos(a) * 0.19, math.sin(a) * 0.19, 0.01))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, segments=8, ring_count=5, location=c + off)
        b = bpy.context.object
        b.data.materials.append(brass)
        parts.append(b)

# ---- splinters at the broken plank ends round the hole ----
spl = []
for u, t, d in breaks:
    for k in range(2):
        tt = t + R(-0.025, 0.025)
        p = P(u, tt, -1)
        spl.append([p, p + Vector((d * R(0.1, 0.3) * HL / 4, R(-0.08, 0.06), R(-0.05, 0.05)))])
parts.append(curve('splinters', spl, 0.02, hull_mat, radii=lambda f: 1 - 0.9 * f))
# darkness inside so the hole reads deep
bpy.ops.mesh.primitive_plane_add(size=1, location=(HOLE[0] * HL, 0.15, 1.0), rotation=(math.radians(90), 0, 0))
inside = bpy.context.object
inside.scale = (2.5, 2.0, 1)
im = new_mat('inside')
N(im, 'OutputMaterial', Surface=N(im, 'BsdfDiffuse', Color=(0.005, 0.008, 0.008, 1)))
inside.data.materials.append(im)
parts.append(inside)

# ---- barnacles in clusters on the lower hull ----
bpy.ops.mesh.primitive_cone_add(vertices=7, radius1=1, radius2=0.45, depth=0.8, location=(0, 0, 0.4))
barn = bpy.context.object
bme = barn.data
bpy.data.objects.remove(barn)
bme.materials.append(pbr('barnacle', (0.36, 0.3, 0.22), (0.15, 0.12, 0.08), rough=0.7, scale=25, bump=0.8, grime=0.9))
for c in range(16):
    uc, tc = R(-0.9, 0.85), R(0.25, 0.65)
    side = -1 if c < 12 else 1
    for k in range(random.randint(5, 14)):
        u, t = uc + R(-0.07, 0.07), max(0.05, tc + R(-0.08, 0.08))
        if side < 0 and abs(u - HOLE[0]) < HOLE[2] * 1.2 and abs(t - HOLE[1]) < HOLE[3]:
            continue
        o = bpy.data.objects.new('barn', bme)
        bpy.context.scene.collection.objects.link(o)
        n = normal(u, t, side)
        o.location = P(u, t, side, 0.02)
        o.rotation_euler = n.to_track_quat('Z', 'Y').to_euler()
        o.scale = [R(0.05, 0.1)] * 3
        parts.append(o)

# ---- algae streamers hanging off the gunwale and yard ----
alg = pbr('algae', (0.05, 0.14, 0.02), (0.18, 0.34, 0.05), rough=0.55, scale=8, bump=0.2, sss=0.4, grime=0.2)
for k in range(16):
    top = P(R(-0.9, 0.85), R(0.8, 1), -1, 0.06) if k < 12 else yard_a.lerp(yard_b, R(0.1, 0.9))
    ln, w, ph = R(0.35, 0.9), R(0.035, 0.07), R(0, 6)
    sv, sf = [], []
    for i in range(13):
        f = i / 12
        c = top + Vector((0.08 * math.sin(f * 5 + ph) * f, -0.05 * f, -ln * f))
        hw = w * (1 - 0.7 * f) * (1 + 0.3 * math.sin(f * 9 + ph))
        sv += [c + Vector((-hw, 0, 0)), c + Vector((hw, 0, 0))]
        if i:
            sf.append((2 * i - 2, 2 * i - 1, 2 * i + 1, 2 * i))
    parts.append(mesh('alga', sv, sf, alg))

# ---- pose the wreck: list toward the camera, bow up and turned a little, sunk in the sand ----
ship = bpy.data.objects.new('ship', None)
bpy.context.scene.collection.objects.link(ship)
for o in parts:
    if o.parent is None:
        o.parent = ship
ship.rotation_euler = (math.radians(6), math.radians(-5), math.radians(-9))
ship.location = (-0.5, 0.3, -0.4)
ship.scale = (0.9, 0.9, 0.9)
bpy.context.view_layer.update()
# ---- anchor in the sand by the bow, chain back up to the hawse ----
iron = pbr('iron', (0.06, 0.03, 0.015), (0.22, 0.09, 0.03), rough=0.9, metal=0.3, scale=6, bump=0.7, vor=0.4, grime=0.8)
anc = bpy.data.objects.new('anchor', None)  # built upright in its own frame, then tipped over into the sand
bpy.context.scene.collection.objects.link(anc)
arc = [Vector((0.45 * math.sin(a), 0, 0.45 - 0.45 * math.cos(a))) for a in [math.radians(-105 + 210 * i / 16) for i in range(17)]]
anch = [curve('shank', [[Vector((0, 0, 0)), Vector((0, 0, 1.25))]], 0.06, iron, 2, radii=lambda f: 1.2 - 0.4 * f),
        curve('arms', [arc], 0.055, iron, 2, radii=lambda f: 0.7 + 0.5 * math.sin(math.pi * f)),
        curve('stock', [[Vector((0, -0.5, 1.08)), Vector((0, 0.5, 1.08))]], 0.04, iron, 2, radii=lambda f: 1.3 - 0.6 * abs(f - 0.5))]
for e in (arc[0], arc[-1]):  # spade flukes on the arm tips
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=12, ring_count=8, location=e + Vector((0, 0, -0.08)))
    fl = bpy.context.object
    fl.scale = (0.14, 0.035, 0.17)
    fl.rotation_euler = (0, -math.copysign(0.45, e.x), 0)
    fl.data.materials.append(iron)
    anch.append(fl)
bpy.ops.mesh.primitive_torus_add(major_radius=0.12, minor_radius=0.03, location=(0, 0, 1.38), rotation=(math.radians(90), 0, 0))
anch.append(bpy.context.object)
anch[-1].data.materials.append(iron)
for o in anch:
    o.parent = anc
anc.location = (HL * 0.9 + 0.55, -1.25, -0.12)
anc.rotation_euler = (math.radians(-20), math.radians(62), math.radians(-25))
bpy.context.view_layer.update()
ring = anc.matrix_world @ Vector((0, 0, 1.38))
hawse = ship.matrix_world @ P(0.85, 0.78, -1, 0.04)
chain = []
for i in range(34):
    f = i / 33
    p = ring.lerp(hawse, f) - Vector((0, 0, 0.9 * math.sin(math.pi * f) * (1 - f)))
    p.z = max(p.z, 0.04)
    chain.append(p)
links = []
for i in range(len(chain) - 1):
    d = (chain[i + 1] - chain[i])
    bpy.ops.mesh.primitive_torus_add(major_radius=0.06, minor_radius=0.016, major_segments=12, minor_segments=6,
                                     location=chain[i] + d / 2)
    l = bpy.context.object
    l.rotation_euler = d.to_track_quat('X', 'Z' if i % 2 else 'Y').to_euler()
    l.scale = (1.45, 1, 1)
    l.data.materials.append(iron)
    links.append(l)

hole = ship.matrix_world @ P(HOLE[0], HOLE[1], -1)
ground(12)
objs = [o for o in parts + anch + links if o.type in ('MESH', 'CURVE')]
fit(objs, margin=0.3)
sprite('ship', {'base': (0, 0, 0), 'hole': tuple(hole)})
