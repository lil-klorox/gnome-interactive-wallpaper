# Sand bed: a horizontally tiling strip of rippled wet sand with gravel, shells and starfish.
# Seamless like the far plates (whole-period ripples, x-wrapped texture, edge objects duplicated).
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *

P = 24.0                 # period (world units) = 2400 px
T = math.radians(TILT)
FRONT, BACK = -1.2, 15.0
FADE = (9.5, 13.5)       # sand fades out between these depths into the far plates


def wrap(o):
    for dx in (-P, P):
        c = o.copy()
        c.location.x += dx
        bpy.context.scene.collection.objects.link(c)


def heights(x, y, rnd):
    """Dunes + meandering ripples whose crests run left-right; every x term has a whole number of
    cycles per period so the strip tiles."""
    h = np.zeros_like(x)
    for k in range(1, 7):
        for j in (0.15, 0.3, 0.5):
            h += rnd.normal() * 0.11 / k * np.sin(2 * math.pi * k * x / P + j * k * y + rnd.uniform(0, 6.3))
    bend = 0.9 * np.sin(2 * math.pi * 3 * x / P + 0.3 * y) + 0.5 * np.sin(2 * math.pi * 11 * x / P - 0.5 * y)
    rip = np.sin(2 * math.pi * y / 0.9 + bend * 2.5)
    crest = (1 - np.abs(rip)) ** 1.5 - 0.4                   # sharper crests, wide troughs
    amp = 0.03 + 0.025 * np.sin(2 * math.pi * 4 * x / P + 0.4 * y) ** 2
    return h + crest * amp


