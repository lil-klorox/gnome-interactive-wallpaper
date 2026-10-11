# Shared render setup so scenery and fish share one camera, light rig and look.
# Run scripts as: ~/opt/blender/blender -b --factory-startup -P blender/<script>.py
import fcntl
import json
import math
import os
import random
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets')
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


def scenery(samples=256):
    """reset + the shared rig + a broad soft light from the surface, for scenery props."""
    s = reset(samples)
    key, fill, rim = lights()
    fill.data.energy = 50  # less flat front light than the fish get: props need modelling
    key.data.energy = 4.0
    top = bpy.data.objects.new('top', bpy.data.lights.new('top', 'AREA'))
    top.data.energy, top.data.size, top.data.color = 60, 5, (0.85, 0.95, 1.0)
    top.location = (0, 0, 6)
    s.collection.objects.link(top)
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
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='OVERLAY', Factor=0.35, A=col, B=(wv, 'Color')), 'Result')
    if cracks:
        cv = N(m, 'TexVoronoi', Vector=co, Scale=scale * 1.3, _feature='DISTANCE_TO_EDGE')
        cw = N(m, 'MapRange', Value=(cv, 'Distance'), **{'From Min': 0.0, 'From Max': 0.012})
        cn = N(m, 'TexNoise', Vector=co, Scale=scale * 2, Detail=2.0)
        keep = N(m, 'MapRange', Value=(cn, 'Fac'), **{'From Min': 0.56, 'From Max': 0.6})  # only some edges crack
        crack = M(m, 'MAXIMUM', (cw, 'Result'), (keep, 'Result'))
        height = M(m, 'MULTIPLY_ADD', crack, cracks, height)
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=M(m, 'SUBTRACT', 1.0, crack), A=col,
                 B=(0.4, 0.4, 0.4, 1)), 'Result')
    if grime:
        ao = N(m, 'AmbientOcclusion', Distance=0.25, _samples=8)
        g = N(m, 'MapRange', Value=(ao, 'AO'), **{'To Min': 1 - grime})
        col = (N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=col, B=(g, 'Result')), 'Result')
    r = rough
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


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def fog(amount, far=0.0, color=WATER, vmap=None):
    """Fade every material toward the water colour: `amount` everywhere plus `far` more per
    10 world units behind y=0 (alpha untouched, so plates stay cut-out). vmap=(a, b) instead
    takes the colour from the backdrop gradient at height a*v + b, v = height on screen in world
    units, so hazy far things melt into exactly the water behind them."""
    s = bpy.context.scene
    t = math.radians(TILT)
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not out or not out.inputs['Surface'].links:
            continue
        surf = out.inputs['Surface'].links[0].from_socket
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
        mix = N(m, 'MixShader', Fac=f)
        nt.links.new(surf, mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])


def mesh(name, verts, faces, mat=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    if smooth:
        me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if mat:
        me.materials.append(mat)
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
    """Shadow-catcher floor so the sprite carries its own soft contact shadow. A big soft light
    from straight above is linked to the floor only, so it darkens around the base without
    changing how the prop itself is lit."""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    p = bpy.context.object
    p.is_shadow_catcher = True
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
    """Render assets/scene/<name>.png cropped to its visible pixels, and record its size plus
    named world points (anchors/pivots/emitters) in pixel coords in assets/scene/manifest.json.
    crop=False keeps the full frame (animation frames that must overlay each other exactly)."""
    s = bpy.context.scene
    path = render(f'scene/{name}.png')
    img = bpy.data.images.load(path)
    W, H = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]  # top row first
    bpy.data.images.remove(img)
    ys, xs = np.nonzero(px[:, :, 3] > cut / 255)
    x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
    if not crop:
        x0, y0, x1, y1 = 0, 0, W, H
    crop = px[y0:y1, x0:x1]
    out = bpy.data.images.new(name, x1 - x0, y1 - y0, alpha=True)
    out.pixels[:] = crop[::-1].ravel()
    out.filepath_raw, out.file_format = path, 'PNG'
    out.save()
    bpy.data.images.remove(out)
    ent = {'w': int(x1 - x0), 'h': int(y1 - y0)}
    for k, co in (points or {}).items():
        v = world_to_camera_view(s, s.camera, Vector(co))
        ent[k] = [round(float(v.x * W - x0), 1), round(float((1 - v.y) * H - y0), 1)]
    ent.update(extra or {})
    manifest(name, ent)
    print('sprite', name, ent)
    return ent


def manifest(name, ent):
    mp = os.path.join(ASSETS, 'scene', 'manifest.json')
    with open(mp, 'a+') as f:  # several scripts may render at once
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        txt = f.read()
        data = json.loads(txt) if txt.strip() else {}
        data[name] = ent
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, indent=1, sort_keys=True))


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
    return pbr(name, c1, c2, rough=0.85, scale=scale, bump=0.5, vor=0.2, moss=moss, grime=0.7, cracks=0.4, strata=0.3)
