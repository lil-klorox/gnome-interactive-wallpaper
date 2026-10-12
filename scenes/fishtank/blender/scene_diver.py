# Deep-sea diver in a Mark V rig: aged brass helmet and corselet, canvas suit, lead boots, air hose.
import math, os, random, sys
import bpy
import numpy as np
from mathutils import Vector, noise
sys.path.insert(0, os.path.dirname(__file__))
from common import *

scenery()
seed(11)
ground(14)
c = bpy.data.objects['contact']  # he is taller than the default contact light: lift it over his head
c.location.z, c.data.size, c.data.energy = 6.0, 2.5, 27000
root = bpy.data.objects.new('root', None)
bpy.context.scene.collection.objects.link(root)
parts = []


def link(o, mat):
    if mat:
        o.data.materials.append(mat)
    o.parent = root
    parts.append(o)
    return o


def aged_brass(name, verdigris=0.6):
    """Polished brass worn to brown tarnish, green verdigris packed into crevices."""
    m = new_mat(name)
    co = N(m, 'TexCoord')
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=6.0, Detail=8.0)
    base = ramp(m, (nz, 'Fac'), [(0.35, (0.2, 0.11, 0.04)), (0.62, (0.62, 0.4, 0.13))])
    ao = N(m, 'AmbientOcclusion', Distance=0.15, _samples=8)
    vn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=14.0, Detail=6.0)
    v = N(m, 'MapRange', Value=M(m, 'SUBTRACT', M(m, 'MULTIPLY', (ao, 'AO'), 1.25), M(m, 'MULTIPLY', (vn, 'Fac'), verdigris)),
          **{'From Min': 0.35, 'From Max': 0.75, 'To Min': 1.0, 'To Max': 0.0})
    # open verdigris blooms on the plain surfaces too, not only in crevices
    pn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=2.2, Detail=5.0)
    bloom = N(m, 'MapRange', Value=M(m, 'ADD', (pn, 'Fac'), M(m, 'MULTIPLY', (vn, 'Fac'), 0.15)),
              **{'From Min': 0.6, 'From Max': 0.68, 'To Max': 0.4 + 0.5 * verdigris})
    v = (M(m, 'MAXIMUM', (v, 'Result'), (bloom, 'Result')), 0)
    # scratches: thin long cells (stretched voronoi edges), only some, rubbed back to bright metal
    def scratch(rot, sc):
        mp = N(m, 'Mapping', Vector=(co, 'Object'), Rotation=(0, rot, rot * 0.7), Scale=(1.0, 1.0, 22.0))
        e = N(m, 'TexVoronoi', Vector=mp, Scale=sc, _feature='DISTANCE_TO_EDGE')
        keep = N(m, 'MapRange', Value=(N(m, 'TexNoise', Vector=(co, 'Object'), Scale=5.0), 'Fac'), **{'From Min': 0.55, 'From Max': 0.6})
        return M(m, 'MULTIPLY', (N(m, 'MapRange', Value=(e, 'Distance'), **{'From Max': 0.025, 'To Min': 1.0, 'To Max': 0.0}), 'Result'),
                 (keep, 'Result'))
    scr = M(m, 'MAXIMUM', scratch(0.6, 9.0), scratch(-1.1, 14.0))
    v = (M(m, 'MULTIPLY', v, M(m, 'SUBTRACT', 1.0, scr)), 0)
    col = N(m, 'Mix', _data_type='RGBA', Factor=v, A=(base, 'Color'), B=(0.08, 0.25, 0.17, 1))
    col = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', scr, 0.8), A=(col, 'Result'), B=(0.75, 0.52, 0.22, 1))
    met = N(m, 'MapRange', Value=v, **{'To Min': 1.0, 'To Max': 0.0})
    rough = N(m, 'MapRange', Value=M(m, 'ADD', v, M(m, 'MULTIPLY', (nz, 'Fac'), 0.4)), **{'To Min': 0.22, 'To Max': 0.9})
    b = N(m, 'Bump', Strength=0.25, Distance=0.01, Height=M(m, 'SUBTRACT', M(m, 'ADD', (vn, 'Fac'), v), M(m, 'MULTIPLY', scr, 0.3)))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (col, 'Result'), 'Metallic': (met, 'Result'),
                                                             'Roughness': (rough, 'Result'), 'Normal': b}))
    return m