def fade_back(m):
    """Final shader -> transparent between FADE depths (after fog, so alpha survives)."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    surf = out.inputs['Surface'].links[0].from_socket
    y = N(m, 'SeparateXYZ', Vector=(N(m, 'NewGeometry'), 'Position'))
    f = N(m, 'MapRange', Value=(y, 'Y'), **{'From Min': FADE[0], 'From Max': FADE[1]}, _interpolation_type='SMOOTHSTEP')
    mix = N(m, 'MixShader', Fac=(f, 'Result'))
    nt.links.new(surf, mix.inputs[1])
    nt.links.new(N(m, 'BsdfTransparent').outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])


def varied(name, stops, rough=0.5, coat=0.0, scale=6.0, bump=0.3, sss=0.0):
    """Per-object colour picked from a ramp by Object Info random, plus surface noise."""
    m = pbr(name, (0.5, 0.5, 0.5), rough=rough, coat=coat, scale=scale, bump=bump, sss=sss, grime=0.4)
    nt = m.node_tree
    bs = principled(m)
    oi = N(m, 'ObjectInfo')
    col = ramp(m, (oi, 'Random'), stops)
    nz = next(n for n in nt.nodes if n.type == 'TEX_NOISE')
    mix = N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.5, A=(col, 'Color'), B=(nz, 'Color'))
    ao = bs.inputs['Base Color'].links[0].from_node  # grime multiply node: feed it the new colour
    nt.links.new(sock(mix.outputs, 'Result'), sock(ao.inputs, 'A'))
    return m


def pebbles(rnd, n):
    mat = varied('gravel', [(0.0, (0.06, 0.05, 0.04)), (0.2, (0.25, 0.17, 0.1)), (0.4, (0.45, 0.33, 0.2)),
                            (0.55, (0.35, 0.13, 0.06)), (0.7, (0.62, 0.55, 0.45)), (0.85, (0.15, 0.13, 0.11)),
                            (1.0, (0.8, 0.72, 0.6))], rough=0.45, coat=0.3)
    shapes = []
    for i in range(10):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1, location=(0, -40 - i * 3, 0))
        o = bpy.context.object
        o.scale = (1, rnd.uniform(0.6, 0.95), rnd.uniform(0.35, 0.6))
        t = bpy.data.textures.new('pb', 'CLOUDS')
        t.noise_scale = 0.7
        mod(o, 'DISPLACE', texture=t, strength=0.25, texture_coords='GLOBAL')
        apply_all(o)
        o.data.shade_smooth()
        o.data.materials.append(mat)
        shapes.append(o)
    cx, cy = 0.0, 0.0
    for i in range(n):
        if rnd.random() < 0.6:  # clump
            cx, cy = rnd.uniform(-P / 2, P / 2), rnd.uniform(FRONT, FADE[0] - 1)
        x, y = cx + rnd.normal(0, 0.6), cy + rnd.normal(0, 0.35)
        if not FRONT < y < FADE[0]:
            continue
        c = shapes[rnd.integers(0, len(shapes))].copy()
        sz = rnd.uniform(0.025, 0.08) * (1.8 if rnd.random() < 0.08 else 1)
        c.scale = (sz, sz, sz)
        c.rotation_euler = (rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(0, 6.3))
        c.location = (x, y, float(heights(np.array([x]), y, np.random.default_rng(1))[0]) - sz * 0.35)
        bpy.context.scene.collection.objects.link(c)
        wrap(c)


def scallop(mat):
    """Fan shell: cupped disc sector with radial ribs and growth lines."""
    verts, faces = [], []
    nr, na = 14, 60
    for i in range(nr + 1):
        r = i / nr
        for j in range(na + 1):
            a = math.radians(-70 + 140 * j / na)
            rib = 0.05 * r * abs(math.sin(j / na * math.pi * 9)) ** 0.7
            verts.append((r * math.sin(a), r * math.cos(a) * 0.95, rib + 0.25 * r * math.cos(a) * (1 - r)))
    for i in range(nr):
        for j in range(na):
            a = i * (na + 1) + j
            faces.append((a, a + 1, a + na + 2, a + na + 1))
    o = mesh('scallop', verts, faces, mat)
    mod(o, 'SOLIDIFY', thickness=0.03)
    mod(o, 'SUBSURF', levels=1, render_levels=1)
    return o


def spiral(mat):
    """Spiral (turret) shell: a tube following a tightening conical helix."""
    verts, faces = [], []
    n, m = 140, 14
    for i in range(n + 1):
        t = i / n
        ang = t * 4.5 * 2 * math.pi
        rad = 0.32 * (1 - t) ** 1.1 + 0.01
        cx, cy, cz = rad * math.cos(ang), rad * math.sin(ang), t * 1.1
        tr = 0.24 * (1 - t) + 0.015
        for j in range(m):
            b = j / m * 2 * math.pi
            k = 1 + 0.08 * math.sin(ang * 6)  # growth ridges
            verts.append((cx + tr * k * math.cos(b) * math.cos(ang), cy + tr * k * math.cos(b) * math.sin(ang), cz + tr * math.sin(b)))
    for i in range(n):
        for j in range(m):
            faces.append((i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j))
    o = mesh('spiral', verts, faces, mat)
    o.rotation_euler = (math.radians(80), 0, 0)
    bpy.context.view_layer.update()
    return o


def starfish(mat, rnd):
    verts, faces = [], []
    na, nr = 120, 12
    ph = rnd.uniform(0, 1)
    for i in range(nr + 1):
        r = i / nr
        for j in range(na):
            a = j / na * 2 * math.pi
            arm = (0.5 + 0.5 * math.cos(5 * a + ph)) ** 2.2
            R = 0.28 + 0.72 * arm * (1 + 0.08 * math.sin(a * 13))
            z = 0.16 * (1 - r ** 2) * (0.4 + 0.6 * arm) + 0.04 * math.sin(r * 3 + a * 2) * arm
            verts.append((r * R * math.cos(a), r * R * math.sin(a), z))
    verts.append((0, 0, -0.02))
    for i in range(nr):
        for j in range(na):
            a, b = i * na + j, i * na + (j + 1) % na
            faces.append((a, b, b + na, a + na))
    o = mesh('star', verts, faces, mat)
    mod(o, 'SUBSURF', levels=1, render_levels=2)
    return o


def build():
    scenery(256)
    rnd = np.random.default_rng(7)
    nx, ny = 700, 220
    xs = np.linspace(-P / 2, P / 2, nx)
    ys = np.linspace(FRONT, BACK, ny)
    verts = []
    for y in ys:
        verts += [(x, y, z) for x, z in zip(xs, heights(xs, y, np.random.default_rng(1)))]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    sm = sand_mat(P)
    bed = mesh('sand', verts, faces, sm)
    wrap(bed)
    pebbles(rnd, 420)
    shell_m = varied('shell', [(0.0, (0.75, 0.62, 0.5)), (0.3, (0.8, 0.45, 0.35)), (0.55, (0.85, 0.75, 0.6)),
                               (0.8, (0.6, 0.3, 0.15)), (1.0, (0.9, 0.85, 0.8))], rough=0.35, coat=0.6, scale=14, bump=0.4, sss=0.1)
    star_m = varied('starfish', [(0.0, (0.75, 0.22, 0.06)), (0.4, (0.85, 0.42, 0.1)), (0.7, (0.55, 0.1, 0.25)),
                                 (1.0, (0.8, 0.12, 0.08))], rough=0.7, scale=25, bump=1.0)
    nz = principled(star_m).inputs['Normal'].links[0].from_node  # bumpy starfish skin: add voronoi nubs
    vo = N(star_m, 'TexVoronoi', Scale=40.0, _feature='SMOOTH_F1')
    nubs = M(star_m, 'MULTIPLY', M(star_m, 'SUBTRACT', 1.0, (vo, 'Distance')), 1.5)
    star_m.node_tree.links.new(nubs.outputs[0], nz.inputs['Height'])
    protos = [scallop(shell_m), spiral(shell_m)] + [starfish(star_m, rnd) for _ in range(3)]
    for p in protos:
        p.location = (0, -60, 0)
    for i in range(30):
        k = 0 if i < 13 else 1 if i < 24 else 2 + i % 3
        x, y = rnd.uniform(-P / 2, P / 2), rnd.uniform(FRONT + 0.3, FADE[0] - 1.5)
        c = protos[k].copy()
        sz = rnd.uniform(0.2, 0.3) if k < 2 else rnd.uniform(0.45, 0.65)
        c.scale = (sz, sz, sz)
        z = float(heights(np.array([x]), y, np.random.default_rng(1))[0])
        if k == 0:
            c.rotation_euler = (rnd.uniform(-0.5, 0.5) + (math.pi if rnd.random() < 0.3 else 0), rnd.uniform(-0.3, 0.3), rnd.uniform(0, 6.3))
        elif k == 1:
            c.rotation_euler = (math.radians(rnd.uniform(70, 100)), 0, rnd.uniform(0, 6.3))
        else:
            c.rotation_euler = (rnd.uniform(-0.1, 0.1), rnd.uniform(-0.1, 0.1), rnd.uniform(0, 6.3))
        c.location = (x, y, z - sz * 0.05)
        bpy.context.scene.collection.objects.link(c)
        wrap(c)
    v0 = (FRONT + 0.6) * math.sin(T)  # a little in from the front edge so dunes never dip below the frame
    fog(0.0, 0.25, vmap=(PPU / 1440, -v0 * PPU / 1440))
    fade_back(sm)
    v1 = BACK * math.sin(T) + 0.15
    hpx = round((v1 - v0) * PPU)
    camera(P, round(P * PPU), hpx, tilt=TILT, z=(v1 + v0) / 2 / math.cos(T))
    render('scene/sand.png')
    manifest('sand', {'w': round(P * PPU), 'h': hpx})


build()
