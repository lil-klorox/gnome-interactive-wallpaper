# Optional decor that swaps in for a default piece (Settings -> Decor). Each carries the same
# manifest points as the piece it replaces, so tank.js only swaps the name:
#   temple   (castle slot)  base          sunken temple: fluted columns, architrave, fallen drums
#   plane    (ship slot)    base, hole    WW2 fighter nose-down in the sand, hole = open cockpit
#   skeleton (diver slot)   base, valve   treasure hunter's skeleton in a diving helmet by a chest
# Usage: blender -b --factory-startup -P blender/scene_slots.py -- temple|plane|skeleton
# (the gravel substrate is scene_sand.py -- gravel)
import math, os, random, sys
import bpy
from mathutils import Vector as V
sys.path.insert(0, os.path.dirname(__file__))
from common import *

TAU = math.tau
R = random.uniform


def link(o, mat=None, parts=None):
    if mat:
        o.data.materials.append(mat)
    if parts is not None:
        parts.append(o)
    return o


def ring_mesh(name, rings, segs, cap_top=True, cap_bot=True):
    """Mesh from rings of points (each a list of `segs` (x, y, z)), quads between rings, fan caps."""
    verts = [p for r in rings for p in r]
    faces = [[k * segs + i, k * segs + (i + 1) % segs, (k + 1) * segs + (i + 1) % segs, (k + 1) * segs + i]
             for k in range(len(rings) - 1) for i in range(segs)]
    for k, on in ((0, cap_bot), (len(rings) - 1, cap_top)):
        if on:
            c = len(verts)
            verts.append(tuple(sum(p[a] for p in rings[k]) / segs for a in range(3)))
            faces += [[k * segs + i, k * segs + (i + 1) % segs, c] for i in range(segs)]
    o = mesh(name, verts, faces)
    return o


def weather(o, amt=0.03, scale=0.6, bevel=0.0):
    """Chips and lumps: cloud displacement (plus an optional bevel), applied."""
    t = bpy.data.textures.new('w', 'CLOUDS')
    t.noise_scale = scale
    if bevel:
        mod(o, 'BEVEL', width=bevel, segments=2, limit_method='ANGLE')
    mod(o, 'DISPLACE', texture=t, strength=amt, texture_coords='GLOBAL')
    apply_all(o)
    return o


def tube(name, pts, rad, mat, parts):
    o = curve(name, [pts], 1.0, mat, res=3, radii=rad)
    return link(o, None, parts)


# ---------- temple ----------

def column(name, H, Rr, mat, broken=0.0, flutes=20):
    """Fluted column with entasis; broken > 0 = jagged snapped top that far below H."""
    segs, n = flutes * 4, 24
    top = H - broken
    jag = [0.18 * math.sin(i / segs * TAU * 3 + 1.3) + 0.1 * math.sin(i / segs * TAU * 7) for i in range(segs)]
    rings = []
    for k in range(n + 1):
        z = top * k / n
        rz = Rr * (1 - 0.12 * (z / H) ** 1.5)
        ring = []
        for i in range(segs):
            a = i / segs * TAU
            f = 1 - 0.07 * (0.5 + 0.5 * math.cos(flutes * a)) ** 0.6
            zz = z + (jag[i] * broken * 0.3 if broken and k == n else 0)
            ring.append((rz * f * math.cos(a), rz * f * math.sin(a), zz))
        rings.append(ring)
    o = ring_mesh(name, rings, segs)
    o.data.shade_smooth()
    return weather(link(o, mat), 0.015, 0.4)


def capital(loc, Rr, mat, parts):
    """Doric capital: necking ring, flared echinus, square abacus."""
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=Rr * 0.9, radius2=Rr * 1.25, depth=0.22,
                                    location=(loc[0], loc[1], loc[2] + 0.11))
    e = link(weather(bpy.context.object, 0.012, 0.3, 0.02), mat, parts)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2] + 0.3))
    a = bpy.context.object
    a.scale = (Rr * 2.7, Rr * 2.7, 0.16)
    link(weather(a, 0.02, 0.3, 0.02), mat, parts)
    return e


