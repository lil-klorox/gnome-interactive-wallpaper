# Fish sprite sheets. Each species is modeled from numpy-built meshes (lofted body, fanned fins
# with real rays, eyes, lips, barbels, spikes) with numpy-painted textures, swum with a sine
# body wave, and rendered with Cycles as swim-cycle frames x yaw angles (profile -> front; the
# runtime mirrors the other half). Writes assets/<name>.png + its manifest entry (+ puffer -puff).
# Run: blender -b --factory-startup -P blender/fish.py -- [species ...] [--preview DIR] [--eyes]
# (--eyes: recompute eye data in the manifest for already-rendered sheets, no render)
import json
import math
import os
import sys
import tempfile

import bpy
import mathutils
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TAU = 2 * math.pi
FRAMES = 12                  # swim cycle frames (one tail beat cycle)
YAWS = [0, 15, 30, 45, 60, 75, 90]  # degrees turned toward the viewer (15 deg steps so the runtime can crossfade rows)
PUFFS = 4                    # puffer inflation steps
SAMPLES = int(os.environ.get('SAMPLES', 128))  # denoised (common.reset)
SIZE = 1.3                   # all fish lengths (px at 1440 p) scaled by this; memory grows with its square


# ---------- small numpy helpers ----------

def hexc(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(col, c, m):
    """Paint colour c over col where mask m (0..1)."""
    m = np.asarray(m)[..., None]
    col[:] = col * (1 - m) + (hexc(c) if isinstance(c, str) else c) * m


def curve(pts):
    """Smooth curve through [(u, v), ...], Hermite with finite-difference slopes."""
    xs, ys = np.array(pts, float).T
    d = np.gradient(ys, xs)

    def f(u):
        u = np.clip(np.asarray(u, float), xs[0], xs[-1])
        i = np.clip(np.searchsorted(xs, u) - 1, 0, len(xs) - 2)
        h = xs[i + 1] - xs[i]
        t = (u - xs[i]) / h
        return ((2 * t**3 - 3 * t**2 + 1) * ys[i] + (t**3 - 2 * t**2 + t) * h * d[i]
                + (-2 * t**3 + 3 * t**2) * ys[i + 1] + (t**3 - t**2) * h * d[i + 1])
    return f


_LATTICE = np.random.default_rng(7).random((256, 256))


def noise(x, y, scale=1.0, octaves=4, seed=0):
    """Smooth value-noise fbm in about 0..1."""
    out, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        fx, fy = x * scale * 2**o + seed * 17.3 + o * 5.1, y * scale * 2**o + seed * 9.7
        ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = smooth(0, 1, fx - ix), smooth(0, 1, fy - iy)
        g = lambda a, b: _LATTICE[(ix + a) & 255, (iy + b) & 255]  # noqa: E731
        out = out + amp * ((g(0, 0) * (1 - tx) + g(1, 0) * tx) * (1 - ty) + (g(0, 1) * (1 - tx) + g(1, 1) * tx) * ty)
        tot += amp
        amp *= 0.5
    return out / tot


def scales(X, Z, size, head=1.0, mid=0.0, seed=0):
    """Overlapping fish scales seen from the side: returns height 0..1 rising toward each free edge.
    Rows wander (noise warp), scales shrink ~30 % toward the head (gill line x = head) and belly,
    and fade out on the head itself."""
    k = 1 - 0.3 * smooth(head - 0.2, head, X) - 0.3 * smooth(mid - 0.02, mid - 0.12, Z)
    X0 = X
    X = X / k + (noise(X * 7, Z * 7, 1, 2, seed + 40) - 0.5) * size * 0.8
    Z = Z / k + (noise(X0 * 7, Z * 7, 1, 2, seed + 41) - 0.5) * size * 0.8
    return _scales(X, Z, size) * smooth(head + 0.01, head - 0.02, X0)


def _scales(X, Z, size):
    row = size * 0.62
    best = np.full(X.shape, -1e9)
    h = np.zeros(X.shape)
    j0 = np.floor(Z / row).astype(int)
    for dj in (-1, 0, 1):
        j = j0 + dj
        cz = j * row
        off = (j % 2) * size * 0.5
        for di in (0, 1):
            cx = (np.floor((X - off) / size) + di) * size + off
            d = np.hypot(X - cx, Z - cz) / (size * 0.72)
            inside = d < 1
            # the most forward scale on top: anterior scales overlap posterior ones
            take = inside & (cx > best)
            best = np.where(take, cx, best)
            h = np.where(take, d**2, h)
    return h


def skin(col, X, Y, Z, mid, half, head):
    """Shared living-skin pass over every body paint: big soft value patches, a fine pigment
    stipple, darker back / paler belly, a faint lateral line, and each flank seeded on its own
    so left and right are not clones."""
    sd = np.where(Y >= 0, 0, 31)
    e = np.clip((Z - mid) / np.maximum(half, 1e-3), -1, 1)
    col *= (1 + 0.16 * (noise(X * 3 + sd, Z * 3, 1, 2, 50) - 0.5))[..., None]
    col *= (1 - 0.07 * e)[..., None]
    dots = smooth(0.78, 0.84, noise(X * 140 + sd, (Z + np.abs(Y) * 0.7) * 140, 1, 1, 51))  # |Y|: no streaks on the belly
    mix(col, col * 0.7, dots * 0.35)
    lz = mid + half * (0.3 + 0.06 * np.sin(X * 9))
    line = smooth(0.01, 0.0, np.abs(Z - lz)) * smooth(head, head - 0.08, X) * (0.6 + 0.4 * noise(X * 40, Z, 1, 1, 52))
    mix(col, col * 0.82, line * 0.35)


# ---------- mesh building ----------

def surface(fn, nu, nv, wrap_u=False):
    """Quad surface from fn(U, V) -> (x, y, z) with U in [0,1] (rows), V in [0,1) wrapping.
    Unless wrap_u, the first and last rows collapse into a single cap vertex each.
    Returns (verts, faces, uvs-per-corner, per-vertex U)."""
    U = np.linspace(0, 1, nu + 1)
    V = np.arange(nv) / nv
    P = np.stack(fn(U[:, None] + 0 * V, 0 * U[:, None] + V), -1)  # (nu+1, nv, 3)
    verts, vu, idx = [], [], {}
    rows = range(nu) if wrap_u else range(1, nu)
    for i in rows:
        for j in range(nv):
            idx[i, j] = len(verts)
            verts.append(P[i, j])
            vu.append(U[i])
    faces, uvs = [], []
    if not wrap_u:
        for i, r in ((0, 1), (nu, nu - 1)):
            c = len(verts)
            verts.append(P[i].mean(0))
            vu.append(U[i])
            for j in range(nv):
                a, b = idx[r, j], idx[r, (j + 1) % nv]
                faces.append((c, b, a) if i == 0 else (c, a, b))
                uv = [(U[i], (j + 0.5) / nv), (U[r], (j + 1) / nv), (U[r], j / nv)]
                uvs.append(uv if i == 0 else [uv[0], uv[2], uv[1]])
    lo, hi = (0, nu) if wrap_u else (1, nu - 1)
    for i in range(lo, hi):
        i2 = (i + 1) % nu if wrap_u else i + 1
        for j in range(nv):
            j2 = (j + 1) % nv
            faces.append((idx[i, j], idx[i, j2], idx[i2, j2], idx[i2, j]))
            uvs.append([(U[i], j / nv), (U[i], (j + 1) / nv), (U[i + 1], (j + 1) / nv), (U[i + 1], j / nv)])
    return np.array(verts), faces, uvs, np.array(vu)


def grid(P, U, V):
    """Open quad grid from points P (n, m, 3) with uv params U (n,), V (m,)."""
    n, m = P.shape[:2]
    faces, uvs = [], []
    for i in range(n - 1):
        for j in range(m - 1):
            faces.append((i * m + j, (i + 1) * m + j, (i + 1) * m + j + 1, i * m + j + 1))
            uvs.append([(U[i], V[j]), (U[i + 1], V[j]), (U[i + 1], V[j + 1]), (U[i], V[j + 1])])
    return P.reshape(-1, 3), faces, uvs


def image(name, arr, data=False):
    """bpy image from an (h, w, 3|4) array whose row 0 is v=0."""
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1))], 2)
    im = bpy.data.images.new(name, w, h, alpha=True)
    if data:
        im.colorspace_settings.name = 'Non-Color'
    im.pixels.foreach_set(np.clip(arr, 0, 1).astype(np.float32).ravel())
    im.pack()
    return im


