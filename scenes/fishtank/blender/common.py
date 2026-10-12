# Shared render setup so scenery and fish share one camera, light rig and look.
# Run scripts as: blender -b --factory-startup -P blender/<script>.py
import fcntl
import json
import math
import os
import random
import struct
import tempfile
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets')
REF = 1440          # screen height the art is drawn for (manifest 'ref')
PPU = 100           # scenery: pixels per world unit at the 1440 px reference height
WATER = (0.03, 0.16, 0.24)  # haze colour (linear) that far things fade into
BACKDROP = [(0.0, (0.004, 0.035, 0.06)), (0.35, (0.012, 0.085, 0.13)),  # water gradient, bottom to top
            (0.75, (0.04, 0.2, 0.27)), (1.0, (0.09, 0.36, 0.42))]
TILT = 14           # scenery camera pitch (degrees) so the floor recedes and props show their tops


def reset(samples=128):
    """Empty scene, Cycles, transparent film, Standard view (no filmic wash-out)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.film_transparent = True
    s.render.image_settings.file_format = 'PNG'
    s.render.image_settings.color_mode = 'RGBA'
    s.view_settings.view_transform = 'Standard'
    s.view_settings.look = 'None'
    world = bpy.data.worlds.new('water')
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.05, 0.22, 0.32, 1)  # blue-green ambient bounce
    bg.inputs['Strength'].default_value = 0.6
    s.world = world
    return s


def camera(width_m, px_w, px_h, y=-10.0, z=0.0, tilt=0.0):
    """Orthographic view looking down +Y; width_m world units map to px_w pixels.
    tilt (degrees) pitches it down so scenery shows its top and sits on a receding floor."""
    s = bpy.context.scene
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = width_m * max(1, px_h / px_w)
    cam.data.clip_end = 400
    a = math.radians(tilt)
    cam.location = (0, y * math.cos(a), z - y * math.sin(a))
    cam.rotation_euler = (math.radians(90 - tilt), 0, 0)
    s.collection.objects.link(cam)
    s.camera = cam
    s.render.resolution_x, s.render.resolution_y = px_w, px_h
    s.render.resolution_percentage = 100
    return cam


def fit(objs, margin=0.15, tilt=TILT, ppu=PPU):
    """Scenery camera framed on objs' bounding boxes at a fixed pixel density, so every
    sprite shares one scale (ppu pixels per world unit at the 1440 px reference height)."""
    cam = camera(1, 1, 1, tilt=tilt)
    bpy.context.view_layer.update()
    inv = cam.matrix_world.inverted()
    pts = [inv @ (o.matrix_world @ Vector(c)) for o in objs for c in o.bound_box]
    x0, x1 = min(p.x for p in pts) - margin, max(p.x for p in pts) + margin
    y0, y1 = min(p.y for p in pts) - margin, max(p.y for p in pts) + margin
    cam.location = cam.matrix_world @ Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0))
    cam.data.ortho_scale = max(x1 - x0, y1 - y0)
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = round((x1 - x0) * ppu), round((y1 - y0) * ppu)
    for o in s.objects:  # shrink shadow-catcher fades to stay inside the frame
        fade = o.is_shadow_catcher and o.active_material and o.active_material.node_tree.nodes.get('fade')
        if fade:
            rx = 0.95 * min(-x0, x1) if x0 < 0 < x1 else 1
            ry = 0.95 * -y0 / math.sin(math.radians(tilt)) if y0 < 0 and tilt else 1
            fade.inputs['Scale'].default_value = (1 / max(rx, 0.3), 1 / max(ry, 0.3), 1)
    return cam


def lights():
    """Warm soft key from the surface, cool fill from the front, rim from behind."""
    s = bpy.context.scene

    def add(name, kind, energy, color, loc, rot, size):
        l = bpy.data.lights.new(name, kind)
        l.energy, l.color = energy, color
        if kind == 'AREA':
            l.size = size
        else:
            l.angle = size
        o = bpy.data.objects.new(name, l)
        o.location, o.rotation_euler = loc, [math.radians(a) for a in rot]
        s.collection.objects.link(o)
        return o

    return [
        add('key', 'SUN', 3.2, (1.0, 0.95, 0.82), (0, 0, 10), (-15, 10, 0), math.radians(8)),
        add('fill', 'AREA', 250, (0.55, 0.8, 1.0), (0, -8, 1), (80, 0, 0), 12),
        add('rim', 'AREA', 180, (0.6, 0.95, 1.0), (0, 6, 4), (-120, 0, 0), 8),
    ]


def scenery(samples=None):
    """reset + the shared rig + a broad soft light from the surface, for scenery props.
    samples defaults to the SAMPLES env var, else 256."""
    s = reset(samples or int(os.environ.get('SAMPLES', 256)))
    key, fill, _ = lights()
    fill.data.energy = 50  # less flat front light than the fish get: props need modelling
    key.data.energy = 4.0
    top = bpy.data.objects.new('top', bpy.data.lights.new('top', 'AREA'))
    top.data.energy, top.data.size, top.data.color = 60, 5, (0.85, 0.95, 1.0)
    top.location = (0, 0, 6)
    s.collection.objects.link(top)
    warm = bpy.data.objects.new('sandbounce', bpy.data.lights.new('sandbounce', 'AREA'))  # sunlit sand bouncing up warm
    warm.data.energy, warm.data.size, warm.data.color = 160, 5, (1.0, 0.72, 0.45)
    warm.location, warm.rotation_euler = (0, -5, 0.2), (math.radians(95), 0, 0)
    s.collection.objects.link(warm)
    s.view_settings.exposure = -0.6
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.6  # water scatters light all round
    return s


def render(path):
    """Render the current scene to assets/<path> (PNG, RGBA)."""
    out = os.path.join(ASSETS, path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    return out


# ---- scenery helpers (fish scripts may use them too) ----

def sock(coll, key):
    """Socket by index or by name, skipping ones hidden by the node's mode (Mix has 3 'A's)."""
    return coll[key] if isinstance(key, int) else next(s for s in coll if s.name == key and s.enabled)


