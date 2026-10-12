# Rare visitors (Settings -> Critters -> visitors, off by default), all side views facing +x:
#   turtle  12-frame swim sheet (flipper stroke), anchor = body centre
#   shark   one soft still for the deep background (drawn far away, low opacity), anchor = centre
#   fry     8-frame sheet of one tiny see-through baby fish (the scene clones it into a school)
# Usage: blender -b --factory-startup -P blender/scene_visitors.py [-- turtle shark fry]
import math, os, sys
import bpy
from mathutils import Vector as V
sys.path.insert(0, os.path.dirname(__file__))
from common import *

TAU = math.tau


def blob(name, r, loc, scale, mat, rot=(0, 0, 0), parent=None, segs=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=r, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    o.parent = parent
    return o


def pivot(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location, e.parent = loc, parent
    return e


def scaly(name, c1, c2, scale=14.0, rough=0.6, seam=(0.55, 1.0)):
    """Skin in polygonal scale cells (voronoi); seam = (border, centre) brightness, >1 = pale borders."""
    m = pbr(name, c1, c2, rough=rough, scale=3.0, bump=0.4, grime=0.6)
    bs = principled(m)
    vo = N(m, 'TexVoronoi', Vector=(N(m, 'TexCoord'), 'Object'), Scale=scale, _feature='DISTANCE_TO_EDGE')
    seam = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Max': 0.08, 'To Min': seam[0], 'To Max': seam[1]})
    mix = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, B=(seam, 'Result'))
    m.node_tree.links.new(bs.inputs['Base Color'].links[0].from_socket, sock(mix.inputs, 'A'))
    m.node_tree.links.new(sock(mix.outputs, 'Result'), bs.inputs['Base Color'])
    return m


def carapace():
    """Turtle shell: scutes as voronoi plates, each its own amber/olive tone with radiating streaks,
    dark seams between, algae speckle."""
    m = new_mat('carapace')
    co = (N(m, 'TexCoord'), 'Object')
    vo = N(m, 'TexVoronoi', Vector=co, Scale=2.6, Randomness=0.6)
    ed = N(m, 'TexVoronoi', Vector=co, Scale=2.6, Randomness=0.6, _feature='DISTANCE_TO_EDGE')
    tone = ramp(m, (vo, 'Color'), [(0.0, (0.12, 0.07, 0.025)), (0.4, (0.3, 0.17, 0.05)), (0.7, (0.2, 0.16, 0.06)),
                                   (1.0, (0.38, 0.24, 0.08))])
    streak = N(m, 'TexWave', Vector=co, _wave_type='RINGS', Scale=6.0, Distortion=9.0, Detail=4.0)
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.45, A=(tone, 'Color'), B=(streak, 'Color'))
    seam = N(m, 'MapRange', Value=(ed, 'Distance'), **{'From Max': 0.05, 'To Min': 0.25, 'To Max': 1.0})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(c, 'Result'), B=(seam, 'Result'))
    al = N(m, 'MapRange', Value=(N(m, 'TexNoise', Vector=co, Scale=9.0, Detail=6.0), 'Fac'), **{'From Min': 0.6, 'From Max': 0.7, 'To Max': 0.6})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(al, 'Result'), A=(c, 'Result'), B=(0.08, 0.13, 0.03, 1))
    c = ao_grime(m, (c, 'Result'), 0.1, 0.4)
    b = N(m, 'Bump', Strength=0.5, Distance=0.02, Height=M(m, 'ADD', (seam, 'Result'), M(m, 'MULTIPLY', (streak, 'Fac'), 0.2)))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': c, 'Roughness': 0.65, 'Normal': b}))
    return m


def side_cam(width_m, ppu, h_m, x=0.0, z=0.0):
    cam = camera(width_m, round(width_m * ppu), round(h_m * ppu), z=z)
    cam.location.x = x
    return cam