def material(name, col, dat, alpha=False, sss=0.12, coat=0.08, film=0.0, sheen=0.0, bump=0.4, metal=0.0):
    """Principled material: col = RGBA image (alpha used if alpha), dat = R height, G roughness, B thin-film mask."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N['Principled BSDF']
    tc = N.new('ShaderNodeTexImage')
    tc.image = col
    td = N.new('ShaderNodeTexImage')
    td.image = dat
    tc.extension = td.extension = 'EXTEND'  # bug fix: REPEAT bled the opaque fin root into the free edge (dark rim line)
    sep = N.new('ShaderNodeSeparateColor')
    L.new(td.outputs['Color'], sep.inputs['Color'])
    L.new(tc.outputs['Color'], bsdf.inputs['Base Color'])
    if alpha:
        L.new(tc.outputs['Alpha'], bsdf.inputs['Alpha'])
    L.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
    bp = N.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = bump
    bp.inputs['Distance'].default_value = 0.004
    L.new(sep.outputs['Red'], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], bsdf.inputs['Normal'])
    if film:
        mul = N.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = film
        L.new(sep.outputs['Blue'], mul.inputs[0])
        L.new(mul.outputs[0], bsdf.inputs['Thin Film Thickness'])
        bsdf.inputs['Thin Film IOR'].default_value = 1.6
    bsdf.inputs['Subsurface Weight'].default_value = sss
    bsdf.inputs['Subsurface Radius'].default_value = (0.6, 0.5, 0.4) if alpha else (1.0, 0.45, 0.25)  # fins: no red glow
    bsdf.inputs['Subsurface Scale'].default_value = 0.03
    bsdf.inputs['Coat Weight'].default_value = coat
    bsdf.inputs['Coat Roughness'].default_value = 0.3
    bsdf.inputs['Sheen Weight'].default_value = sheen
    bsdf.inputs['Metallic'].default_value = metal
    return m


def flat_material(name, color, rough=0.3, coat=0.0, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*(hexc(color) ** 2.2), 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = coat
    b.inputs['Coat Roughness'].default_value = 0.05
    b.inputs['Subsurface Weight'].default_value = sss
    b.inputs['Subsurface Scale'].default_value = 0.02
    return m


# ---------- the fish ----------

class Fish:
    """Holds the parts of one fish in fish-local coords (+X nose, +Z up, Y lateral; origin = body centre)."""

    def __init__(self, name, px, amp=0.06, iris='#6a4010', inflate=None):
        self.name, self.px, self.amp, self.iris, self.inflate = name, px, amp, iris, inflate
        self.parts, self.eyes = [], []
        self.root = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(self.root)

    def add(self, name, verts, faces, uvs, mat, sub=2, solid=0.0, smooth=True, **motion):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], faces)
        if uvs:
            uv = me.uv_layers.new()
            uv.data.foreach_set('uv', np.array([c for f in uvs for c in f], np.float32).ravel())
        me.polygons.foreach_set('use_smooth', [smooth] * len(me.polygons))
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = self.root
        if solid:
            s = ob.modifiers.new('solid', 'SOLIDIFY')
            s.thickness, s.offset = solid, 0
        if sub:
            s = ob.modifiers.new('sub', 'SUBSURF')
            s.levels = s.render_levels = sub
        part = dict(ob=ob, rest=np.array(verts, float), **motion)
        self.parts.append(part)
        return part

    # Body: a loft from tail root (u=0) to nose (u=1). top/bot = z of the outline, wid = half width,
    # all curves of u; q < 1 squares off the section; paint(X,Y,Z,U) -> (col, height, rough, film).
    def body(self, x0, x1, top, bot, wid, paint, nose=0.1, q=1.0, tex=(1024, 512), head=None, **mat):
        def sec(U, V):
            r = np.sqrt(np.clip(1 - (np.clip(U - (1 - nose), 0, None) / nose) ** 2, 0, 1))
            tl = np.sqrt(np.clip(1 - (np.clip(0.03 - U, 0, None) / 0.03) ** 2, 0.35, 1))
            t, b, w = top(U), bot(U), wid(U) * r * tl
            zc, hh = (t + b) / 2, (t - b) / 2 * r * tl
            th = V * TAU  # 0 = belly, 0.5 = back
            s, c = np.sin(th), np.cos(th)
            sp = lambda a: np.sign(a) * np.abs(a) ** q  # noqa: E731
            return x0 + U * (x1 - x0), w * sp(s), zc - hh * sp(c)
        self.sec = sec
        self.x0, self.x1, self._top, self._bot = x0, x1, top, bot
        v, f, uv, _ = surface(sec, 64, 48)
        h, w = tex[1], tex[0]
        U, V = np.meshgrid((np.arange(w) + 0.5) / w, (np.arange(h) + 0.5) / h)
        X, Y, Z = sec(U, V)
        col, height, rough, film = paint(X, Y, Z, U)
        self.head = x1 - 0.24 * (x1 - x0) if head is None else head
        mid, half = (top(U) + bot(U)) / 2, (top(U) - bot(U)) / 2
        skin(col, X, Y, Z, mid, half, self.head)
        rough = np.clip(rough + 0.3 * (noise(X * 2.5, Z * 2.5 + Y, 1, 2, 53) - 0.5), 0.05, 1)  # sheen breaks up
        dat = np.stack([height, rough, film], -1)
        m = material(self.name + '-body', image(self.name + '-bc', col), image(self.name + '-bd', dat, True), **mat)
        return self.add('body', v, f, uv, m)

    def tz(self, x, inset=0.0):
        """Back outline height at x (minus inset, so fins root inside the skin)."""
        return float(self._top((x - self.x0) / (self.x1 - self.x0))) - inset

    def bz(self, x, inset=0.0):
        return float(self._bot((x - self.x0) / (self.x1 - self.x0))) + inset

    def zc(self, x):
        return (self.tz(x) + self.bz(x)) / 2

    def at(self, u, side):
        """Point on the body surface at u, angle side (0 belly, .25 flank, .5 back) and its outward normal."""
        p = np.array(self.sec(np.array(u), np.array(side)), float)
        e = 1e-3
        du = np.array(self.sec(np.array(u + e), np.array(side)), float) - p
        dv = np.array(self.sec(np.array(u), np.array(side + e)), float) - p
        n = np.cross(dv, du)  # outward
        return p, n / (np.linalg.norm(n) or 1)

    # Fin: rays fanned from a root line p0->p1 (2D x,z in the fin plane). ang(t)/ln(t) give each
    # ray's angle (degrees) and length; curl bends rays toward the tip. M/O place the fin in 3D
    # (columns: fin x, fin normal, fin z). paint(T, V) -> RGBA, height, rough.
    def fin(self, name, p0, p1, ang, ln, paint, rays=24, rows=10, curl=0.0, pleat=0.006, M=None, O=(0, 0, 0),
            flap=0.0, ripple=0.0, hinge=None, solid=0.004, tex=256, stack=0.0, path=None, **mat):
        T = np.linspace(0, 1, rays)
        V = np.linspace(0, 1, rows + 1)
        p0, p1 = np.array(p0, float), np.array(p1, float)
        root = np.stack(path(T), -1) if path else p0 + (p1 - p0) * T[:, None]  # path(T) -> (x, z): curved root
        a = np.radians(ang(T) + 0 * T)[:, None] + np.radians(curl) * V[None, :]
        step = ((ln(T) + 0 * T) / rows)[:, None]
        dx = np.concatenate([np.zeros((rays, 1)), np.cumsum(np.cos(a[:, :-1]) * step, 1)], 1)
        dz = np.concatenate([np.zeros((rays, 1)), np.cumsum(np.sin(a[:, :-1]) * step, 1)], 1)
        if stack:  # overlapping fins keep a fixed depth order; pleats must not cross it
            pleat = min(pleat, abs(stack) / 2)
        fold = stack + pleat * np.where(np.arange(rays) % 2, 1, -1)[:, None] * np.sqrt(V)[None, :]
        P = np.stack([root[:, 0:1] + dx, fold + 0 * dx, root[:, 1:2] + dz], -1)
        M = np.eye(3) if M is None else np.array(M, float)
        P0 = np.array([p0[0], 0, p0[1]])
        P = (P - P0) @ M.T + P0 + np.array(O, float)
        v, f, uv = grid(P, T, V)
        tv, tt = np.meshgrid((np.arange(tex) + 0.5) / tex, (np.arange(tex) + 0.5) / tex)
        tt, tv = tt.T, tv.T  # arrays indexed [v, t]: image rows are v, columns t
        fi, fj = tt * (rays - 1), tv * rows  # bilinear lookup of the fin surface position per texel
        i0, j0 = np.minimum(fi.astype(int), rays - 2), np.minimum(fj.astype(int), rows - 1)
        a, b = (fi - i0)[..., None], (fj - j0)[..., None]
        XYZ = (P[i0, j0] * (1 - a) * (1 - b) + P[i0 + 1, j0] * a * (1 - b) + P[i0, j0 + 1] * (1 - a) * b + P[i0 + 1, j0 + 1] * a * b)
        rgba, height, rough, *film = paint(tt, tv, XYZ[..., 0], XYZ[..., 2])
        col = rgba
        dat = np.stack([height, rough, film[0] if film else np.zeros_like(rough)], -1)
        m = material(f'{self.name}-{name}', image(f'{self.name}-{name}c', col), image(f'{self.name}-{name}d', dat, True),
                     alpha=True, **{'sss': 0.35, 'coat': 0.05, 'bump': 0.25, **mat})
        vv = np.repeat(V[None, :], rays, 0).ravel()
        if hinge is None:
            hinge = (P[0, 0], P[-1, 0])
        return self.add(name, v, f, uv, m, sub=1, solid=solid, v=vv, flap=flap, ripple=ripple,
                        hinge=np.array(hinge, float), t=np.repeat(T, rows + 1))

    def eye(self, u, side, r, toe=15, rim='#203040', out=0.3, gloss=0.6):
        """Pair of eyes set into the head (out = fraction of the ball above the skin), turned forward
        by toe degrees. Ball = dark iris tone (no white), rim = a thin lid in the body colour there.
        The iris and pupil are not modeled: the runtime draws them."""
        r *= 0.7
        p, n = self.at(u, side)
        t = math.radians(toe)
        dark = '#%02x%02x%02x' % tuple(int(c * 127) for c in hexc(self.iris))
        sink = r * (1 - 2 * out)  # ball centre below the skin
        lid = math.sqrt(max(r * r - sink * sink, 0)) * 1.02
        for sign in (-1, 1):
            pp = np.array([p[0], sign * abs(p[1]), p[2]])
            nn = np.array([n[0], sign * abs(n[1]), n[2]]) * math.cos(t) + np.array([math.sin(t), 0, 0])
            nn /= np.linalg.norm(nn)
            ctr = pp - nn * sink

            def ball(U, V, ctr=ctr):
                th, ph = U * math.pi, V * TAU
                return ctr[0] + r * np.cos(th), ctr[1] + r * np.sin(th) * np.cos(ph), ctr[2] + r * np.sin(th) * np.sin(ph)
            v, f, uv, _ = surface(ball, 16, 24)
            self.add(f'eye{sign}', v, f, uv, flat_material(self.name + '-ball', dark, rough=0.12 + 0.3 * (0.6 - gloss), coat=gloss, sss=0.1), sub=1)
            k = np.cross(nn, [0, 0, 1])
            k = k / (np.linalg.norm(k) or 1)
            j = np.cross(nn, k)

            def ring(U, V, ctr=ctr, nn=nn, k=k, j=j):
                a, b = U * TAU, V * TAU
                R = lid + r * 0.08 * np.cos(b)
                d = r * 0.08 * np.sin(b) + sink
                return tuple(ctr[i] + R * (np.cos(a) * k[i] + np.sin(a) * j[i]) + d * nn[i] for i in range(3))
            v, f, uv, _ = surface(ring, 32, 10, wrap_u=True)
            self.add(f'rim{sign}', v, f, None, flat_material(self.name + '-rim', rim, rough=0.45, sss=0.2), sub=1)
            self.eyes.append((ctr + nn * r, nn, r, f'eye{sign}'))

    def lips(self, c, r, color, open_=0.5, thick=0.2, shade=0.8, down=False):
        """Mouth ring at c facing +X (down: a sucker disc facing -Z) with a dark throat; gulps with
        the swim cycle. color = the body tone there, darkened by shade."""
        c = np.array(c, float)
        color = '#%02x%02x%02x' % tuple(int(min(1, v * shade) * 255) for v in hexc(color))
        gape = None if down else open_

        def turn(x, y, z):  # facing -Z instead of +X
            return (c[0] - (z - c[2]), y, c[2] - (x - c[0])) if down else (x, y, z)

        def ring(U, V):
            a, b = U * TAU, V * TAU
            R = r + r * thick * np.cos(b)
            return turn(c[0] + r * thick * np.sin(b) * 1.2, c[1] + R * np.cos(a), c[2] + R * np.sin(a) * 0.8)
        v, f, uv, _ = surface(ring, 32, 12, wrap_u=True)
        self.add('lips', v, f, None, flat_material(self.name + '-lips', color, rough=0.45, coat=0.1, sss=0.4), sub=1,
                 mouth=c, gape=gape)

        def throat(U, V):
            th, ph = U * math.pi, V * TAU
            return turn(c[0] - r * 0.2 + r * 0.5 * np.cos(th) * 0.5, c[1] + r * 0.95 * np.sin(th) * np.cos(ph), c[2] + r * 0.8 * np.sin(th) * np.sin(ph))
        v, f, uv, _ = surface(throat, 8, 16)
        self.add('throat', v, f, None, flat_material(self.name + '-throat', '#2a0c10', rough=0.6), sub=1, mouth=c, gape=gape)
    def tube(self, name, path, r0, r1, color, wiggle=0.0):
        """Tapered tube along a polyline (barbels, filaments)."""
        path = np.array(path, float)
        seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()

        def fn(U, V):
            pts = np.stack([np.interp(U, s, path[:, i]) for i in range(3)], -1)
            tng = np.stack([np.interp(np.clip(U + 0.02, 0, 1), s, path[:, i]) - np.interp(np.clip(U - 0.02, 0, 1), s, path[:, i]) for i in range(3)], -1)
            tng /= np.linalg.norm(tng, axis=-1, keepdims=True) + 1e-9
            a = np.cross(tng, [0, 1, 0.01])
            a /= np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9
            b = np.cross(tng, a)
            rad = (r0 + (r1 - r0) * U)
            out = pts + rad[..., None] * (np.cos(V * TAU)[..., None] * a + np.sin(V * TAU)[..., None] * b)
            return out[..., 0], out[..., 1], out[..., 2]
        v, f, uv, vu = surface(fn, 16, 8)
        return self.add(name, v, f, None, flat_material(f'{self.name}-{name}', color, rough=0.5, sss=0.3), sub=1,
                        wig=vu, wiggle=wiggle)

    def spikes(self, pts, normals, length, r, color, back=0.6):
        """Prickles: small cones on the skin, raked back toward the tail. Puffing stretches them."""
        verts, faces, base = [], [], []
        for p, n in zip(pts, normals):
            d = n + np.array([-back, 0, 0])
            d /= np.linalg.norm(d)
            k = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0, 0])
            k /= np.linalg.norm(k)
            j = np.cross(d, k)

            def cone(U, V, p=p, d=d, k=k, j=j):
                rad = r * (1 - U) ** 1.3
                o = p - d * r
                pts_ = o + (U[..., None] * (length + r)) * d + rad[..., None] * (np.cos(V * TAU)[..., None] * k + np.sin(V * TAU)[..., None] * j)
                return pts_[..., 0], pts_[..., 1], pts_[..., 2]
            v, f, _, _ = surface(cone, 3, 6)
            faces += [tuple(i + len(verts) for i in fc) for fc in f]
            verts += list(v)
            base += [p] * len(v)
        return self.add('spikes', np.array(verts), faces, None, flat_material(self.name + '-spike', color, rough=0.4, sss=0.3),
                        sub=0, spk=np.array(base))

    # ---------- posing ----------

    def deform(self, co, ph, puff, part=None):
        co = co.copy()
        if part is not None:
            if part.get('gape') is not None:  # gulping mouth
                o = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(TAU * 2 * ph))
                k = 0.55 + 0.75 * o * part['gape'] / 0.5
                c = part['mouth']
                co[:, 1] = c[1] + (co[:, 1] - c[1]) * (0.8 + 0.25 * k)
                co[:, 2] = c[2] + (co[:, 2] - c[2]) * k
            if part.get('flap'):  # pectoral flutter: rotate about the root line, tips lag
                p0, p1 = part['hinge']
                ax = (p1 - p0) / np.linalg.norm(p1 - p0)
                ang = part['flap'] * np.sin(TAU * 2 * ph - part['v'] * 1.6) * (0.35 + 0.65 * part['v'])
                d = co - p0
                cs, sn = np.cos(ang)[:, None], np.sin(ang)[:, None]
                co = p0 + d * cs + np.cross(ax, d) * sn + ax * (d @ ax)[:, None] * (1 - cs)
            if part.get('ripple'):  # flowing edge ripple on long fins
                # bug fix: phase/amplitude came from each fin's own ray index, so overlapping fins (betta
                # anal over caudal) rippled opposite ways and passed through each other. Both now come
                # from the world position: overlapping fins move in lockstep, `stack` keeps them apart.
                x, z = co[:, 0], co[:, 2]
                U = np.clip((x - self.x0) / (self.x1 - self.x0), 0, 1)
                out = np.maximum(np.maximum(z - self._top(U), self._bot(U) - z), np.maximum(self.x0 - x, 0))
                co[:, 1] += part['ripple'] * np.clip(out / 0.25, 0, 1)**1.5 * np.sin(TAU * ph * 2 - x * 22 - z * 6)
            if part.get('wiggle'):
                w = part['wig']
                co[:, 1] += part['wiggle'] * w**1.5 * np.sin(TAU * 2 * ph + w * 3)
                co[:, 2] += part['wiggle'] * 0.6 * w**1.5 * np.cos(TAU * 2 * ph + w * 3)
        if puff and self.inflate:
            co = self.inflate(co, puff, part)
        # body wave: travelling sine, swing grows toward the tail, head counter-swings a little
        s = np.clip((self.xn - co[:, 0]) / (self.xn - self.xt), 0, 1.3)
        co[:, 1] += self.amp * (s**2 * np.sin(TAU * ph - 2.6 * s) - 0.1 * np.sin(TAU * ph))
        co[:, 2] += self.amp * 0.12 * s**3 * np.sin(TAU * ph - 2.6 * s + 1.2)  # a little up/down flick reads in profile
        return co

    def pose(self, ph, puff=0.0):
        for p in self.parts:
            co = self.deform(p['rest'], ph, puff, p)
            me = p['ob'].data
            me.vertices.foreach_set('co', co.astype(np.float32).ravel())
            me.update()

    def finish(self):
        allv = np.concatenate([p['rest'] for p in self.parts])
        self.xn, self.xt = allv[:, 0].max(), allv[:, 0].min()


# ---------- rendering ----------

def euler(yaw, tilt=0.0):
    """Root rotation for a yaw (degrees toward the viewer) after a tilt about the length axis."""
    return (math.radians(tilt), 0, math.radians(-yaw))


def rotm(yaw, tilt=0.0):
    return np.array(mathutils.Euler(euler(yaw, tilt)).to_matrix())


def world_points(fish, ph, puff, yaw, tilt=0.0):
    pts = np.concatenate([fish.deform(p['rest'], ph, puff, p) for p in fish.parts])
    return pts @ rotm(yaw, tilt).T


def frame_box(fish, ppm, puffs, yaws, tilt=0.0):
    lo, hi = np.full(2, 1e9), np.full(2, -1e9)
    for yaw in yaws:
        for ph in (0, 0.25, 0.5, 0.75):
            for pf in puffs:
                w = world_points(fish, ph, pf, yaw, tilt)[:, [0, 2]]
                lo, hi = np.minimum(lo, w.min(0)), np.maximum(hi, w.max(0))
    pad = 2 / ppm
    lo, hi = lo - pad, hi + pad
    W, H = int(math.ceil((hi[0] - lo[0]) * ppm)), int(math.ceil((hi[1] - lo[1]) * ppm))
    return (lo + hi) / 2, W, H


def render_sheet(fish, ppm, puffs, phases, tmp, out, yaws=YAWS, tilt=0.0, dry=False):
    """dry: pose and measure only (eye data, frame size), no rendering."""
    s = bpy.context.scene
    ctr, W, H = frame_box(fish, ppm, puffs, yaws, tilt)
    cam = common.camera(W / ppm, W, H, z=ctr[1])
    cam.location.x = ctr[0]
    cols = len(phases) * len(puffs)
    sheet = np.zeros((len(yaws) * H, cols * W, 4), np.float32)
    eyes = []
    path = os.path.join(tmp, 'f.png')
    for yi, yaw in enumerate(yaws):
        fish.root.rotation_euler = euler(yaw, tilt)
        row = []
        for ci, (pf, ph) in enumerate((pf, ph) for pf in puffs for ph in phases):
            fish.pose(ph, pf)
            bpy.context.view_layer.update()
            if not dry:
                s.render.filepath = path
                bpy.ops.render.render(write_still=True)
                sheet[yi * H:(yi + 1) * H, ci * W:(ci + 1) * W] = common.load_png(path)
            row.append(eye_info(fish, ph, pf, yaw, ctr, W, H, ppm))
        eyes.append(row)
    anchor = [round(-ctr[0] * ppm + W / 2, 2), round(H / 2 + ctr[1] * ppm, 2)]
    if not dry:
        common.save_png(sheet, out)
    # rows = yaws, cols = frames; eyes flattened row-major so eyes[i] belongs to frame i
    return dict(w=W, h=H, cols=cols, n=cols * len(yaws), anchor=anchor, eyes=[e for r in eyes for e in r])


def eye_info(fish, ph, puff, yaw, ctr, W, H, ppm):
    """Where the pupil overlay goes in this frame: [[x, y, r, squash], ...] for each visible eye."""
    out = []
    dg = bpy.context.evaluated_depsgraph_get()
    R = rotm(yaw)
    rot = lambda p: R @ p  # noqa: E731
    for front, n, r, obname in fish.eyes:
        pts = fish.deform(np.array([front, front - n * r]), ph, puff)
        P, Q = rot(pts[0]), rot(pts[1])
        nn = (P - Q) / np.linalg.norm(P - Q)
        facing = -nn[1]
        if facing < 0.1:
            continue
        # visible if a camera ray meets the ball (or its lid) first at any of a few points on the
        # cap facing the camera. bug fix: one ray through the ball's centre hit the head skin
        # first at 75/90 deg (the ball is set into the head), so those rows lost their eyes.
        cam = np.array([0.0, -1.0, 0.0])
        caps = [P] + [Q + r * 0.95 * (v / np.linalg.norm(v)) for v in (nn + cam, nn * 0.4 + cam, nn + 0.4 * cam)]
        names = (obname, obname.replace('eye', 'rim'))

        def seen(C):
            hit, _, _, _, ob, _ = bpy.context.scene.ray_cast(dg, (C[0], -50, C[2]), (0, 1, 0))
            return hit and ob.name in names
        if not any(seen(C) for C in caps):
            continue
        x = (P[0] - ctr[0]) * ppm + W / 2
        y = H / 2 - (P[2] - ctr[1]) * ppm
        out.append([round(x, 2), round(y, 2), round(r * ppm, 2), round(float(facing), 3)])
    return out


def build(name):
    common.reset(SAMPLES)
    key, fill, _ = common.lights()
    fill.data.energy = 70  # a bit less flat than the shared fill so bodies read round
    fill.data.color = (0.85, 0.92, 1.0)  # the flanks face the fill: a cyan fill turned every white band sky blue
    key.data.energy = 3.8
    s = bpy.context.scene
    s.cycles.pixel_filter_width = 1.2
    s.view_settings.exposure = 0.15  # fish sit in the tank's light, not a stop above it
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.3  # less blue bounce: whites stay white
    fish = SPECIES[name]()
    fish.finish()
    return fish


def run(name, preview=None, eyes=False):
    fish = build(name)
    rest = np.concatenate([p['rest'] for p in fish.parts])
    ppm = fish.px * SIZE / (rest[:, 0].max() - rest[:, 0].min())
    with tempfile.TemporaryDirectory() as tmp:
        if eyes:  # recompute only the eye data of existing sheets (same pose and framing, no render)
            with open(os.path.join(common.ASSETS, 'manifest.json')) as fh:
                old = json.load(fh)['images']
            sheets = [(name, [0.0], [i / FRAMES for i in range(FRAMES)])]
            if fish.inflate:
                sheets.append((name + '-puff', [i / (PUFFS - 1) for i in range(PUFFS)], [0.0]))
            for n, puffs, phases in sheets:
                e = render_sheet(fish, ppm, puffs, phases, tmp, None, dry=True)
                if (e['w'], e['h']) != (old[n]['w'], old[n]['h']):
                    sys.exit(f'fish.py: {n} framing changed, re-render it')
                common.manifest(n, {**old[n], 'eyes': e['eyes']})
                print(f'fish: {n} eyes updated')
            return
        if preview:  # big stills at a few yaws for looking at the model
            render_sheet(fish, ppm * 3, [0.0], [0.0, 0.25, 0.5, 0.75], tmp, os.path.join(preview, f'{name}.png'), yaws=[0, 45, 90])
            return
        man = dict(iris=fish.iris, yaws=YAWS, len=round(fish.px * SIZE))
        out = os.path.join(common.ASSETS, name)
        man.update(render_sheet(fish, ppm, [0.0], [i / FRAMES for i in range(FRAMES)], tmp, out + '.png'))
        if name == 'pleco':  # clinging to the glass: a belly-view still, anchored at the sucker mouth
            g = render_sheet(fish, ppm, [0.0], [0.0], tmp, out + '-glass.png', yaws=[0], tilt=-90)
            m = rotm(0, -90) @ next(p['mouth'] for p in fish.parts if p.get('mouth') is not None)
            common.manifest(name + '-glass', dict(w=g['w'], h=g['h'], anchor=[round(g['anchor'][0] + m[0] * ppm, 2),
                                                                              round(g['anchor'][1] - m[2] * ppm, 2)]))
        if fish.inflate:
            man['puff'] = name + '-puff'
            common.manifest(name + '-puff', render_sheet(fish, ppm, [i / (PUFFS - 1) for i in range(PUFFS)], [0.0], tmp,
                                                        out + '-puff.png'))
    common.manifest(name, man)
    print(f'fish: {name} {man["w"]}x{man["h"]} x {man["cols"]} x {len(YAWS)}')


# ---------- species ----------

def finpaint(base, tip=None, alpha=(0.8, 0.5), bands=(), rays=24, rough=0.35, spots=None, seed=0, mark='#1a1410',
            film=0.0, ray_alpha=0.25, ray_w=0.1, spiny=False):
    """Fin texture: base colour fading to tip, (v0, v1, colour, alpha) bands across the rays,
    optional spots(T, V, X, Z) mask, thin darker rays (uneven spacing, each forking once near the
    edge), membrane alpha varying cell to cell, and a ragged trailing edge with a notch or two.
    film > 0 adds a thin-film (iridescent) mask strength."""
    rng = np.random.default_rng(seed + 100)
    notches = rng.random(1 + (seed % 2)) * 0.8 + 0.1

    def paint(T, V, X, Z):
        col = np.zeros(T.shape + (3,))
        col[:] = hexc(base)
        if tip:
            mix(col, tip, smooth(0.25, 1.0, V))
        a = alpha[0] + (alpha[1] - alpha[0]) * V
        for v0, v1, c, al in bands:
            m = smooth(v0 - 0.03, v0 + 0.03, V) * (1 - smooth(v1 - 0.03, v1 + 0.03, V))
            mix(col, c, m)
            a = a * (1 - m) + al * m
        n = rays - 1
        u = T * n + (noise(T * n * 0.5, V * 0.3, 1, 1, seed + 60) - 0.5) * 0.3  # +-15 % ray spacing
        f = u - np.round(u)
        fork = 0 if spiny else 0.2 * smooth(0.6, 1.0, V)  # each ray splits in two toward the edge
        d = np.minimum(np.abs(f - fork), np.abs(f + fork))
        ray = smooth(ray_w, ray_w * 0.2, d)
        if spots is not None:
            m = spots(T, V, X, Z)
            if spiny:  # marks band the free spines, the thin web stays clear
                mix(col, mark, m * np.maximum(ray, 0.3) * 0.9)
            else:
                mix(col, mark, m * 0.85)
                a = np.maximum(a, m * 0.85)
        mix(col, col * 0.62, ray * 0.65)
        cell = _LATTICE[np.floor(u).astype(int) & 255, (seed * 7) & 255]
        a = a * (0.85 + 0.3 * (cell - 0.5)) + ray * ray_alpha * (1 - V * 0.5)
        lim = 0.93 - 0.07 * noise(T * 9, V, 1, 3, seed)
        for tn in notches:
            lim = lim - 0.12 * np.exp(-((T - tn) / 0.03) ** 2)
        a = np.clip(a, 0, 1) * smooth(lim + 0.07, lim, V)
        rgba = np.concatenate([col, a[..., None]], -1)
        h = ray * 0.8 + noise(T * 20, V * 6, 1, 3, seed) * 0.2
        return rgba, h, rough + 0 * T, film * (0.5 + 0.5 * V) * (1 - ray * 0.5)
    return paint


def side_fin(fish, name, u, side, rays_ang, ln, paint, splay=0.45, drop=0.15, size=0.05, flap=0.45, stack=0.0, **kw):
    """Paired fin (pectoral / pelvic) on both flanks, rays pointing back, splayed outward."""
    for sign in (-1, 1):
        p, n = fish.at(u, side)
        p = np.array([p[0], sign * abs(p[1]), p[2]]) - np.array([0, sign * 0.006, 0])
        ex = np.array([1.0, -sign * splay, drop])
        ex /= np.linalg.norm(ex)
        ez = np.array([0, 0, 1.0]) - ex * ex[2]
        ez /= np.linalg.norm(ez)
        en = np.cross(ez, ex)
        M = np.stack([ex, en, ez], 1)
        fish.fin(f'{name}{sign}', (0, -size / 2), (0, size / 2), rays_ang, ln, paint, M=M, O=p,
                 flap=flap * sign, stack=stack * sign, **kw)


def clown():
    f = Fish('clown', px=82, amp=0.055, iris='#c8581a')
    top = curve([(0, .055), (.12, .07), (.35, .155), (.55, .19), (.75, .175), (.9, .12), (1, .04)])
    bot = curve([(0, -.055), (.12, -.07), (.35, -.14), (.55, -.165), (.75, -.15), (.9, -.09), (1, -.035)])
    wid = curve([(0, .025), (.2, .05), (.5, .095), (.75, .105), (.9, .085), (1, .05)])

    def paint(X, Y, Z, U):
        n = noise(X * 3, Z * 3 + Y, 4)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#ee6814')
        mix(col, '#f4923a', smooth(-0.04, -0.16, Z) * 0.6)       # paler belly
        mix(col, '#c4480f', smooth(0.06, 0.19, Z) * 0.45)       # deeper back
        bands = [
            (0.17 + 0.09 * (Z / 0.17) ** 2, 0.042),              # head band, curving forward
            (-0.05 + 0.055 * np.exp(-(Z / 0.06) ** 2) - 0.02 * (Z / 0.17) ** 2, 0.04),  # mid band, forward bulge
            (-0.355, 0.02),                                      # tail band
        ]
        white, near = np.zeros(X.shape), np.full(X.shape, 1.0)
        for i, (xc, w) in enumerate(bands):
            d = np.abs(X - xc + (n - 0.5) * 0.03 + 0.008 * np.sin(Z * 70 + i))
            near = np.minimum(near, d - w)
            mix(col, '#151214', smooth(w + 0.03 + 0.006 * n, w + 0.016, d))  # wide, uneven black edge
            m = smooth(w + 0.004, w - 0.004, d)
            mix(col, '#f2eee4', m)
            white += m
        mix(col, '#d95210', smooth(0.09, 0.02, near) * (1 - white.clip(0, 1)) * 0.5)  # orange deepens toward each band
        sc = scales(X, Z, 0.02, head=0.21)
        gx, gz, R = 0.33, -0.005, 0.12
        d = np.hypot(X - gx, (Z - gz) * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - R)) * (X < gx) * (np.abs(Z - gz) < 0.13)
        mix(col, col * 0.75, gill * 0.6)
        height = 0.15 * sc + 0.4 * (d < R) + 0.3 * gill
        rough = 0.45 + 0.12 * n - 0.1 * white.clip(0, 1)
        return col, height, rough, 0 * X

    f.body(-0.42, 0.42, top, bot, wid, paint, nose=0.13, q=0.95, sss=0.15, head=0.21, coat=0.06)
    tz, bz, zc = f.tz, f.bz, f.zc
    edged = finpaint('#ec681c', '#f08030', (0.85, 0.7), [(0.82, 0.89, '#141012', 0.95), (0.89, 1.1, '#f2eee4', 0.8)], seed=1)
    f.fin('dorsal1', (0.15, tz(0.15) - 0.02), (-0.03, tz(-0.03) - 0.02), lambda t: 95 + 35 * t,
          lambda t: 0.06 + 0.035 * np.sin(np.pi * t) + 0.01 * np.sin(np.pi * t * 8), edged, rays=10)
    f.fin('dorsal2', (-0.03, tz(-0.03) - 0.02), (-0.30, tz(-0.30) - 0.015), lambda t: 110 + 55 * t,
          lambda t: 0.06 + 0.07 * np.sin(np.pi * (0.1 + 0.85 * t)), edged, rays=16, curl=-15, stack=-0.006)
    f.fin('anal', (-0.06, bz(-0.06) + 0.02), (-0.30, bz(-0.30) + 0.015), lambda t: -110 - 55 * t,
          lambda t: 0.05 + 0.07 * np.sin(np.pi * (0.1 + 0.85 * t)), edged, rays=14, curl=15, stack=0.006)
    f.fin('caudal', (-0.405, -0.045), (-0.405, 0.045), lambda t: 208 - 56 * t,
          lambda t: 0.19 + 0.035 * np.sin(np.pi * t), edged, rays=26, curl=0, pleat=0.008, ripple=0.01)
    pect = finpaint('#f07a28', '#f8a050', (0.75, 0.45), [(0.84, 1.1, '#1a1214', 0.85)], rays=14, seed=2)
    side_fin(f, 'pect', 0.68, 0.2, lambda t: 200 - 40 * t, lambda t: 0.08 + 0.025 * np.sin(np.pi * t), pect, rays=14)
    side_fin(f, 'pelvic', 0.66, 0.08, lambda t: 240 - 25 * t, lambda t: 0.06 + 0.01 * t, pect, splay=0.3, drop=-0.6, size=0.03,
             flap=0.2, rays=8)
    f.eye(0.86, 0.36, 0.045, rim='#c45016')
    f.lips((0.425, 0, zc(0.38) - 0.012), 0.03, '#ee6814')
    return f


def bars(xs, w, lean=0.02, dots=False):
    """Fin marks continuing the body's vertical bars out across the fin; dots: broken into spots."""
    def m(T, V, X, Z):
        x = X + lean * Z + 0.005 * np.sin(Z * 40)
        b = np.clip(sum(smooth(w + 0.01, w - 0.005, np.abs(x - c)) for c in xs), 0, 1)
        if dots:  # out on the fin the bar breaks into a row of spots
            b *= 1 - smooth(0.3, 0.6, V) * smooth(0.45, 0.6, noise(T * 30, V * 12, 1, 2, 70))
        return b
    return m