def streaks(m):
    """Dark rust/silt streaks running down from ledges: noise stretched along z, multiplied in."""
    bs = principled(m)
    mp = N(m, 'Mapping', Vector=(N(m, 'TexCoord'), 'Object'), Scale=(7.0, 7.0, 0.5))
    nz = N(m, 'MapRange', Value=(N(m, 'TexNoise', Vector=mp, Scale=2.0, Detail=4.0), 'Fac'),
           **{'From Min': 0.45, 'From Max': 0.75, 'To Min': 1.0, 'To Max': 0.55})
    mix = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, B=(nz, 'Result'))
    m.node_tree.links.new(bs.inputs['Base Color'].links[0].from_socket, sock(mix.inputs, 'A'))
    m.node_tree.links.new(sock(mix.outputs, 'Result'), bs.inputs['Base Color'])
    return m


def temple():
    scenery()
    seed(5)
    parts = []
    marble = streaks(pbr('marble', (0.36, 0.3, 0.21), (0.64, 0.55, 0.41), rough=0.6, scale=1.2, bump=0.35, moss=0.5,
                         grime=0.9, strata=0.35))
    old = streaks(pbr('oldmarble', (0.26, 0.22, 0.16), (0.52, 0.45, 0.33), rough=0.75, scale=1.6, bump=0.5, moss=0.6,
                      grime=0.95, cracks=0.1, strata=0.3, vor=0.3))
    # stylobate: two worn steps, sunk at the front-left
    for i, (w, d, z) in enumerate(((3.6, 1.5, -0.1), (3.1, 1.15, 0.2))):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.05, 0.25, z))
        s = bpy.context.object
        s.scale = (w, d, 0.3)
        s.rotation_euler = (0.03, -0.035, 0.02)
        link(weather(s, 0.06, 0.5, 0.04), old, parts)
    Rr = 0.34
    # back-left full column with capital, carrying a broken architrave to the middle column
    cols = [(-1.15, 0.45, 4.3, 0.0), (0.05, 0.5, 4.3, 0.0), (1.2, 0.4, 4.3, 2.6)]
    for i, (x, y, H, br) in enumerate(cols):
        c = column(f'col{i}', H, Rr, marble, broken=br)
        c.location = (x, y, 0.25)
        c.rotation_euler = (0, 0.02 * (i - 1), R(0, 1))
        parts.append(c)
        if not br:
            capital((x, y, 0.25 + H), Rr, marble, parts)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.45, 0.47, 0.25 + 4.3 + 0.62))
    ar = bpy.context.object
    ar.scale = (1.95, 0.75, 0.5)
    ar.rotation_euler = (0, 0.06, 0)
    link(weather(ar, 0.07, 0.45, 0.03), old, parts)
    # triglyph grooves on the architrave front: three dark slots
    for gx in (-1.0, -0.45, 0.1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(gx, 0.47 - 0.38, 0.25 + 4.3 + 0.62))
        g = bpy.context.object
        g.scale = (0.05, 0.03, 0.36)
        g.rotation_euler = (0, 0.06, 0)
        link(g, old, parts)
    # fallen drums and a toppled capital on the sand in front
    for i, (x, y, l, rot) in enumerate(((1.75, -0.7, 0.75, 0.4), (0.95, -1.05, 0.6, -0.2), (-1.65, -0.9, 0.5, 1.2))):
        d = column(f'drum{i}', l, Rr * 0.95, marble)
        d.rotation_euler = (math.pi / 2, 0, rot)
        d.location = (x, y, Rr * 0.75)
        parts.append(d)
    capital((0.25, -1.2, -0.05), Rr, old, parts)
    for o in parts[-2:]:
        o.rotation_euler = (0.5, 0.35, 0.2)
    # pediment corner leaning against the steps
    v = [(-0.9, 0, 0), (0.9, 0, 0), (0.3, 0, 0.8)]
    pd = mesh('pediment', [(x, y - 0.12, z) for x, y, z in v] + [(x, y + 0.12, z) for x, y, z in v],
              [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)], smooth=False)
    pd.location, pd.rotation_euler = (-1.3, -0.25, 0.05), (math.radians(-15), 0, math.radians(18))
    mod(pd, 'SUBSURF', levels=2, render_levels=2, subdivision_type='SIMPLE')
    link(weather(pd, 0.06, 0.4), old, parts)
    algae(parts, [(-1.15, 0.2, 0.25), (1.2, 0.3, 1.9), (0.05, 0.1, 0.4), (-1.4, -0.4, 0.0), (1.9, -0.4, 0.0)])
    ground(14, soft=7, power=12000)
    bpy.data.objects['contact'].location = (0, 0.3, 6.0)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -0.1, 0))
    foot = bpy.context.object
    foot.scale = (4.6, 3.0, 1)
    fit(parts + [foot], margin=0.05)
    bpy.data.objects.remove(foot)
    sprite('temple', {'base': (0, 0.3, 0)})


