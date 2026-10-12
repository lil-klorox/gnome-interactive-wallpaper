# Seamless dry raked-garden sand tile (512x512 at ref): fine grey-beige grit, a few dark and rust
# grains, faint undulation. Rendered at 2x plus a 96 px overlap, edges cross-faded with the opposite
# side so it tiles, then halved.
import os, sys
import bpy
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garden import *

T, O = 1024, 96          # tile and overlap in render px (2x)
W = 5.12                 # world units across one tile (100 px/unit at ref)


def sand():
    m = pbr('drysand', (0.45, 0.42, 0.36), (0.51, 0.48, 0.41), rough=0.95, scale=0.6, bump=0.15, grime=0.25)
    nt, bs = m.node_tree, principled(m)
    sock(nt.nodes['macro'].inputs, 'Factor').default_value = 0.0  # its patches are bigger than a tile: bands when tiled
    co = next(n for n in nt.nodes if n.type == 'TEX_COORD').outputs['Object']
    vo = N(m, 'TexVoronoi', Scale=42.0, Randomness=1.0)  # grit: each grain its own tint
    nt.links.new(co, vo.inputs['Vector'])
    pick = ramp(m, (vo, 'Color'), [(0.0, (0.25, 0.23, 0.21)), (0.05, (0.25, 0.23, 0.21)), (0.06, (0.9, 0.9, 0.88)),
                                   (0.5, (1.05, 1.03, 1.0)), (0.85, (1.0, 1.0, 1.0)), (0.86, (0.75, 0.52, 0.36)),
                                   (0.9, (1.25, 1.24, 1.2)), (0.97, (1.0, 1.0, 1.0))])
    pick.color_ramp.interpolation = 'CONSTANT'
    base = bs.inputs['Base Color'].links[0].from_socket
    mix = N(m, 'Mix', _data_type='RGBA', _blend_type='MULTIPLY', Factor=0.9, B=(pick, 'Color'))
    nt.links.new(base, sock(mix.inputs, 'A'))
    nt.links.new(sock(mix.outputs, 'Result'), bs.inputs['Base Color'])
    gh = N(m, 'MapRange', Value=(vo, 'Distance'), **{'From Max': 0.5, 'To Min': 1.0, 'To Max': 0.0})  # rounded grains
    b = N(m, 'Bump', Strength=0.5, Distance=0.004, Height=(gh, 'Result'), Normal=bs.inputs['Normal'].links[0].from_node)
    nt.links.new(b.outputs[0], bs.inputs['Normal'])
    pb = N(m, 'TexVoronoi', Scale=7.0, Randomness=1.0)  # sparse small pebbles among the grit
    nt.links.new(co, pb.inputs['Vector'])
    keep = M(m, 'GREATER_THAN', (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(pb, 'Color')), 'Value'), 0.8)
    peb = M(m, 'MULTIPLY', (N(m, 'MapRange', Value=(pb, 'Distance'), **{'From Min': 0.05, 'From Max': 0.13, 'To Min': 1.0, 'To Max': 0.0}), 'Result'), keep)
    pc = ramp(m, (N(m, 'TexWhiteNoise', _noise_dimensions='3D', Vector=(pb, 'Color')), 'Color'),
              [(0.0, (0.3, 0.29, 0.28)), (0.5, (0.55, 0.52, 0.47)), (1.0, (0.68, 0.64, 0.58))])
    mix2 = N(m, 'Mix', _data_type='RGBA', Factor=peb, B=(pc, 'Color'))
    nt.links.new(sock(mix.outputs, 'Result'), sock(mix2.inputs, 'A'))
    nt.links.new(sock(mix2.outputs, 'Result'), bs.inputs['Base Color'])
    b2 = N(m, 'Bump', Strength=0.8, Distance=0.02, Height=M(m, 'POWER', peb, 0.5), Normal=b)
    nt.links.new(b2.outputs[0], bs.inputs['Normal'])
    bs.inputs['Specular IOR Level'].default_value = 0.2  # dry: no wet glints
    return m


def tile(px):
    """(T+O)^2 render -> seamless T^2: the first O rows/cols fade in from the strip past the far edge."""
    t = np.linspace(0, 1, O, dtype=np.float32)
    a = px.copy()
    a[:, :O] = a[:, T:T + O] * (1 - t)[None, :, None] + a[:, :O] * t[None, :, None]
    a = a[:, :T]
    a[:O] = a[T:T + O] * (1 - t)[:, None, None] + a[:O] * t[:, None, None]
    return a[:T]


if __name__ == '__main__':
    s = rig()
    bpy.data.objects.remove(bpy.data.objects['fill'])  # an area light shades a flat tile unevenly: seams
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.1
    bpy.ops.mesh.primitive_plane_add(size=W * 1.6)
    bpy.context.object.data.materials.append(sand())
    cam = camera(W * (T + O) / T, T + O, T + O, tilt=90)
    cam.location.x += W * O / T / 2
    cam.location.y -= W * O / T / 2  # image top = +y; the overlap strip lies past the right and bottom edges
    s.view_settings.exposure = 0.0
    out = render('sand_raw.png')
    px = load_png(out)  # top row first
    os.remove(out)
    a = tile(px)
    a = a.reshape(T // 2, 2, T // 2, 2, 4).mean((1, 3))
    a[..., 3] = 1
    save_png(a, os.path.join(ASSETS, 'sand.png'))
    manifest('sand', {'w': T // 2, 'h': T // 2})