def N(mat, kind, x=0, **inputs):
    """Add a shader node; inputs are socket values or (node, output) links. _attr sets a property
    (pass those first, they change which sockets exist)."""
    nt = mat.node_tree
    n = nt.nodes.new('ShaderNode' + kind)
    n.location = (x, 0)
    for k, v in inputs.items():
        if k.startswith('_'):
            setattr(n, k[1:], v)
        elif isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], bpy.types.Node):
            nt.links.new(sock(v[0].outputs, v[1]), sock(n.inputs, k))
        elif isinstance(v, bpy.types.Node):
            nt.links.new(next(s for s in v.outputs if s.enabled), sock(n.inputs, k))
        else:
            sock(n.inputs, k).default_value = v
    return n


def M(mat, op, *args):
    """Math node; args are numbers, nodes or (node, output)."""
    n = N(mat, 'Math', _operation=op)
    for i, a in enumerate(args):
        if isinstance(a, (int, float)):
            n.inputs[i].default_value = a
        else:
            node, out = a if isinstance(a, tuple) else (a, 0)
            mat.node_tree.links.new(sock(node.outputs, out), n.inputs[i])
    return n


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    return m


def ramp(mat, fac, stops):
    """ColorRamp from (pos, rgb) stops."""
    r = N(mat, 'ValToRGB', Fac=fac)
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0)
    for e, (p, c) in zip(els, stops):
        e.position, e.color = p, (*c, 1) if len(c) == 3 else c
    return r