def tetra():
    f = Fish('tetra', px=48, amp=0.06, iris='#2c5f86')
    top = curve([(0, .04), (.2, .06), (.5, .115), (.75, .115), (.9, .08), (1, .03)])
    bot = curve([(0, -.04), (.2, -.06), (.5, -.1), (.75, -.095), (.9, -.065), (1, -.025)])
    wid = curve([(0, .02), (.3, .045), (.6, .06), (.85, .055), (1, .035)])

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y, 2, 4, 3)
        mid = (top(U) + bot(U)) / 2
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#8a947a')                                   # olive translucent back
        mix(col, '#d8e0e2', smooth(mid - 0.01, mid - 0.06, Z) * 0.8)  # pale, see-through belly
        sz = mid + 0.022 - 0.01 * (X - 0.1)                        # neon stripe line
        stripe = smooth(0.013, 0.007, np.abs(Z - sz)) * smooth(0.36, 0.3, X) * smooth(-0.34, -0.28, X)
        red = smooth(sz - 0.012, sz - 0.03, Z) * smooth(0.1, 0.0, X) * smooth(-0.38, -0.3, X)
        mix(col, '#d0182e', red * 0.9)
        mix(col, '#5d6a52', smooth(sz + 0.02, sz + 0.05, Z) * 0.6)  # darker dorsal edge
        mix(col, '#2ad0f0', stripe)
        sc = scales(X, Z, 0.022, head=0.3, mid=mid)
        gx, R = 0.3, 0.1
        d = np.hypot(X - gx - R, (Z - mid) * 0.9)
        gill = smooth(0.01, 0.0, np.abs(d - R)) * (np.abs(Z - mid) < 0.08)
        mix(col, col * 0.75, gill * 0.5)
        film = np.clip(stripe * 1.0 + 0.2 * smooth(mid - 0.01, mid - 0.05, Z), 0, 1)
        return col, 0.2 * sc + 0.3 * (d < R) + 0.2 * gill, 0.32 + 0.1 * n - 0.15 * stripe, film

    f.body(-0.4, 0.4, top, bot, wid, paint, nose=0.12, film=480, sss=0.5, coat=0.1, head=0.3)
    clear = finpaint('#d4e0e4', '#eef4f6', (0.4, 0.18), [(0.86, 1.1, '#ffffff', 0.7)], rays=12, seed=3)
    plain = finpaint('#d4e0e4', '#eef4f6', (0.38, 0.15), rays=22, seed=4)
    f.fin('dorsal', (0.0, f.tz(0.0, .012)), (-0.13, f.tz(-0.13, .012)), lambda t: 105 + 40 * t,
          lambda t: 0.12 - 0.06 * t, clear, rays=12, curl=-10)
    f.fin('adipose', (-0.24, f.tz(-0.24, .01)), (-0.3, f.tz(-0.3, .01)), lambda t: 120 + 40 * t,
          lambda t: 0.028 * np.sin(np.pi * (0.2 + 0.7 * t)) + 0.006, finpaint('#a8b0a0', None, (0.6, 0.5), rays=6), rays=6)
    f.fin('anal', (0.02, f.bz(0.02, .012)), (-0.3, f.bz(-0.3, .01)), lambda t: -120 - 40 * t,
          lambda t: 0.09 - 0.04 * t, clear, rays=18, curl=8, stack=0.005)
    f.fin('caudal', (-0.385, -0.035), (-0.385, 0.035), lambda t: 218 - 76 * t,
          lambda t: 0.1 + 0.12 * np.abs(2 * t - 1) ** 1.3, plain, rays=22, pleat=0.005)
    side_fin(f, 'pect', 0.72, 0.22, lambda t: 195 - 35 * t, lambda t: 0.07 + 0.01 * np.sin(np.pi * t),
             finpaint('#dde8ec', None, (0.3, 0.12), rays=10), rays=10, size=0.03)
    side_fin(f, 'pelvic', 0.6, 0.06, lambda t: 235 - 20 * t, lambda t: 0.05, plain, splay=0.3, drop=-0.6, size=0.02,
             flap=0.2, rays=6)
    f.eye(0.86, 0.33, 0.05, rim='#7c8a78')
    f.lips((0.402, 0, f.zc(0.37) - 0.004), 0.013, '#9aa08c')
    return f


