# Eels. Garden eel: a thin spotted tube rising out of a sand collar (frames 0-7 emerge, 8-11 sway).
# Tessellated moray as a chain: head sheet (mouth closed -> open, the neck is the joint), one body
# segment (soft ends, drawn 10x by tank.js) and a tail; all facing +x.
# Usage: blender -b --factory-startup -P blender/scene_eels.py   (SAMPLES env = render samples)
import math, os, sys
import bmesh
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig, half

PPU = 100  # 2x render: on-screen px = 50 per unit


def tube(name, pts, rad, mat, m=20, sq=1.0):
    """Tube mesh along pts (head first); uv = (distance from the head, angle) so a pattern stays on
    the skin however long the visible part is. rad(t), t = 0 head .. 1 end; sq squashes y."""
    pts = [np.array(p, float) for p in pts]
    s = np.r_[0, np.cumsum([np.linalg.norm(b - a) for a, b in zip(pts, pts[1:])])]
    verts, uv, faces = [], [], []
    for i, p in enumerate(pts):
        d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        d /= np.linalg.norm(d)
        side = np.array([0, 1.0, 0])
        up = np.cross(d, side)
        up /= np.linalg.norm(up)
        r = rad(s[i] / s[-1])
        for j in range(m):
            a = j / m * math.tau
            verts.append(tuple(p + up * r * math.cos(a) + side * r * sq * math.sin(a)))
            uv.append((s[i], j / m))
    n = len(pts)
    for i in range(n - 1):
        for j in range(m):
            faces.append((i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j))
    verts += [tuple(pts[0]), tuple(pts[-1])]
    faces += [(n * m, (j + 1) % m, j) for j in range(m)] + [(n * m + 1, (n - 1) * m + j, (n - 1) * m + (j + 1) % m) for j in range(m)]
    uv += [(0, 0), (s[-1], 0)]
    return outward(mesh(name, verts, faces, mat, uv=uv))