def pbr(name, c1, c2=None, rough=0.6, metal=0.0, scale=3.0, bump=0.25, moss=0.0, grime=0.6,
        sss=0.0, coat=0.0, detail=8.0, vor=0.0, color=None, cracks=0.0, strata=0.0, wrap=0.0):
    """Principled material with real surface detail: noise colour variation, bump (plus voronoi
    pits when vor>0), crevice grime from AO, and moss on upward faces when moss>0.
    color: optional (node, socket) replacing the noise colour (wood grain etc.)."""
    m = new_mat(name)
    co = (N(m, 'TexCoord'), 'Object')
    if wrap:  # texture repeats every `wrap` units in x (for tiling strips): x wraps round a circle
        sep = N(m, 'SeparateXYZ', Vector=(N(m, 'TexCoord'), 'Object'))
        a = M(m, 'MULTIPLY', (sep, 'X'), 2 * math.pi / wrap)
        r = wrap / (2 * math.pi)
        co = (N(m, 'CombineXYZ', X=M(m, 'MULTIPLY', M(m, 'COSINE', a), r), Y=M(m, 'MULTIPLY', M(m, 'SINE', a), r),
                Z=M(m, 'MULTIPLY_ADD', (sep, 'Y'), 0.37, (sep, 'Z'))), 'Vector')
    nz = N(m, 'TexNoise', Vector=co, Scale=scale, Detail=detail, Roughness=0.62)
    fine = N(m, 'TexNoise', Vector=co, Scale=scale * 9, Detail=4.0)
    col = color or (ramp(m, (nz, 'Fac'), [(0.3, c1), (0.75, c2 or c1)]), 'Color')
    height = M(m, 'MULTIPLY_ADD', (fine, 'Fac'), 0.4, M(m, 'MULTIPLY', (nz, 'Fac'), 0.6))
    if vor:
        v = N(m, 'TexVoronoi', Vector=co, Scale=scale * 4, _feature='SMOOTH_F1')
        height = M(m, 'MULTIPLY_ADD', (v, 'Distance'), vor, height)
    if strata:
        wv = N(m, 'TexWave', Vector=co, _bands_direction='Z', Scale=scale * 0.8, Distortion=6.0,
               Detail=4.0, **{'Detail Scale': 1.5})
        height = M(m, 'MULTIPLY_ADD', (wv, 'Fac'), strata, height)
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.15, A=col, B=(wv, 'Color')), 'Result')
    if cracks:
        cv = N(m, 'TexVoronoi', Vector=co, Scale=scale * 1.3, _feature='DISTANCE_TO_EDGE')
        cw = N(m, 'MapRange', Value=(cv, 'Distance'), **{'From Min': 0.0, 'From Max': 0.012})
        cn = N(m, 'TexNoise', Vector=co, Scale=scale * 2, Detail=2.0)
        keep = N(m, 'MapRange', Value=(cn, 'Fac'), **{'From Min': 0.56, 'From Max': 0.6})  # only some edges crack
        crack = M(m, 'MAXIMUM', (cw, 'Result'), (keep, 'Result'))
        height = M(m, 'MULTIPLY_ADD', crack, cracks, height)
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=M(m, 'SUBTRACT', 1.0, crack), A=col,
                 B=(0.4, 0.4, 0.4, 1)), 'Result')
    # macro value variation (big soft patches, x0.85-1.15) so no surface reads as one flat fill
    mac = N(m, 'TexNoise', Vector=co, Scale=scale * 0.15, Detail=2.0)
    mv = N(m, 'MapRange', Value=(mac, 'Fac'), **{'From Min': 0.3, 'From Max': 0.7, 'To Min': 0.85, 'To Max': 1.15})
    col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=col, B=(mv, 'Result')), 'Result')
    col[0].name = 'macro'  # first colour stage: callers that swap the base colour link into its A
    if grime:
        col = ao_grime(m, col, 0.25, 1 - grime)
        col = ao_grime(m, col, 0.8, 1 - grime * 0.45)  # broad occlusion: bases and under-hangs darker
    rn = N(m, 'TexNoise', Vector=co, Scale=scale * 0.3, Detail=2.0)
    r = (N(m, 'MapRange', Value=(rn, 'Fac'), **{'From Min': 0.3, 'From Max': 0.7, 'To Min': max(0, rough - 0.12),
                                                 'To Max': min(1, rough + 0.12)}), 'Result')  # sheen breaks up
    if moss:
        geo = N(m, 'NewGeometry')
        up = N(m, 'SeparateXYZ', Vector=(geo, 'Normal'))
        mn = N(m, 'TexNoise', Vector=co, Scale=scale * 1.7, Detail=10.0)
        mask = M(m, 'MULTIPLY', (up, 'Z'), (mn, 'Fac'))
        mk = N(m, 'MapRange', Value=mask, **{'From Min': 0.62 - moss * 0.3, 'From Max': 0.7 - moss * 0.3})
        mc = ramp(m, (fine, 'Fac'), [(0.35, (0.05, 0.09, 0.015)), (0.65, (0.16, 0.22, 0.04))])
        col = (N(m, 'Mix', _data_type='RGBA', Factor=(mk, 'Result'), A=col, B=(mc, 'Color')), 'Result')
        r = N(m, 'MapRange', Value=(mk, 'Result'), **{'To Min': rough, 'To Max': 0.95})
        r = (r, 'Result')
    b = N(m, 'Bump', Strength=bump, Distance=0.05, Height=height)
    bs = N(m, 'BsdfPrincipled', **{'Base Color': col, 'Roughness': r, 'Metallic': metal, 'Normal': b,
                                   'Subsurface Weight': sss, 'Coat Weight': coat})
    if sss:
        bs.inputs['Subsurface Radius'].default_value = (0.4, 0.25, 0.15)
        bs.inputs['Subsurface Scale'].default_value = 0.05
    N(m, 'OutputMaterial', Surface=bs)
    return m