def angel(morph=None):
    gold = morph == 'gold'
    f = Fish('angel', px=86, amp=0.035, iris='#c21c18')
    top = curve([(0, .06), (.15, .085), (.4, .21), (.6, .25), (.8, .19), (.93, .095), (1, .03)])
    bot = curve([(0, -.06), (.15, -.085), (.4, -.19), (.6, -.22), (.8, -.17), (.93, -.075), (1, -.02)])
    wid = curve([(0, .015), (.3, .035), (.6, .045), (.85, .04), (1, .025)])
    BARS = [(0.205, 0.02), (0.02, 0.032), (-0.17, 0.026), (-0.285, 0.01)]

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 5)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#f4a844' if gold else '#d6d9ce')
        mix(col, '#f0962c' if gold else '#c4ad78', smooth(0.05, 0.22, Z) * smooth(-0.1, 0.25, X) * 0.7)  # crown wash
        mix(col, '#f2e6c0' if gold else '#eeede4', smooth(-0.05, -0.2, Z) * 0.6)
        bar = np.zeros(X.shape)
        for xc, w in BARS:
            d = np.abs(X - xc + (n - 0.5) * 0.03 + 0.02 * Z)
            bar += smooth(w + 0.01, w - 0.008, d) * (0.6 if w < 0.015 else 1)
        mix(col, '#1c1c20', np.clip(bar, 0, 1) * (0.12 if gold else 0.92))
        mix(col, col * 0.8, (noise(X * 30, Z * 30, 1, 2, 6) > 0.62) * 0.3)  # faint speckles
        sc = scales(X, Z, 0.016, head=0.16)
        d = np.hypot(X - 0.28, (Z - 0.0) * 0.8)
        gill = smooth(0.01, 0.0, np.abs(d - 0.12)) * (np.abs(Z) < 0.1)
        return col, 0.2 * sc + 0.3 * (d < 0.12) + 0.2 * gill, 0.38 + 0.1 * n, 0.5 * (1 - np.clip(bar, 0, 1))

    f.body(-0.3, 0.3, top, bot, wid, paint, nose=0.1, q=0.9, film=0 if gold else 380, sss=0.2, head=0.16)
    xs = [b[0] for b in BARS]
    fc, ft = ('#f2c486', '#f8e2c0') if gold else ('#e2e0d2', '#f2f0e8')
    sail = lambda s: finpaint(fc, ft, (0.72, 0.38), [(0.93, 1.1, '#ffffff', 0.55)], rays=18, seed=s,  # noqa: E731
                              spots=None if gold else bars(xs, 0.022, dots=True), mark='#121214')
    f.fin('dorsal', (0.14, f.tz(0.14, .02)), (-0.27, f.tz(-0.27, .015)), lambda t: 108 + 62 * t,
          lambda t: 0.48 - 0.34 * t, sail(2), rays=18, curl=-12, ripple=0.012, stack=-0.008)
    f.fin('anal', (0.06, f.bz(0.06, .02)), (-0.27, f.bz(-0.27, .015)), lambda t: -108 - 62 * t,
          lambda t: 0.44 - 0.3 * t, sail(3), rays=16, curl=12, ripple=0.012, stack=0.008)
    f.fin('caudal', (-0.29, -0.05), (-0.29, 0.05), lambda t: 212 - 64 * t,
          lambda t: 0.17 + 0.2 * np.abs(2 * t - 1) ** 5, finpaint(fc, ft, (0.6, 0.3), rays=22, seed=5,
          spots=lambda T, V, X, Z: smooth(0.05, 0.02, np.abs(V - 0.2)) * (0.15 if gold else 0.6)), rays=22, pleat=0.004,
          ripple=0.012)
    side_fin(f, 'pect', 0.7, 0.24, lambda t: 195 - 30 * t, lambda t: 0.07, finpaint('#e8eae0', None, (0.3, 0.12), rays=10),
             rays=10, size=0.03)
    for sign in (-1, 1):  # long trailing ventral threads
        x0, z0 = 0.15, f.bz(0.15, 0.01)
        f.tube(f'ventral{sign}', [(x0, sign * 0.02, z0), (0.12, sign * 0.04, z0 - 0.12), (0.05, sign * 0.05, z0 - 0.3),
                                  (-0.04, sign * 0.05, z0 - 0.44)], 0.009, 0.003, fc, wiggle=0.025)
    f.eye(0.83, 0.36, 0.044, rim='#9a2018')  # angels have a red ring round the eye
    f.lips((0.302, 0, f.zc(0.28) - 0.005), 0.018, '#c8b48a' if gold else '#b8b2a0')
    return f