def turtle():
    scenery(int(os.environ.get('SAMPLES', 128)))
    seed(3)
    skin = scaly('tskin', (0.05, 0.055, 0.03), (0.16, 0.15, 0.08), scale=9.0, seam=(2.6, 0.9))
    belly = pbr('plastron', (0.45, 0.38, 0.2), (0.62, 0.55, 0.32), rough=0.6, scale=4, bump=0.3, grime=0.7)
    eye = pbr('teye', (0.01, 0.008, 0.005), rough=0.15, scale=3, grime=0.0)
    root = pivot('turtle', (0, 0, 0))
    shell = blob('shell', 1.0, (0, 0, 0.05), (0.95, 0.72, 0.38), carapace(), parent=root, segs=64)
    blob('plastron', 1.0, (0.02, 0, -0.04), (0.9, 0.66, 0.18), belly, parent=root)
    neck = blob('neck', 0.17, (0.92, 0, 0.02), (1.3, 0.85, 0.85), skin, parent=root)
    head = blob('head', 0.2, (1.17, 0, 0.06), (1.25, 0.82, 0.8), skin, rot=(0, -0.15, 0), parent=root)
    for s in (-1, 1):
        blob('eye', 0.035, (1.27, s * 0.13, 0.1), (1, 0.6, 0.8), eye, parent=root)
    blob('beak', 0.08, (1.39, 0, 0.02), (1.1, 0.8, 0.7), belly, parent=root)
    blob('tail', 0.08, (-0.98, 0, -0.02), (1.6, 0.6, 0.5), skin, parent=root)
    fl = []  # (pivot, base rotation, stroke amplitude, phase lag)
    for s in (-1, 1):  # front flippers: long paddles swept back
        p = pivot('fsh', (0.52, s * 0.55, -0.02), root)
        f = blob('front', 1.0, (-0.25, s * 0.42, -0.02), (0.55, 0.22, 0.04), skin, rot=(0, 0, s * -0.95), parent=p)
        mod(f, 'SIMPLE_DEFORM', deform_method='TAPER', factor=-0.9, deform_axis='X')  # broad at the wrist, pointed tip
        fl.append((p, s, 0.75, 0.0 if s < 0 else 0.15))
        p = pivot('rsh', (-0.65, s * 0.45, -0.05), root)
        blob('rear', 1.0, (-0.15, s * 0.15, 0), (0.24, 0.13, 0.03), skin, rot=(0, 0, s * -0.6), parent=p)
        fl.append((p, s, 0.25, 0.5))
    root.rotation_euler = (0.15, 0, 0)  # a little of the back toward us, so the shell reads

    def pose(ph):
        def f():
            a = TAU * ph
            for p, s, amp, lag in fl:
                st = math.sin(a - lag * TAU)
                p.rotation_euler = (s * amp * st, 0.35 * amp * math.cos(a - lag * TAU), 0)
            root.location.z = 0.04 * math.sin(a + 1.2)
        return f

    side_cam(3.4, 80, 2.4, x=0.1)
    sheet('turtle', [pose(i / 12) for i in range(12)], 12, points={'anchor': (0.1, 0, 0)})


