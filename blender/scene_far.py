# Far depth plates: three horizontally tiling strips (ridges, rock spires + sea fans + kelp, reef),
# each hazier the further back. Seamless: everything near an edge is duplicated one period over,
# heightfields use whole-period sines, and wide surfaces use x-wrapped texture coords.
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *

T = math.radians(TILT)
FRONT = -1.0  # floor front edge (y) = bottom of every plate
FLOORS = []


def periodic(x, L, rnd, terms=48, rough=1.15):
    out = np.zeros_like(x)
    for k in range(1, terms + 1):
        out += rnd.normal() / k ** rough * np.sin(2 * math.pi * k * x / L + rnd.uniform(0, 2 * math.pi))
    return out


def ridge(name, L, y0, depth, hmax, sd, mat, nx=720, ny=36):
    """Craggy range as a heightfield: ridged periodic noise, peaking mid-depth."""
    rnd = np.random.default_rng(sd)
    xs = np.linspace(-L / 2, L / 2, nx)
    h = periodic(xs, L, rnd, 40, 1.4)
    h = (h - h.min()) / (h.max() - h.min())
    q = h * 3.0                                   # terraces: flat-topped buttes with steep sides
    f = q - np.floor(q)
    h = (np.floor(q) + f * f * f * (f * (f * 6 - 15) + 10)) / 3.0
    verts, faces = [], []
    for j in range(ny):
        t = j / (ny - 1)
        prof = math.sin(math.pi * min(1, t * 1.25)) ** 0.35
        detail = periodic(xs + j * 0.37, L, rnd, 60, 1.0) * 0.05
        z = np.maximum(0, (h + detail) * prof * hmax)
        verts += [(x, y0 + t * depth, zz - 0.15) for x, zz in zip(xs, z)]
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))
    o = mesh(name, verts, faces, mat)
    wrap(o, L)
    return o


def wrap(o, L):
    for dx in (-L, L):
        c = o.copy()
        c.location.x += dx
        bpy.context.scene.collection.objects.link(c)


def floor(L, depth, mat):
    """Floor strip that fades in from the front and out again by `depth`."""
    FLOORS.append((mat, depth))
    o = mesh('floor', [(-L / 2, FRONT, 0), (L / 2, FRONT, 0), (L / 2, depth, 0), (-L / 2, depth, 0)], [(0, 1, 2, 3)], mat)
    wrap(o, L)
    return o


def fade_front(m, y0=0.5, y1=3.5, y2=1e9):
    """Make a material transparent toward the front edge and past depth y2 (after fog, so alpha survives)."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    surf = out.inputs['Surface'].links[0].from_socket
    y = N(m, 'SeparateXYZ', Vector=(N(m, 'NewGeometry'), 'Position'))
    f = N(m, 'MapRange', Value=(y, 'Y'), **{'From Min': y0, 'From Max': y1}, _interpolation_type='SMOOTHSTEP')
    b = N(m, 'MapRange', Value=(y, 'Y'), **{'From Min': y2 - 3, 'From Max': y2, 'To Min': 1.0, 'To Max': 0.0},
          _interpolation_type='SMOOTHSTEP')
    mix = N(m, 'MixShader', Fac=M(m, 'MULTIPLY', (f, 'Result'), (b, 'Result')))
    nt.links.new(N(m, 'BsdfTransparent').outputs[0], mix.inputs[1])
    nt.links.new(surf, mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])


def branches(name, root, rnd, mat, depth=4, length=1.0, radius=0.06, spread=0.6, planar=False, up=1.0):
    """Recursive branching tubes (sea fans when planar, staghorn otherwise)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', 1.0, 2, True

    def grow(p, d, ln, r, lvl):
        sp = cu.splines.new('POLY')
        sp.points.add(4)
        q = np.array(p, float)
        for i, pt in enumerate(sp.points):
            pt.co = (*q, 1)
            pt.radius = r * (1 - 0.35 * i / 4)
            d = d + rnd.normal(0, 0.12, 3) * (np.array([1, 0, 1]) if planar else 1)
            d[2] += 0.08 * up
            d /= np.linalg.norm(d)
            q = q + d * ln / 4
        if lvl:
            for _ in range(2 + (rnd.random() < 0.35)):
                nd = d + rnd.normal(0, spread, 3) * (np.array([1, 0, 1]) if planar else 1)
                grow(q - d * ln / 4, nd / np.linalg.norm(nd), ln * rnd.uniform(0.6, 0.8), r * 0.68, lvl - 1)

    grow(root, np.array([0, 0, 1.0]), length, radius, depth)
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    cu.materials.append(mat)
    return o