def goldfish():
    f = Fish('goldfish', px=94, amp=0.05, iris='#c08a2c')
    top = curve([(0, .06), (.15, .1), (.4, .23), (.6, .26), (.8, .21), (.93, .12), (1, .05)])
    bot = curve([(0, -.06), (.15, -.1), (.4, -.21), (.6, -.23), (.8, -.17), (.93, -.09), (1, -.03)])
    wid = curve([(0, .03), (.3, .11), (.6, .15), (.85, .12), (1, .06)])

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y * 2, 1, 4, 8)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#ec6a10')
        mix(col, '#f4a838', smooth(0.0, -0.2, Z) * 0.75)                # golden belly
        mix(col, '#cc4c0a', smooth(0.1, 0.25, Z) * 0.55)                # deep back
        pearl = smooth(0.68, 0.74, noise(X * 6, Z * 6 + Y, 1, 3, 9)) * smooth(-0.04, -0.14, Z)
        mix(col, '#f2e6d0', pearl * 0.9)                                 # a few pearly patches low down
        sc = scales(X, Z, 0.045, head=0.24)
        back = smooth(0.02, 0.15, Z)
        mix(col, '#ffcc70', smooth(0.75, 1.0, sc) * 0.45 * back * (1 - pearl))  # metallic rims, back only
        d = np.hypot(X - 0.37, (Z + 0.01) * 0.8)
        gill = smooth(0.012, 0.0, np.abs(d - 0.13)) * (np.abs(Z) < 0.15)
        mix(col, col * 0.7, gill * 0.5)
        return col, 0.5 * sc + 0.35 * (d < 0.13) + 0.3 * gill, 0.3 + 0.12 * n, (0.3 + 0.4 * sc) * (0.4 + 0.6 * back)

    f.body(-0.35, 0.35, top, bot, wid, paint, nose=0.14, film=420, metal=0.2, sss=0.2, coat=0.1, head=0.24)
    veil = finpaint('#ee7c1c', '#fbe8d0', (0.85, 0.3), rays=26, seed=4)
    f.fin('dorsal', (0.14, f.tz(0.14, .02)), (-0.24, f.tz(-0.24, .015)), lambda t: 100 + 62 * t,
          lambda t: 0.17 - 0.03 * t + 0.02 * np.sin(np.pi * t), veil, rays=18, curl=-22, ripple=0.015)
    for sign in (-1, 1):  # fantail: twin tails splayed 35 deg so the fan reads in 3/4
        a = math.radians(35 * sign)
        M = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
        f.fin(f'caudal{sign}', (-0.335, -0.06), (-0.335, 0.06), lambda t: 205 - 52 * t,
              lambda t: 0.3 + 0.14 * np.abs(2 * t - 1) ** 1.5, finpaint('#ee7c1c', '#fbe8d0', (0.85, 0.3), rays=26, seed=5 + sign),
              rays=26, curl=0, pleat=0.008, ripple=0.03, M=M)
        a = math.radians(28 * sign)
        M = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
        f.fin(f'anal{sign}', (-0.12, f.bz(-0.12, .02)), (-0.25, f.bz(-0.25, .015)), lambda t: -140 - 30 * t,
              lambda t: 0.12, veil, rays=10, curl=10, ripple=0.012, M=M)
    side_fin(f, 'pect', 0.72, 0.18, lambda t: 205 - 40 * t, lambda t: 0.1 + 0.02 * np.sin(np.pi * t), veil, rays=12, size=0.04)
    side_fin(f, 'pelvic', 0.6, 0.05, lambda t: 240 - 25 * t, lambda t: 0.09, veil, splay=0.35, drop=-0.6, size=0.03,
             flap=0.25, rays=8)
    f.eye(0.85, 0.37, 0.05, rim='#e2701a', out=0.25, gloss=0.25)
    f.lips((0.355, 0, f.zc(0.32) - 0.01), 0.032, '#f4a08a', shade=1.0, thick=0.28)  # goldfish keep a paler lip
    return f


def tang():
    f = Fish('tang', px=110, amp=0.05, iris='#141418')
    top = curve([(0, .045), (.15, .075), (.4, .2), (.6, .22), (.8, .18), (.93, .1), (1, .02)])
    bot = curve([(0, -.045), (.15, -.075), (.4, -.19), (.6, -.2), (.8, -.15), (.93, -.075), (1, -.03)])
    wid = curve([(0, .02), (.3, .05), (.6, .065), (.85, .055), (1, .03)])

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 11)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#2244a6')
        mix(col, '#3a68c0', smooth(0.25, 0.4, X) * 0.4)           # brighter face
        mix(col, '#18307e', smooth(0.05, 0.2, Z) * 0.4)
        mix(col, '#2c58b4', smooth(0.45, 0.7, noise(X * 7, Z * 7 + Y, 1, 3, 15)) * 0.35)  # uneven tone
        # the "palette": a black sweep from the eye to the tail with a blue window inside
        e1 = ((X + 0.02) / 0.3) ** 2 + ((Z - 0.07) / 0.105) ** 2
        e2 = ((X + 0.07) / 0.13) ** 2 + ((Z - 0.035) / 0.045) ** 2
        tail = smooth(0.03, 0.015, np.abs(Z - 0.05)) * smooth(-0.2, -0.3, X) * smooth(-0.4, -0.34, X)
        rag = (n - 0.5) * 0.35 + (noise(X * 30, Z * 30, 1, 2, 16) - 0.5) * 0.45  # ragged, not a clean vector edge
        ring = np.clip(smooth(1.1, 0.92, e1 + rag) - smooth(1.1, 0.92, e2 + rag * 1.2) + tail, 0, 1)
        eye = smooth(0.026, 0.016, np.abs(X - 0.3 + 0.12 * (Z - 0.03))) * (Z > 0.0)  # mask runs up from the eye
        mix(col, '#080a1c', np.clip(ring + eye, 0, 1))
        spine = smooth(0.022, 0.012, np.hypot(X + 0.35, (Z - 0.0) * 1.5))
        mix(col, '#f2c828', spine)                                # yellow scalpel spot on the tail root
        sc = scales(X, Z, 0.012, head=0.27)
        d = np.hypot(X - 0.42, (Z + 0.01) * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - 0.15)) * (np.abs(Z) < 0.13)
        mix(col, col * 0.7, gill * 0.5)
        mix(col, col * 0.85, smooth(0.6, 1.0, sc) * 0.5)          # faint scale texture
        return col, 0.22 * sc + 0.3 * (d < 0.15) + 0.3 * gill, 0.58 + 0.1 * n, 0.12 * (1 - ring)

    f.body(-0.38, 0.38, top, bot, wid, paint, nose=0.1, q=0.92, film=200, sss=0.12, head=0.27, coat=0.02)
    # the eye mask carries on up onto the front of the dorsal fin
    mask = lambda T, V, X, Z: smooth(0.035, 0.015, np.abs(X - 0.3 + 0.12 * (Z - 0.03)) - 0.01)  # noqa: E731
    edge = finpaint('#1c48c8', None, (0.92, 0.85), [(0.62, 0.86, '#0a0c22', 0.95), (0.86, 1.1, '#5aa8ff', 0.9)], rays=30,
                    spots=mask, mark='#080a1c', seed=6)
    f.fin('dorsal', (0.26, f.tz(0.26, .02)), (-0.33, f.tz(-0.33, .015)), lambda t: 125 + 40 * t,
          lambda t: 0.06 + 0.035 * np.sin(np.pi * (0.2 + 0.8 * t)), edge, rays=30, curl=-8)
    f.fin('anal', (0.05, f.bz(0.05, .02)), (-0.33, f.bz(-0.33, .015)), lambda t: -125 - 40 * t,
          lambda t: 0.055 + 0.035 * np.sin(np.pi * (0.2 + 0.8 * t)), finpaint('#1c48c8', None, (0.92, 0.85),
          [(0.62, 0.86, '#0a0c22', 0.95), (0.86, 1.1, '#5aa8ff', 0.9)], rays=22, seed=7), rays=22, curl=8)
    yellow = finpaint('#f2c41c', '#f6d650', (0.95, 0.85), rays=20, seed=8,
                      spots=lambda T, V, X, Z: smooth(0.12, 0.04, np.minimum(T, 1 - T)) * smooth(0.2, 0.5, V))
    f.fin('caudal', (-0.37, -0.045), (-0.37, 0.045), lambda t: 222 - 84 * t,
          lambda t: 0.2 + 0.05 * np.abs(2 * t - 1) ** 2 - 0.03 * np.sin(np.pi * t), yellow, rays=20, pleat=0.005)
    side_fin(f, 'pect', 0.74, 0.22, lambda t: 200 - 40 * t, lambda t: 0.1 + 0.02 * np.sin(np.pi * t),
             finpaint('#2a5ad8', '#f2c41c', (0.8, 0.7), rays=12), rays=12, size=0.04)
    f.eye(0.87, 0.35, 0.045, rim='#0a0c1c')
    f.lips((0.38, 0, f.zc(0.35) - 0.012), 0.016, '#1c4cd2')
    return f


