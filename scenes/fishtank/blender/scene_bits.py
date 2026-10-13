# Small tank bits: fish food sheet (3 flake kinds + pellet, 8 tumble steps) and four numpy stills
# (shadow, glow, ring, crumb). Also holds rig()/half(), shared by the critter scripts.
# Usage: blender -b --factory-startup -P blender/scene_bits.py   (SAMPLES env = render samples)
import json, math, os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *


def rig(ppu, w_px, h_px, cx=0.0, cz=0.0):
    """Critter render: the scenery light rig and exposure (critters live among the props; the fish
    rig's blue fill turns warm colours olive on side-lit bodies), straight-on ortho camera, ppu
    pixels per unit. Render at 2x on-screen size, then half()."""
    s = scenery(int(os.environ.get('SAMPLES', 96)))
    s.cycles.pixel_filter_width = 1.2
    cam = camera(w_px / ppu, w_px, h_px, z=cz)
    cam.location.x = cx
    return s


def half(name):
    """A sheet rendered at 2x -> on-screen size: box-filter each frame (premultiplied), halve w/h
    and every point."""
    path = os.path.join(ASSETS, name + '.png')
    with open(os.path.join(ASSETS, 'manifest.json')) as f:
        ent = json.load(f)['images'][name]
    fw, fh, n, cols = ent['w'], ent['h'], ent.get('n', 1), ent.get('cols', 1)
    rows = -(-n // cols)
    ew, eh = fw + fw % 2, fh + fh % 2
    fr = np.zeros((rows, eh, cols, ew, 4), np.float32)
    fr[:, :fh, :, :fw] = load_png(path).reshape(rows, fh, cols, fw, 4)
    fr[..., :3] *= fr[..., 3:]
    sm = fr.reshape(rows, eh // 2, 2, cols, ew // 2, 2, 4).mean((2, 5))
    sm[..., :3] /= np.maximum(sm[..., 3:], 1e-6)
    save_png(sm.reshape(rows * eh // 2, cols * ew // 2, 4), path)
    for k, v in ent.items():
        if isinstance(v, list) and len(v) == 2 and k != 'px':
            ent[k] = [round(v[0] / 2, 1), round(v[1] / 2, 1)]
    ent.update(w=ew // 2, h=eh // 2)
    ent.pop('px', None)
    manifest(name, ent)
    print('half', name, ent)


def flake_mesh(sd, mat):
    """Thin torn flake: irregular rim with a few bites out of it, a crinkle, uv.x = 0 centre .. 1 rim."""
    rng = np.random.default_rng(sd)
    na, rings = 56, (0.0, 0.35, 0.7, 0.9, 1.0)
    ang = np.linspace(0, math.tau, na, endpoint=False)
    ca = np.sort(rng.uniform(0, math.tau, 11))  # torn polygon: straight-ish edges between random corners
    cr = rng.uniform(0.72, 1.1, 11)
    rad = np.interp(ang, np.r_[ca - math.tau, ca, ca + math.tau], np.r_[cr, cr, cr])
    rad += 0.04 * np.sin(ang * 17 + sd) + 0.03 * np.sin(ang * 29)  # ragged fibre edge
    for _ in range(rng.integers(2, 4)):  # bites: torn notches
        c = rng.uniform(0, math.tau)
        d = np.angle(np.exp(1j * (ang - c)))
        rad -= rng.uniform(0.15, 0.3) * np.exp(-(d / rng.uniform(0.12, 0.25)) ** 2)
    sx = rng.uniform(0.75, 1.0)
    verts, uv, faces = [(0, 0, 0)], [(0, 0)], []
    for ri, r in enumerate(rings[1:], 1):
        for a, ra in zip(ang, rad):
            x, z = math.cos(a) * ra * r * sx, math.sin(a) * ra * r
            y = 0.06 * math.sin(x * 4 + sd) * math.cos(z * 3) + 0.04 * r * math.sin(a * 3 + sd)  # crinkle
            verts.append((x, y, z))
            uv.append((r, 0))
    for j in range(na):
        faces.append((0, 1 + j, 1 + (j + 1) % na))
    for ri in range(len(rings) - 2):
        b0, b1 = 1 + ri * na, 1 + (ri + 1) * na
        for j in range(na):
            faces.append((b0 + j, b1 + j, b1 + (j + 1) % na, b0 + (j + 1) % na))
    o = mesh('flake', verts, faces, mat, uv=uv)
    mod(o, 'SOLIDIFY', thickness=0.025)
    return o


def flake_mat(name, c1, c2, speck):
    """Papery flake: mottled colour, dark specks, light shining through, see-through torn rim."""
    m = new_mat(name)
    co = (N(m, 'TexCoord'), 'Object')
    rim = N(m, 'SeparateXYZ', Vector=(N(m, 'UVMap', _uv_map='UVMap'), 'UV'))
    nz = N(m, 'TexNoise', Vector=co, Scale=3.0, Detail=6.0, Roughness=0.7)
    col = (ramp(m, (nz, 'Fac'), [(0.3, c1), (0.7, c2)]), 'Color')
    vo = N(m, 'TexVoronoi', Vector=co, Scale=14.0)
    dot = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.05, 'From Max': 0.14, 'To Min': 0.8, 'To Max': 0.0})
    col = (N(m, 'Mix', _data_type='RGBA', Factor=(dot, 'Result'), A=col, B=(*speck, 1)), 'Result')
    fib = N(m, 'TexWave', Vector=co, Scale=2.5, Distortion=8.0, Detail=6.0)  # pressed fibres
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.25, A=col, B=(fib, 'Color')), 'Result')
    alpha = N(m, 'MapRange', Value=(rim, 'X'), **{'From Min': 0.6, 'From Max': 1.0, 'To Min': 0.92, 'To Max': 0.45})
    bump = N(m, 'Bump', Strength=0.4, Distance=0.02, Height=M(m, 'ADD', (nz, 'Fac'), (fib, 'Fac')))
    bs = N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': 0.55, 'Normal': bump, 'Alpha': (alpha, 'Result')})
    tr = N(m, 'BsdfTranslucent', Color=col)
    mx = N(m, 'MixShader', Fac=0.35)
    m.node_tree.links.new(bs.outputs[0], mx.inputs[1])
    m.node_tree.links.new(tr.outputs[0], mx.inputs[2])
    tp = N(m, 'MixShader', Fac=M(m, 'SUBTRACT', 1.0, (alpha, 'Result')))  # rim alpha on the whole mix
    m.node_tree.links.new(mx.outputs[0], tp.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], tp.inputs[2])
    N(m, 'OutputMaterial', Surface=tp)
    return m


