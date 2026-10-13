# Tank extras: vignette (512 px glass-edge darkening) and torch (400 px night light pool) as numpy
# stills; moulted shrimp shell, snail egg clutch and fish eggs on a leaf (Cycles, kept at 2x, sized at half).
# Usage: blender -b --factory-startup -P blender/scene_extras.py [-- name ...]   (SAMPLES env = samples)
import math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scene_bits import rig
from scene_eels import tube, skin_coords
from scene_shrimp import spine, radius, tailfan


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def waves(x, y, rng, n=6, f=(1.5, 4.0)):
    """Low-frequency wobble in -1..1: a few random plane waves (no uniform noise)."""
    out = np.zeros_like(x)
    for _ in range(n):
        a, k, ph = rng.uniform(0, math.tau), rng.uniform(*f), rng.uniform(0, math.tau)
        out += np.sin(k * (x * math.cos(a) + y * math.sin(a)) + ph)
    return out / math.sqrt(n)


def vignette():
    rng = np.random.default_rng(7)

    def fn(x, y):
        w = waves(x, y, rng)
        d = (np.abs(x) ** 2.6 + np.abs(y) ** 2.6) ** (1 / 2.6) * (1 + 0.05 * w)  # rounded box, uneven
        d *= 1 + 0.07 * y  # heavier toward the floor, lighter under the surface
        a = 0.43 * smooth((d - 0.42) / 0.62) ** 1.3
        e = np.maximum(np.abs(x), np.abs(y))  # glass edge: a thin greener band right at the rim
        band = smooth((e - 0.955) / 0.045) * (0.6 + 0.4 * waves(x, y, rng, 4, (3, 9)))
        a = np.clip(a + 0.08 * band, 0, 0.52)
        t = np.clip(0.5 + 0.5 * waves(x, y, rng, 4, (2, 5)), 0, 1)[..., None]
        rgb = (1 - t) * np.array([0.004, 0.028, 0.03]) + t * np.array([0.012, 0.05, 0.035])
        rgb = rgb + band[..., None] * np.array([0.02, 0.07, 0.045])
        return rgb, a
    still('vignette', 512, 512, fn, ss=2)


def torch():
    rng = np.random.default_rng(11)
    dust = [(rng.uniform(-0.75, 0.75), rng.uniform(-0.75, 0.75), rng.uniform(0.004, 0.02), rng.uniform(0.03, 0.12))
            for _ in range(70)]

    def fn(x, y):
        # beam hits the glass a little from above: pool slightly tall, hot spot nudged up
        r = np.sqrt((x * 1.04) ** 2 + ((y + 0.04) * 0.97) ** 2) * (1 + 0.025 * waves(x, y, rng, 5, (3, 7)))
        h = np.sqrt(x * x + (y + 0.1) ** 2)
        spill = 0.36 * (1 - smooth((r - 0.1) / 0.88)) ** 1.2  # wide dim spill, long soft falloff
        ring = 0.035 * np.exp(-((r - 0.52) / 0.12) ** 2) * (0.5 + 0.5 * waves(x, y, rng, 4, (4, 8)))  # broken reflector ring
        hot = 0.45 * np.exp(-(h / 0.2) ** 2)
        a = spill + ring + hot
        for dx, dy, s, k in dust:  # specks lit by the beam only
            a = a + k * np.exp(-((x - dx) ** 2 + (y - dy) ** 2) / (s * s)) * (spill / 0.36)
        a = np.clip(a, 0, 0.9) * (r < 1.0)
        warm = smooth(1 - h / 0.35)[..., None]  # core a touch warmer white, spill cool
        rgb = (1 - warm) * np.array([0.78, 0.9, 1.0]) + warm * np.array([0.97, 0.98, 1.0])
        return rgb, a
    still('torch', 400, 400, fn, ss=2)
    manifest('torch', {'w': 400, 'h': 400, 'anchor': [200.0, 200.0]})