def canvas(name):
    """Heavy twill canvas: woven bump, stains darkening toward the boots, soft sheen."""
    m = new_mat(name)
    co = N(m, 'TexCoord')
    w1 = N(m, 'TexWave', Vector=(co, 'Object'), Scale=180.0, _bands_direction='DIAGONAL')
    w2 = N(m, 'TexWave', Vector=(co, 'Object'), Scale=120.0, _bands_direction='Z')
    nz = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=3.0, Detail=10.0)
    geo = N(m, 'NewGeometry')
    z = N(m, 'SeparateXYZ', Vector=(geo, 'Position'))
    dirt = N(m, 'MapRange', Value=M(m, 'ADD', (z, 'Z'), M(m, 'MULTIPLY', (nz, 'Fac'), 0.9)), **{'From Min': 0.6, 'From Max': 1.9,
                                                                                            'To Min': 1.0, 'To Max': 0.0})
    base = ramp(m, (nz, 'Fac'), [(0.3, (0.27, 0.17, 0.075)), (0.72, (0.5, 0.36, 0.18))])
    sn = N(m, 'TexNoise', Vector=(co, 'Object'), Scale=3.5, Detail=4.0)  # water stains
    stain = N(m, 'MapRange', Value=(sn, 'Fac'), **{'From Min': 0.4, 'From Max': 0.62, 'To Min': 0.68, 'To Max': 1.1})
    base = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(base, 'Color'), B=(stain, 'Result'))
    col = N(m, 'Mix', _data_type='RGBA', Factor=(dirt, 'Result'), A=(base, 'Result'), B=(0.13, 0.12, 0.07, 1))
    col = ao_grime(m, (col, 'Result'), 0.12, 0.3)
    b = N(m, 'Bump', Strength=0.18, Distance=0.004, Height=M(m, 'ADD', (w1, 'Fac'), (w2, 'Fac')))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': 0.85,
                                                             'Sheen Weight': 0.15, 'Normal': b}))
    return m


brass = aged_brass('brass', 0.45)
copper = aged_brass('copper', 0.9)
next(n for n in copper.node_tree.nodes if n.type == 'VALTORGB').color_ramp.elements[1].color = (0.62, 0.27, 0.12, 1)
cloth = canvas('canvas')
rubber = pbr('rubber', (0.02, 0.018, 0.016), (0.06, 0.05, 0.04), rough=0.55, scale=5, bump=0.15, grime=0.4)
lead = pbr('lead', (0.05, 0.055, 0.06), (0.14, 0.15, 0.16), rough=0.6, metal=0.4, scale=5, bump=0.5, vor=0.5, grime=0.7)
leather = pbr('leather', (0.06, 0.03, 0.015), (0.17, 0.09, 0.04), rough=0.55, scale=8, bump=0.3, grime=0.6)
glass = new_mat('glass')
N(glass, 'OutputMaterial', Surface=N(glass, 'BsdfPrincipled', **{'Base Color': (0.004, 0.012, 0.012, 1), 'Roughness': 0.04,
                                                                 'Coat Weight': 1.0, 'Specular IOR Level': 1.0}))


def lathe(name, prof, mat, sy=1.0, segs=48, loc=(0, 0, 0), smooth=True):
    """Surface of revolution from (radius, z) pairs around Z, squashed by sy in Y."""
    verts = [(r * math.cos(a), r * math.sin(a) * sy, z) for r, z in prof
             for a in (2 * math.pi * i / segs for i in range(segs))]
    faces = [[k * segs + i, k * segs + (i + 1) % segs, (k + 1) * segs + (i + 1) % segs, (k + 1) * segs + i]
             for k in range(len(prof) - 1) for i in range(segs)]
    o = mesh(name, verts, faces, None, smooth)
    o.location = loc
    return link(o, mat)


def tube(name, pts, radii, mat, caps=True):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.resolution_u, cu.use_fill_caps = '3D', 1.0, 6, 16, caps
    sp = cu.splines.new('NURBS')
    sp.points.add(len(pts) - 1)
    for p, co, r in zip(sp.points, pts, radii):
        p.co, p.radius = (*co, 1), r
    sp.use_endpoint_u, sp.order_u = True, 3
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    o.data.shade_smooth()
    return link(o, mat)