def algae(parts, spots):
    """Tufts of stringy green algae and a few red sprigs at the given spots."""
    mats = [pbr('alg', (0.04, 0.11, 0.02), (0.16, 0.28, 0.05), rough=0.6, scale=10, bump=0.2, sss=0.4, grime=0.3),
            pbr('red', (0.18, 0.03, 0.02), (0.4, 0.08, 0.05), rough=0.6, scale=10, bump=0.2, sss=0.4, grime=0.3)]
    for k, (x, y, z) in enumerate(spots):
        for j in range(9):
            a, h = R(0, TAU), R(0.15, 0.45)
            pts = [(x + math.cos(a) * h * 0.4 * t + 0.04 * math.sin(t * 6 + j), y + math.sin(a) * 0.1 * t, z + h * t)
                   for t in (i / 6 for i in range(7))]
            tube('tuft', pts, lambda t: 0.012 * (1 - 0.8 * t), mats[1 if j == 0 and k % 2 else 0], parts)


# ---------- plane ----------

def plane():
    scenery()
    seed(41)
    parts = []
    paint = streaks(pbr('paint', (0.055, 0.065, 0.032), (0.14, 0.15, 0.075), rough=0.75, scale=2.0, bump=0.2, moss=0.3, grime=0.8))
    # peeling paint: bare corroded aluminium shows through in blotches
    nt = paint.node_tree
    bs = principled(paint)
    pn = N(paint, 'TexNoise', Vector=(N(paint, 'TexCoord'), 'Object'), Scale=2.5, Detail=10.0, Roughness=0.7)
    peel = N(paint, 'MapRange', Value=(pn, 'Fac'), **{'From Min': 0.61, 'From Max': 0.63})
    alu = N(paint, 'Mix', _data_type='RGBA', Factor=(peel, 'Result'), B=(0.32, 0.31, 0.28, 1))
    nt.links.new(bs.inputs['Base Color'].links[0].from_socket, sock(alu.inputs, 'A'))
    nt.links.new(sock(alu.outputs, 'Result'), bs.inputs['Base Color'])
    nt.links.new(peel.outputs['Result'], bs.inputs['Metallic'])
    rust = pbr('rust', (0.08, 0.035, 0.015), (0.3, 0.12, 0.04), rough=0.9, metal=0.2, scale=6, bump=0.7, vor=0.5, grime=0.8)
    glass = pbr('canopy', (0.02, 0.04, 0.04), (0.06, 0.09, 0.08), rough=0.25, scale=4, bump=0.1, moss=0.4, grime=0.4)
    red = pbr('nosepaint', (0.2, 0.04, 0.02), (0.4, 0.1, 0.04), rough=0.8, scale=3, bump=0.3, moss=0.3, grime=0.8)
    dark = pbr('cockpit', (0.004, 0.006, 0.007), rough=1.0, scale=3, grime=0.0)
    L = 8.0

    def rad(u):  # fuselage radius along u in 0 (tail) .. 1 (nose): thin tail, fat middle, blunt engine cowl
        if u < 0.62:
            return 0.1 + 0.45 * math.sin(math.pi / 2 * u / 0.62) ** 0.8
        return 0.55 - 0.14 * ((u - 0.62) / 0.38) ** 2

    segs, n = 32, 40
    rings = [[(u * L - L / 2, rad(u) * math.cos(a), rad(u) * 1.12 * math.sin(a) + 0.12 * (1 - u) ** 2)
              for a in (i / segs * TAU for i in range(segs))] for u in (k / n for k in range(n + 1))]
    fus = link(ring_mesh('fuselage', rings, segs), paint, parts)
    fus.data.shade_smooth()
    weather(fus, 0.015, 0.3)

    def surface(name, root, span, c0, c1, sweep, dz, side, mat):
        """Tapered wing/tail panel with a thin rounded airfoil; side = +1/-1 for direction in y."""
        m, k = 12, 10
        rings = []
        for j in range(k + 1):
            t = j / k
            c = c0 + (c1 - c0) * t ** 1.4 * (1 if t < 0.9 else 1 + (t - 0.9) * 2)
            x0 = root[0] - sweep * t
            ring = []
            for i in range(m):
                a = i / m * TAU
                ring.append((x0 + c * 0.5 * math.cos(a), root[1] + side * span * t, root[2] + dz * t + c * 0.06 * math.sin(a)))
            rings.append(ring)
        o = link(ring_mesh(name, rings, m), mat, parts)
        o.data.shade_smooth()
        return weather(o, 0.01, 0.4)

    surface('wingL', (0.6, -0.3, -0.25), 3.6, 1.9, 0.7, 0.45, 0.35, -1, paint)
    surface('wingR', (0.6, 0.3, -0.25), 3.6, 1.9, 0.7, 0.45, 0.35, 1, paint)
    surface('tailL', (-3.6, -0.1, 0.25), 1.3, 0.9, 0.4, 0.25, 0.05, -1, paint)
    surface('tailR', (-3.6, 0.1, 0.25), 1.3, 0.9, 0.4, 0.25, 0.05, 1, paint)
    fin = surface('fin', (-3.6, 0.0, 0.3), 1.2, 1.1, 0.45, 0.5, 0.0, 1, paint)
    fin.rotation_euler = (math.pi / 2, 0, 0)
    fin.location = (0, 0.3, -0.3)
    # faded roundel on the near side of the fuselage
    u = 0.3
    for r, c in ((0.3, (0.05, 0.07, 0.15)), (0.19, (0.5, 0.48, 0.42)), (0.09, (0.25, 0.05, 0.03))):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=0.01, rotation=(math.pi / 2, 0, 0),
                                            location=(u * L - L / 2, -rad(u) - 0.01 - (0.3 - r) * 0.02, 0.12 * (1 - u) ** 2))
        link(bpy.context.object, pbr('roundel', c, rough=0.8, scale=3, bump=0.3, moss=0.2, grime=0.6), parts)
    # open cockpit: dark well, canopy slid back and cracked, gun sight bar
    cx = 0.35
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=(cx, 0, 0.62))
    well = bpy.context.object
    well.scale = (0.55, 0.32, 0.12)
    link(well, dark, parts)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1, location=(cx - 0.75, 0, 0.62))
    can = bpy.context.object
    can.scale = (0.7, 0.33, 0.3)
    bpy.ops.object.shade_smooth()
    link(weather(can, 0.02, 0.2), glass, parts)
    for fx in (-0.25, 0.25):
        tube('frame', [(cx - 0.75 + fx * 1.6, -0.3 * math.cos(a), 0.62 + 0.3 * math.sin(a)) for a in (i / 8 * math.pi for i in range(9))],
             lambda t: 0.025, rust, parts)
    # nose: spinner and three blades, two bent back where they hit the sand
    nose = (L / 2 + 0.05, 0, 0.0)
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.42, depth=0.6, location=(nose[0] + 0.25, 0, 0), rotation=(0, math.pi / 2, 0))
    link(weather(bpy.context.object, 0.01, 0.3), red, parts)
    for i, bend in enumerate((0.0, 0.9, 1.4)):
        a = i / 3 * TAU + 0.4
        pts = []
        for t in (j / 8 for j in range(9)):
            r = 0.3 + 1.5 * t
            b = bend * t * t
            pts.append((nose[0] + 0.1 - b * 0.9 * r * 0.4, math.cos(a) * r * (1 - b * 0.2), math.sin(a) * r * (1 - b * 0.2)))
        tube('blade', pts, lambda t: 0.09 * (1 - 0.5 * t) + 0.02, rust, parts)
    # exhaust stubs and panel rivet lines are below sprite resolution; a few dents instead
    root = bpy.data.objects.new('plane', None)
    bpy.context.scene.collection.objects.link(root)
    for o in parts:
        o.parent = root
    root.rotation_euler = (math.radians(9), math.radians(14), math.radians(-12))  # nose down, rolled toward us
    root.location = (0, 0, 1.05)
    bpy.context.view_layer.update()
    hole = root.matrix_world @ V((cx, 0, 0.66))
    # whatever dug into the sand is cut off by an invisible holdout floor just under the contact shadow
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -0.004))
    ho = new_mat('holdout')
    N(ho, 'OutputMaterial', Surface=N(ho, 'Holdout'))
    link(bpy.context.object, ho)
    algae(parts, [(0.0, -2.2, 0.0), (-2.5, 0.6, 1.3), (3.0, -0.8, 0.2)])
    ground(16)
    objs = [o for o in parts if o.type in ('MESH', 'CURVE')]
    fit(objs, margin=0.3)
    sprite('plane', {'base': (0, 0, 0), 'hole': tuple(hole)})


