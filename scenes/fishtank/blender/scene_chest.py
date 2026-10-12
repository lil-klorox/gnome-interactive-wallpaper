# Treasure chest: plank body heaped with gold, plus lid frames (closed -> ~35 deg open) rendered
# from the same camera with the body as holdout, so scene.js can stack them pixel-exact.
import math, os, random, sys
import bpy
from mathutils import Vector, Euler
sys.path.insert(0, os.path.dirname(__file__))
from common import *

scenery()
seed(7)
floor = ground(12)
W, D, H = 1.0, 0.6, 0.82   # half width, half depth, body height
root = bpy.data.objects.new('root', None)
bpy.context.scene.collection.objects.link(root)
root.rotation_euler.z = math.radians(-24)
root.scale = (0.78,) * 3   # a 3/4 view so a side and the handle show
body, lid = [], []


def wood(name, c1, c2, moss=0.0):
    """Planks: ring grain stretched along local X, per-board offset, AO grime, rot toward the base."""
    m = new_mat(name)
    co = N(m, 'TexCoord')
    rnd = N(m, 'ObjectInfo')
    mp = N(m, 'Mapping', Vector=(co, 'Object'), Location=M(m, 'MULTIPLY', (rnd, 'Random'), 17.0), Scale=(0.08, 1.4, 1.4))
    wv = N(m, 'TexWave', _wave_type='RINGS', Vector=mp, Scale=9.0, Distortion=9.0, Detail=4.0, **{'Detail Scale': 1.8})
    nz = N(m, 'TexNoise', Vector=mp, Scale=5.0, Detail=6.0)
    g = M(m, 'MULTIPLY_ADD', (wv, 'Fac'), 0.65, M(m, 'MULTIPLY', (nz, 'Fac'), 0.35))
    col = ramp(m, g, [(0.25, c1), (0.75, c2)])
    tone = ramp(m, (rnd, 'Random'), [(0.0, (0.75, 0.75, 0.75)), (1.0, (1.15, 1.1, 1.0))])
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(col, 'Color'), B=(tone, 'Color'))
    c = ao_grime(m, (c, 'Result'), 0.12, 0.4)
    geo = N(m, 'NewGeometry')
    pos = N(m, 'SeparateXYZ', Vector=(geo, 'Position'))
    rn = N(m, 'TexNoise', Vector=(geo, 'Position'), Scale=7.0, Detail=8.0)
    rot = N(m, 'MapRange', Value=M(m, 'ADD', (pos, 'Z'), M(m, 'MULTIPLY', (rn, 'Fac'), 0.5)),
            **{'From Min': 0.05, 'From Max': 0.3, 'To Min': 0.6, 'To Max': 0.0})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(rot, 'Result'), A=c, B=(0.035, 0.03, 0.015, 1))
    r = (N(m, 'MapRange', Value=(rot, 'Result'), **{'To Min': 0.62, 'To Max': 0.9}), 'Result')
    if moss:
        up = N(m, 'SeparateXYZ', Vector=(geo, 'Normal'))
        mk = N(m, 'MapRange', Value=M(m, 'MULTIPLY', (up, 'Z'), (rn, 'Fac')), **{'From Min': 0.55 - moss * 0.1, 'From Max': 0.62 - moss * 0.1})
        c = N(m, 'Mix', _data_type='RGBA', Factor=(mk, 'Result'), A=(c, 'Result'), B=(0.05, 0.075, 0.02, 1))
    b = N(m, 'Bump', Strength=0.15, Distance=0.02, Height=g)
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': r, 'Normal': b}))
    return m