def wrinkle(o, amp, freq, sub=1):
    """Canvas folds: rings along Z broken up by noise, pushed out along the normals."""
    if sub:
        mod(o, 'SUBSURF', levels=sub, render_levels=sub)
        p = o.parent
        o.parent = None
        apply_all(o)
        o.parent = p
    me = o.data
    n = len(me.vertices)
    co, nr = np.empty(n * 3), np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    me.vertices.foreach_get('normal', nr)
    co, nr = co.reshape(n, 3), nr.reshape(n, 3)
    off = np.array([noise.noise(Vector(c) * 2.5) for c in co])
    fold = np.abs(np.sin(co[:, 2] * freq * (1 + off * 0.3) + off * 5 + co[:, 0] * 3)) ** 4
    co += nr * (fold * amp + off * amp * 0.5)[:, None]
    me.vertices.foreach_set('co', co.ravel())
    me.update()


def nubs(n_, r, h, mat, places, verts=6):
    """Hex nuts / bolt heads: places = [(loc, normal)]."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h)
    src = bpy.context.object
    mod(src, 'BEVEL', width=r * 0.15, segments=1)
    apply_all(src)
    me = src.data
    bpy.data.objects.remove(src)
    me.materials.append(mat)
    for loc, nrm in places:
        o = bpy.data.objects.new(n_, me)
        bpy.context.scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = aim(nrm)
        o.rotation_euler.rotate_axis('Z', random.uniform(0, 1))
        o.parent = root
        parts.append(o)


def sph(name, r, loc, scale=(1, 1, 1), mat=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    o.data.shade_smooth()
    return link(o, mat)


# --- boots: lead soles, canvas uppers, brass toe caps, laces
for sx in (-1, 1):
    x = sx * 0.3
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -0.05, 0.06))
    sole = bpy.context.object
    sole.scale = (0.36, 0.66, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    mod(sole, 'BEVEL', width=0.03, segments=3)
    link(sole, lead)
    sph('boot', 0.25, (x, 0.0, 0.25), (0.95, 1.25, 0.85), leather)
    sph('toe', 0.17, (x, -0.24, 0.17), (1.0, 1.0, 0.72), copper)
    for k in range(4):  # laces criss-crossing up the front
        z = 0.24 + k * 0.06
        for s in (-1, 1):
            tube('lace', [(x - 0.07 * s, -0.27 + k * 0.02, z), (x, -0.29 + k * 0.02, z + 0.02), (x + 0.07 * s, -0.27 + k * 0.02, z + 0.04)],
                     [0.01] * 3, leather)
    nubs('eyelet', 0.016, 0.01, brass, [((x + s * 0.08, -0.25 + k * 0.02, 0.24 + k * 0.06), (s * 0.4, -1, 0))
                                        for k in range(4) for s in (-1, 1)], verts=10)

# --- legs and torso: canvas tubes with folds
for sx in (-1, 1):
    leg = tube('leg', [(sx * 0.3, 0, 0.3), (sx * 0.29, -0.02, 0.62), (sx * 0.28, -0.08, 0.95), (sx * 0.29, -0.02, 1.3), (sx * 0.27, 0, 1.6)],
               [0.2, 0.22, 0.23, 0.27, 0.3], cloth)
    wrinkle(leg, 0.02, 20)
    tube('seam', [(sx * 0.53, -0.0, 0.42), (sx * 0.53, -0.04, 0.95), (sx * 0.57, 0.0, 1.55)], [0.012] * 3, leather)  # stitched outer seam
torso = lathe('torso', [(0.38, 1.35), (0.47, 1.5), (0.52, 1.8), (0.56, 2.2), (0.57, 2.55), (0.52, 2.8), (0.3, 2.95)], cloth, sy=0.8)
wrinkle(torso, 0.026, 14)
lathe('yoke', [(0.57, 2.37), (0.595, 2.385), (0.595, 2.415), (0.57, 2.43)], leather, sy=0.8)  # chest seam
# belt with lead weights and a brass buckle
lathe('belt', [(0.53, 1.62), (0.555, 1.64), (0.555, 1.8), (0.53, 1.82)], leather, sy=0.82)
for a in (-62, -36, 36, 62, 160, 200):
    t = math.radians(a - 90)
    p = Vector((0.6 * math.cos(t), 0.6 * 0.82 * math.sin(t), 1.66))
    bpy.ops.mesh.primitive_cube_add(size=1, location=p, rotation=(0, 0, t + math.pi / 2))
    w = bpy.context.object
    w.scale = (0.2, 0.08, 0.26)
    mod(w, 'BEVEL', width=0.02, segments=2)
    link(w, lead)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.47, 1.72))
bk = bpy.context.object
bk.scale = (0.16, 0.04, 0.13)
mod(bk, 'BEVEL', width=0.015, segments=2)
link(bk, brass)
# a knife in a sheath on the hip: every diver had one
tube('sheath', [(0.5, -0.25, 1.62), (0.52, -0.28, 1.35), (0.53, -0.3, 1.12)], [0.06, 0.055, 0.035], leather)
tube('handle', [(0.5, -0.25, 1.62), (0.5, -0.25, 1.82)], [0.04, 0.035], copper)

# --- corselet (breastplate) with brail straps and wing nuts, neck ring
lathe('corselet', [(0.74, 2.72), (0.76, 2.8), (0.72, 2.95), (0.6, 3.08), (0.45, 3.16), (0.38, 3.2)], brass, sy=0.82)
lathe('gasket', [(0.72, 2.66), (0.77, 2.68), (0.77, 2.76), (0.72, 2.78)], rubber, sy=0.82)
bolts = []
for i in range(14):
    t = 2 * math.pi * i / 14 + 0.2
    bolts.append(((0.79 * math.cos(t), 0.79 * 0.82 * math.sin(t), 2.75), (math.cos(t), 0.82 * math.sin(t), 0.25)))
nubs('stud', 0.045, 0.06, brass, bolts)
for i in (2, 5, 9, 12):  # wing nuts on the brails
    loc, nrm = bolts[i]
    n = Vector(nrm).normalized()
    for s in (-1, 1):
        sph('wing', 0.065, Vector(loc) + n * 0.04 + Vector((0, 0, s * 0.045)), (0.4, 0.4, 1.0), brass)
for t in (-90, 90, 0, 180):  # brail plates (straps clamping the suit to the corselet)
    r = math.radians(t)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.775 * math.cos(r), 0.775 * 0.82 * math.sin(r), 2.75), rotation=(0, 0, r))
    br = bpy.context.object
    br.scale = (0.03, 0.42, 0.07)
    mod(br, 'BEVEL', width=0.01, segments=2)
    link(br, brass)
lathe('neck', [(0.36, 3.16), (0.42, 3.18), (0.43, 3.26), (0.36, 3.28)], copper, sy=0.95)
nubs('neckbolt', 0.025, 0.04, brass, [((0.43 * math.cos(t), 0.43 * 0.95 * math.sin(t), 3.22), (math.cos(t), math.sin(t), 0))
                                       for t in (2 * math.pi * i / 10 for i in range(10))])

# --- helmet: copper bonnet, ports with grilles, exhaust valve, gooseneck
HC, HR = Vector((0, 0, 3.72)), 0.56
helm = sph('helmet', HR, HC, (1.0, 0.96, 1.05), copper)


def on_helm(yaw, pitch, out=0.0):
    d = Vector((math.sin(math.radians(yaw)) * math.cos(math.radians(pitch)), -math.cos(math.radians(yaw)) * math.cos(math.radians(pitch)),
                math.sin(math.radians(pitch))))
    return HC + d * (HR + out), d


def port(yaw, pitch, r, bars):
    loc, d = on_helm(yaw, pitch, 0.02)
    rot = aim(d)
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.04, location=loc, rotation=rot)
    rim = bpy.context.object
    rim.data.shade_smooth()
    link(rim, brass)
    bpy.ops.mesh.primitive_cylinder_add(radius=r + 0.03, depth=0.05, location=loc - d * 0.02, rotation=rot)
    link(bpy.context.object, glass)
    nubs('portbolt', 0.018, 0.03, brass, [(rim.matrix_world @ Vector((math.cos(a) * (r + 0.05), math.sin(a) * (r + 0.05), 0.0)), d)
                                           for a in (2 * math.pi * i / 6 + 0.5 for i in range(6))])
    for k in range(bars):  # grille bars across the window
        off = (k - (bars - 1) / 2) * r * 0.62
        a = loc + d * 0.04
        bpy.context.view_layer.update()
        mw = rim.matrix_world.to_3x3()
        x, y = mw @ Vector((1, 0, 0)), mw @ Vector((0, 1, 0))
        p0, p1 = a + x * off - y * r * 0.95, a + x * off + y * r * 0.95
        tube('bar', [p0, (p0 + p1) / 2 + d * 0.02, p1], [0.016] * 3, brass)


# riveted band where the bonnet meets the breech ring
zb = HC.z - 0.36
rb = math.sqrt(HR ** 2 - 0.36 ** 2 / 1.05 ** 2) + 0.015
lathe('helmband', [(rb - 0.01, zb - 0.06), (rb + 0.02, zb - 0.05), (rb + 0.02, zb + 0.05), (rb - 0.03, zb + 0.07)], brass, sy=0.96)
nubs('helmrivet', 0.016, 0.03, brass, [((( rb + 0.025) * math.cos(t), (rb + 0.025) * 0.96 * math.sin(t), zb), (math.cos(t), math.sin(t), 0))
                                       for t in (2 * math.pi * i / 22 for i in range(22))], verts=12)
port(0, 4, 0.2, 0)
port(-78, 4, 0.14, 3)
port(78, 4, 0.14, 3)
port(0, 52, 0.09, 0)
# hinged faceplate: a wing nut at the front port
loc = on_helm(0, -26, 0.03)[0]
sph('facewing', 0.06, loc, (1.2, 0.5, 0.5), brass)
# exhaust valve on the right side, slightly back: the bubbles leave here
vl, vd = on_helm(105, 18, 0.0)
vrot = aim(vd)
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.06, depth=0.2, location=vl + vd * 0.08, rotation=vrot)
link(bpy.context.object, brass)
sph('valvecap', 0.075, vl + vd * 0.19, (1, 1, 0.6), brass, rot=vrot)
VALVE = vl + vd * 0.27
# gooseneck air inlet at the back, the hose clamps onto it
gl, gd = on_helm(165, 26, 0.0)
tube('goose', [gl, gl + gd * 0.12, gl + gd * 0.18 + Vector((0, 0.08, -0.08))], [0.055, 0.05, 0.05], brass)

# --- arms: left hangs, right is raised in a little wave; rubber cuffs, gloves
for pts, rad in (([(-0.66, 0.0, 2.62), (-0.76, -0.02, 2.3), (-0.78, -0.08, 2.0), (-0.74, -0.14, 1.75), (-0.7, -0.18, 1.55)], [0.25, 0.22, 0.2, 0.18, 0.15]),
                 ([(0.66, 0.0, 2.62), (0.86, -0.04, 2.42), (1.0, -0.12, 2.25), (1.06, -0.25, 2.5), (1.08, -0.32, 2.78)], [0.25, 0.22, 0.2, 0.18, 0.15])):
    arm = tube('arm', pts, rad, cloth)
    wrinkle(arm, 0.02, 22)
    w = Vector(pts[-1])
    dirn = (w - Vector(pts[-2])).normalized()
    rot = aim(dirn)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.13, minor_radius=0.045, location=w, rotation=rot)
    link(bpy.context.object, rubber)
    hand = w + dirn * 0.15
    sph('glove', 0.13, hand, (0.8, 1.0, 1.25), cloth, rot=rot)
    sph('thumb', 0.055, hand + Vector((0.08 if w.x > 0 else -0.08, -0.08, 0.02)), (1, 1, 1.6), cloth, rot=rot)
# shoulder seams
for sx in (-1, 1):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.23, minor_radius=0.018, location=(sx * 0.66, 0, 2.6), rotation=(0, math.pi / 2 + sx * 0.4, 0))
    link(bpy.context.object, cloth)

# --- air hose: off the gooseneck, arcs behind, loops down into the sand
hose = tube('hose', [gl + gd * 0.18 + Vector((0, 0.08, -0.08)), (0.3, 0.9, 3.4), (0.6, 1.2, 2.6), (1.3, 1.0, 1.8),
                     (1.6, 0.6, 0.9), (1.4, 0.2, 0.15), (1.9, -0.2, 0.05), (2.3, 0.3, 0.02), (2.6, 0.6, -0.15)], [0.065] * 9, None)
hm = pbr('hose', (0.03, 0.028, 0.022), (0.09, 0.075, 0.05), rough=0.6, scale=4, bump=0.2, grime=0.5)
w = N(hm, 'TexWave', Vector=(N(hm, 'TexCoord'), 'UV'), Scale=60.0, _bands_direction='X')
bmp = next(n for n in hm.node_tree.nodes if n.type == 'BUMP')
hm.node_tree.links.new(w.outputs['Fac'], bmp.inputs['Height'])
bmp.inputs['Strength'].default_value = 0.5
hose.data.materials.append(hm)

# --- pose: a 3/4 turn and a small lean so he is not standing to attention
root.rotation_euler = (math.radians(1.5), math.radians(-3), math.radians(-22))
root.location.z = -0.03  # boots settle into the sand
bpy.context.view_layer.update()
fit(parts, margin=0.15)
sprite('diver', {'base': (0, 0, 0), 'valve': tuple(root.matrix_world @ VALVE)})