def ao_grime(m, col, dist, lo):
    """Darken colour socket col toward lo in crevices (AO); returns the new (node, socket)."""
    ao = N(m, 'AmbientOcclusion', Distance=dist, _samples=8)
    g = N(m, 'MapRange', Value=(ao, 'AO'), **{'To Min': lo})
    return (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=col, B=(g, 'Result')), 'Result')


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def fog(amount, far=0.0, color=WATER, vmap=None):
    """Fade every material toward the water colour: `amount` plus `far` more per 10 units behind
    y=0 (alpha untouched). vmap=(a, b) takes the colour from the backdrop gradient at a*v + b,
    v = height on screen in world units."""
    s = bpy.context.scene
    t = math.radians(TILT)
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not out or not out.inputs['Surface'].links:
            continue
        geo = N(m, 'NewGeometry')
        y = N(m, 'SeparateXYZ', Vector=(geo, 'Position'))
        f = M(m, 'MULTIPLY_ADD', (y, 'Y'), far / 10, amount)
        f.use_clamp = True
        em = N(m, 'Emission', Color=(*color, 1), Strength=2 ** -s.view_settings.exposure)
        if vmap:
            v = N(m, 'VectorMath', _operation='DOT_PRODUCT', Vector=(geo, 'Position'))
            v.inputs[1].default_value = (0, math.sin(t), math.cos(t))
            g = ramp(m, M(m, 'MULTIPLY_ADD', (v, 'Value'), vmap[0], vmap[1]), BACKDROP)
            nt.links.new(g.outputs['Color'], em.inputs['Color'])
        mix_surface(m, f, em)


def mix_surface(m, fac, shader, first=False):
    """Insert MixShader(fac) between m's final shader and its output; `shader` goes in the
    second slot (the first if first=True)."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    surf = out.inputs['Surface'].links[0].from_socket
    mix = N(m, 'MixShader', Fac=fac)
    a, b = (shader.outputs[0], surf) if first else (surf, shader.outputs[0])
    nt.links.new(a, mix.inputs[1])
    nt.links.new(b, mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])


def wrap(o, L):
    """Copies of o one period L either side, so a tiling strip has no seam."""
    for dx in (-L, L):
        c = o.copy()
        c.location.x += dx
        bpy.context.scene.collection.objects.link(c)


def mesh(name, verts, faces, mat=None, smooth=True, uv=None):
    """Mesh object from verts/faces; uv = optional per-vertex UVs."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    if smooth:
        me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if mat:
        me.materials.append(mat)
    if uv is not None:
        lay = me.uv_layers.new(name='UVMap')
        for loop in me.loops:
            lay.data[loop.index].uv = uv[loop.vertex_index]
    return o


def aim(normal):
    """Euler turning +Z onto normal."""
    return Vector((0, 0, 1)).rotation_difference(Vector(normal)).to_euler()


