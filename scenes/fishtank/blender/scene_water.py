# Water: backdrop gradient, underside of the surface, light shafts, caustics.
# These are light, not objects, so they are flat emission renders; the tiling ones wrap their
# noise around a 4D torus so the PNG repeats seamlessly (scene.js tiles them with content_repeat).
import math, os, sys
import bpy
sys.path.insert(0, os.path.dirname(__file__))
from common import *


def flat(name, w, h, build, samples=32):
    """Render a w x h emission card; build(mat, uv) returns (colour, alpha) sockets."""
    reset(samples)
    s = bpy.context.scene
    s.cycles.use_denoising = False
    s.render.dither_intensity = 1.0
    camera(w / h, w, h) if w >= h else camera(1, w, h)
    bpy.ops.mesh.primitive_plane_add(size=1, rotation=(math.radians(90), 0, 0))
    p = bpy.context.object
    p.scale = (w / h, 1, 1) if w >= h else (1, h / w, 1)
    m = new_mat(name)
    uv = N(m, 'TexCoord')
    col, a = build(m, (uv, 'UV'))
    em = N(m, 'Emission', Color=col, Strength=1.0)
    mix = N(m, 'MixShader', Fac=a, **{})
    m.node_tree.links.new(N(m, 'BsdfTransparent').outputs[0], mix.inputs[1])
    m.node_tree.links.new(em.outputs[0], mix.inputs[2])
    N(m, 'OutputMaterial', Surface=mix)
    p.data.materials.append(m)
    return render(f'scene/{name}.png')


def torus(m, uv, R, both=True, vscale=1.0):
    """Periodic 4D coords from UV: returns (vector, w) for 4D noise/voronoi."""
    sep = N(m, 'SeparateXYZ', Vector=uv)
    u = M(m, 'MULTIPLY', (sep, 'X'), 2 * math.pi)
    v = M(m, 'MULTIPLY', (sep, 'Y'), 2 * math.pi)
    cu, su = M(m, 'COSINE', u), M(m, 'SINE', u)
    if both:
        cv, sv = M(m, 'COSINE', v), M(m, 'SINE', v)
        vec = N(m, 'CombineXYZ', X=M(m, 'MULTIPLY', cu, R), Y=M(m, 'MULTIPLY', su, R), Z=M(m, 'MULTIPLY', cv, R))
        return vec, M(m, 'MULTIPLY', sv, R)
    vec = N(m, 'CombineXYZ', X=M(m, 'MULTIPLY', cu, R), Y=M(m, 'MULTIPLY', su, R), Z=M(m, 'MULTIPLY', (sep, 'Y'), vscale))
    return vec, M(m, 'MULTIPLY', (sep, 'Y'), 0.0)


def caustic(m, vec, w, scale, width):
    """Bright wobbly network lines: voronoi edge distance on noise-warped 4D coords."""
    warp = N(m, 'TexNoise', _noise_dimensions='4D', Vector=vec, W=w, Scale=scale * 0.35, Detail=3.0)
    off = N(m, 'VectorMath', _operation='SCALE', Vector=(warp, 'Color'), Scale=0.9)
    p = N(m, 'VectorMath', _operation='ADD', Vector=vec)
    m.node_tree.links.new(off.outputs[0], p.inputs[1])
    vo = N(m, 'TexVoronoi', _voronoi_dimensions='4D', _feature='DISTANCE_TO_EDGE', Vector=p, W=w, Scale=scale, Randomness=0.9)
    return N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Min': 0.0, 'From Max': width, 'To Min': 1.0, 'To Max': 0.0},
             _interpolation_type='SMOOTHSTEP')


# Backdrop: deep water, brighter toward the surface, slow soft mottling. Smooth, so it is rendered
# at half the reference size and stretched.
def backdrop(m, uv):
    sep = N(m, 'SeparateXYZ', Vector=uv)
    g = ramp(m, (sep, 'Y'), BACKDROP)
    n = N(m, 'TexNoise', Vector=uv, Scale=2.2, Detail=2.0)
    mot = N(m, 'MapRange', Value=(n, 'Fac'), **{'From Min': 0.3, 'From Max': 0.7, 'To Min': 0.85, 'To Max': 1.15})
    # a broad glow where the light comes in, upper middle
    d = N(m, 'VectorMath', _operation='DISTANCE', Vector=uv)
    d.inputs[1].default_value = (0.55, 1.15, 0)
    glow = N(m, 'MapRange', Value=(d, 'Value'), **{'From Min': 0.15, 'From Max': 0.9, 'To Min': 1.6, 'To Max': 1.0},
             _interpolation_type='SMOOTHSTEP')
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(g, 'Color'), B=(mot, 'Result'))
    c = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=1.0, A=(c, 'Result'), B=(glow, 'Result'))
    return (c, 'Result'), 1.0