def glass(name, col, clear, rough=0.25, coat=0.4, sss=0.0):
    """Clear-ish chitin / jelly: Principled mixed with Transparent, denser at grazing edges.
    clear = how see-through the middle is. Returns (mat, principled) so callers can add detail."""
    m = new_mat(name)
    bs = N(m, 'BsdfPrincipled', **{'Base Color': (*col, 1), 'Roughness': rough, 'Coat Weight': coat,
                                  'Coat Roughness': 0.2, 'Subsurface Weight': sss})
    if sss:
        bs.inputs['Subsurface Radius'].default_value = (1.0, 0.5, 0.35)
        bs.inputs['Subsurface Scale'].default_value = 0.02
    lw = N(m, 'LayerWeight', Blend=0.35)
    mx = N(m, 'MixShader', Fac=M(m, 'MULTIPLY_ADD', (lw, 'Facing'), clear * 0.6, 1 - clear))
    m.node_tree.links.new(N(m, 'BsdfTransparent', Color=(*[0.6 + 0.4 * c for c in col], 1)).outputs[0], mx.inputs[1])
    m.node_tree.links.new(bs.outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    return m, bs


def tilt_cam(ppu, w, h, t, cx=0.0, cz=0.0):
    cam = camera(w / ppu, w, h, z=cz, tilt=t)
    cam.location.x = cx


def shell_mat(name, rings):
    """Empty moult: glassy pale pink, faint red pigment remnants; rings=True adds abdomen segment joints,
    denser and whiter."""
    m, bs = glass(name, (0.95, 0.6, 0.55), 0.62, rough=0.3, coat=0.5, sss=0.2)
    co, sp = skin_coords(m)
    seg = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', (sp, 'X'), math.pi / 0.072))), 6.0)
    seg = M(m, 'SUBTRACT', 1.0, seg)  # 1 at each segment joint (carapace: none)
    if not rings:
        seg = M(m, 'MULTIPLY', seg, 0.0)
    vo = N(m, 'TexVoronoi', Vector=co, Scale=60.0)
    dot = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.05, 'From Max': 0.12, 'To Min': 0.45, 'To Max': 0.0})
    nz = N(m, 'TexNoise', Vector=co, Scale=14.0, Detail=6.0)
    c = ramp(m, (nz, 'Fac'), [(0.35, (0.88, 0.5, 0.45)), (0.7, (1.0, 0.82, 0.76))])
    c = N(m, 'Mix', _data_type='RGBA', Factor=(dot, 'Result'), A=(c, 'Color'), B=(0.75, 0.12, 0.08, 1))
    c = N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', seg, 0.6), A=(c, 'Result'), B=(1.0, 0.93, 0.9, 1))
    m.node_tree.links.new(sock(c.outputs, 'Result'), bs.inputs['Base Color'])
    b = N(m, 'Bump', Strength=0.35, Distance=0.01, Height=M(m, 'MULTIPLY_ADD', (nz, 'Fac'), 0.3, seg))
    m.node_tree.links.new(b.outputs[0], bs.inputs['Normal'])
    mx = next(n for n in m.node_tree.nodes if n.type == 'MIX_SHADER')
    src = mx.inputs[0].links[0].from_node
    m.node_tree.links.new(M(m, 'MINIMUM', M(m, 'MULTIPLY_ADD', seg, 0.3, src), 1.0).outputs[0], mx.inputs[0])  # joints more solid
    return m