oak = wood('oak', (0.24, 0.08, 0.025), (0.62, 0.27, 0.08))
oak_lid = wood('oak_lid', (0.2, 0.07, 0.022), (0.55, 0.24, 0.07), moss=0.15)
iron = pbr('iron', (0.035, 0.03, 0.028), (0.2, 0.08, 0.025), rough=0.65, metal=0.6, scale=7, bump=0.5, vor=0.5, grime=0.6)
brass = pbr('brass', (0.5, 0.33, 0.1), (0.22, 0.2, 0.08), rough=0.35, metal=1.0, scale=6, bump=0.25, grime=0.8)
gold = pbr('gold', (1.0, 0.5, 0.08), (1.0, 0.68, 0.2), rough=0.3, metal=1.0, scale=40, bump=0.08, grime=0.75)
dark = new_mat('keyhole')
N(dark, 'OutputMaterial', Surface=N(dark, 'BsdfDiffuse', Color=(0.003, 0.003, 0.003, 1)))


def put(o, mat, parent, group):
    o.data.materials.append(mat)
    o.parent = parent
    group.append(o)
    return o


def box(size, loc, rot=(0, 0, 0), mat=oak, bev=0.012, parent=root, group=body):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    o.location, o.rotation_euler = loc, rot
    if bev:
        mod(o, 'BEVEL', width=bev, segments=2)
    return put(o, mat, parent, group)


def jit(a):
    return random.uniform(-a, a)


# --- body: three boards per wall, slightly uneven, gaps between them
t = 0.07
for k in range(3):
    z, h = 0.03 + k * 0.265 + 0.13, 0.25
    for sy in (-1, 1):
        box((2 * W, t, h), (jit(0.01), sy * (D - t / 2) + jit(0.006), z), (jit(0.01), jit(0.008), jit(0.006)))
    for sx in (-1, 1):
        box((2 * D - 2 * t, t, h), (sx * (W - t / 2), jit(0.006), z), (0, jit(0.01), math.pi / 2 + jit(0.01)))
box((2 * W, 2 * D, 0.05), (0, 0, 0.025))

# iron: corner straps, two wrap-around bands, top rim band, rivets
bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.022)
rv = bpy.context.object
rv.scale.y = 0.6
bpy.ops.object.transform_apply(scale=True)
rivet = rv.data
rv.data.shade_smooth()
bpy.data.objects.remove(rv)


def rivets(p0, p1, n, normal, parent=root, group=body):
    p0, p1 = Vector(p0), Vector(p1)
    for i in range(n):
        o = bpy.data.objects.new('rv', rivet)
        bpy.context.scene.collection.objects.link(o)
        o.location = p0.lerp(p1, (i + 0.5) / n)
        o.rotation_euler = aim(normal)
        o.rotation_euler.rotate_axis('Z', jit(3))
        o.parent = parent
        group.append(o)


rivet.materials.append(iron)
for sx in (-0.62, 0.62):
    for sy in (-1, 1):
        box((0.11, 0.022, H + 0.02), (sx, sy * (D + 0.01), H / 2), mat=iron, bev=0.006)
        rivets((sx, sy * (D + 0.026), 0.05), (sx, sy * (D + 0.026), H - 0.02), 6, (0, sy, 0))
for sx in (-1, 1):
    for sy in (-1, 1):
        box((0.12, 0.022, H + 0.02), (sx * (W - 0.05), sy * (D + 0.01), H / 2), mat=iron, bev=0.006)
        box((0.022, 0.12, H + 0.02), (sx * (W + 0.01), sy * (D - 0.05), H / 2), mat=iron, bev=0.006)
        rivets((sx * (W - 0.05), sy * (D + 0.026), 0.06), (sx * (W - 0.05), sy * (D + 0.026), H - 0.03), 5, (0, sy, 0))
for sy in (-1, 1):
    box((2 * W + 0.04, 0.024, 0.07), (0, sy * (D + 0.012), H - 0.035), mat=iron, bev=0.006)
for sx in (-1, 1):
    box((0.024, 2 * D + 0.04, 0.07), (sx * (W + 0.012), 0, H - 0.035), mat=iron, bev=0.006)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.11, minor_radius=0.018, location=(sx * (W + 0.07), 0, H * 0.55),
                                     rotation=(0, math.pi / 2, 0))
    h = bpy.context.object
    h.rotation_euler = (math.radians(70) * sx, math.pi / 2, 0)
    h.location.z -= 0.08
    put(h, iron, root, body)
    box((0.03, 0.14, 0.08), (sx * (W + 0.025), 0, H * 0.55), mat=iron, bev=0.008)