def puffer():
    zc0 = 0.0

    def inflate(co, puff, part):
        def blow(c):
            c = c.copy()
            e = np.clip(1 - ((c[:, 0] - 0.03) / 0.4) ** 2, 0, 1)
            k = 1 + 0.75 * puff * e
            c[:, 1] *= k
            c[:, 2] = zc0 + (c[:, 2] - zc0) * k
            c[:, 0] *= 1 + 0.08 * puff
            return c
        if part is not None and 'spk' in part:
            b = part['spk']
            return blow(b) + (co - b) * (1 + 2.6 * puff)
        return blow(co)

    f = Fish('puffer', px=80, amp=0.035, iris='#4a8a4e', inflate=inflate)
    top = curve([(0, .05), (.2, .1), (.45, .19), (.7, .21), (.88, .16), (1, .06)])
    bot = curve([(0, -.05), (.2, -.1), (.45, -.2), (.7, -.21), (.88, -.14), (1, -.04)])
    wid = curve([(0, .035), (.3, .13), (.6, .19), (.85, .15), (1, .07)])
    rng = np.random.default_rng(3)
    dots = rng.random((140, 2)) * [0.62, 0.3] + [-0.3, -0.02]
    dots = dots[rng.random(140) < 0.25 + 0.75 * (dots[:, 1] > 0.06)]  # spots cluster on the back

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y * 3, 1, 4, 12)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#d0ba68')
        mix(col, '#b09244', smooth(0.05, 0.2, Z) * 0.6)
        belly = smooth(-0.02, -0.07, Z + (n - 0.5) * 0.04)
        mix(col, '#f4f1e8', belly)                                 # clean white belly
        spot = np.zeros(X.shape)
        for dx, dz in dots:
            r = 0.009 + 0.007 * smooth(-0.3, 0.05, -abs(dx + 0.02))
            spot = np.maximum(spot, smooth(r + 0.005, r, np.hypot(X - dx, (Z - dz) * 1.1)))
        mix(col, '#563616', spot * (1 - belly))
        saddle = smooth(0.06, 0.03, np.abs(X + 0.05)) * smooth(0.05, 0.12, Z) * 0.5
        mix(col, '#6a4a20', saddle)
        return col, 0.15 * noise(X * 40, Z * 40, 1, 2, 13) + 0.2 * spot, 0.52 + 0.1 * n, 0 * X

    f.body(-0.32, 0.32, top, bot, wid, paint, nose=0.16, sss=0.3, coat=0.08)
    pts, nrm = [], []
    for u in np.linspace(0.18, 0.8, 9):
        for sd in np.linspace(0.04, 0.96, 15):
            if abs(sd - 0.5) < 0.08:
                continue  # leave the back ridge clear for the dorsal line
            p, n = f.at(u + 0.012 * ((sd * 15) % 2), sd)
            pts.append(p)
            nrm.append(n)
    f.spikes(pts, nrm, 0.007, 0.005, '#e2d8b6')
    tiny = finpaint('#e8d690', '#f4ecc8', (0.6, 0.3), rays=10, seed=9)
    f.fin('dorsal', (-0.16, f.tz(-0.16, .02)), (-0.25, f.tz(-0.25, .015)), lambda t: 115 + 40 * t, lambda t: 0.08 - 0.02 * t, tiny, rays=9, curl=-10)
    f.fin('anal', (-0.16, f.bz(-0.16, .02)), (-0.25, f.bz(-0.25, .015)), lambda t: -115 - 40 * t, lambda t: 0.075 - 0.02 * t, tiny, rays=9, curl=10)
    f.fin('caudal', (-0.31, -0.04), (-0.31, 0.04), lambda t: 215 - 70 * t, lambda t: 0.13 + 0.02 * np.sin(np.pi * t),
          finpaint('#d8c070', '#f0e4b8', (0.8, 0.5), rays=16, spots=lambda T, V, X, Z: (noise(T * 9, V * 9, 1, 2, 14) > 0.6) * 0.8,
                   mark='#5b3a18', seed=10), rays=16)
    side_fin(f, 'pect', 0.66, 0.28, lambda t: 190 - 30 * t, lambda t: 0.07 + 0.015 * np.sin(np.pi * t),
             finpaint('#eee2b0', None, (0.55, 0.25), rays=12), rays=12, size=0.045, flap=0.8)
    f.eye(0.82, 0.4, 0.052, rim='#c4a24a', out=0.27, toe=20, gloss=0.25)
    f.lips((0.325, 0, f.zc(0.3) - 0.012), 0.03, '#efe4c8', shade=1.0, thick=0.3)  # puffer keeps a paler lip
    return f


def cory(morph=None):
    albino = morph == 'albino'
    f = Fish('cory', px=68, amp=0.05, iris='#c42438' if albino else '#222018')
    top = curve([(0, .045), (.15, .06), (.45, .165), (.62, .185), (.8, .15), (.93, .085), (1, .03)])
    bot = curve([(0, -.04), (.15, -.05), (.45, -.08), (.7, -.085), (.9, -.07), (1, -.045)])
    wid = curve([(0, .025), (.3, .06), (.6, .085), (.85, .07), (1, .04)])
    base = '#f2ccb8' if albino else '#b4aa94'

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 15)
        mid = (top(U) + bot(U)) / 2
        col = np.zeros(X.shape + (3,))
        col[:] = hexc(base)
        mix(col, '#e8b0a0' if albino else '#7c765e', smooth(mid, mid + 0.1, Z) * 0.6)  # darker back
        mix(col, '#f6ece4' if albino else '#e8e0cc', smooth(mid - 0.02, mid - 0.06, Z))  # pale belly
        if not albino:
            pep = smooth(0.62, 0.68, noise(X * 45, Z * 45 + Y * 9, 1, 2, 16)) * smooth(mid - 0.04, mid + 0.02, Z)
            mix(col, '#2e2a24', pep * 0.9)                              # pepper spots
        # armour: two rows of plates meeting at a lateral seam; each row's grooves are offset
        # half a plate and slant the other way, like the real scutes
        seam = smooth(0.006, 0.0, np.abs(Z - mid - 0.005))
        up = Z > mid + 0.005
        k = (X - np.where(up, 0.25, -0.25) * (Z - mid)) / 0.042 + np.where(up, 0, 0.5)
        groove = smooth(0.09, 0.0, np.abs(k - np.round(k))) * (X < 0.24) * (X > -0.33)
        plates = np.clip(seam + groove, 0, 1)
        mix(col, col * 0.62, plates * (0.5 if albino else 0.8))
        d = np.hypot(X - 0.34, (Z - mid) * 0.8)
        gill = smooth(0.012, 0.0, np.abs(d - 0.11)) * (np.abs(Z - mid) < 0.1)
        mix(col, col * 0.6, gill * 0.7)
        sheen = smooth(0.24, 0.32, X) * smooth(mid - 0.04, mid + 0.04, Z)  # bronze-green cheek plate
        mix(col, '#e0b0a0' if albino else '#768646', sheen * 0.45)
        h = 0.5 * (k - np.floor(k)) * (X < 0.24) + 0.3 * (d < 0.11) - 0.3 * plates
        return col, h, 0.47 + 0.1 * n, np.clip(sheen + 0.3 * (1 - plates), 0, 1) * (0.3 if albino else 1)

    f.body(-0.36, 0.36, top, bot, wid, paint, nose=0.12, q=0.8, film=520, sss=0.25 if albino else 0.08, coat=0.08,
           bump=0.6, head=0.24)
    fin = '#efdcd2' if albino else '#d6cebc'
    speck = lambda s: lambda T, V, X, Z: (noise(T * 7, V * 7, 1, 2, s) > 0.62) * (0.0 if albino else 1.0)  # noqa: E731
    f.fin('dorsal', (0.08, f.tz(0.08, .015)), (-0.06, f.tz(-0.06, .015)), lambda t: 98 + 45 * t,
          lambda t: 0.19 - 0.12 * t, finpaint(fin, None, (0.55, 0.3), rays=9, spots=speck(17), mark='#2e2a24', seed=11), rays=9, curl=-12)
    f.fin('adipose', (-0.22, f.tz(-0.22, .01)), (-0.28, f.tz(-0.28, .01)), lambda t: 125 + 40 * t, lambda t: 0.04 - 0.015 * t,
          finpaint(base, None, (0.75, 0.6), rays=5), rays=5)
    f.fin('anal', (-0.14, f.bz(-0.14, .012)), (-0.24, f.bz(-0.24, .012)), lambda t: -125 - 35 * t, lambda t: 0.06,
          finpaint(fin, None, (0.5, 0.25), rays=7, seed=12), rays=7, curl=8)
    f.fin('caudal', (-0.35, -0.035), (-0.35, 0.035), lambda t: 222 - 84 * t,
          lambda t: 0.13 + 0.07 * np.abs(2 * t - 1) ** 1.2,
          finpaint(fin, None, (0.5, 0.3), rays=16, mark='#2e2a24', seed=13,
                   spots=lambda T, V, X, Z: smooth(0.3, 0.12, np.abs(np.sin(V * 14))) * (0.0 if albino else 0.8)), rays=16, pleat=0.005)
    side_fin(f, 'pect', 0.72, 0.1, lambda t: 205 - 40 * t, lambda t: 0.1 - 0.03 * t,
             finpaint(fin, None, (0.6, 0.3), rays=8), rays=8, size=0.03, drop=-0.35, splay=0.6)
    side_fin(f, 'pelvic', 0.5, 0.04, lambda t: 230 - 20 * t, lambda t: 0.06, finpaint(fin, None, (0.5, 0.25), rays=6),
             splay=0.4, drop=-0.6, size=0.025, flap=0.2, rays=6)
    xs, zs = 0.33, f.bz(0.33, 0.012)
    bc = '#e6cabc' if albino else '#c8bca2'
    for sign in (-1, 1):  # two pairs of long barbels under the snout
        f.tube(f'barbel{sign}a', [(xs, sign * 0.018, zs), (xs + 0.035, sign * 0.03, zs - 0.035), (xs + 0.055, sign * 0.05, zs - 0.08)],
               0.006, 0.002, bc, wiggle=0.012)
        f.tube(f'barbel{sign}b', [(xs - 0.02, sign * 0.03, zs + 0.005), (xs - 0.005, sign * 0.055, zs - 0.04), (xs + 0.005, sign * 0.08, zs - 0.075)],
               0.005, 0.0018, bc, wiggle=0.014)
    f.eye(0.78, 0.4, 0.04, rim=base, toe=18)
    f.lips((0.35, 0, f.bz(0.35, 0.02)), 0.014, base)
    return f


def betta(morph=None):
    koi = morph == 'koi'
    f = Fish('betta', px=100, amp=0.04, iris='#2a0a0e')
    top = curve([(0, .035), (.2, .065), (.5, .11), (.75, .11), (.92, .07), (1, .025)])  # slim peduncle: the tail
    bot = curve([(0, -.035), (.2, -.065), (.5, -.1), (.75, -.1), (.92, -.06), (1, -.02)])  # grows out of it, no step
    wid = curve([(0, .015), (.3, .045), (.6, .055), (.85, .05), (1, .03)])

    def koi_marks(X, Z, s):  # white base, red and black blotches like a koi
        red = smooth(0.48, 0.55, noise(X * 6, Z * 6, 1, 3, s))
        black = smooth(0.6, 0.66, noise(X * 7 + 3, Z * 7, 1, 3, s + 1))
        return red, black

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 18)
        col = np.zeros(X.shape + (3,))
        if koi:
            col[:] = hexc('#ece2dc')
            red, black = koi_marks(X, Z + 0.3 * Y, 30)
            mix(col, '#c41a2c', red)
            mix(col, '#16121a', black * 0.9)
        else:
            col[:] = hexc('#bc1636')
            mix(col, '#5a0818', smooth(0.18, 0.3, X) * 0.65)        # dark mask on the head
        sc = scales(X, Z, 0.02, head=0.19)
        blue = smooth(0.5, 0.9, sc) * smooth(0.22, 0.1, X) * (0.6 + 0.4 * n)
        mix(col, '#3a52c8', blue * (0.3 if koi else 0.6))          # iridescent blue scale edges
        d = np.hypot(X - 0.28, Z * 0.85)
        gill = smooth(0.01, 0.0, np.abs(d - 0.09)) * (np.abs(Z) < 0.08)
        mix(col, '#2a0410', gill * 0.5)
        return col, 0.35 * sc + 0.3 * (d < 0.09), 0.32 + 0.1 * n, np.clip(blue + 0.35, 0, 1)

    f.body(-0.3, 0.3, top, bot, wid, paint, nose=0.12, film=430, sss=0.25, coat=0.06, head=0.19)
    if koi:
        def marks(T, V, X, Z):
            red, black = koi_marks(X, Z, 31)
            return np.clip(black + 0.0 * red, 0, 1)
        flow = lambda s: finpaint('#e8dcd8', '#c42438', (0.85, 0.6), [(0.92, 1.1, '#f6eef0', 0.6)], rays=40, seed=s,  # noqa: E731
                                  spots=marks, mark='#16121a', film=0.6)
    else:
        flow = lambda s: finpaint('#ac122e', '#3a3cc0', (0.88, 0.6), [(0.92, 1.1, '#f0e6f0', 0.6)], rays=40, seed=s,  # noqa: E731
                                  spots=lambda T, V, X, Z: smooth(0.3, 0.5, V) * smooth(0.55, 0.75, noise(T * 30, V * 4, 1, 2, 19)) * 0.6,
                                  mark='#5a1060', film=1.0)
    # The three big fins overlap. Same ripple + world-phased deform + a fixed depth order (stack wider
    # than both pleats plus the fin thickness) keep them from passing through each other in any frame.
    # Dorsal and anal taper to a trailing point that stays off the middle of the tail fan.
    R = 0.035
    f.fin('caudal', (-0.27, -0.035), (-0.27, 0.035), lambda t: 242 - 124 * t,  # edges swept back, not vertical cuts
          lambda t: 0.36 + 0.1 * np.sin(np.pi * t), flow(6), rays=40, rows=12, pleat=0.003, ripple=R, film=430)
    f.fin('dorsal', (0.02, f.tz(0.02, .015)), (-0.22, f.tz(-0.22, .012)), lambda t: 102 + 48 * t,
          lambda t: 0.12 + 0.2 * t ** 0.8, flow(7), rays=22, curl=-12, pleat=0.004, ripple=R,
          stack=-0.02, film=430)
    f.fin('anal', (0.14, f.bz(0.14, .015)), (-0.22, f.bz(-0.22, .012)), lambda t: -98 - 46 * t,
          lambda t: 0.14 + 0.27 * t ** 0.8, flow(8), rays=26, curl=12, pleat=0.004, ripple=R,
          stack=0.02, film=430)
    side_fin(f, 'pelvic', 0.72, 0.06, lambda t: 260 - 15 * t, lambda t: 0.2 - 0.04 * t,
             finpaint('#e8dcd8' if koi else '#b01430', '#d8c8d0' if koi else '#4a3ab8', (0.85, 0.55), rays=5), splay=0.25, drop=-1.4, size=0.015,
             flap=0.15, rays=5, ripple=0.02, stack=0.02)
    side_fin(f, 'pect', 0.76, 0.24, lambda t: 195 - 35 * t, lambda t: 0.07, finpaint('#e8d0d0' if koi else '#b83048', None, (0.4, 0.15), rays=10),
             rays=10, size=0.03, flap=0.7)
    f.eye(0.85, 0.38, 0.04, rim='#e0d0cc' if koi else '#5a0818')
    f.lips((0.3, 0, f.zc(0.27) - 0.004), 0.019, '#d8c8c4' if koi else '#7a1020')
    return f