def shrimp_shell():
    rig(100, 150, 70, cz=0.08)
    tilt_cam(100, 150, 70, 8, cx=0.12, cz=0.08)
    body, cmat = shell_mat('moult', True), shell_mat('carapace', False)
    limb, _ = glass('moultleg', (0.95, 0.62, 0.56), 0.4, rough=0.35, coat=0.2)
    eyec, _ = glass('eyecap', (0.9, 0.85, 0.85), 0.85, rough=0.1, coat=0.8)
    pts = [(x, y, z - 0.02) for x, y, z in spine(0.12)]  # slumped onto the sand
    pts = [(x, y, max(z, 0.038 if i < 6 else 0.026)) for i, (x, y, z) in enumerate(pts)]
    cara = [(x, y, z + 0.01 * k / 4) for k, (x, y, z) in enumerate(pts[:5])]  # carapace lifted open at the back
    objs = [tube('cara', cara, lambda t: radius(t * 0.38) * 1.06, cmat, m=22, sq=0.7),
            tube('abd', pts[4:], lambda t: radius(0.42 + t * 0.58), body, m=22, sq=0.7)]
    end, pre = np.array(pts[-1]), np.array(pts[-3])
    d = (end - pre) / np.linalg.norm(end - pre)
    d = np.array([d[0], 0, max(d[2], -0.15)])
    objs.append(tailfan(end, d / np.linalg.norm(d), body))
    for s in (-1, 1):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.016, location=(0.25, s * 0.035, 0.12))
        objs.append(bpy.context.object)
        objs[-1].data.materials.append(eyec)
        objs[-1].data.shade_smooth()
    rng = np.random.default_rng(5)
    legs = []
    for k in range(5):  # walking legs + claws lying limp, splayed out, feet on the sand
        hx = 0.21 - k * 0.05
        for s in (-1, 1):
            out = rng.uniform(0.05, 0.08)
            kx = hx + rng.uniform(-0.02, 0.05)  # knee forward and up, foot splayed on the sand
            legs.append([(hx, s * 0.02, 0.085), (kx, s * (0.03 + out * 0.5), rng.uniform(0.05, 0.085)),
                         (kx + rng.uniform(-0.05, 0.06), s * (0.03 + out), 0.004)])
    for k in range(4):  # swimmerets folded flat under the abdomen
        q = np.array(pts[5 + k * 2])
        legs.append([tuple(q - [0, 0, 0.012]), tuple(q + [-0.035, 0, -q[2] + 0.004])])
    objs.append(curve('legs', legs, 0.008, limb, radii=lambda t: 1 - 0.5 * t))
    # one long antenna draped back over the shell, the other fallen forward onto the sand; short antennules
    ant = [[(0.27, -0.02, 0.115), (0.34, -0.03, 0.18), (0.22, -0.04, 0.235), (0.04, -0.05, 0.225), (-0.14, -0.06, 0.13),
            (-0.28, -0.07, 0.03), (-0.36, -0.06, 0.005)],
           [(0.27, 0.02, 0.115), (0.36, 0.03, 0.1), (0.45, 0.05, 0.04), (0.53, 0.07, 0.006), (0.62, 0.11, 0.004),
            (0.66, 0.16, 0.012)]]
    ant += [[(0.28, s * 0.015, 0.11), (0.36, s * 0.025, 0.1), (0.42, s * 0.03, 0.06)] for s in (-1, 1)]
    objs.append(curve('ant', ant, 0.005, limb, radii=lambda t: 1 - 0.6 * t))
    objs.append(curve('rostrum', [[(0.24, 0, 0.125), (0.34, 0, 0.13)]], 0.011, cmat, radii=lambda t: 1 - 0.85 * t))
    ground(3, soft=1.5, power=800)
    sheet('shrimp_shell', [lambda: None], 1, {'base': (0.05, 0, 0)}, pad=3)
    hidpi('shrimp_shell')


def packed(rng, n, rx, rz, rmin, rmax):
    """Up to n non-overlapping circles (x, z, r) inside an ellipse; tries a while, then gives up."""
    out = []
    for _ in range(n * 60):
        r = rng.uniform(rmin, rmax)
        x, z = rng.uniform(-rx, rx), rng.uniform(-rz, rz)
        if (x / (rx - r)) ** 2 + (z / (rz - r)) ** 2 > 1:
            continue
        if all((x - a) ** 2 + (z - b) ** 2 > (r + c) ** 2 * 1.02 for a, b, c in out):
            out.append((x, z, r))
            if len(out) == n:
                break
    return out


def ball(loc, r, mat, sq=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=24, ring_count=12)
    o = bpy.context.object
    o.scale = sq
    o.data.shade_smooth()
    o.data.materials.append(mat)
    return o