# lock plate on the front, keyhole cut in black
box((0.26, 0.025, 0.28), (0, -D - 0.022, H - 0.2), mat=brass, bev=0.01)
rivets((-0.1, -D - 0.04, H - 0.08), (0.1, -D - 0.04, H - 0.08), 2, (0, -1, 0))
rivets((-0.1, -D - 0.04, H - 0.32), (0.1, -D - 0.04, H - 0.32), 2, (0, -1, 0))
bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.01, location=(0, -D - 0.035, H - 0.18), rotation=(math.pi / 2, 0, 0))
put(bpy.context.object, dark, root, body)
box((0.026, 0.01, 0.07), (0, -D - 0.035, H - 0.225), mat=dark, bev=0)

# barnacles crusting the lower boards and corners
shell = pbr('barnacle', (0.32, 0.3, 0.25), (0.6, 0.55, 0.45), rough=0.8, scale=30, bump=0.6, vor=0.6, grime=0.8)
bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.035, radius2=0.012, depth=0.035)
bc = bpy.context.object
mod(bc, 'BEVEL', width=0.004, segments=1)
apply_all(bc)
barn = bc.data
barn.materials.append(shell)
bpy.data.objects.remove(bc)
for i in range(26):
    side = random.random() < 0.7
    x = random.choice((-1, 1)) * random.uniform(0.45, 1.0) if side else random.uniform(-0.9, 0.9)
    z = random.uniform(0.03, 0.22) if side else random.uniform(0.02, 0.1)
    o = bpy.data.objects.new('barnacle', barn)
    bpy.context.scene.collection.objects.link(o)
    o.location = (x, -D - 0.025, z)
    o.rotation_euler = (math.pi / 2 + jit(0.4), jit(0.4), jit(3))
    o.scale = (random.uniform(0.6, 1.3),) * 3
    o.parent = root
    body.append(o)

# --- the hoard: a gold mound, coins over it, gems, a pearl string over the front edge
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, H - 0.04))
mound = bpy.context.object
mound.scale = (W - 0.08, D - 0.08, 0.2)
deep = pbr('deepgold', (0.35, 0.18, 0.03), (0.6, 0.35, 0.08), rough=0.55, metal=1.0, scale=30, bump=0.4, vor=0.8, grime=0.9)
put(mound, deep, root, body)
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.072, depth=0.014)
cn = bpy.context.object
mod(cn, 'BEVEL', width=0.004, segments=2)
apply_all(cn)
coin = cn.data
coin.shade_smooth()
coin.materials.append(gold)
bpy.data.objects.remove(cn)
# stamped faces: rim ridge + concentric relief + a lumpy portrait, via bump on the shared coin mesh
stamp = gold.copy()
stamp.name = 'coin'
coin.materials[0] = stamp
nt = stamp.node_tree
co = N(stamp, 'TexCoord')
gr = N(stamp, 'TexGradient', _gradient_type='SPHERICAL', Vector=N(stamp, 'Mapping', Vector=(co, 'Object'), Scale=(13.9, 13.9, 13.9)))
rim = N(stamp, 'MapRange', Value=(gr, 'Fac'), **{'From Min': 0.08, 'From Max': 0.16, 'To Min': 1.0, 'To Max': 0.0})
face = N(stamp, 'TexNoise', Vector=(co, 'Object'), Scale=60.0, Detail=1.0)
inner = N(stamp, 'MapRange', Value=(gr, 'Fac'), **{'From Min': 0.25, 'From Max': 0.35})
hgt = M(stamp, 'MULTIPLY_ADD', M(stamp, 'MULTIPLY', (face, 'Fac'), (inner, 'Result')), 0.6, (rim, 'Result'))
bump = next(n for n in nt.nodes if n.type == 'BUMP')
nt.links.new(hgt.outputs[0], bump.inputs['Height'])
bump.inputs['Strength'].default_value = 0.6
bump.inputs['Distance'].default_value = 0.004