def lionfish():
    f = Fish('lionfish', px=104, amp=0.04, iris='#7a2a16')
    top = curve([(0, .045), (.2, .065), (.5, .15), (.75, .17), (.9, .13), (1, .04)])
    bot = curve([(0, -.045), (.2, -.06), (.5, -.12), (.75, -.13), (.9, -.09), (1, -.03)])
    wid = curve([(0, .02), (.3, .05), (.6, .07), (.85, .065), (1, .035)])

    def stripes(X, Z, n):  # broad maroon bands with thin pale gaps, slanting back, through the eye
        ph = X * 15 + Z * (4 + 3 * smooth(0.1, 0.35, X)) + (n - 0.5) * 1.3
        return smooth(0.2, 0.42, np.abs(np.sin(np.pi * ph)))

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y, 1, 3, 20)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#f4dcc0')
        mix(col, '#842818', stripes(X, Z, n) * (0.95 - 0.45 * smooth(-0.04, -0.12, Z)))
        mix(col, '#f2e2d8', smooth(-0.06, -0.12, Z) * 0.4)       # pinkish pale belly
        d = np.hypot(X - 0.27, Z * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - 0.1)) * (np.abs(Z) < 0.1)
        mix(col, col * 0.7, gill * 0.5)
        sc = scales(X, Z, 0.014, head=0.17)
        return col, 0.15 * sc + 0.3 * (d < 0.1) + 0.3 * gill, 0.5 + 0.1 * n, 0 * X

    f.body(-0.38, 0.38, top, bot, wid, paint, nose=0.12, q=0.95, sss=0.2, head=0.17)
    band = lambda k: lambda T, V, X, Z: smooth(0.3, 0.6, np.abs(np.sin(V * k + T * 2)))  # noqa: E731
    spines = finpaint('#f0e0cc', None, (0.35, 0.0), rays=13, spots=band(14), mark='#7a2414', ray_alpha=1.2, ray_w=0.14, seed=21,
                      spiny=True)
    f.fin('spines', (0.2, f.tz(0.2, .02)), (-0.12, f.tz(-0.12, .02)), lambda t: 100 + 35 * t,
          lambda t: 0.34 - 0.14 * t + 0.03 * np.sin(t * 40), spines, rays=13, rows=12, curl=-10, pleat=0.002, stack=-0.006)
    soft = finpaint('#e8d8c4', None, (0.35, 0.15), rays=12, seed=22, mark='#5a2010',
                    spots=lambda T, V, X, Z: smooth(0.62, 0.68, noise(T * 14, V * 10, 1, 2, 23)))
    f.fin('dorsal2', (-0.12, f.tz(-0.12, .015)), (-0.32, f.tz(-0.32, .012)), lambda t: 120 + 40 * t,
          lambda t: 0.13 - 0.04 * t, soft, rays=12, curl=-10)
    f.fin('anal', (-0.1, f.bz(-0.1, .015)), (-0.3, f.bz(-0.3, .012)), lambda t: -120 - 40 * t,
          lambda t: 0.11 - 0.03 * t, soft, rays=10, curl=10, stack=0.006)
    f.fin('caudal', (-0.37, -0.04), (-0.37, 0.04), lambda t: 210 - 60 * t, lambda t: 0.16 + 0.02 * np.sin(np.pi * t),
          finpaint('#ecdccc', None, (0.4, 0.2), rays=14, seed=24, mark='#5a2010',
                   spots=lambda T, V, X, Z: smooth(0.6, 0.66, noise(T * 16, V * 12, 1, 2, 25))), rays=14)
    # the big feathery pectoral fans: rays standing free past a banded web
    fan = finpaint('#e8d4c0', None, (0.4, 0.12), rays=16, spots=band(12), mark='#7a2414', ray_alpha=1.0, ray_w=0.14, seed=26,
                   spiny=True)
    side_fin(f, 'pect', 0.66, 0.22, lambda t: 235 - 75 * t, lambda t: 0.26 + 0.06 * np.sin(np.pi * t), fan, rays=16,
             rows=12, size=0.06, splay=0.75, drop=0.0, flap=0.25, ripple=0.01)
    side_fin(f, 'pelvic', 0.62, 0.06, lambda t: 250 - 20 * t, lambda t: 0.12, fan, splay=0.4, drop=-0.8, size=0.03,
             flap=0.15, rays=7)
    xs = 0.3
    for sign in (-1, 1):  # little feathery tentacles over the eyes and on the chin
        z0 = f.tz(xs, 0.01)
        f.tube(f'brow{sign}', [(xs, sign * 0.025, z0), (xs + 0.01, sign * 0.035, z0 + 0.04), (xs - 0.005, sign * 0.04, z0 + 0.075)],
               0.007, 0.002, '#d8c0a8', wiggle=0.008)
    f.eye(0.82, 0.38, 0.05, rim='#ecdcc8')
    f.lips((0.38, 0, f.zc(0.35) - 0.01), 0.024, '#c89a88')
    return f


def discus():
    f = Fish('discus', px=88, amp=0.03, iris='#c03018')
    top = curve([(0, .045), (.1, .085), (.3, .24), (.55, .3), (.8, .25), (.95, .13), (1, .04)])
    bot = curve([(0, -.045), (.1, -.085), (.3, -.23), (.55, -.29), (.8, -.24), (.95, -.12), (1, -.03)])
    wid = curve([(0, .015), (.3, .05), (.6, .068), (.85, .055), (1, .028)])

    def lines(X, Z, s):  # wormy branching turquoise lines of varying width, some broken off
        wx = X + 0.06 * (noise(X * 5, Z * 5, 1, 3, s + 2) - 0.5)
        wz = Z + 0.06 * (noise(X * 5 + 9, Z * 5, 1, 3, s + 3) - 0.5)
        v = noise(wx * 7, wz * 9, 1, 3, s) * 9
        w = 0.1 + 0.12 * noise(X * 9, Z * 9, 1, 2, s + 4)
        line = smooth(w, w * 0.4, np.abs(v - np.round(v)))
        return line * smooth(0.28, 0.4, noise(X * 11, Z * 11, 1, 2, s + 1))

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y, 1, 3, 27)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#d8682a')
        mix(col, '#d8702a', smooth(0.4, 0.7, noise(X * 5, Z * 5, 1, 2, 26)) * 0.4)
        mix(col, '#50d0d0', lines(X, Z, 28) * 0.9)
        bars = sum(smooth(0.016, 0.006, np.abs(X - c + 0.01 * Z)) for c in np.linspace(-0.26, 0.26, 9))
        mix(col, '#3a1408', np.clip(bars, 0, 1) * 0.12)           # faint stress bars
        for c, k in ((0.235, 0.5), (-0.27, 0.45)):                # dark bars: through the eye, at the tail root
            mix(col, '#2a0e06', smooth(0.03, 0.012, np.abs(X - c + 0.02 * Z + (n - 0.5) * 0.04 + 0.008 * np.sin(Z * 30))) * k)
        mid, half = (top(U) + bot(U)) / 2, (top(U) - bot(U)) / 2
        mix(col, col * 0.7, smooth(0.6, 1.0, np.abs(Z - mid) / half) * 0.5)  # darker toward the rim: reads round
        d = np.hypot(X - 0.24, Z * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - 0.1)) * (np.abs(Z) < 0.1)
        mix(col, col * 0.7, gill * 0.5)
        sc = scales(X, Z, 0.012, head=0.14)
        return col, 0.12 * sc + 0.3 * (d < 0.1) + 0.3 * gill, 0.4 + 0.1 * n, 0.4 * lines(X, Z, 28)

    f.body(-0.33, 0.33, top, bot, wid, paint, nose=0.08, q=0.92, sss=0.15, film=360, head=0.14)
    U = lambda x: (x + 0.33) / 0.66  # noqa: E731
    edge = finpaint('#a8441c', None, (0.9, 0.7), [(0.84, 0.92, '#4a1408', 0.9), (0.92, 1.1, '#62d0d4', 0.7)], rays=30, seed=29,
                    spots=lambda T, V, X, Z: lines(X, Z, 28) * 0.7, mark='#3ab4b8')
    # dorsal and anal follow the round outline from the forehead to the tail root
    f.fin('dorsal', (0.16, 0), (-0.3, 0), lambda t: 88 + 80 * t, lambda t: 0.06 + 0.035 * np.sin(np.pi * t),
          edge, rays=30, curl=-10, stack=-0.006,
          path=lambda T: (0.16 - 0.46 * T, top(U(0.16 - 0.46 * T)) - 0.015))
    f.fin('anal', (0.08, 0), (-0.3, 0), lambda t: -92 - 76 * t, lambda t: 0.055 + 0.035 * np.sin(np.pi * t),
          edge, rays=26, curl=10, stack=0.006,
          path=lambda T: (0.08 - 0.38 * T, bot(U(0.08 - 0.38 * T)) + 0.015))
    f.fin('caudal', (-0.32, -0.035), (-0.32, 0.035), lambda t: 210 - 60 * t, lambda t: 0.12 + 0.01 * np.sin(np.pi * t),
          finpaint('#b0603a', '#d08860', (0.6, 0.35), rays=16, seed=30), rays=16)
    side_fin(f, 'pect', 0.72, 0.24, lambda t: 195 - 30 * t, lambda t: 0.07, finpaint('#e8d0c0', None, (0.3, 0.12), rays=10),
             rays=10, size=0.03)
    side_fin(f, 'pelvic', 0.66, 0.06, lambda t: 250 - 20 * t, lambda t: 0.09, finpaint('#c04020', '#f0d040', (0.85, 0.7), rays=6),
             splay=0.3, drop=-0.8, size=0.02, flap=0.15, rays=6)
    f.eye(0.86, 0.38, 0.042, rim='#9a3a18')
    f.lips((0.335, 0, f.zc(0.31) - 0.004), 0.016, '#b04a1c')
    return f