def curve(name, paths, depth, mat, res=0, radii=None):
    """One round-bevelled POLY curve object, a tube per point path; radii(t) tapers each."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', depth, res, True
    for pts in paths:
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (*p, 1)
            if radii:
                sp.points[i].radius = radii(i / (len(pts) - 1))
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    cu.materials.append(mat)
    return o


def mod(o, kind, **kw):
    m = o.modifiers.new(kind.lower(), kind)
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def apply_all(o):
    bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def ground(size=8.0, z=0.0, soft=3.0, power=3000):
    """Shadow-catcher floor for a soft contact shadow, lit by its own floor-only light."""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    p = bpy.context.object
    p.is_shadow_catcher = True
    # shadow fades out on an ellipse (fit() sizes it) so it has no hard edge
    m = new_mat('catcher')
    d = N(m, 'VectorMath', _operation='LENGTH', Vector=N(m, 'Mapping', Vector=(N(m, 'TexCoord'), 'Object')))
    d.inputs[0].links[0].from_node.name = 'fade'
    f = N(m, 'MapRange', Value=(d, 'Value'), **{'From Min': 0.5, 'To Min': 1.0, 'To Max': 0.0}, _interpolation_type='SMOOTHSTEP')
    mx = N(m, 'MixShader', Fac=(f, 'Result'))
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mx.inputs[1])
    m.node_tree.links.new(N(m, 'BsdfDiffuse').outputs[0], mx.inputs[2])
    N(m, 'OutputMaterial', Surface=mx)
    p.data.materials.append(m)
    p.visible_diffuse = p.visible_glossy = p.visible_transmission = False  # its light must not bounce onto the prop
    rc = bpy.data.collections.new('floor_only')
    rc.objects.link(p)
    l = bpy.data.objects.new('contact', bpy.data.lights.new('contact', 'AREA'))
    l.data.energy, l.data.size = power, soft
    l.location = (0, 0, z + 2.0)
    l.light_linking.receiver_collection = rc
    bpy.context.scene.collection.objects.link(l)
    # unseen sand-coloured floor just below, so the rig's light still bounces up warm
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z - 0.003))
    b = bpy.context.object
    b.visible_camera = b.visible_shadow = False
    m = new_mat('bounce')
    N(m, 'OutputMaterial', Surface=N(m, 'BsdfDiffuse', Color=(0.32, 0.27, 0.19, 1)))
    b.data.materials.append(m)
    return p


def sprite(name, points=None, pad=6, cut=8, extra=None, crop=True):
    """Render assets/<name>.png cropped to its visible pixels, and record its size plus
    named world points (anchors/pivots/emitters) in pixel coords in assets/manifest.json.
    crop=False keeps the full frame: animation frames are cropped together later by crop_frames."""
    s = bpy.context.scene
    render(f'{name}.png')
    W, H = s.render.resolution_x, s.render.resolution_y
    ent = {'w': W, 'h': H}
    for k, co in (points or {}).items():
        v = world_to_camera_view(s, s.camera, Vector(co))
        ent[k] = [round(float(v.x * W), 1), round(float((1 - v.y) * H), 1)]
    ent.update(extra or {})
    manifest(name, ent)
    return crop_frames([name], pad, cut)[0] if crop else ent


def crop_frames(names, pad=6, cut=8):
    """Crop same-size PNGs to the union of their visible pixels (so frames still overlay), shift
    their manifest points to match and record the crop offset as ox/oy."""
    paths = [os.path.join(ASSETS, n + '.png') for n in names]
    pxs = [load_png(p) for p in paths]
    x0, x1, y0, y1 = _box(pxs, pad, cut)
    ents = []
    for n, p, px in zip(names, paths, pxs):
        save_png(px[y0:y1, x0:x1], p)
        with open(os.path.join(ASSETS, 'manifest.json')) as f:
            fcntl.flock(f, fcntl.LOCK_SH)  # manifest() rewrites it under LOCK_EX
            ent = json.load(f)['images'].get(n, {})
        for k, v in ent.items():
            if isinstance(v, list) and len(v) == 2:
                ent[k] = [round(v[0] - float(x0), 1), round(v[1] - float(y0), 1)]
        ent.update(w=int(x1 - x0), h=int(y1 - y0), ox=ent.get('ox', 0) + int(x0), oy=ent.get('oy', 0) + int(y0))
        manifest(n, ent)
        print('sprite', n, ent)
        ents.append(ent)
    return ents


def _box(pxs, pad, cut):
    """Union crop box (x0, x1, y0, y1) of same-size frames' visible pixels."""
    H, W = pxs[0].shape[:2]
    a = np.stack(pxs)[..., 3].max(0) > cut / 255  # np.stack fails loudly if sizes differ
    ys, xs = np.nonzero(a.sum(1) >= 3)[0], np.nonzero(a.sum(0) >= 3)[0]  # ignore stray noise specks
    return max(0, xs.min() - pad), min(W, xs.max() + 1 + pad), max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)