def coin_at(loc, normal, parent=root):
    o = bpy.data.objects.new('coin', coin)
    bpy.context.scene.collection.objects.link(o)
    q = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized())
    o.rotation_euler = (q.to_matrix() @ Euler((jit(0.35), jit(0.35), jit(3.1))).to_matrix()).to_euler()
    o.location = loc
    o.parent = parent
    body.append(o)


a, b, c, cz = W - 0.08, D - 0.08, 0.2, H - 0.04
for i in range(650):
    x, y = random.uniform(-1, 1), random.uniform(-1, 1)
    if x * x + y * y > 0.96:
        continue
    z = math.sqrt(max(0.0, 1 - x * x - y * y))
    coin_at((x * a, y * b, cz + z * c + random.uniform(0.0, 0.02)), (x / a, y / b, z / c + 0.4))
for x, y in ((-0.7, -0.95), (-0.45, -1.1), (0.15, -1.02), (0.55, -0.85), (1.15, -0.7), (-1.2, -0.6), (0.9, -1.15)):
    coin_at((x, y, 0.0), (jit(0.4), jit(0.4), 1))
for k in range(4):  # a little stack fallen on the sand
    coin_at((-0.95, -0.95, 0.008 + k * 0.015), (jit(0.06), jit(0.06), 1))

for i, (col, loc, r) in enumerate((((0.6, 0.0, 0.02), (-0.3, -0.15, H + 0.17), 0.075),
                                   ((0.0, 0.35, 0.08), (0.35, 0.05, H + 0.16), 0.065),
                                   ((0.02, 0.08, 0.6), (0.62, -0.3, H + 0.09), 0.06),
                                   ((0.5, 0.05, 0.4), (-0.7, 0.1, H + 0.08), 0.055),
                                   ((0.6, 0.0, 0.02), (1.05, -0.95, 0.03), 0.05))):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r, location=loc)
    g = bpy.context.object
    g.scale.z = 0.75
    g.rotation_euler = (jit(1), jit(1), jit(3))
    m = new_mat(f'gem{i}')
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (*col, 1), 'Transmission Weight': 1.0,
                                                               'IOR': 1.77, 'Roughness': 0.05}))
    put(g, m, root, body)

pearl = new_mat('pearl')
N(pearl, 'OutputMaterial', Surface=N(pearl, 'BsdfPrincipled', **{'Base Color': (0.95, 0.76, 0.48, 1), 'Roughness': 0.3,
                                                                  'Coat Weight': 1.0, 'Sheen Weight': 0.5}))
path = [Vector(p) for p in ((0.1, -0.1, H + 0.19), (0.3, -0.4, H + 0.1), (0.42, -D - 0.06, H + 0.02),
                            (0.36, -D - 0.08, H - 0.2), (0.22, -D - 0.08, H - 0.3), (0.1, -D - 0.08, H - 0.22),
                            (-0.02, -D - 0.07, H + 0.0), (-0.3, -D - 0.06, H + 0.02), (-0.45, -D - 0.1, H - 0.3),
                            (-0.55, -D - 0.2, 0.05), (-0.35, -D - 0.4, 0.02), (-0.1, -D - 0.45, 0.02))]
for i in range(len(path) - 1):
    seg = (path[i + 1] - path[i]).length
    for k in range(int(seg / 0.05)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.024,
                                             location=path[i].lerp(path[i + 1], k * 0.05 / seg))
        bpy.context.object.data.shade_smooth()
        put(bpy.context.object, pearl, root, body)