def ribbon(name, root, rnd, mat, height, width=0.12, sway=0.5):
    """Kelp/seagrass blade: a curve extruded into a twisting ribbon."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions, cu.extrude, cu.twist_mode = '3D', width, 'MINIMUM'
    sp = cu.splines.new('BEZIER')
    n = 6
    sp.bezier_points.add(n - 1)
    ph = rnd.uniform(0, 6.3)
    for i, bp in enumerate(sp.bezier_points):
        t = i / (n - 1)
        bp.co = (root[0] + sway * math.sin(ph + t * 3) * t, root[1] + 0.2 * math.sin(ph * 2 + t * 2), root[2] + t * height)
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
        bp.radius = 1 - 0.6 * t
        bp.tilt = rnd.uniform(-1, 1) + t * rnd.uniform(-2, 2)
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    cu.materials.append(mat)
    return o


def brain(rnd, r, loc, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=r, location=loc)
    o = bpy.context.object
    o.scale.z = 0.65
    t = bpy.data.textures.new('brain', 'MARBLE')
    t.marble_type, t.noise_scale, t.turbulence, t.noise_depth = 'SHARPER', r * 0.25, 9.0, 3
    mod(o, 'DISPLACE', texture=t, strength=r * 0.07, texture_coords='GLOBAL')
    o.data.shade_smooth()
    o.data.materials.append(mat)
    return o


def sponges(rnd, loc, mat, n=4, k=1.0):
    out = []
    for i in range(n):
        h = rnd.uniform(0.5, 1.3) * k
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=rnd.uniform(0.08, 0.14) * k, depth=h, end_fill_type='NOTHING',
                                            location=(loc[0] + rnd.uniform(-0.25, 0.25) * k, loc[1] + rnd.uniform(-0.2, 0.2) * k, h / 2 - 0.05))
        o = bpy.context.object
        o.rotation_euler = (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0)
        mod(o, 'SIMPLE_DEFORM', deform_method='TAPER', factor=0.5)
        mod(o, 'SOLIDIFY', thickness=0.03)
        mod(o, 'SUBSURF', levels=1, render_levels=2)
        o.data.shade_smooth()
        o.data.materials.append(mat)
        out.append(o)
    return out


def plate(name, L, haze, far, yb, build, sd, res):
    """Render one plate. yb = screen row (ref px from top) its bottom edge sits at in scene.js,
    used so the haze colour matches the backdrop gradient behind it."""
    scenery(160)
    rnd = np.random.default_rng(sd)
    objs = build(L, rnd)
    bpy.context.view_layer.update()
    top = 0
    for o in bpy.context.scene.objects:
        if o.type in ('MESH', 'CURVE') and not o.name.startswith('floor'):
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                if abs(w.x) < L / 2 + 1:
                    top = max(top, w.y * math.sin(T) + w.z * math.cos(T))
    v0 = FRONT * math.sin(T)
    a = PPU / 1440
    fog(haze, far, vmap=(a, (1440 - yb) / 1440 - v0 * a))
    while FLOORS:
        m, d = FLOORS.pop()
        fade_front(m, FRONT - 2, FRONT - 1, d)  # opaque to the bottom edge: nearer layers cover it
    top += 0.1
    hpx = round((top - v0) * PPU)
    camera(L, round(L * PPU * res), round(hpx * res), tilt=TILT, z=(top + v0) / 2 / math.cos(T))  # hazy: low res, scaled up
    render(f'scene/{name}.png')
    manifest(name, {'w': round(L * PPU), 'h': hpx, 'yb': yb})


def far0(L, rnd):
    rk2 = pbr('ridge2', (0.05, 0.06, 0.06), (0.16, 0.15, 0.13), rough=0.9, scale=0.4, bump=0.5, moss=0.25,
              cracks=0.3, strata=0.4, wrap=L)
    floor(L, 16, pbr('floor0', (0.1, 0.09, 0.07), (0.17, 0.14, 0.1), scale=0.5, wrap=L))
    ridge('back', L, 9, 6, 4.4, 1, rk2)
    ridge('front', L, 4, 4, 1.8, 2, rk2)
    return []


def far1(L, rnd):
    rkm = stone('spire', moss=0.5, scale=0.9)
    fan = pbr('fan', (0.35, 0.08, 0.12), (0.55, 0.2, 0.18), rough=0.7, scale=6, sss=0.2)
    kelp = pbr('kelp', (0.08, 0.12, 0.02), (0.2, 0.22, 0.05), rough=0.5, scale=2, sss=0.4)
    floor(L, 11, pbr('floor1', (0.12, 0.1, 0.08), (0.2, 0.16, 0.11), scale=0.7, wrap=L))
    ridge('low', L, 5, 4, 1.6, 3, pbr('ridge1', (0.05, 0.06, 0.06), (0.15, 0.14, 0.12), rough=0.9, scale=0.6,
                                         bump=0.5, moss=0.4, strata=0.4, wrap=L))
    for i in range(6):  # spires: stacked rocks
        x, y = (i + rnd.uniform(0.0, 1.0)) * L / 6 - L / 2, rnd.uniform(1.5, 3.5)
        z = 0
        for k in range(rnd.integers(2, 5)):
            s = rnd.uniform(0.9, 1.4) * (1 - 0.18 * k)
            o = rock((s * rnd.uniform(0.8, 1.2), s, s * rnd.uniform(1.2, 1.8)), sink=-z if k else 0.3,
                     sd=int(rnd.integers(1, 99)), loc=(x + rnd.uniform(-0.2, 0.2), y, 0))
            o.data.materials.append(rkm)
            wrap(o, L)
            z += s * 1.5
    for i in range(6):
        x, y = rnd.uniform(-L / 2, L / 2), rnd.uniform(0.5, 3)
        wrap(branches('fan', (x, y, 0), rnd, fan, depth=5, length=1.5, radius=0.07, spread=0.55, planar=True), L)
    for i in range(10):
        x, y = rnd.uniform(-L / 2, L / 2), rnd.uniform(0, 3)
        for k in range(rnd.integers(3, 7)):
            wrap(ribbon('kelp', (x + rnd.uniform(-0.3, 0.3), y + rnd.uniform(-0.2, 0.2), -0.1), rnd, kelp,
                        rnd.uniform(2.5, 5.2), 0.14), L)
    return []


def far2(L, rnd):
    rkm = stone('reefrock', moss=0.6, scale=1.2)
    cols = [((0.45, 0.12, 0.25), (0.7, 0.3, 0.4)), ((0.55, 0.25, 0.06), (0.8, 0.45, 0.15)),
            ((0.25, 0.12, 0.45), (0.45, 0.3, 0.65)), ((0.5, 0.42, 0.25), (0.7, 0.6, 0.4))]
    mats = [pbr(f'coral{i}', a, b, rough=0.75, scale=8, bump=0.6, sss=0.25, vor=0.3) for i, (a, b) in enumerate(cols)]
    grass = pbr('grass', (0.06, 0.13, 0.03), (0.18, 0.25, 0.06), rough=0.5, scale=3, sss=0.4)
    floor(L, 7, pbr('floor2', (0.14, 0.12, 0.09), (0.24, 0.19, 0.13), scale=1.0, wrap=L))
    for i in range(10):  # reef mounds: rock clusters dressed with coral
        cx, cy = (i + rnd.uniform(0.15, 0.85)) * L / 10 - L / 2, rnd.uniform(0.8, 2.5)
        for k in range(rnd.integers(3, 6)):
            s = rnd.uniform(0.6, 1.5)
            o = rock((s * 1.4, s, s * rnd.uniform(0.8, 1.3)), sink=0.25 * s, sd=int(rnd.integers(1, 99)),
                     loc=(cx + rnd.uniform(-1.4, 1.4), cy + rnd.uniform(-0.4, 0.4), 0))
            o.data.materials.append(rkm)
            wrap(o, L)
        for kind in rnd.permutation(4)[:2]:
            m = mats[rnd.integers(0, len(mats))]
            px, py = cx + rnd.uniform(-1.2, 1.2), cy - rnd.uniform(0.3, 0.8)
            if kind == 0:
                wrap(brain(rnd, rnd.uniform(0.6, 1.0), (px, py, 0.2), m), L)
            elif kind == 1:
                for o in sponges(rnd, (px, py, 0), m, int(rnd.integers(4, 7)), 2.0):
                    wrap(o, L)
            elif kind == 2:
                wrap(branches('stag', (px, py, 0), rnd, m, depth=4, length=0.9, radius=0.09, spread=0.7), L)
            else:
                wrap(branches('fan2', (px, py + 0.4, 0), rnd, m, depth=5, length=1.1, radius=0.05, spread=0.55, planar=True), L)
    for i in range(18):
        x, y = rnd.uniform(-L / 2, L / 2), rnd.uniform(0.0, 2.5)
        for k in range(rnd.integers(6, 14)):
            wrap(ribbon('grass', (x + rnd.uniform(-0.35, 0.35), y + rnd.uniform(-0.2, 0.2), -0.05), rnd, grass,
                        rnd.uniform(0.8, 2.2), 0.07, 0.35), L)
    return []


plate('far0', 36, 0.74, 0.2, 1185, far0, 10, 0.35)
plate('far1', 31, 0.42, 0.2, 1200, far1, 11, 0.5)
plate('far2', 27, 0.24, 0.12, 1215, far2, 12, 0.5)