def project(co):
    """World point -> [x, y] px in the current render frame."""
    s = bpy.context.scene
    v = world_to_camera_view(s, s.camera, Vector(co))
    return [float(v.x * s.render.resolution_x), float((1 - v.y) * s.render.resolution_y)]


def sheet(name, poses, cols, points=None, pad=6, cut=8, extra=None):
    """Sprite sheet: render one full frame per pose() call, crop all to their union (frames still
    overlay), tile row-major into assets/<name>.png, write {w, h, n, cols, px, points, extra}.
    points: key -> world co (or a callable returning one), projected right after poses[0]()."""
    s = bpy.context.scene
    pxs, pts = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'f.png')
        for i, pose in enumerate(poses):
            pose()
            bpy.context.view_layer.update()
            if not i:
                pts = {k: project(co() if callable(co) else co) for k, co in (points or {}).items()}
            s.render.filepath = path
            bpy.ops.render.render(write_still=True)
            pxs.append(load_png(path))
    x0, x1, y0, y1 = _box(pxs, pad, cut)
    fw, fh, n = int(x1 - x0), int(y1 - y0), len(pxs)
    out = np.zeros((-(-n // cols) * fh, cols * fw, 4), np.float32)
    for i, p in enumerate(pxs):
        r, c = divmod(i, cols)
        out[r * fh:(r + 1) * fh, c * fw:(c + 1) * fw] = p[y0:y1, x0:x1]
    save_png(out, os.path.join(ASSETS, name + '.png'))
    ent = dict(w=fw, h=fh, n=n, cols=cols, **{k: [round(x - float(x0), 1), round(y - float(y0), 1)] for k, (x, y) in pts.items()})
    ent.update(extra or {})
    manifest(name, ent)
    print('sheet', name, ent)
    return ent


def mark_rest(name, over=None):
    """Add `rest` = [x, y] to name's manifest entry: the top edge (median over the middle 60 % of
    columns) where falling food comes to lie on it. over: a separately cropped overlay on top of it
    (chest lid), placed by ox/oy; its top edge is used instead."""
    with open(os.path.join(ASSETS, 'manifest.json')) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        imgs = json.load(f)['images']
    ent, src = imgs[name], imgs[over or name]
    a = load_png(os.path.join(ASSETS, (over or name) + '.png'))[..., 3] > 0.5
    mid = a[:, int(a.shape[1] * 0.2):int(a.shape[1] * 0.8)]
    y = float(np.median([np.argmax(c) for c in mid.T if c.any()])) + src.get('oy', 0) - ent.get('oy', 0)
    ent['rest'] = [round(ent['w'] / 2, 1), round(y, 1)]
    manifest(name, ent)


def load_png(path):
    """PNG -> (H, W, 4) float32 array, top row first."""
    im = bpy.data.images.load(path)
    W, H = im.size
    px = np.empty(W * H * 4, np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(H, W, 4)[::-1]


def save_png(px, path):
    """Write an (H, W, 4) float array, top row first, as an RGBA PNG."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = bpy.data.images.new('png', px.shape[1], px.shape[0], alpha=True)
    im.pixels.foreach_set(np.ascontiguousarray(px[::-1], np.float32).ravel())
    im.filepath_raw, im.file_format = path, 'PNG'
    im.save()
    bpy.data.images.remove(im)


def manifest(name, ent):
    """Set images[name] in assets/manifest.json ({ref, images}); px = the PNG's real size."""
    png = os.path.join(ASSETS, name + '.png')
    if os.path.exists(png):
        with open(png, 'rb') as f:
            ent['px'] = list(struct.unpack('>II', f.read(24)[16:24]))  # IHDR width, height
    with open(os.path.join(ASSETS, 'manifest.json'), 'a+') as f:  # several scripts may render at once
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        txt = f.read()
        data = json.loads(txt) if txt.strip() else {'images': {}}
        data['ref'] = REF
        data['images'][name] = ent
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, separators=(',', ':'), sort_keys=True))


def seed(n):
    random.seed(n)
    np.random.seed(n)


def rock(size, sink=0.3, sd=1, facets=0.015, loc=(0, 0, 0)):
    """Chunky natural rock: noise-displaced sphere, decimated into big facets, then softened.
    sd picks a different shape; sink buries it that far below z=0."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=1)
    o = bpy.context.object
    o.scale = size
    for kind, s, strength, depth in (('VORONOI', 0.9, 0.35, 0), ('CLOUDS', 0.5, 0.25, 4), ('CLOUDS', 0.12, 0.05, 2)):
        t = bpy.data.textures.new('rk', kind)
        t.noise_scale = s
        if depth:
            t.noise_depth = depth
        mod(o, 'DISPLACE', texture=t, strength=strength, texture_coords='GLOBAL')
    o.location = (sd * 7.3, sd * 3.1, sd * 1.7)  # moves the noise per rock
    mod(o, 'DECIMATE', ratio=facets)
    apply_all(o)
    o.scale = (1, 1, 1) if o.scale[0] == 1 else o.scale
    mod(o, 'BEVEL', width=0.05, segments=3, limit_method='ANGLE', angle_limit=math.radians(25))
    mod(o, 'SUBSURF', levels=1, render_levels=1)
    apply_all(o)
    o.location = (0, 0, -sink)
    bpy.ops.object.transform_apply(location=True, scale=True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    o.location = loc
    return o


def stone(name, moss=0.4, c1=(0.07, 0.065, 0.06), c2=(0.2, 0.17, 0.13), scale=1.6):
    return pbr(name, c1, c2, rough=0.85, scale=scale, bump=0.5, vor=0.2, moss=moss, grime=0.7, cracks=0.4, strata=0.12)


def sand_mat(wrap=0.0):
    """Wet aquarium sand with coloured grains; the sand bed and the berms props sink into share it."""
    m = pbr('sand', (0.24, 0.14, 0.055), (0.5, 0.34, 0.16), rough=0.75, scale=0.6, bump=0.3, grime=0.6, wrap=wrap)
    nt = m.node_tree
    bs = principled(m)
    # coloured grains: tiny voronoi cells, a few tinted dark / rust / white
    cx = next((n for n in nt.nodes if n.type == 'COMBXYZ'), None)
    co = cx.outputs[0] if cx else next(n for n in nt.nodes if n.type == 'TEX_COORD').outputs['Object']
    vo = N(m, 'TexVoronoi', Scale=95.0, Randomness=1.0)
    nt.links.new(co, vo.inputs['Vector'])
    pick = ramp(m, (vo, 'Color'), [(0.0, (0.05, 0.04, 0.035)), (0.08, (0.05, 0.04, 0.035)), (0.09, (1, 1, 1)),
                                   (0.9, (1, 1, 1)), (0.91, (0.45, 0.18, 0.08)), (0.95, (1.0, 1.0, 1.0))])
    pick.color_ramp.interpolation = 'CONSTANT'
    base = bs.inputs['Base Color'].links[0].from_socket
    mix = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=0.8, B=(pick, 'Color'))
    nt.links.new(base, sock(mix.inputs, 'A'))
    nt.links.new(sock(mix.outputs, 'Result'), bs.inputs['Base Color'])
    bs.inputs['Specular IOR Level'].default_value = 0.6  # wet glints
    return m