def snail_eggs():
    s = rig(100, 64, 60)
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.2
    rng = np.random.default_rng(3)
    jelly, _ = glass('jelly', (0.95, 0.85, 0.82), 0.8, rough=0.08, coat=0.9)
    egg, _ = glass('egg', (0.97, 0.88, 0.84), 0.25, rough=0.3, coat=0.3, sss=0.5)
    emb = pbr('embryo', (0.75, 0.42, 0.3), (0.92, 0.6, 0.45), rough=0.5, scale=40, bump=0.1, grime=0, sss=0.4)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=48, ring_count=24)
    j = bpy.context.object
    j.scale = (0.2, 0.045, 0.15)
    j.rotation_euler.y = 0.3
    j.data.shade_smooth()
    t = bpy.data.textures.new('jel', 'CLOUDS')
    t.noise_scale = 0.6
    mod(j, 'DISPLACE', texture=t, strength=0.45, texture_coords='GLOBAL')  # lumpy, not an ellipse
    j.data.materials.append(jelly)
    c, sn = math.cos(0.3), math.sin(0.3)
    for x, z, r in packed(rng, 18, 0.17, 0.125, 0.022, 0.031):
        x, z = x * c + z * sn, -x * sn + z * c  # follow the blob's tilt
        ball((x, -0.005, z), r, egg, (1, 0.8, 1))
        a = rng.uniform(0, math.tau)
        ball((x + 0.4 * r * math.cos(a), -0.01, z + 0.4 * r * math.sin(a)), r * rng.uniform(0.38, 0.5), emb)
    sheet('snail_eggs', [lambda: None], 1, {'anchor': (0, 0, 0)}, pad=3)
    hidpi('snail_eggs')


def leaf_mat():
    """Sword-plant leaf: green ramp, pale midrib, lateral veins, see-through, a browned edge patch."""
    m = new_mat('eggleaf')
    sp = N(m, 'SeparateXYZ', Vector=N(m, 'UVMap', _uv_map='UVMap'))
    co = (N(m, 'TexCoord'), 'Object')
    du = M(m, 'MULTIPLY', M(m, 'ABSOLUTE', M(m, 'SUBTRACT', (sp, 'X'), 0.5)), 2.0)
    col = (ramp(m, (sp, 'Y'), [(0.0, (0.05, 0.11, 0.025)), (1.0, (0.12, 0.25, 0.05))]), 'Color')
    nz = N(m, 'TexNoise', Vector=co, Scale=25.0, Detail=6.0)
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.35, A=col, B=(nz, 'Color')), 'Result')
    mid = N(m, 'MapRange', Value=du, **{'From Max': 0.08, 'To Min': 1.0, 'To Max': 0.0})
    lat = M(m, 'POWER', M(m, 'ABSOLUTE', M(m, 'SINE', M(m, 'MULTIPLY', M(m, 'SUBTRACT', (sp, 'Y'), M(m, 'MULTIPLY', du, 0.3)), 34.0))), 20.0)
    vn = M(m, 'MAXIMUM', (mid, 'Result'), M(m, 'MULTIPLY', lat, 0.5))
    col = (N(m, 'Mix', _data_type='RGBA', Factor=M(m, 'MULTIPLY', vn, 0.5), A=col, B=(0.25, 0.35, 0.1, 1)), 'Result')
    bn = N(m, 'TexNoise', Vector=co, Scale=9.0, Detail=8.0)
    brown = N(m, 'MapRange', Value=M(m, 'ADD', (bn, 'Fac'), M(m, 'MULTIPLY', du, 0.4)), **{'From Min': 0.85, 'From Max': 0.95})
    col = (N(m, 'Mix', _data_type='RGBA', Factor=(brown, 'Result'), A=col, B=(0.22, 0.12, 0.03, 1)), 'Result')
    an = N(m, 'TexNoise', Vector=co, Scale=90.0, Detail=3.0)  # algae fuzz, more toward the tip
    am = N(m, 'MapRange', Value=M(m, 'ADD', (an, 'Fac'), M(m, 'MULTIPLY', (sp, 'Y'), 0.2)), **{'From Min': 0.7, 'From Max': 0.8, 'To Max': 0.6})
    col = (N(m, 'Mix', _data_type='RGBA', Factor=(am, 'Result'), A=col, B=(0.12, 0.12, 0.04, 1)), 'Result')
    bump = N(m, 'Bump', Strength=0.25, Distance=0.01, Height=M(m, 'ADD', vn, M(m, 'MULTIPLY', (nz, 'Fac'), 0.3)))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': 0.45, 'Normal': bump, 'Coat Weight': 0.15})
    mx = N(m, 'MixShader', Fac=0.3)
    m.node_tree.links.new(bs.outputs[0], mx.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTranslucent', Color=col, Normal=bump).outputs[0], mx.inputs[2])
    bite = M(m, 'LESS_THAN', M(m, 'ADD', M(m, 'MULTIPLY', M(m, 'ABSOLUTE', M(m, 'SUBTRACT', (sp, 'Y'), 0.78)), 3.0),
                               M(m, 'MULTIPLY', M(m, 'SUBTRACT', 1.0, (sp, 'X')), 1.6)), 0.12)  # snail bite, right edge
    cut = N(m, 'MixShader', Fac=bite)
    m.node_tree.links.new(mx.outputs[0], cut.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], cut.inputs[2])
    N(m, 'OutputMaterial', Surface=cut)
    return m