# --- lid: arched staves on a hinge at the back top edge, end caps, bands, hasp
hinge = bpy.data.objects.new('hinge', None)
bpy.context.scene.collection.objects.link(hinge)
hinge.parent, hinge.location = root, (0, D, H)
LH, n = 0.34, 8
arc = [(-D + D * math.cos(math.pi * (1 - k / n)), LH * math.sin(math.pi * k / n)) for k in range(n + 1)]
for k in range(n):
    (y0, z0), (y1, z1) = arc[k], arc[k + 1]
    ang = math.atan2(z1 - z0, y1 - y0)
    ln = math.hypot(y1 - y0, z1 - z0)
    nrm = Vector((0, -(z1 - z0), y1 - y0)).normalized() * 0.03
    box((2 * W - 0.02, ln - 0.008, 0.06), ((0, (y0 + y1) / 2 + nrm.y, (z0 + z1) / 2 + nrm.z)),
        (ang + jit(0.01), jit(0.006), 0), mat=oak_lid, parent=hinge, group=lid)
fan = [(0, -D, 0)] + [(0, y, z) for y, z in arc]
for sx in (-1, 1):
    cap = mesh('cap', [(y, -sx * (W - 0.03), z) for _, y, z in fan], [list(range(len(fan)))], smooth=False)
    cap.rotation_euler.z = math.pi / 2  # local X along world Y so the grain runs level
    mod(cap, 'SOLIDIFY', thickness=0.06)
    mod(cap, 'BEVEL', width=0.01, segments=2)
    put(cap, oak_lid, hinge, lid)
for sx in (-0.62, 0.62, -W + 0.05, W - 0.05):
    verts, faces = [], []
    for i, (y, z) in enumerate(arc):
        e = 0.065
        ny, nz = (y + D) / D, z / LH  # outward on the ellipse
        l = math.hypot(ny, nz) or 1
        oy, oz = ny / l * e, nz / l * e
        verts += [(sx - 0.055, y + oy, z + oz), (sx + 0.055, y + oy, z + oz)]
        if i:
            j = 2 * i
            faces.append([j - 2, j - 1, j + 1, j])
    bd = mesh('band', verts, faces, None)
    mod(bd, 'SOLIDIFY', thickness=0.022, offset=1)
    mod(bd, 'BEVEL', width=0.005, segments=1)
    put(bd, iron, hinge, lid)
    for i in range(1, n, 2):
        y, z = verts[2 * i][1], verts[2 * i][2]
        ny, nz = (y + D) / D, z / LH
        rivets((sx, y + ny * 0.02, z + nz * 0.02), (sx, y + ny * 0.02, z + nz * 0.02), 1, (0, ny, nz), hinge, lid)
box((2 * W + 0.04, 0.024, 0.06), (0, -2 * D - 0.012, 0.03), mat=iron, bev=0.006, parent=hinge, group=lid)
box((0.12, 0.02, 0.2), (0, -2 * D - 0.035, -0.06), mat=iron, bev=0.006, parent=hinge, group=lid)
rivets((0, -2 * D - 0.05, 0.0), (0, -2 * D - 0.05, 0.0), 1, (0, -1, 0), hinge, lid)
for sx in (-0.75, 0.75):  # hinges on the back
    box((0.16, 0.02, 0.12), (sx, 0.015, -0.02), mat=iron, bev=0.005, parent=hinge, group=lid)

# --- render: body with the lid hidden, then lid frames with the body held out
OPEN = math.radians(35)
hinge.rotation_euler.x = -OPEN
fit(body + lid, margin=0.12)
hinge.rotation_euler.x = 0
for o in lid:
    o.hide_render = True
mouth = root.matrix_world @ Vector((0, -D, H + 0.05))
sprite('chest', {'base': (0, 0, 0), 'mouth': tuple(mouth)}, crop=False)
for o in lid:
    o.hide_render = False
for o in body:
    o.is_holdout = True
floor.hide_render = True
for f in range(10):
    hinge.rotation_euler.x = -OPEN * f / 9
    sprite(f'chest_lid_{f}', crop=False)
crop_frames(['chest'])  # body and lid frames cropped apart; ox/oy keep them aligned
crop_frames([f'chest_lid_{f}' for f in range(10)])