# ---------- skeleton ----------

def skeleton():
    scenery()
    seed(23)
    parts = []
    bone = pbr('bone', (0.36, 0.32, 0.22), (0.66, 0.6, 0.46), rough=0.7, scale=6, bump=0.4, vor=0.3, moss=0.35, grime=0.85, sss=0.1)
    copper = pbr('helmet', (0.22, 0.1, 0.04), (0.55, 0.3, 0.12), rough=0.4, metal=0.85, scale=3, bump=0.25, moss=0.6, grime=0.85)
    brass = pbr('brass', (0.3, 0.2, 0.06), (0.55, 0.4, 0.15), rough=0.35, metal=1.0, scale=5, bump=0.2, moss=0.3, grime=0.8)
    glass = pbr('port', (0.004, 0.01, 0.012), rough=0.08, scale=3, grime=0.0)
    wood = pbr('chestwood', (0.06, 0.03, 0.012), (0.18, 0.09, 0.035), rough=0.8, scale=3, bump=0.4, moss=0.5, grime=0.85, strata=0.6)
    iron = pbr('iron', (0.05, 0.03, 0.02), (0.22, 0.09, 0.03), rough=0.85, metal=0.4, scale=7, bump=0.6, vor=0.5, grime=0.8)
    gold = pbr('gold', (0.9, 0.48, 0.08), (1.0, 0.7, 0.25), rough=0.3, metal=1.0, scale=40, bump=0.1, grime=0.7)
    # chest behind him
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.15, 0.75, 0.38))
    ch = bpy.context.object
    ch.scale = (1.5, 0.85, 0.85)
    ch.rotation_euler = (0, 0, 0.12)
    link(weather(ch, 0.03, 0.5, 0.03), wood, parts)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.18, 1.25, 1.05))
    lid = bpy.context.object
    lid.scale = (1.5, 0.12, 0.8)
    lid.rotation_euler = (-0.35, 0, 0.12)
    link(weather(lid, 0.03, 0.5, 0.03), wood, parts)
    for bx in (-0.45, 0.75):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(bx, 0.33, 0.38))
        b = bpy.context.object
        b.scale = (0.08, 0.03, 0.87)
        b.rotation_euler = (0, 0, 0.12)
        link(b, iron, parts)
    # coins spilling out over the sand
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.07, depth=0.015)
    coin = bpy.context.object
    coin.location = (0, -40, 0)
    link(coin, gold)
    for i in range(60):
        c = coin.copy()
        t = R(0, 1)
        c.location = (0.9 + t * 0.7 + R(-0.25, 0.25), 0.2 - t * 0.6 + R(-0.2, 0.2), 0.01 + R(0, 0.06) * (1 - t))
        c.rotation_euler = (R(-0.6, 0.6), R(-0.6, 0.6), R(0, TAU))
        bpy.context.scene.collection.objects.link(c)
        parts.append(c)
    # skeleton sitting against the chest: pelvis, spine, ribs, limbs (tapered tubes), feet
    hip = V((-0.1, 0.15, 0.22))
    for side in (-1, 1):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.16, location=hip + V((side * 0.14, 0.02, 0.05)))
        w = bpy.context.object
        w.scale, w.rotation_euler = (1.1, 0.3, 0.75), (0.3, side * 0.7, side * 0.5)
        link(weather(w, 0.03, 0.15), bone, parts)
    spine = [hip + V((0, 0.08 + 0.04 * math.sin(t * 2), 0.1 + t * 1.0)) for t in (i / 10 for i in range(11))]
    for p in spine:
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.055, depth=0.06, location=p)
        link(weather(bpy.context.object, 0.01, 0.1), bone, parts)
    chest_c = hip + V((0, 0.05, 0.75))
    for k in range(8):  # ribs: arcs round the front, shorter toward the bottom
        z = chest_c.z + 0.28 - k * 0.075
        w = 0.32 - abs(k - 2) * 0.025
        for side in (-1, 1):
            pts = [(chest_c.x + side * w * math.sin(a), chest_c.y + 0.08 - 0.22 * (1 - math.cos(a)) * 1.2, z - 0.14 * a + 0.05 * math.sin(a))
                   for a in (i / 8 * 2.6 for i in range(9))]
            tube('rib', pts, lambda t: 0.018, bone, parts)
    tube('sternum', [chest_c + V((0, -0.37, 0.25)), chest_c + V((0, -0.4, -0.05))], lambda t: 0.025, bone, parts)
    sh = chest_c + V((0, 0.05, 0.38))
    tube('clavicle', [sh + V((-0.36, 0, 0)), sh, sh + V((0.36, 0, 0))], lambda t: 0.02, bone, parts)
    limb = lambda pts, r: tube('limb', pts, lambda t: r * (1.2 - 0.4 * math.sin(math.pi * t)), bone, parts)
    # left arm resting on the knee, right arm draped over the coins
    limb([sh + V((-0.36, 0, 0)), V((-0.6, 0.0, 0.6)), V((-0.5, -0.4, 0.45))], 0.03)
    limb([V((-0.5, -0.4, 0.45)), V((-0.35, -0.75, 0.55))], 0.025)
    limb([sh + V((0.36, 0, 0)), V((0.6, 0.05, 0.55)), V((0.75, -0.1, 0.25))], 0.03)
    limb([V((0.75, -0.1, 0.25)), V((1.0, -0.25, 0.06))], 0.025)
    for side, knee in ((-1, V((-0.3, -0.75, 0.55))), (1, V((0.15, -0.95, 0.18)))):
        h = hip + V((side * 0.15, -0.05, 0))
        limb([h, knee], 0.04)
        foot = knee + V((side * 0.05, -0.45, -knee.z + 0.05))
        limb([knee, foot], 0.032)
        tube('foot', [foot, foot + V((side * 0.03, -0.2, -0.02))], lambda t: 0.04 * (1 - 0.5 * t), bone, parts)
    for j in (V((-0.6, 0.0, 0.6)), V((0.6, 0.05, 0.55)), V((-0.5, -0.4, 0.45)), V((0.75, -0.1, 0.25)),
              V((-0.3, -0.75, 0.55)), V((0.15, -0.95, 0.18))):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.05, location=j)
        link(bpy.context.object, bone, parts)
    for hand in (V((-0.33, -0.8, 0.55)), V((1.03, -0.28, 0.05))):
        for f in range(4):
            tube('finger', [hand, hand + V(((f - 1.5) * 0.03, -0.1, -0.05))], lambda t: 0.009, bone, parts)
    # the helmet: copper dome, brass breastplate collar, three portholes, valve on top
    head = sh + V((0.02, -0.02, 0.42))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.4, location=head)
    hm = bpy.context.object
    hm.scale = (1, 1, 1.05)
    hm.rotation_euler = (0.15, -0.2, 0)
    bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.12, depth=0.5, location=head + V((0, -0.4, 0.02)), rotation=(math.pi / 2, 0, 0))
    cut = bpy.context.object
    mod(hm, 'BOOLEAN', object=cut, operation='DIFFERENCE')
    apply_all(hm)
    bpy.data.objects.remove(cut)
    mod(hm, 'SOLIDIFY', thickness=0.02)
    link(weather(hm, 0.008, 0.2), copper, parts)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.2, location=head + V((0, 0.0, -0.02)))
    sk = bpy.context.object
    sk.scale = (0.85, 1.0, 1.05)
    link(weather(sk, 0.01, 0.1), bone, parts)
    for ex in (-0.07, 0.07):  # eye sockets
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.05, location=head + V((ex, -0.17, 0.02)))
        link(bpy.context.object, glass, parts)
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=0.5, radius2=0.3, depth=0.2, location=sh + V((0, 0, 0.02)))
    col = bpy.context.object
    col.scale = (1, 0.85, 1)
    link(weather(col, 0.01, 0.2, 0.02), brass, parts)
    for d in (V((0, -1, 0.05)), V((-0.85, -0.5, 0.0)), V((0.85, -0.5, 0.0))):
        d.normalize()
        p = head + d * 0.39
        bpy.ops.mesh.primitive_torus_add(major_radius=0.13 if d.y < -0.9 else 0.09, minor_radius=0.03, location=p)
        t = bpy.context.object
        t.rotation_euler = aim(d)
        link(t, brass, parts)
        if d.y < -0.9:
            continue  # front glass long gone: the skull looks out
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.08, depth=0.02, location=p - d * 0.01)
        g = bpy.context.object
        g.rotation_euler = aim(d)
        link(g, glass, parts)
    vtop = head + V((0.18, 0.05, 0.38))
    tube('valve', [head + V((0.1, 0.03, 0.3)), vtop], lambda t: 0.045, brass, parts)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.06, minor_radius=0.015, location=vtop)
    link(bpy.context.object, brass, parts)
    algae(parts, [(-0.9, 0.5, 0.0), (0.9, 1.0, 0.75), (1.4, 0.1, 0.0)])
    root = bpy.data.objects.new('skel', None)
    bpy.context.scene.collection.objects.link(root)
    for o in parts:
        o.parent = root
    root.scale = (1.5, 1.5, 1.5)
    bpy.context.view_layer.update()
    vtop = root.matrix_world @ vtop
    ground(14)
    c = bpy.data.objects['contact']
    c.location.z, c.data.size, c.data.energy = 6.0, 2.5, 27000
    objs = [o for o in parts if o.type in ('MESH', 'CURVE')]
    fit(objs, margin=0.25)
    sprite('skeleton', {'base': (0, 0, 0), 'valve': tuple(vtop + V((0, 0, 0.04)))})


PIECES = {'temple': temple, 'plane': plane, 'skeleton': skeleton}
want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(PIECES)
for w in want:
    if w not in PIECES:
        sys.exit(f'scene_slots.py: unknown piece {w}; choose from {list(PIECES)}')
    PIECES[w]()