# Underside of the surface: bright sheen at the top broken by long wobbling ripple streaks
# (squashed caustic lines + stretched noise), tiles horizontally.
def surface(m, uv):
    vec, w = torus(m, uv, 2.0, both=False, vscale=14.0)
    lines = caustic(m, vec, w, 1.4, 0.1)
    st = N(m, 'TexNoise', _noise_dimensions='4D', Vector=vec, W=1.3, Scale=0.9, Detail=4.0)
    streak = N(m, 'MapRange', Value=(st, 'Fac'), **{'From Min': 0.42, 'From Max': 0.62}, _interpolation_type='SMOOTHSTEP')
    sep = N(m, 'SeparateXYZ', Vector=uv)
    fade = N(m, 'MapRange', Value=(sep, 'Y'), _interpolation_type='SMOOTHSTEP')
    body = M(m, 'ADD', M(m, 'MULTIPLY', (lines, 'Result'), 0.45), M(m, 'MULTIPLY', (streak, 'Result'), 0.45))
    a = M(m, 'MULTIPLY', M(m, 'ADD', body, M(m, 'MULTIPLY', (fade, 'Result'), 0.3)), M(m, 'POWER', (fade, 'Result'), 1.8))
    a.use_clamp = True
    return (0.75, 0.97, 1.0, 1), a


# One light shaft: soft across, fading with depth, streaked along its length.
def ray(m, uv):
    sep = N(m, 'SeparateXYZ', Vector=uv)
    x = M(m, 'ABSOLUTE', M(m, 'SUBTRACT', (sep, 'X'), 0.5))
    across = N(m, 'MapRange', Value=x, **{'From Min': 0.0, 'From Max': 0.5, 'To Min': 1.0, 'To Max': 0.0},
               _interpolation_type='SMOOTHERSTEP')
    down = N(m, 'MapRange', Value=(sep, 'Y'), **{'From Min': 0.0, 'From Max': 1.0, 'To Min': 0.0, 'To Max': 1.0},
             _interpolation_type='SMOOTHSTEP')
    st = N(m, 'Mapping', Vector=uv, Scale=(9.0, 0.25, 1.0))
    streak = N(m, 'TexNoise', Vector=st, Scale=3.0, Detail=3.0)
    sk = N(m, 'MapRange', Value=(streak, 'Fac'), **{'From Min': 0.3, 'From Max': 0.7, 'To Min': 0.35, 'To Max': 1.0})
    a = M(m, 'MULTIPLY', M(m, 'MULTIPLY', M(m, 'POWER', (across, 'Result'), 1.5), (down, 'Result')), (sk, 'Result'))
    return (0.8, 1.0, 0.95, 1), M(m, 'MULTIPLY', a, 0.55)


# Caustic net for the sand: tiles horizontally, squashed 3x like light lying on a floor seen at a
# low angle, fading out toward the back (top).
def caustics(m, uv):
    vec, w = torus(m, uv, 2.0, both=False, vscale=20.0)
    a1 = caustic(m, vec, w, 1.15, 0.06)
    a2 = caustic(m, vec, M(m, 'ADD', w, 3.7), 2.0, 0.04)
    a = M(m, 'ADD', M(m, 'MULTIPLY', (a1, 'Result'), 0.8), M(m, 'MULTIPLY', (a2, 'Result'), 0.35))
    sep = N(m, 'SeparateXYZ', Vector=uv)
    fade = N(m, 'MapRange', Value=(sep, 'Y'), **{'From Min': 0.95, 'From Max': 0.45}, _interpolation_type='SMOOTHSTEP')
    a = M(m, 'MULTIPLY', a, (fade, 'Result'))
    a.use_clamp = True
    return (0.85, 1.0, 0.9, 1), a


# (name, texture w, h, shown at w, h ref px): all soft light, so rendered small and scaled up.
for n, w, h, k, fn in (('backdrop', 860, 360, 4, backdrop), ('surface', 1024, 80, 2, surface),
                       ('ray', 128, 512, 2, ray), ('caustics', 512, 150, 2, caustics)):
    flat(n, w, h, fn)
    manifest(n, {'w': w * k, 'h': h * k})