def pellet():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.62, segments=48, ring_count=24)
    o = bpy.context.object
    o.scale = (1, 0.95, 0.92)
    o.data.shade_smooth()
    t = bpy.data.textures.new('pel', 'CLOUDS')
    t.noise_scale = 0.3
    mod(o, 'DISPLACE', texture=t, strength=0.05)
    m = pbr('pellet', (0.28, 0.1, 0.035), (0.5, 0.22, 0.07), rough=0.7, scale=2.5, bump=0.6, vor=0.5, grime=0.3, sss=0.4)
    o.data.materials.append(m)
    return o


def food():
    s = rig(18, 52, 52)  # 2x: flake ~2 units = 36 px -> 18 px on screen in a 26 px frame
    kinds = [flake_mat('red', (0.42, 0.03, 0.02), (0.75, 0.12, 0.05), (0.15, 0.01, 0.01)),
             flake_mat('green', (0.08, 0.2, 0.03), (0.25, 0.42, 0.07), (0.03, 0.06, 0.01)),
             flake_mat('tan', (0.35, 0.2, 0.05), (0.62, 0.42, 0.12), (0.12, 0.06, 0.02))]
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.4  # tiny: no dead-black side
    bpy.data.objects['key'].data.angle = math.radians(45)  # soft terminator on the pellet
    objs = [flake_mesh(sd, m) for sd, m in zip((3, 11, 23), kinds)] + [pellet()]
    poses = []
    for i, o in enumerate(objs):
        for k in range(8):
            def pose(i=i, k=k):
                for j, q in enumerate(objs):
                    q.hide_render = j != i
                if i < 3:  # flat flake faces the camera tilted 20 deg; tumble = flip about x
                    objs[i].rotation_euler = (math.radians(20 + k * 45), math.radians(10 * i), 0)
                else:  # pellet rolls about the view axis
                    objs[i].rotation_euler = (0, math.radians(k * 45), 0)
            poses.append(pose)
    sheet('food', poses, 8, {'anchor': (0, 0, 0)}, pad=2)
    half('food')


def stills():
    r = lambda x, y: np.sqrt(x * x + y * y)  # noqa: E731
    still('shadow', 96, 32, lambda x, y: ((0.0, 0.02, 0.04), 0.6 * np.exp(-3.2 * r(x, y) ** 2) * (r(x, y) < 1)))
    still('glow', 64, 64, lambda x, y: ((0.8, 0.95, 1.0), 0.85 * np.clip(1 - r(x, y), 0, 1) ** 2.2))

    def ring(x, y):
        d = r(x, y)
        a = 0.85 * np.exp(-((d - 0.82) / 0.07) ** 2) + 0.25 * np.exp(-((d - 0.6) / 0.08) ** 2)
        return (0.85, 0.97, 1.0), a * (0.75 + 0.25 * np.sin(np.arctan2(y, x) * 3) ** 2)
    still('ring', 48, 16, ring)

    def crumb(x, y):
        a = np.arctan2(y, x)
        d = r(x, y) / (0.7 + 0.15 * np.sin(a * 3 + 1) + 0.1 * np.sin(a * 5))
        return (0.45, 0.2, 0.08), np.clip((1 - d) * 4, 0, 1) * 0.95
    still('crumb', 8, 8, crumb)


if __name__ == '__main__':
    stills()
    food()