def guppy():
    f = Fish('guppy', px=50, amp=0.06, iris='#26261c')
    top = curve([(0, .04), (.2, .05), (.5, .09), (.8, .085), (.93, .06), (1, .025)])
    bot = curve([(0, -.04), (.2, -.05), (.5, -.1), (.75, -.095), (.9, -.06), (1, -.02)])
    wid = curve([(0, .02), (.3, .04), (.6, .05), (.85, .045), (1, .03)])

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 3, 31)
        mid = (top(U) + bot(U)) / 2
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#9aa090')
        mix(col, '#e2e6e0', smooth(mid - 0.01, mid - 0.06, Z) * 0.85)   # silver belly
        sd = np.where(Y >= 0, 0, 7)  # each flank its own patches, like a real male
        orange = smooth(0.55, 0.62, noise(X * 7 + sd, Z * 7, 1, 2, 32)) * smooth(0.2, 0.05, X)
        mix(col, '#ee6a1c', orange * 0.9)
        black = smooth(0.016, 0.01, np.hypot(X + 0.08 + 0.03 * (sd > 0), Z - mid - 0.01))
        mix(col, '#121212', black)
        blue = smooth(0.6, 0.66, noise(X * 6 + sd, Z * 6, 1, 2, 33)) * smooth(0.15, 0.0, X)
        mix(col, '#3a9cb4', blue * 0.8)
        sc = scales(X, Z, 0.02, head=0.2, mid=mid)
        d = np.hypot(X - 0.3, (Z - mid) * 0.9)
        gill = smooth(0.01, 0.0, np.abs(d - 0.09)) * (np.abs(Z - mid) < 0.07)
        mix(col, col * 0.75, gill * 0.5)
        return col, 0.2 * sc + 0.3 * (d < 0.09) + 0.2 * gill, 0.35 + 0.1 * n, np.clip(blue + 0.3, 0, 1)

    f.body(-0.3, 0.3, top, bot, wid, paint, nose=0.12, film=460, sss=0.35, head=0.2)
    spots = lambda s: lambda T, V, X, Z: smooth(0.6, 0.66, noise(T * 18, V * 10, 1, 2, s)) * smooth(0.15, 0.4, V)  # noqa: E731
    tail = finpaint('#f07a2a', '#e83a22', (0.85, 0.75), [(0.55, 0.7, '#3a7cd0', 0.85)], rays=28, seed=34,
                    spots=spots(35), mark='#141414', film=0.6)
    f.fin('caudal', (-0.29, -0.035), (-0.29, 0.035), lambda t: 232 - 104 * t,
          lambda t: 0.42 + 0.05 * np.sin(np.pi * t), tail, rays=28, rows=12, pleat=0.004, ripple=0.02, film=400)
    f.fin('dorsal', (0.02, f.tz(0.02, .01)), (-0.14, f.tz(-0.14, .01)), lambda t: 130 + 40 * t,
          lambda t: 0.12 + 0.12 * t, finpaint('#a0b0a0', '#ee7a3a', (0.7, 0.5), rays=12, spots=spots(36), mark='#141414', seed=37),
          rays=12, curl=-12, ripple=0.015, stack=-0.006)
    f.fin('anal', (-0.05, f.bz(-0.05, .01)), (-0.15, f.bz(-0.15, .01)), lambda t: -130 - 30 * t, lambda t: 0.07,
          finpaint('#c8d0c8', None, (0.4, 0.2), rays=7), rays=7, curl=8, stack=0.006)
    side_fin(f, 'pect', 0.72, 0.22, lambda t: 195 - 35 * t, lambda t: 0.06, finpaint('#dde6e6', None, (0.3, 0.12), rays=8),
             rays=8, size=0.025, flap=0.6)
    f.eye(0.86, 0.36, 0.052, rim='#8a9a8a')
    f.lips((0.3, 0, f.zc(0.27) + 0.004), 0.013, '#9aa090')
    return f


def pleco():
    f = Fish('pleco', px=124, amp=0.04, iris='#8a6a30')
    top = curve([(0, .03), (.15, .045), (.4, .1), (.6, .13), (.8, .12), (.93, .075), (1, .025)])
    bot = curve([(0, -.03), (.15, -.035), (.4, -.06), (.7, -.07), (.9, -.06), (1, -.03)])
    wid = curve([(0, .02), (.3, .07), (.6, .105), (.85, .115), (1, .07)])
    base = '#6a5034'

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y, 1, 3, 40)
        mid = (top(U) + bot(U)) / 2
        col = np.zeros(X.shape + (3,))
        col[:] = hexc(base)
        mix(col, '#9c8460', smooth(mid - 0.01, mid - 0.06, Z))        # paler underside
        cells = noise(X * 22, Z * 22 + Y * 9, 1, 2, 41)
        mix(col, '#22180e', smooth(0.42, 0.36, np.abs(cells - 0.5) * 2 + 0.25) * 0.85)  # dark reticulated spots
        mix(col, '#a08a62', smooth(0.66, 0.74, noise(X * 30, Z * 30 + Y * 9, 1, 2, 42)) * 0.5)  # pale freckles
        k = (X - 0.2 * np.abs(Z - mid)) / 0.035                      # rows of bony plates
        groove = smooth(0.08, 0.0, np.abs(k - np.round(k))) * (X < 0.22)
        keel = smooth(0.008, 0.0, np.abs(Z - mid - 0.02))
        mix(col, col * 0.6, np.clip(groove + keel, 0, 1) * 0.7)
        return col, 0.4 * (k - np.floor(k)) * (X < 0.22) + 0.2 * cells, 0.62 + 0.1 * n, 0 * X

    f.body(-0.4, 0.4, top, bot, wid, paint, nose=0.1, q=0.75, sss=0.05, bump=0.7, head=0.22)
    spotted = lambda s, b='#7a603e': finpaint(b, None, (0.85, 0.6), rays=12, seed=s, mark='#1e140a',  # noqa: E731
                                              spots=lambda T, V, X, Z: smooth(0.58, 0.64, noise(T * 16, V * 12, 1, 2, s)))
    f.fin('sail', (0.16, f.tz(0.16, .015)), (-0.06, f.tz(-0.06, .015)), lambda t: 100 + 50 * t,
          lambda t: 0.26 - 0.12 * t, spotted(43), rays=10, curl=-14, ripple=0.008, stack=-0.006)
    f.fin('adipose', (-0.24, f.tz(-0.24, .01)), (-0.3, f.tz(-0.3, .01)), lambda t: 130 + 30 * t, lambda t: 0.035,
          spotted(44), rays=5)
    f.fin('anal', (-0.12, f.bz(-0.12, .012)), (-0.2, f.bz(-0.2, .012)), lambda t: -130 - 30 * t, lambda t: 0.06,
          spotted(45), rays=6, stack=0.006)
    f.fin('caudal', (-0.39, -0.03), (-0.39, 0.03), lambda t: 218 - 76 * t,
          lambda t: 0.15 + 0.12 * np.abs(2 * t - 1) ** 1.5 + 0.04 * (1 - t), spotted(46), rays=18, pleat=0.004)
    # broad flat pectorals and pelvics with a thick first ray
    side_fin(f, 'pect', 0.76, 0.12, lambda t: 200 - 35 * t, lambda t: 0.16 - 0.04 * t, spotted(47), rays=9, size=0.04,
             splay=0.9, drop=-0.15, flap=0.25)
    side_fin(f, 'pelvic', 0.48, 0.08, lambda t: 210 - 25 * t, lambda t: 0.12, spotted(48), rays=7, size=0.035,
             splay=0.9, drop=-0.2, flap=0.15)
    f.eye(0.83, 0.43, 0.036, rim=base, toe=10, gloss=0.25)
    f.lips((0.36, 0, f.bz(0.36, 0.02) - 0.004), 0.04, '#9c8460', down=True, thick=0.35, shade=0.9)  # sucker mouth
    return f


def mandarin():
    f = Fish('mandarin', px=62, amp=0.045, iris='#b8401a')
    top = curve([(0, .045), (.2, .065), (.5, .13), (.75, .15), (.92, .11), (1, .04)])
    bot = curve([(0, -.04), (.2, -.05), (.5, -.09), (.75, -.11), (.92, -.08), (1, -.03)])
    wid = curve([(0, .025), (.3, .07), (.6, .1), (.85, .1), (1, .06)])

    def maze(X, Z, s):  # wavy orange lines with dark borders over blue-green
        v = noise(X * 5, Z * 5, 1, 3, s) * 7 + noise(X * 11, Z * 11, 1, 2, s + 1) * 1.5
        f_ = np.abs(v - np.floor(v) - 0.5)
        return smooth(0.17, 0.12, f_), smooth(0.24, 0.18, f_)

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y, 1, 3, 50)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#1d58b8')
        mix(col, '#2aa08a', smooth(0.45, 0.65, noise(X * 3, Z * 3 + Y, 1, 2, 51)) * 0.6)
        line, rim = maze(X, Z + Y * 0.5, 52)
        mix(col, '#1a1630', rim)
        mix(col, '#ee7418', line)
        face = smooth(0.18, 0.26, X)  # orange-striped face
        mix(col, '#ee7418', face * smooth(0.5, 0.75, np.abs(np.sin(Z * 70 + X * 20))) * 0.8)
        return col, 0.2 * rim - 0.1 * line, 0.42 + 0.1 * n, 0.4 * (1 - rim)

    f.body(-0.32, 0.32, top, bot, wid, paint, nose=0.12, q=0.9, sss=0.15, film=380, head=0.18)
    fin_maze = lambda s: lambda T, V, X, Z: maze(X, Z, s)[1] * 0.8  # noqa: E731
    f.fin('dorsal1', (0.08, f.tz(0.08, .012)), (0.0, f.tz(0.0, .012)), lambda t: 95 + 30 * t, lambda t: 0.16 - 0.05 * t,
          finpaint('#ee8a2a', '#2a62c8', (0.85, 0.6), rays=4, spots=fin_maze(53), mark='#1a1630', seed=54), rays=4, curl=-15)
    soft = finpaint('#2a62c8', None, (0.85, 0.6), [(0.85, 1.1, '#ee8a2a', 0.85)], rays=14, spots=fin_maze(55), mark='#ee7418', seed=56)
    f.fin('dorsal2', (-0.03, f.tz(-0.03, .012)), (-0.27, f.tz(-0.27, .012)), lambda t: 120 + 40 * t,
          lambda t: 0.1 - 0.02 * t, soft, rays=14, curl=-10, stack=-0.006)
    f.fin('anal', (-0.04, f.bz(-0.04, .012)), (-0.27, f.bz(-0.27, .012)), lambda t: -120 - 40 * t,
          lambda t: 0.09 - 0.02 * t, soft, rays=12, curl=10, stack=0.006)
    f.fin('caudal', (-0.31, -0.04), (-0.31, 0.04), lambda t: 215 - 70 * t, lambda t: 0.15 + 0.02 * np.sin(np.pi * t),
          finpaint('#2a62c8', '#ee8a2a', (0.85, 0.7), rays=16, spots=fin_maze(57), mark='#ee7418', seed=58), rays=16)
    side_fin(f, 'pect', 0.68, 0.24, lambda t: 190 - 40 * t, lambda t: 0.11 + 0.02 * np.sin(np.pi * t),
             finpaint('#e8d8a8', None, (0.45, 0.2), rays=12), rays=12, size=0.05, flap=0.9)
    side_fin(f, 'pelvic', 0.72, 0.06, lambda t: 235 - 25 * t, lambda t: 0.1, finpaint('#ee7418', '#2a62c8', (0.9, 0.8), rays=6),
             splay=0.5, drop=-0.5, size=0.03, flap=0.2, rays=6)
    f.eye(0.82, 0.45, 0.06, rim='#1d58b8', out=0.4)
    f.lips((0.33, 0, f.zc(0.3) - 0.012), 0.014, '#ee7418')
    return f


SPECIES = {'clown': clown, 'tetra': tetra, 'angel': angel, 'goldfish': goldfish, 'tang': tang, 'puffer': puffer,
           'cory': cory, 'betta': betta, 'lionfish': lionfish, 'discus': discus, 'guppy': guppy, 'pleco': pleco,
           'mandarin': mandarin,
           # colour morphs: same shape, own sheet `<species>-<morph>`
           'cory-albino': lambda: cory('albino'), 'betta-koi': lambda: betta('koi'), 'angel-gold': lambda: angel('gold')}


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    pv = None
    if '--preview' in argv:
        i = argv.index('--preview')
        pv = argv[i + 1]
        del argv[i:i + 2]
    eyes = '--eyes' in argv
    argv = [a for a in argv if a != '--eyes']
    bad = [a for a in argv if a not in SPECIES]
    if bad:
        sys.exit(f'fish.py: unknown species {bad}; choose from {list(SPECIES)}')
    for n in argv or SPECIES:
        run(n, pv, eyes)