def shark():
    scenery(int(os.environ.get('SAMPLES', 96)))
    # matte skin: fine dermal grain in the bump, rough (no plastic sheen)
    m = pbr('shark', (0.025, 0.04, 0.055), (0.05, 0.065, 0.08), rough=0.85, scale=2.5, bump=0.35, grime=0.3, detail=10.0)
    nt, bs = m.node_tree, principled(m)
    co = (N(m, 'TexCoord'), 'Object')
    grain = N(m, 'TexNoise', Vector=co, Scale=90.0, Detail=2.0)
    bump = N(m, 'Bump', Strength=0.15, Distance=0.01, Height=(grain, 'Fac'))
    nt.links.new(bs.inputs['Normal'].links[0].from_socket, bump.inputs['Normal'])
    nt.links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    # countershading: dark blue-grey back, pale belly, the line between wavering a little
    z = N(m, 'SeparateXYZ', Vector=co)
    wav = N(m, 'TexNoise', Vector=co, Scale=1.8, Detail=3.0)
    line = M(m, 'ADD', (z, 'Z'), M(m, 'MULTIPLY', M(m, 'SUBTRACT', (wav, 'Fac'), 0.5), 0.12))
    cs = N(m, 'MapRange', Value=line, **{'From Min': -0.22, 'From Max': 0.02, 'To Min': 1.0, 'To Max': 0.0}, _interpolation_type='SMOOTHSTEP')
    base = nt.nodes['macro'].inputs['A'].links[0].from_socket
    mix = N(m, 'Mix', _data_type='RGBA', Factor=(cs, 'Result'), B=(0.32, 0.35, 0.36, 1))
    nt.links.new(base, sock(mix.inputs, 'A'))
    nt.links.new(sock(mix.outputs, 'Result'), nt.nodes['macro'].inputs['A'])
    L, segs, n = 5.0, 32, 40

    def rad(u):  # u 0 tail .. 1 snout: thickest a little ahead of the middle, pointed both ends
        return 0.04 + 0.42 * math.sin(math.pi * u ** 1.36) ** 0.7

    rings = [[(u * L - L / 2, rad(u) * math.cos(a), rad(u) * 1.15 * math.sin(a) + 0.12 * u * (1 - u))
              for a in (i / segs * TAU for i in range(segs))] for u in (k / n for k in range(n + 1))]
    verts = [p for r in rings for p in r]
    faces = [[k * segs + i, k * segs + (i + 1) % segs, (k + 1) * segs + (i + 1) % segs, (k + 1) * segs + i]
             for k in range(n) for i in range(segs)]
    body = mesh('shark', verts, faces, m)
    parts = [body]

    def fin(pts, thick=0.04):
        o = mesh('fin', [(x, -thick, z) for x, z in pts] + [(x, thick, z) for x, z in pts],
                 [list(range(len(pts))), list(range(2 * len(pts) - 1, len(pts) - 1, -1))] +
                 [[i, (i + 1) % len(pts), len(pts) + (i + 1) % len(pts), len(pts) + i] for i in range(len(pts))], m)
        mod(o, 'SUBSURF', levels=2, render_levels=2)
        parts.append(o)
        return o

    fin([(0.1, 0.35), (-0.55, 1.2), (-0.75, 1.15), (-0.75, 0.3)])           # dorsal
    fin([(-2.3, 0.05), (-3.0, 0.95), (-3.15, 0.9), (-2.75, 0.0), (-3.0, -0.55), (-2.85, -0.55), (-2.35, -0.05)])  # tail
    fin([(0.9, -0.3), (0.2, -1.0), (0.05, -0.95), (0.3, -0.3)], 0.03).location.y = -0.3  # pectoral
    fin([(-1.5, -0.2), (-1.85, -0.5), (-1.95, -0.45), (-1.8, -0.15)], 0.02)  # pelvic
    for x in (1.45, 1.35, 1.25, 1.15, 1.05):  # gill slits
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -rad((x + L / 2) / L) * 0.97, 0.12 * 0.4))
        g = bpy.context.object
        g.scale = (0.012, 0.05, 0.35)
        g.data.materials.append(pbr('slit', (0.025, 0.035, 0.045), rough=0.9, scale=3, grime=0.0))
    fog(0.3)  # far away: a little water haze baked in (alpha untouched)
    # soft: render at half density, the manifest doubles the on-screen size
    side_cam(6.6, 50, 2.6, x=-0.3, z=0.1)
    e = sprite('shark', {'anchor': (-0.3, 0, 0.1)})
    manifest('shark', dict(e, w=e['w'] * 2, h=e['h'] * 2, anchor=[e['anchor'][0] * 2, e['anchor'][1] * 2]))


def fry():
    scenery(int(os.environ.get('SAMPLES', 96)))
    flesh = new_mat('fry')
    bs = N(flesh, 'BsdfPrincipled', **{'Base Color': (0.75, 0.7, 0.55, 1), 'Roughness': 0.3, 'Alpha': 0.55,
                                       'Subsurface Weight': 0.4, 'Coat Weight': 0.5})
    N(flesh, 'OutputMaterial', Surface=bs)
    gut = pbr('gut', (0.5, 0.3, 0.08), (0.75, 0.5, 0.15), rough=0.4, scale=8, grime=0.0)
    eye = pbr('fryeye', (0.01, 0.01, 0.012), rough=0.1, scale=3, grime=0.0)
    root = pivot('fry', (0, 0, 0))
    blob('body', 0.5, (0, 0, 0), (1.0, 0.28, 0.32), flesh, parent=root)
    blob('gut', 0.14, (0.08, 0, -0.04), (1.2, 0.8, 0.8), gut, parent=root)
    for s in (-1, 1):
        blob('eye', 0.09, (0.33, s * 0.08, 0.04), (1, 0.6, 1), eye, parent=root)
    tp = pivot('tailp', (-0.42, 0, 0), root)
    blob('tail', 0.3, (-0.25, 0, 0), (1.0, 0.03, 0.55), flesh, parent=tp)

    def pose(ph):
        def f():
            a = TAU * ph
            tp.rotation_euler = (0, 0, 0.6 * math.sin(a))
            root.rotation_euler = (0, 0, -0.15 * math.sin(a - 0.6))
        return f

    side_cam(1.6, 50, 0.7)  # 1 unit = 50 px rendered, shown at a third: ~17 px long on screen
    e = sheet('fry', [pose(i / 8) for i in range(8)], 8, points={'anchor': (0, 0, 0)})
    manifest('fry', dict(e, w=e['w'] / 3, h=e['h'] / 3, anchor=[e['anchor'][0] / 3, e['anchor'][1] / 3]))


PIECES = {'turtle': turtle, 'shark': shark, 'fry': fry}
want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(PIECES)
for w in want:
    if w not in PIECES:
        sys.exit(f'scene_visitors.py: unknown visitor {w}; choose from {list(PIECES)}')
    PIECES[w]()