def outward(o):
    """Point every face normal out of the closed mesh (the hand-built windings face in)."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    return o


def skin_coords(m):
    """(along, cos, sin) from the tube uv: a 3D texture space wrapped round the body."""
    sp = N(m, 'SeparateXYZ', Vector=(N(m, 'UVMap', _uv_map='UVMap'), 'UV'))
    a = M(m, 'MULTIPLY', (sp, 'Y'), math.tau)
    return (N(m, 'CombineXYZ', X=(sp, 'X'), Y=M(m, 'MULTIPLY', M(m, 'COSINE', a), 0.12),
              Z=M(m, 'MULTIPLY', M(m, 'SINE', a), 0.12)), 'Vector'), sp


def under(m):
    """1 below the sand line (world z < 0): the part a viewer could not see."""
    return M(m, 'LESS_THAN', (N(m, 'SeparateXYZ', Vector=(N(m, 'NewGeometry'), 'Position')), 'Z'), 0.0)


def garden_mat():
    """Spotted garden eel: pearly cream, dense small black spots, a dark patch behind the head,
    paler belly."""
    m = new_mat('garden')
    co, sp = skin_coords(m)
    vo = N(m, 'TexVoronoi', Vector=co, Scale=18.0, Randomness=0.9)
    spot = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.17, 'From Max': 0.24, 'To Min': 1.0, 'To Max': 0.0})
    nz = N(m, 'TexNoise', Vector=co, Scale=4.0, Detail=4.0)
    col = ramp(m, (nz, 'Fac'), [(0.3, (0.85, 0.74, 0.52)), (0.7, (1.0, 0.88, 0.66))])
    belly = N(m, 'MapRange', Value=M(m, 'COSINE', M(m, 'MULTIPLY', (sp, 'Y'), math.tau)), **{'To Min': 1.15, 'To Max': 0.8})
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(col, 'Color'), B=(belly, 'Result'))
    patch = N(m, 'MapRange', Value=(sp, 'X'), **{'From Min': 0.18, 'From Max': 0.3, 'To Min': 0.0, 'To Max': 1.0})
    pm = M(m, 'MULTIPLY', M(m, 'SUBTRACT', 1.0, (patch, 'Result')), N(m, 'MapRange', Value=(sp, 'X'), **{'From Min': 0.1, 'From Max': 0.16}))
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', pm, 0.8), A=(c, 'Result'), B=(0.05, 0.04, 0.03, 1))
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', (spot, 'Result'), 0.9), A=(c, 'Result'), B=(0.03, 0.025, 0.02, 1))
    bump = N(m, 'Bump', Strength=0.15, Distance=0.01, Height=(nz, 'Fac'))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.5, 'Subsurface Weight': 0.2,
                                  'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    mix_surface(m, under(m), N(m, 'BsdfTransparent'))
    return m


def eye_mat(iris=(0.6, 0.55, 0.3)):
    """Dark pupil with a thin iris ring round it (object coords: the ring faces +y and -y)."""
    m = new_mat('eye')
    sep = N(m, 'SeparateXYZ', Vector=(N(m, 'TexCoord'), 'Object'))
    rr = M(m, 'SQRT', M(m, 'ADD', M(m, 'MULTIPLY', (sep, 'X'), (sep, 'X')), M(m, 'MULTIPLY', (sep, 'Z'), (sep, 'Z'))))
    ring = N(m, 'MapRange', Value=rr, **{'From Min': 0.45, 'From Max': 0.55})
    c = N(m, 'Mix', _data_type='RGBA', Factor=(ring, 'Result'), A=(0.01, 0.01, 0.012, 1), B=(*iris, 1))
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.15,
                                                            'Coat Weight': 0.5}))
    mix_surface(m, under(m), N(m, 'BsdfTransparent'))
    return m


def eye(loc, r, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=24, ring_count=12)
    o = bpy.context.object
    o.data.shade_smooth()
    o.data.materials.append(mat)
    o.scale.y = 0.7
    return o


def garden_line(e, sway):
    """Centre line, head first. e 0..1 = how far out; sway shifts the S-curve phase."""
    L = 2.3 * max(e, 0.06)
    curl = 1.2 * min(1, max(0, (e - 0.3) / 0.5))  # the head tips forward once it is out
    p, pts = np.array([0.0, 0.0, -0.1]), []
    for i in range(41):
        s_ = L * i / 40
        phi = 0.12 * math.sin(s_ * 2.2 + sway) * min(1, s_) + curl * ss(L - 0.55, L, s_) ** 1.5
        pts.append(tuple(p))
        p = p + np.array([math.sin(phi), 0, math.cos(phi)]) * (L / 40)
    return pts[::-1]


def garden():
    rig(PPU, 90, 270, cz=1.15)
    gm, em = garden_mat(), eye_mat((0.75, 0.7, 0.45))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, -0.01), segments=48, ring_count=24)
    collar = bpy.context.object
    collar.scale = (0.27, 0.27, 0.16)
    collar.data.shade_smooth()
    t = bpy.data.textures.new('mound', 'CLOUDS')
    t.noise_scale = 0.08
    mod(collar, 'DISPLACE', texture=t, strength=0.025, texture_coords='GLOBAL')
    sm = sand_mat()
    sep = N(sm, 'SeparateXYZ', Vector=(N(sm, 'TexCoord'), 'Object'))
    rr = M(sm, 'SQRT', M(sm, 'ADD', M(sm, 'MULTIPLY', (sep, 'X'), (sep, 'X')), M(sm, 'MULTIPLY', (sep, 'Y'), (sep, 'Y'))))
    fade = M(sm, 'MAXIMUM', N(sm, 'MapRange', Value=rr, **{'From Min': 0.5, 'From Max': 0.9}), under(sm))
    mix_surface(sm, fade, N(sm, 'BsdfTransparent'))  # only the top of the mound, edges fade into the tank sand
    collar.data.materials.append(sm)
    live = []
    E = [0.0, 0.08, 0.2, 0.35, 0.52, 0.7, 0.86, 1.0]

    def pose_for(e, sway):
        def pose():
            for o in live:
                bpy.data.objects.remove(o)
            pts = garden_line(e, sway)
            r0 = 0.12 / (2.3 * max(e, 0.06))  # rounded snout over the first 0.12 units
            body = tube('eel', pts, lambda t: 0.1 * math.sqrt(max(0.05, 1 - max(0, 1 - t / r0) ** 2)) * (0.8 + 0.2 * min(1, t * 8)), gm)
            hd, nx = np.array(pts[0]), np.array(pts[3])
            d = (hd - nx) / np.linalg.norm(hd - nx)
            ep = hd - d * 0.09 + np.cross(d, [0, 1, 0]) * -0.03
            live[:] = [body, eye(tuple(ep + [0, -0.075, 0]), 0.038, em), eye(tuple(ep + [0, 0.075, 0]), 0.038, em)]
        return pose
    poses = [pose_for(e, 0) for e in E] + [pose_for(1, s) for s in (0.6, 1.2, 0.6, 0.0)]
    sheet('garden_eel', poses, 12, {'base': (0, 0, 0)}, pad=3)
    half('garden_eel')


def moray_mat():
    """Tessellated (honeycomb) moray: dark brown polygons in a pale yellow network, finer on the head."""
    m = new_mat('moray')
    co = (N(m, 'TexCoord'), 'Object')
    warp = N(m, 'TexNoise', Vector=co, Scale=3.0, Detail=2.0)
    wco = N(m, 'Mix', _data_type='VECTOR', Factor=0.12, A=co, B=(warp, 'Color'))
    vo = N(m, 'TexVoronoi', Vector=(wco, 'Result'), Scale=7.0, _feature='DISTANCE_TO_EDGE')
    net = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.02, 'From Max': 0.045, 'To Min': 0.0, 'To Max': 1.0})
    nz = N(m, 'TexNoise', Vector=co, Scale=12.0, Detail=5.0)
    cell = ramp(m, (nz, 'Fac'), [(0.3, (0.05, 0.032, 0.015)), (0.7, (0.12, 0.075, 0.03))])
    line = ramp(m, (nz, 'Fac'), [(0.3, (0.7, 0.52, 0.12)), (0.7, (0.9, 0.74, 0.28))])
    c = N(m, 'Mix', _data_type='RGBA', Factor=(net, 'Result'), A=(line, 'Color'), B=(cell, 'Color'))
    bump = N(m, 'Bump', Strength=0.2, Distance=0.02, Height=M(m, 'ADD', (net, 'Result'), (nz, 'Fac')))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (c, 'Result'), 'Roughness': 0.55, 'Normal': bump})
    N(m, 'OutputMaterial', Surface=bs)
    return m


def loft(name, xs, top, bot, half_w, mat, m=28, fin=None, finb=None):
    """Solid lofted along x from cross-sections: upper edge top(x), lower edge bot(x), half width
    half_w(x); fin(x) adds a thin dorsal ridge on top."""
    verts, faces = [], []
    for x in xs:
        t, b, w = top(x), bot(x), half_w(x)
        c, h = (t + b) / 2, (t - b) / 2
        for j in range(m):
            a = j / m * math.tau
            sn, cs = math.sin(a), math.cos(a)
            up, dn = max(0, sn) ** 40 * bool(fin), max(0, -sn) ** 40 * bool(finb)
            z = c + h * sn + (fin(x) * up if fin else 0) - (finb(x) * dn if finb else 0)
            verts.append((x, w * cs * (1 - up - dn), z))
    n = len(xs)
    for i in range(n - 1):
        for j in range(m):
            faces.append((i * m + j, (i + 1) * m + j, (i + 1) * m + (j + 1) % m, i * m + (j + 1) % m))
    verts += [(xs[0], 0, (top(xs[0]) + bot(xs[0])) / 2), (xs[-1], 0, (top(xs[-1]) + bot(xs[-1])) / 2)]
    faces += [(n * m, j, (j + 1) % m) for j in range(m)] + [(n * m + 1, (n - 1) * m + (j + 1) % m, (n - 1) * m + j) for j in range(m)]
    o = outward(mesh(name, verts, faces, mat))
    mod(o, 'SUBSURF', levels=1, render_levels=1)
    return o


def ss(a, b, x):
    t = min(1, max(0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


R = 0.22  # body half height where the head, segments and tail meet


def moray_head():
    rig(PPU, 170, 110, cx=0.6, cz=0.0)
    mm, em = moray_mat(), eye_mat((0.75, 0.62, 0.2))
    mouth = new_mat('mouth')
    N(mouth, 'OutputMaterial', Surface=N(mouth, 'BsdfPrincipled', **{'Base Color': (0.25, 0.05, 0.05, 1), 'Roughness': 0.5}))
    tooth = new_mat('tooth')
    N(tooth, 'OutputMaterial', Surface=N(tooth, 'BsdfPrincipled', **{'Base Color': (0.8, 0.78, 0.7, 1), 'Roughness': 0.3}))
    xs = list(np.linspace(-0.08, 1.2, 40))
    # upper head: full round neck, a bump of gill muscle behind the eye, the mouth line from x~0.5
    top = lambda x: R + 0.07 * math.sin(math.pi * ss(0.0, 0.75, x)) - 0.13 * ss(0.8, 1.2, x) ** 1.4  # noqa: E731
    bot = lambda x: -R * (1 - ss(0.3, 0.62, x)) - 0.02 + 0.03 * ss(1.0, 1.2, x)  # noqa: E731
    wid = lambda x: 0.17 * (1 - 0.6 * ss(0.6, 1.2, x) ** 1.5)  # noqa: E731
    head = loft('head', xs, top, bot, wid, mm, fin=lambda x: 0.05 * (1 - ss(0.0, 0.45, x)))
    jx = list(np.linspace(0.35, 1.17, 24))
    jaw = loft('jaw', jx, lambda x: 0.0, lambda x: -0.2 * (1 - 0.75 * ss(0.4, 1.17, x)) - 0.02, lambda x: 0.14 * (1 - 0.55 * ss(0.5, 1.15, x)), mm)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0.7, 0, -0.03))
    throat = bpy.context.object
    throat.scale = (0.42, 0.11, 0.08)
    throat.data.materials.append(mouth)
    teeth = []
    for k in range(7):
        x = 0.6 + k * 0.08
        for low in (False, True):  # upper row points down, lower row (on the jaw) up
            bpy.ops.mesh.primitive_cone_add(radius1=0.012, depth=0.035, vertices=8,
                                            location=(x, -0.08 * (1 - 0.4 * (x - 0.6)), 0.0 if low else -0.01))
            tth = bpy.context.object
            tth.rotation_euler = (0 if low else math.pi, 0, 0)
            tth.data.materials.append(tooth)
            teeth.append((tth, low))
    lower_teeth = [t for t, low in teeth if low]
    jaw_parts = [jaw] + lower_teeth
    hinge = bpy.data.objects.new('hinge', None)
    hinge.location = (0.38, 0, -0.03)
    bpy.context.scene.collection.objects.link(hinge)
    for o in jaw_parts:
        o.parent = hinge
        o.location.x -= 0.38
        o.location.z += 0.03
    eye((0.9, -0.125, 0.1), 0.05, em)
    eye((0.9, 0.125, 0.1), 0.05, em)
    for sd in (-1, 1):  # tube nostrils at the snout tip
        curve('nostril', [[(1.12, sd * 0.04, 0.03), (1.19, sd * 0.05, 0.08)]], 0.012, mm)

    def pose_for(k):
        def pose():
            hinge.rotation_euler = (0, math.radians(17 * (k / 5) ** 1.2), 0)
            throat.scale.z, throat.location.z = 0.01 + 0.07 * k / 5, -0.01 - 0.04 * k / 5
        return pose
    sheet('moray_head', [pose_for(k) for k in range(6)], 6, {'anchor': (0, 0, 0)}, pad=3)
    half('moray_head')


def soft_ends(m, x0, x1, at_left=True, at_right=True):
    """Fade alpha over the last bit of each end in x so overlapping segments blend into one body."""
    sep = N(m, 'SeparateXYZ', Vector=(N(m, 'TexCoord'), 'Object'))
    a = 1.0
    if at_left:
        a = N(m, 'MapRange', Value=(sep, 'X'), **{'From Min': x0, 'From Max': x0 + 0.12})
        a = (a, 'Result')
    if at_right:
        b = N(m, 'MapRange', Value=(sep, 'X'), **{'From Min': x1, 'From Max': x1 - 0.12})
        a = M(m, 'MULTIPLY', a, (b, 'Result')) if at_left else (b, 'Result')
    mix_surface(m, M(m, 'SUBTRACT', 1.0, a), N(m, 'BsdfTransparent'))


def moray_seg():
    rig(PPU, 60, 56)
    mm = moray_mat()
    soft_ends(mm, -0.28, 0.28)
    xs = list(np.linspace(-0.28, 0.28, 16))
    loft('seg', xs, lambda x: R, lambda x: -R, lambda x: 0.17, mm, fin=lambda x: 0.05)
    sheet('moray_seg', [lambda: None], 1, {'anchor': (0, 0, 0)}, pad=1)
    half('moray_seg')


def moray_tail():
    rig(PPU, 116, 64, cx=0.5)
    mm = moray_mat()
    soft_ends(mm, -0.04, 0, at_right=False)
    xs = list(np.linspace(-0.04, 1.0, 30))
    # tapering body; the fin ridge runs top and bottom and swells into a rounded tip fin
    body = lambda x: R * max(0.03, 1 - min(1, max(0, x)) ** 1.1)  # noqa: E731
    fin = lambda x: 0.05 + 0.05 * math.sin(math.pi * min(1, max(0, x))) ** 0.6  # noqa: E731
    loft('tail', xs, body, lambda x: -body(x), lambda x: 0.17 * max(0.05, 1 - x), mm, fin=fin,
         finb=lambda x: 0.06 * math.sin(math.pi * min(1, max(0, x))) ** 0.6)
    sheet('moray_tail', [lambda: None], 1, {'anchor': (0, 0, 0)}, pad=1)
    half('moray_tail')


if __name__ == '__main__':
    garden()
    moray_head()
    moray_seg()
    moray_tail()