def egg_cluster():
    s = rig(100, 80, 70, cz=0.3)
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.4
    rng = np.random.default_rng(9)
    L = 0.46

    def W(t):  # thin stalk, then a lance-shaped blade
        return 0.008 if t < 0.2 else 0.008 + 0.15 * math.sin(math.pi * ((t - 0.2) / 0.8) ** 0.8)

    def at(u, t, lift=0.0):
        w = W(t)
        return (u * w + 0.14 * t * t, 0.12 * t * t - 0.3 * u * u * w - lift, L * t)

    n, mm = 40, 11
    verts = [at(j / (mm - 1) * 2 - 1, i / (n - 1)) for i in range(n) for j in range(mm)]
    uv = [((j / (mm - 1)), i / (n - 1)) for i in range(n) for j in range(mm)]
    faces = [(i * mm + j, i * mm + j + 1, (i + 1) * mm + j + 1, (i + 1) * mm + j) for i in range(n - 1) for j in range(mm - 1)]
    lf = mesh('leaf', verts, faces, leaf_mat(), uv=uv)
    mod(lf, 'SOLIDIFY', thickness=0.006)
    egg, _ = glass('fishegg', (0.85, 0.62, 0.25), 0.4, rough=0.2, coat=0.6, sss=0.6)
    eye = pbr('eggeye', (0.01, 0.01, 0.012), (0.03, 0.025, 0.02), rough=0.3, grime=0)
    dud = pbr('dud', (0.75, 0.75, 0.68), (0.9, 0.9, 0.85), rough=0.9, scale=60, bump=0.8, grime=0.2)  # unfertilised, gone white
    k = 0
    for row in range(7):  # slanted rows like a pair lays them, a bit ragged
        t = 0.36 + row * 0.07
        for u in np.arange(-0.65, 0.66, 0.36) + row % 2 * 0.18:
            if abs(u) > 0.75 or rng.random() < 0.15:
                continue
            r = rng.uniform(0.016, 0.019)
            x, y, z = at(u + rng.uniform(-0.05, 0.05), t + rng.uniform(-0.01, 0.01), 0.75 * r)
            k += 1
            if k % 9 == 4:
                ball((x, y, z), r * 1.1, dud)
                continue
            ball((x, y, z), r, egg)
            if rng.random() < 0.6:  # eyed: two dark dots of the fry inside
                for dx in (-0.35 * r, 0.35 * r):
                    ball((x + dx, y - 0.7 * r, z + 0.2 * r), 0.2 * r, eye)
    ground(3, soft=1.5, power=600)
    sheet('egg_cluster', [lambda: None], 1, {'base': (0, 0, 0)}, pad=3)
    hidpi('egg_cluster')


JOBS = {'vignette': vignette, 'torch': torch, 'shrimp_shell': shrimp_shell, 'snail_eggs': snail_eggs,
        'egg_cluster': egg_cluster}

if __name__ == '__main__':
    want = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(JOBS)
    bad = [w for w in want if w not in JOBS]
    if bad:
        sys.exit(f'scene_extras.py: unknown {bad}; choose from {list(JOBS)}')
    for w in want:
        JOBS[w]()
