# Fish sprite sheets. Each species is modeled from numpy-built meshes (lofted body, fanned fins
# with real rays, eyes, lips, barbels, spikes) with numpy-painted textures, swum with a sine
# body wave, and rendered with Cycles as swim-cycle frames x yaw angles (profile -> front; the
# runtime mirrors the other half). Writes assets/<name>.png + its manifest entry (+ puffer -puff).
# Run: ~/opt/blender/blender -b --factory-startup -P blender/fish.py -- [species ...] [--preview DIR]
import math
import os
import sys
import tempfile

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TAU = 2 * math.pi
FRAMES = 12                  # swim cycle frames (one tail beat cycle)
YAWS = [0, 25, 50, 70, 90]   # degrees turned toward the viewer
PUFFS = 4                    # puffer inflation steps
SAMPLES = 160
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


def scales(X, Z, size, seed=0):
    """Overlapping fish scales seen from the side: returns height 0..1 rising toward each free edge."""
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


def material(name, col, dat, alpha=False, sss=0.12, coat=0.25, film=0.0, sheen=0.0, bump=0.4, metal=0.0):
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
    bsdf.inputs['Coat Roughness'].default_value = 0.12
    bsdf.inputs['Sheen Weight'].default_value = sheen
    bsdf.inputs['Metallic'].default_value = metal
    return m


def flat_material(name, color, rough=0.3, coat=0.0, sss=0.0, emit=0.0):
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
    def body(self, x0, x1, top, bot, wid, paint, nose=0.1, q=1.0, tex=(1024, 512), **mat):
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
            flap=0.0, ripple=0.0, hinge=None, solid=0.004, tex=256, **mat):
        T = np.linspace(0, 1, rays)
        V = np.linspace(0, 1, rows + 1)
        p0, p1 = np.array(p0, float), np.array(p1, float)
        root = p0 + (p1 - p0) * T[:, None]
        a = np.radians(ang(T) + 0 * T)[:, None] + np.radians(curl) * V[None, :]
        step = ((ln(T) + 0 * T) / rows)[:, None]
        dx = np.concatenate([np.zeros((rays, 1)), np.cumsum(np.cos(a[:, :-1]) * step, 1)], 1)
        dz = np.concatenate([np.zeros((rays, 1)), np.cumsum(np.sin(a[:, :-1]) * step, 1)], 1)
        fold = pleat * np.where(np.arange(rays) % 2, 1, -1)[:, None] * np.sqrt(V)[None, :]
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
        rgba, height, rough = paint(tt, tv, XYZ[..., 0], XYZ[..., 2])
        col = rgba
        dat = np.stack([height, rough, np.zeros_like(rough)], -1)
        m = material(f'{self.name}-{name}', image(f'{self.name}-{name}c', col), image(f'{self.name}-{name}d', dat, True),
                     alpha=True, **{'sss': 0.35, 'coat': 0.1, 'bump': 0.25, **mat})
        vv = np.repeat(V[None, :], rays, 0).ravel()
        if hinge is None:
            hinge = (P[0, 0], P[-1, 0])
        return self.add(name, v, f, uv, m, sub=1, solid=solid, v=vv, flap=flap, ripple=ripple,
                        hinge=np.array(hinge, float), t=np.repeat(T, rows + 1))

    def eye(self, u, side, r, toe=25, rim='#203040', sclera='#f4f1e6', out=0.6):
        """Pair of eyeballs on the head (out = fraction sticking out), turned forward by toe degrees
        so both show from the front. The pupil is not modeled: the runtime draws it."""
        p, n = self.at(u, side)
        t = math.radians(toe)
        for sign in (-1, 1):
            pp = np.array([p[0], sign * abs(p[1]), p[2]])
            nn = np.array([n[0], sign * abs(n[1]), n[2]]) * math.cos(t) + np.array([math.sin(t), 0, 0])
            nn /= np.linalg.norm(nn)
            ctr = pp + nn * r * (out * 2 - 1)

            def ball(U, V, ctr=ctr):
                th, ph = U * math.pi, V * TAU
                return ctr[0] + r * np.cos(th), ctr[1] + r * np.sin(th) * np.cos(ph), ctr[2] + r * np.sin(th) * np.sin(ph)
            v, f, uv, _ = surface(ball, 16, 24)
            self.add(f'eye{sign}', v, f, uv, flat_material(self.name + '-sclera', sclera, rough=0.08, coat=1.0, sss=0.2), sub=1)
            # socket rim: a fleshy ring around the ball
            k = np.cross(nn, [0, 0, 1])
            k = k / (np.linalg.norm(k) or 1)
            j = np.cross(nn, k)

            def ring(U, V, ctr=ctr, nn=nn, k=k, j=j):
                a, b = U * TAU, V * TAU
                R = r * 1.02 + r * 0.16 * np.cos(b)
                d = r * 0.16 * np.sin(b) + r * (out * 2 - 1) * 0.6
                return tuple(ctr[i] + R * (np.cos(a) * k[i] + np.sin(a) * j[i]) + d * nn[i] for i in range(3))
            v, f, uv, _ = surface(ring, 32, 10, wrap_u=True)
            self.add(f'rim{sign}', v, f, None, flat_material(self.name + '-rim', rim, rough=0.45, sss=0.2), sub=1)
            self.eyes.append((ctr + nn * r, nn, r, f'eye{sign}'))

    def lips(self, c, r, color, open_=0.5, thick=0.35):
        """Puckered O-mouth ring at c facing +X with a dark throat; gulps with the swim cycle."""
        c = np.array(c, float)

        def ring(U, V):
            a, b = U * TAU, V * TAU
            R = r + r * thick * np.cos(b)
            return c[0] + r * thick * np.sin(b) * 1.2, c[1] + R * np.cos(a), c[2] + R * np.sin(a) * 0.8
        v, f, uv, _ = surface(ring, 32, 12, wrap_u=True)
        self.add('lips', v, f, None, flat_material(self.name + '-lips', color, rough=0.35, coat=0.4, sss=0.4), sub=1,
                 mouth=c, gape=open_)

        def throat(U, V):
            th, ph = U * math.pi, V * TAU
            return c[0] - r * 0.2 + r * 0.5 * np.cos(th) * 0.5, c[1] + r * 0.95 * np.sin(th) * np.cos(ph), c[2] + r * 0.8 * np.sin(th) * np.sin(ph)
        v, f, uv, _ = surface(throat, 8, 16)
        self.add('throat', v, f, None, flat_material(self.name + '-throat', '#2a0c10', rough=0.6), sub=1, mouth=c, gape=open_)

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
                co[:, 1] += part['ripple'] * part['v']**1.5 * np.sin(TAU * ph * 2 - part['t'] * 9 - part['v'] * 3)
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

def world_points(fish, ph, puff, yaw):
    pts = np.concatenate([fish.deform(p['rest'], ph, puff, p) for p in fish.parts])
    c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
    return np.stack([pts[:, 0] * c - pts[:, 1] * s, pts[:, 0] * s + pts[:, 1] * c, pts[:, 2]], -1)


def frame_box(fish, ppm, puffs):
    lo, hi = np.full(2, 1e9), np.full(2, -1e9)
    for yaw in YAWS:
        for ph in (0, 0.25, 0.5, 0.75):
            for pf in puffs:
                w = world_points(fish, ph, pf, yaw)[:, [0, 2]]
                lo, hi = np.minimum(lo, w.min(0)), np.maximum(hi, w.max(0))
    pad = 2 / ppm
    lo, hi = lo - pad, hi + pad
    W, H = int(math.ceil((hi[0] - lo[0]) * ppm)), int(math.ceil((hi[1] - lo[1]) * ppm))
    return (lo + hi) / 2, W, H


def render_sheet(fish, ppm, tag, puffs, phases, tmp, preview=None):
    s = bpy.context.scene
    ctr, W, H = frame_box(fish, ppm, puffs)
    cam = common.camera(W / ppm, W, H, z=ctr[1])
    cam.location.x = ctr[0]
    cols = len(phases) * len(puffs)
    sheet = np.zeros((len(YAWS) * H, cols * W, 4), np.float32)
    eyes = []
    path = os.path.join(tmp, 'f.png')
    for yi, yaw in enumerate(YAWS):
        fish.root.rotation_euler = (0, 0, math.radians(-yaw))
        row = []
        for ci, (pf, ph) in enumerate((pf, ph) for pf in puffs for ph in phases):
            fish.pose(ph, pf)
            bpy.context.view_layer.update()
            s.render.filepath = path
            bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(path)
            a = np.empty(W * H * 4, np.float32)
            im.pixels.foreach_get(a)
            bpy.data.images.remove(im)
            sheet[yi * H:(yi + 1) * H, ci * W:(ci + 1) * W] = a.reshape(H, W, 4)[::-1]
            row.append(eye_info(fish, ph, pf, yaw, ctr, W, H, ppm))
        eyes.append(row)
    anchor = [round((0 - ctr[0]) * ppm + W / 2, 2), round(H / 2 + (ctr[1] - 0) * ppm, 2)]
    if preview:
        return sheet, W, H
    out = os.path.join(common.ASSETS, f'{tag}.png')
    im = bpy.data.images.new(tag, sheet.shape[1], sheet.shape[0], alpha=True)
    im.pixels.foreach_set(sheet[::-1].ravel())
    im.filepath_raw = out
    im.file_format = 'PNG'
    im.save()
    # rows = yaws, cols = frames; eyes flattened row-major so eyes[i] belongs to frame i
    return dict(w=W, h=H, cols=cols, n=cols * len(YAWS), anchor=anchor, eyes=[e for r in eyes for e in r])


def eye_info(fish, ph, puff, yaw, ctr, W, H, ppm):
    """Where the pupil overlay goes in this frame: [[x, y, r, squash], ...] for each visible eye."""
    out = []
    dg = bpy.context.evaluated_depsgraph_get()
    c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
    rot = lambda p: np.array([p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]])  # noqa: E731
    for front, n, r, obname in fish.eyes:
        pts = fish.deform(np.array([front, front - n * r]), ph, puff)
        P, Q = rot(pts[0]), rot(pts[1])
        nn = (P - Q) / np.linalg.norm(P - Q)
        facing = -nn[1]
        if facing < 0.1:
            continue
        # visible if a ray through the ball's centre meets the ball (or its rim) first; a ray
        # through the front point would only graze the ball when it's seen side-on
        hit, _, _, _, ob, _ = bpy.context.scene.ray_cast(dg, (Q[0], -50, Q[2]), (0, 1, 0))
        if not hit or ob.name not in (obname, obname.replace('eye', 'rim')):
            continue
        x = (P[0] - ctr[0]) * ppm + W / 2
        y = H / 2 - (P[2] - ctr[1]) * ppm
        out.append([round(x, 2), round(y, 2), round(r * ppm, 2), round(float(facing), 3)])
    return out


def build(name):
    common.reset(SAMPLES)
    key, fill, rim = common.lights()
    fill.data.energy = 110  # less flat than the shared fill so bodies read round
    key.data.energy = 4.5
    s = bpy.context.scene
    s.cycles.pixel_filter_width = 1.2
    s.view_settings.exposure = 0.5  # small bright subjects against dark water: lift them a touch
    fish = SPECIES[name]()
    fish.finish()
    return fish


def run(name, preview=None):
    fish = build(name)
    rest = np.concatenate([p['rest'] for p in fish.parts])
    ppm = fish.px * SIZE / (rest[:, 0].max() - rest[:, 0].min())
    with tempfile.TemporaryDirectory() as tmp:
        if preview:  # big stills at a few yaws for looking at the model
            global YAWS
            keep, YAWS = YAWS, [0, 30, 60, 90]
            sheet, W, H = render_sheet(fish, ppm * 4, name, [0.0], [0.0, 0.3], tmp, preview=True)
            YAWS = keep
            im = bpy.data.images.new('pv', sheet.shape[1], sheet.shape[0], alpha=True)
            im.pixels.foreach_set(sheet[::-1].ravel())
            im.filepath_raw = os.path.join(preview, f'{name}.png')
            im.file_format = 'PNG'
            im.save()
            return
        man = dict(iris=fish.iris, yaws=YAWS, len=round(fish.px * SIZE))
        man.update(render_sheet(fish, ppm, name, [0.0], [i / FRAMES for i in range(FRAMES)], tmp))
        if fish.inflate:
            man['puff'] = name + '-puff'
            common.manifest(name + '-puff', render_sheet(fish, ppm, name + '-puff', [i / (PUFFS - 1) for i in range(PUFFS)], [0.0], tmp))
    common.manifest(name, man)
    print(f'fish: {name} {man["w"]}x{man["h"]} x {man["cols"]} x {len(YAWS)}')


# ---------- species ----------

def finpaint(base, tip=None, alpha=(0.8, 0.5), bands=(), rays=24, rough=0.35, spots=None, seed=0, mark='#1a1410'):
    """Fin texture: base colour fading to tip, (v0, v1, colour, alpha) bands across the rays,
    darker opaque rays, optional spots(T, V) mask, and a ragged worn trailing edge."""
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
        if spots is not None:
            m = spots(T, V, X, Z)
            mix(col, mark, m * 0.85)
            a = np.maximum(a, m * 0.85)
        ray = (1 - np.abs(np.sin(np.pi * T * (rays - 1)))) ** 5
        mix(col, col * 0.62, ray * 0.6)
        a = np.clip(a + ray * 0.25 * (1 - V * 0.5), 0, 1)
        edge = smooth(1.0, 0.92 - 0.07 * noise(T * 9, V, 1, 3, seed), V)
        a *= edge
        return np.concatenate([col, a[..., None]], -1), ray * 0.8 + noise(T * 20, V * 6, 1, 3, seed) * 0.2, rough + 0 * T
    return paint


def side_fin(fish, name, u, side, rays_ang, ln, paint, splay=0.45, drop=0.15, size=0.05, flap=0.45, **kw):
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
        fish.fin(f'{name}{sign}', (0, -size / 2), (0, size / 2), rays_ang, ln, paint, M=M, O=p - np.array([0, 0, 0]),
                 flap=flap * sign, **kw)


def clown():
    f = Fish('clown', px=82, amp=0.055, iris='#d0601a')
    top = curve([(0, .055), (.12, .07), (.35, .155), (.55, .19), (.75, .175), (.9, .12), (1, .04)])
    bot = curve([(0, -.055), (.12, -.07), (.35, -.14), (.55, -.165), (.75, -.15), (.9, -.09), (1, -.035)])
    wid = curve([(0, .025), (.2, .05), (.5, .095), (.75, .105), (.9, .085), (1, .05)])

    def paint(X, Y, Z, U):
        n = noise(X * 3, Z * 3 + Y, 4)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#f46a12')
        mix(col, '#f8963a', smooth(-0.04, -0.16, Z) * 0.7)       # paler belly
        mix(col, '#c94a10', smooth(0.06, 0.19, Z) * 0.5)        # deeper back
        mix(col, '#f27d24', (noise(X * 14, Z * 14, 1, 3, 2) - 0.5).clip(0) * 0.8)  # mottling
        bands = [
            (0.17 + 0.09 * (Z / 0.17) ** 2, 0.042),              # head band, curving forward
            (-0.05 + 0.055 * np.exp(-(Z / 0.06) ** 2) - 0.02 * (Z / 0.17) ** 2, 0.04),  # mid band, forward bulge
            (-0.355, 0.02),                                      # tail band
        ]
        white = np.zeros(X.shape)
        for xc, w in bands:
            d = np.abs(X - xc + (n - 0.5) * 0.025)
            mix(col, '#151214', smooth(w + 0.026, w + 0.014, d))
            m = smooth(w + 0.004, w - 0.004, d)
            mix(col, '#f6f2ea', m)
            white += m
        sc = scales(X, Z, 0.02)
        gx, gz, R = 0.33, -0.005, 0.12
        d = np.hypot(X - gx, (Z - gz) * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - R)) * (X < gx) * (np.abs(Z - gz) < 0.13)
        mix(col, col * 0.75, gill * 0.6)
        height = 0.15 * sc + 0.4 * (d < R) + 0.3 * gill
        rough = 0.42 + 0.12 * n - 0.1 * white.clip(0, 1)
        return col, height, rough, 0 * X

    f.body(-0.42, 0.42, top, bot, wid, paint, nose=0.13, q=0.95, sss=0.15)
    tz, bz, zc = f.tz, f.bz, f.zc
    edged = finpaint('#ef6a1c', '#f08030', (0.85, 0.7), [(0.74, 0.88, '#141012', 0.95), (0.88, 1.1, '#f4f0e6', 0.8)])
    f.fin('dorsal1', (0.15, tz(0.15) - 0.02), (-0.03, tz(-0.03) - 0.02), lambda t: 95 + 35 * t,
          lambda t: 0.06 + 0.035 * np.sin(np.pi * t) + 0.01 * np.sin(np.pi * t * 8), edged, rays=10)
    f.fin('dorsal2', (-0.03, tz(-0.03) - 0.02), (-0.30, tz(-0.30) - 0.015), lambda t: 110 + 55 * t,
          lambda t: 0.06 + 0.07 * np.sin(np.pi * (0.1 + 0.85 * t)), edged, rays=16, curl=-15)
    f.fin('anal', (-0.06, bz(-0.06) + 0.02), (-0.30, bz(-0.30) + 0.015), lambda t: -110 - 55 * t,
          lambda t: 0.05 + 0.07 * np.sin(np.pi * (0.1 + 0.85 * t)), edged, rays=14, curl=15)
    f.fin('caudal', (-0.405, -0.045), (-0.405, 0.045), lambda t: 208 - 56 * t,
          lambda t: 0.19 + 0.035 * np.sin(np.pi * t), edged, rays=26, curl=0, pleat=0.008, ripple=0.01)
    pect = finpaint('#f07a28', '#f8a050', (0.75, 0.45), [(0.8, 1.1, '#1a1214', 0.85)], rays=14)
    side_fin(f, 'pect', 0.68, 0.2, lambda t: 200 - 40 * t, lambda t: 0.08 + 0.025 * np.sin(np.pi * t), pect, rays=14)
    side_fin(f, 'pelvic', 0.66, 0.08, lambda t: 240 - 25 * t, lambda t: 0.06 + 0.01 * t, pect, splay=0.3, drop=-0.6, size=0.03,
             flap=0.2, rays=8)
    f.eye(0.86, 0.36, 0.045, rim='#b8461a')
    f.lips((0.425, 0, zc(0.38) - 0.012), 0.03, '#f28c76')
    return f



def bars(xs, w, lean=0.02):
    """Fin marks continuing the body's vertical bars out across the fin."""
    def m(T, V, X, Z):
        x = X + lean * Z + 0.005 * np.sin(Z * 40)
        return np.clip(sum(smooth(w + 0.01, w - 0.005, np.abs(x - c)) for c in xs), 0, 1)
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
        col[:] = hexc('#8f9a80')                                   # olive translucent back
        mix(col, '#e9eef0', smooth(mid - 0.01, mid - 0.06, Z))     # silver belly
        sz = mid + 0.022 - 0.01 * (X - 0.1)                        # neon stripe line
        stripe = smooth(0.02, 0.012, np.abs(Z - sz)) * smooth(0.36, 0.3, X) * smooth(-0.34, -0.28, X)
        red = smooth(sz - 0.012, sz - 0.03, Z) * smooth(0.1, 0.0, X)
        mix(col, '#e3132e', red)
        mix(col, '#5d6a52', smooth(sz + 0.02, sz + 0.05, Z) * 0.6)  # darker dorsal edge
        mix(col, '#27ddff', stripe)
        sc = scales(X, Z, 0.022)
        gx, R = 0.3, 0.1
        d = np.hypot(X - gx - R, (Z - mid) * 0.9)
        gill = smooth(0.01, 0.0, np.abs(d - R)) * (np.abs(Z - mid) < 0.08)
        mix(col, col * 0.75, gill * 0.5)
        film = np.clip(stripe * 1.0 + 0.25 * smooth(mid - 0.01, mid - 0.05, Z), 0, 1)
        return col, 0.2 * sc + 0.3 * (d < R) + 0.2 * gill, 0.3 + 0.1 * n - 0.15 * stripe, film

    f.body(-0.4, 0.4, top, bot, wid, paint, nose=0.12, film=480, sss=0.3, coat=0.35)
    clear = finpaint('#d4e0e4', '#eef4f6', (0.4, 0.18), [(0.84, 1.1, '#ffffff', 0.75)], rays=12)
    plain = finpaint('#d4e0e4', '#eef4f6', (0.38, 0.15), rays=22)
    f.fin('dorsal', (0.0, f.tz(0.0, .012)), (-0.13, f.tz(-0.13, .012)), lambda t: 105 + 40 * t,
          lambda t: 0.12 - 0.06 * t, clear, rays=12, curl=-10)
    f.fin('adipose', (-0.24, f.tz(-0.24, .01)), (-0.3, f.tz(-0.3, .01)), lambda t: 120 + 40 * t,
          lambda t: 0.028 * np.sin(np.pi * (0.2 + 0.7 * t)) + 0.006, finpaint('#a8b0a0', None, (0.6, 0.5), rays=6), rays=6)
    f.fin('anal', (0.02, f.bz(0.02, .012)), (-0.3, f.bz(-0.3, .01)), lambda t: -120 - 40 * t,
          lambda t: 0.09 - 0.04 * t, clear, rays=18, curl=8)
    f.fin('caudal', (-0.385, -0.035), (-0.385, 0.035), lambda t: 218 - 76 * t,
          lambda t: 0.1 + 0.12 * np.abs(2 * t - 1) ** 1.3, plain, rays=22, pleat=0.005)
    side_fin(f, 'pect', 0.72, 0.22, lambda t: 195 - 35 * t, lambda t: 0.07 + 0.01 * np.sin(np.pi * t),
             finpaint('#dde8ec', None, (0.3, 0.12), rays=10), rays=10, size=0.03)
    side_fin(f, 'pelvic', 0.6, 0.06, lambda t: 235 - 20 * t, lambda t: 0.05, plain, splay=0.3, drop=-0.6, size=0.02,
             flap=0.2, rays=6)
    f.eye(0.86, 0.33, 0.05, rim='#5c7f96', out=0.55)
    f.lips((0.402, 0, f.zc(0.37) - 0.004), 0.013, '#c9a898', thick=0.3)
    return f


def angel():
    f = Fish('angel', px=86, amp=0.035, iris='#c21c18')
    top = curve([(0, .06), (.15, .085), (.4, .21), (.6, .25), (.8, .19), (.93, .095), (1, .03)])
    bot = curve([(0, -.06), (.15, -.085), (.4, -.19), (.6, -.22), (.8, -.17), (.93, -.075), (1, -.02)])
    wid = curve([(0, .015), (.3, .035), (.6, .045), (.85, .04), (1, .025)])
    BARS = [(0.205, 0.02), (0.02, 0.032), (-0.17, 0.026), (-0.285, 0.01)]

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 5)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#dcdfd4')
        mix(col, '#c9b27a', smooth(0.05, 0.22, Z) * smooth(-0.1, 0.25, X) * 0.7)  # gold wash on the forehead
        mix(col, '#f2f1ea', smooth(-0.05, -0.2, Z) * 0.6)
        bar = np.zeros(X.shape)
        for xc, w in BARS:
            d = np.abs(X - xc + (n - 0.5) * 0.03 + 0.02 * Z)
            bar += smooth(w + 0.01, w - 0.008, d) * (0.6 if w < 0.015 else 1)
        mix(col, '#1c1c20', np.clip(bar, 0, 1) * 0.95)
        mix(col, '#9aa0a0', (noise(X * 30, Z * 30, 1, 2, 6) > 0.62) * 0.3)  # faint speckles
        sc = scales(X, Z, 0.016)
        d = np.hypot(X - 0.28, (Z - 0.0) * 0.8)
        gill = smooth(0.01, 0.0, np.abs(d - 0.12)) * (np.abs(Z) < 0.1)
        return col, 0.2 * sc + 0.3 * (d < 0.12) + 0.2 * gill, 0.35 + 0.1 * n, 0.5 * (1 - np.clip(bar, 0, 1))

    f.body(-0.3, 0.3, top, bot, wid, paint, nose=0.1, q=0.9, film=380, sss=0.2)
    xs = [b[0] for b in BARS]
    sail = lambda a, b: finpaint('#e4e2d4', '#f4f2ea', (0.75, 0.4), [(0.93, 1.1, '#ffffff', 0.6)], rays=18,  # noqa: E731
                                 spots=bars(xs, 0.022), seed=2, mark='#121214')
    f.fin('dorsal', (0.14, f.tz(0.14, .02)), (-0.27, f.tz(-0.27, .015)), lambda t: 108 + 62 * t,
          lambda t: 0.48 - 0.34 * t, sail(0.14, -0.27), rays=18, curl=-12, ripple=0.012)
    f.fin('anal', (0.06, f.bz(0.06, .02)), (-0.27, f.bz(-0.27, .015)), lambda t: -108 - 62 * t,
          lambda t: 0.44 - 0.3 * t, sail(0.06, -0.27), rays=16, curl=12, ripple=0.012)
    f.fin('caudal', (-0.29, -0.05), (-0.29, 0.05), lambda t: 212 - 64 * t,
          lambda t: 0.17 + 0.2 * np.abs(2 * t - 1) ** 5, finpaint('#e0ded0', '#f0eee4', (0.6, 0.3), rays=22,
          spots=lambda T, V, X, Z: smooth(0.05, 0.02, np.abs(V - 0.2)) * 0.6), rays=22, pleat=0.006, ripple=0.012)
    side_fin(f, 'pect', 0.7, 0.24, lambda t: 195 - 30 * t, lambda t: 0.07, finpaint('#e8eae0', None, (0.3, 0.12), rays=10),
             rays=10, size=0.03)
    for sign in (-1, 1):  # long trailing ventral threads
        x0, z0 = 0.15, f.bz(0.15, 0.01)
        f.tube(f'ventral{sign}', [(x0, sign * 0.02, z0), (0.12, sign * 0.04, z0 - 0.12), (0.05, sign * 0.05, z0 - 0.3),
                                  (-0.04, sign * 0.05, z0 - 0.44)], 0.009, 0.003, '#e8e2cc', wiggle=0.025)
    f.eye(0.83, 0.36, 0.04, rim='#2b2a2c', out=0.6)
    f.lips((0.302, 0, f.zc(0.28) - 0.005), 0.018, '#cdbca8', thick=0.32)
    return f


def goldfish():
    f = Fish('goldfish', px=94, amp=0.05, iris='#2a1a0c')
    top = curve([(0, .06), (.15, .1), (.4, .23), (.6, .26), (.8, .21), (.93, .12), (1, .05)])
    bot = curve([(0, -.06), (.15, -.1), (.4, -.21), (.6, -.23), (.8, -.17), (.93, -.09), (1, -.03)])
    wid = curve([(0, .03), (.3, .11), (.6, .15), (.85, .12), (1, .06)])

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y * 2, 1, 4, 8)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#f2700e')
        mix(col, '#f9b23a', smooth(0.0, -0.2, Z) * 0.8)                 # golden belly
        mix(col, '#d6500a', smooth(0.1, 0.25, Z) * 0.6)                 # deep back
        pearl = smooth(0.6, 0.68, noise(X * 6, Z * 6 + Y, 1, 3, 9)) * smooth(-0.02, -0.12, Z)
        mix(col, '#f6eedc', pearl)                                       # pearly white patches
        sc = scales(X, Z, 0.045)
        mix(col, '#ffd27a', smooth(0.75, 1.0, sc) * 0.5 * (1 - pearl))   # bright scale rims
        d = np.hypot(X - 0.37, (Z + 0.01) * 0.8)
        gill = smooth(0.012, 0.0, np.abs(d - 0.13)) * (np.abs(Z) < 0.15)
        mix(col, col * 0.7, gill * 0.5)
        return col, 0.55 * sc + 0.35 * (d < 0.13) + 0.3 * gill, 0.28 + 0.12 * n, 0.4 + 0.4 * sc

    f.body(-0.35, 0.35, top, bot, wid, paint, nose=0.14, film=420, metal=0.25, sss=0.2, coat=0.35)
    veil = finpaint('#f2801c', '#fff1de', (0.85, 0.3), rays=26, seed=4)
    f.fin('dorsal', (0.14, f.tz(0.14, .02)), (-0.24, f.tz(-0.24, .015)), lambda t: 100 + 62 * t,
          lambda t: 0.17 - 0.03 * t + 0.02 * np.sin(np.pi * t), veil, rays=18, curl=-22, ripple=0.015)
    for sign in (-1, 1):  # fantail: twin tails splayed sideways
        a = math.radians(26 * sign)
        M = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
        f.fin(f'caudal{sign}', (-0.335, -0.06), (-0.335, 0.06), lambda t: 205 - 52 * t,
              lambda t: 0.3 + 0.14 * np.abs(2 * t - 1) ** 1.5, veil, rays=26, curl=0, pleat=0.01, ripple=0.03, M=M)
        f.fin(f'anal{sign}', (-0.12, f.bz(-0.12, .02)), (-0.25, f.bz(-0.25, .015)), lambda t: -140 - 30 * t,
              lambda t: 0.12, veil, rays=10, curl=10, ripple=0.012, M=M)
    side_fin(f, 'pect', 0.72, 0.18, lambda t: 205 - 40 * t, lambda t: 0.1 + 0.02 * np.sin(np.pi * t), veil, rays=12, size=0.04)
    side_fin(f, 'pelvic', 0.6, 0.05, lambda t: 240 - 25 * t, lambda t: 0.09, veil, splay=0.35, drop=-0.6, size=0.03,
             flap=0.25, rays=8)
    f.eye(0.85, 0.37, 0.058, rim='#e07418', out=0.72, toe=28)
    f.lips((0.355, 0, f.zc(0.32) - 0.01), 0.032, '#f39a7c', thick=0.4)
    return f


def tang():
    f = Fish('tang', px=110, amp=0.05, iris='#141418')
    top = curve([(0, .045), (.15, .075), (.4, .2), (.6, .22), (.8, .18), (.93, .1), (1, .02)])
    bot = curve([(0, -.045), (.15, -.075), (.4, -.19), (.6, -.2), (.8, -.15), (.93, -.075), (1, -.03)])
    wid = curve([(0, .02), (.3, .05), (.6, .065), (.85, .055), (1, .03)])

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 11)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#1d4fdc')
        mix(col, '#3f86f2', smooth(0.25, 0.4, X) * 0.5)           # brighter face
        mix(col, '#163cb0', smooth(0.05, 0.2, Z) * 0.4)
        # the "palette": a black sweep from the eye to the tail with a blue window inside
        e1 = ((X + 0.02) / 0.3) ** 2 + ((Z - 0.07) / 0.105) ** 2
        e2 = ((X + 0.07) / 0.13) ** 2 + ((Z - 0.035) / 0.045) ** 2
        tail = smooth(0.03, 0.015, np.abs(Z - (0.05 + 0.9 * (X + 0.25) ** 2 * 0))) * smooth(-0.2, -0.3, X) * smooth(-0.4, -0.34, X)
        ring = np.clip(smooth(1.06, 0.94, e1 + (n - 0.5) * 0.25) - smooth(1.06, 0.94, e2 + (n - 0.5) * 0.3) + tail, 0, 1)
        eye = smooth(0.026, 0.016, np.abs(X - 0.3 + 0.12 * (Z - 0.03))) * (Z > 0.0)
        mix(col, '#080a1c', np.clip(ring + eye, 0, 1))
        spine = smooth(0.022, 0.012, np.hypot(X + 0.35, (Z - 0.0) * 1.5))
        mix(col, '#f6d02a', spine)                                # yellow scalpel spot on the tail root
        sc = scales(X, Z, 0.012)
        d = np.hypot(X - 0.42, (Z + 0.01) * 0.85)
        gill = smooth(0.012, 0.0, np.abs(d - 0.15)) * (np.abs(Z) < 0.13)
        mix(col, col * 0.7, gill * 0.5)
        return col, 0.12 * sc + 0.3 * (d < 0.15) + 0.3 * gill, 0.4 + 0.1 * n, 0.25 * (1 - ring)

    f.body(-0.38, 0.38, top, bot, wid, paint, nose=0.1, q=0.92, film=300, sss=0.12)
    edge = finpaint('#1c48c8', None, (0.92, 0.85), [(0.62, 0.86, '#0a0c22', 0.95), (0.86, 1.1, '#5aa8ff', 0.9)], rays=30)
    f.fin('dorsal', (0.26, f.tz(0.26, .02)), (-0.33, f.tz(-0.33, .015)), lambda t: 125 + 40 * t,
          lambda t: 0.06 + 0.035 * np.sin(np.pi * (0.2 + 0.8 * t)), edge, rays=30, curl=-8)
    f.fin('anal', (0.05, f.bz(0.05, .02)), (-0.33, f.bz(-0.33, .015)), lambda t: -125 - 40 * t,
          lambda t: 0.055 + 0.035 * np.sin(np.pi * (0.2 + 0.8 * t)), edge, rays=22, curl=8)
    yellow = finpaint('#f6cc1c', '#f8dc50', (0.95, 0.85), rays=20,
                      spots=lambda T, V, X, Z: smooth(0.12, 0.04, np.minimum(T, 1 - T)) * smooth(0.2, 0.5, V))
    f.fin('caudal', (-0.37, -0.045), (-0.37, 0.045), lambda t: 222 - 84 * t,
          lambda t: 0.2 + 0.05 * np.abs(2 * t - 1) ** 2 - 0.03 * np.sin(np.pi * t), yellow, rays=20, pleat=0.005)
    side_fin(f, 'pect', 0.74, 0.22, lambda t: 200 - 40 * t, lambda t: 0.1 + 0.02 * np.sin(np.pi * t),
             finpaint('#2a5ad8', '#f6cc1c', (0.8, 0.7), rays=12), rays=12, size=0.04)
    f.eye(0.87, 0.35, 0.045, rim='#0a0c1c', out=0.6)
    f.lips((0.38, 0, f.zc(0.35) - 0.012), 0.016, '#2c56c4', thick=0.35)
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

    f = Fish('puffer', px=80, amp=0.035, iris='#2f8a46', inflate=inflate)
    top = curve([(0, .05), (.2, .1), (.45, .19), (.7, .21), (.88, .16), (1, .06)])
    bot = curve([(0, -.05), (.2, -.1), (.45, -.2), (.7, -.21), (.88, -.14), (1, -.04)])
    wid = curve([(0, .035), (.3, .13), (.6, .19), (.85, .15), (1, .07)])
    rng = np.random.default_rng(3)
    dots = rng.random((90, 2)) * [0.62, 0.42] + [-0.3, -0.05]

    def paint(X, Y, Z, U):
        n = noise(X * 4, Z * 4 + Y * 3, 1, 4, 12)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#d8c26e')
        mix(col, '#b89a48', smooth(0.05, 0.2, Z) * 0.6)
        belly = smooth(-0.02, -0.08, Z + (n - 0.5) * 0.04)
        mix(col, '#f4efe0', belly)
        spot = np.zeros(X.shape)
        for dx, dz in dots:  # brown spots on the back, bigger toward the middle
            spot = np.maximum(spot, smooth(0.016, 0.01, np.hypot(X - dx, (Z - dz) * 1.1 + 0.3 * Y * 0)))
        mix(col, '#5b3a18', spot * (1 - belly))
        saddle = smooth(0.06, 0.03, np.abs(X + 0.05)) * smooth(0.05, 0.12, Z) * 0.5
        mix(col, '#6a4a20', saddle)
        return col, 0.15 * noise(X * 40, Z * 40, 1, 2, 13) + 0.2 * spot, 0.5 + 0.1 * n, 0 * X

    f.body(-0.32, 0.32, top, bot, wid, paint, nose=0.16, sss=0.3, coat=0.2)
    pts, nrm = [], []
    for u in np.linspace(0.18, 0.8, 9):
        for sd in np.linspace(0.04, 0.96, 15):
            if abs(sd - 0.5) < 0.08:
                continue  # leave the back ridge clear for the dorsal line
            p, n = f.at(u + 0.012 * ((sd * 15) % 2), sd)
            pts.append(p)
            nrm.append(n)
    f.spikes(pts, nrm, 0.012, 0.006, '#e6dcb8')
    tiny = finpaint('#e8d690', '#f4ecc8', (0.6, 0.3), rays=10)
    f.fin('dorsal', (-0.16, f.tz(-0.16, .02)), (-0.25, f.tz(-0.25, .015)), lambda t: 115 + 40 * t, lambda t: 0.08 - 0.02 * t, tiny, rays=9, curl=-10)
    f.fin('anal', (-0.16, f.bz(-0.16, .02)), (-0.25, f.bz(-0.25, .015)), lambda t: -115 - 40 * t, lambda t: 0.075 - 0.02 * t, tiny, rays=9, curl=10)
    f.fin('caudal', (-0.31, -0.04), (-0.31, 0.04), lambda t: 215 - 70 * t, lambda t: 0.13 + 0.02 * np.sin(np.pi * t),
          finpaint('#d8c070', '#f0e4b8', (0.8, 0.5), rays=16, spots=lambda T, V, X, Z: (noise(T * 9, V * 9, 1, 2, 14) > 0.6) * 0.8,
                   mark='#5b3a18'), rays=16)
    side_fin(f, 'pect', 0.66, 0.28, lambda t: 190 - 30 * t, lambda t: 0.07 + 0.015 * np.sin(np.pi * t),
             finpaint('#eee2b0', None, (0.55, 0.25), rays=12), rays=12, size=0.045, flap=0.8)
    f.eye(0.82, 0.4, 0.062, rim='#c4a24a', out=0.72, toe=30)
    f.lips((0.325, 0, f.zc(0.3) - 0.012), 0.03, '#efe2c2', thick=0.45)
    return f


def cory():
    f = Fish('cory', px=68, amp=0.05, iris='#222018')
    top = curve([(0, .045), (.15, .06), (.45, .165), (.62, .185), (.8, .15), (.93, .085), (1, .03)])
    bot = curve([(0, -.04), (.15, -.05), (.45, -.08), (.7, -.085), (.9, -.07), (1, -.045)])
    wid = curve([(0, .025), (.3, .06), (.6, .085), (.85, .07), (1, .04)])

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 15)
        mid = (top(U) + bot(U)) / 2
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#b6ad98')
        mix(col, '#7f7a62', smooth(mid, mid + 0.1, Z) * 0.6)       # darker back
        mix(col, '#ece4d0', smooth(mid - 0.02, mid - 0.06, Z))     # pale belly
        pep = smooth(0.62, 0.68, noise(X * 45, Z * 45 + Y * 9, 1, 2, 16)) * smooth(mid - 0.04, mid + 0.02, Z)
        mix(col, '#2e2a24', pep * 0.9)                              # pepper spots
        # armour: two rows of overlapping plates meeting at a lateral seam, slanted grooves
        seam = smooth(0.006, 0.0, np.abs(Z - mid - 0.005))
        k = (X - 0.25 * (Z - mid)) / 0.042
        groove = smooth(0.1, 0.0, np.abs(k - np.round(k))) * (X < 0.24) * (X > -0.33)
        plates = np.clip(seam + groove, 0, 1)
        mix(col, col * 0.62, plates * 0.8)
        d = np.hypot(X - 0.34, (Z - mid) * 0.8)
        gill = smooth(0.012, 0.0, np.abs(d - 0.11)) * (np.abs(Z - mid) < 0.1)
        mix(col, col * 0.6, gill * 0.7)
        sheen = smooth(0.24, 0.32, X) * smooth(mid - 0.04, mid + 0.04, Z)  # bronze-green cheek plate
        mix(col, '#7a8a4a', sheen * 0.5)
        h = 0.5 * (k - np.floor(k)) * (X < 0.24) + 0.3 * (d < 0.11) - 0.3 * plates
        return col, h, 0.45 + 0.1 * n, np.clip(sheen + 0.3 * (1 - plates), 0, 1)

    f.body(-0.36, 0.36, top, bot, wid, paint, nose=0.12, q=0.8, film=520, sss=0.08, coat=0.2, bump=0.6)
    speck = lambda s: lambda T, V, X, Z: (noise(T * 7, V * 7, 1, 2, s) > 0.62) * 1.0  # noqa: E731
    f.fin('dorsal', (0.08, f.tz(0.08, .015)), (-0.06, f.tz(-0.06, .015)), lambda t: 98 + 45 * t,
          lambda t: 0.19 - 0.12 * t, finpaint('#d8d0bc', None, (0.55, 0.3), rays=9, spots=speck(17), mark='#2e2a24'), rays=9, curl=-12)
    f.fin('adipose', (-0.22, f.tz(-0.22, .01)), (-0.28, f.tz(-0.28, .01)), lambda t: 125 + 40 * t, lambda t: 0.04 - 0.015 * t,
          finpaint('#a49c88', None, (0.75, 0.6), rays=5), rays=5)
    f.fin('anal', (-0.14, f.bz(-0.14, .012)), (-0.24, f.bz(-0.24, .012)), lambda t: -125 - 35 * t, lambda t: 0.06,
          finpaint('#d8d0bc', None, (0.5, 0.25), rays=7), rays=7, curl=8)
    f.fin('caudal', (-0.35, -0.035), (-0.35, 0.035), lambda t: 222 - 84 * t,
          lambda t: 0.13 + 0.07 * np.abs(2 * t - 1) ** 1.2,
          finpaint('#d8d0bc', None, (0.5, 0.3), rays=16, mark='#2e2a24',
                   spots=lambda T, V, X, Z: smooth(0.3, 0.12, np.abs(np.sin(V * 14))) * 0.8), rays=16, pleat=0.005)
    side_fin(f, 'pect', 0.72, 0.1, lambda t: 205 - 40 * t, lambda t: 0.1 - 0.03 * t,
             finpaint('#d0c8b4', None, (0.6, 0.3), rays=8), rays=8, size=0.03, drop=-0.35, splay=0.6)
    side_fin(f, 'pelvic', 0.5, 0.04, lambda t: 230 - 20 * t, lambda t: 0.06, finpaint('#d8d0bc', None, (0.5, 0.25), rays=6),
             splay=0.4, drop=-0.6, size=0.025, flap=0.2, rays=6)
    xs, zs = 0.33, f.bz(0.33, 0.012)
    for sign in (-1, 1):  # two pairs of barbels under the snout
        f.tube(f'barbel{sign}a', [(xs, sign * 0.018, zs), (xs + 0.03, sign * 0.03, zs - 0.03), (xs + 0.04, sign * 0.045, zs - 0.06)],
               0.006, 0.0025, '#cbbfa6', wiggle=0.01)
        f.tube(f'barbel{sign}b', [(xs - 0.02, sign * 0.03, zs + 0.005), (xs - 0.005, sign * 0.05, zs - 0.035), (xs, sign * 0.07, zs - 0.06)],
               0.005, 0.002, '#cbbfa6', wiggle=0.012)
    f.eye(0.78, 0.4, 0.036, rim='#6c6656', out=0.65, toe=22)
    f.lips((0.35, 0, f.bz(0.35, 0.02)), 0.014, '#d8c8ae', thick=0.35)
    return f


def betta():
    f = Fish('betta', px=100, amp=0.04, iris='#2a0a0e')
    top = curve([(0, .05), (.2, .07), (.5, .11), (.75, .11), (.92, .07), (1, .025)])
    bot = curve([(0, -.05), (.2, -.07), (.5, -.1), (.75, -.1), (.92, -.06), (1, -.02)])
    wid = curve([(0, .02), (.3, .045), (.6, .055), (.85, .05), (1, .03)])

    def paint(X, Y, Z, U):
        n = noise(X * 5, Z * 5 + Y, 1, 4, 18)
        col = np.zeros(X.shape + (3,))
        col[:] = hexc('#c8183a')
        mix(col, '#5c0818', smooth(0.18, 0.3, X) * 0.7)            # dark mask on the head
        sc = scales(X, Z, 0.02)
        blue = smooth(0.5, 0.9, sc) * smooth(0.22, 0.1, X) * (0.6 + 0.4 * n)
        mix(col, '#3a52c8', blue * 0.7)                            # iridescent blue scale edges
        d = np.hypot(X - 0.28, Z * 0.85)
        gill = smooth(0.01, 0.0, np.abs(d - 0.09)) * (np.abs(Z) < 0.08)
        mix(col, '#2a0410', gill * 0.6)
        return col, 0.35 * sc + 0.3 * (d < 0.09), 0.3 + 0.1 * n, blue

    f.body(-0.3, 0.3, top, bot, wid, paint, nose=0.12, film=430, sss=0.25, coat=0.15)
    flow = finpaint('#b0122e', '#3a3cc0', (0.9, 0.6), [(0.9, 1.1, '#f0e6f0', 0.65)], rays=40, seed=6,
                    spots=lambda T, V, X, Z: smooth(0.3, 0.5, V) * smooth(0.55, 0.75, noise(T * 30, V * 4, 1, 2, 19)) * 0.6,
                    mark='#5a1060')
    f.fin('caudal', (-0.29, -0.05), (-0.29, 0.05), lambda t: 262 - 164 * t,
          lambda t: 0.4 + 0.06 * np.sin(np.pi * t), flow, rays=40, rows=12, pleat=0.014, ripple=0.04)
    f.fin('dorsal', (0.02, f.tz(0.02, .015)), (-0.27, f.tz(-0.27, .015)), lambda t: 118 + 55 * t,
          lambda t: 0.22 + 0.1 * t, flow, rays=22, curl=-28, pleat=0.01, ripple=0.03)
    f.fin('anal', (0.14, f.bz(0.14, .015)), (-0.27, f.bz(-0.27, .015)), lambda t: -112 - 62 * t,
          lambda t: 0.28 + 0.1 * t, flow, rays=26, curl=24, pleat=0.012, ripple=0.035)
    side_fin(f, 'pelvic', 0.72, 0.06, lambda t: 260 - 15 * t, lambda t: 0.2 - 0.04 * t,
             finpaint('#c01634', '#f4e8f0', (0.95, 0.8), rays=5), splay=0.25, drop=-1.4, size=0.015, flap=0.15, rays=5, ripple=0.02)
    side_fin(f, 'pect', 0.76, 0.24, lambda t: 195 - 35 * t, lambda t: 0.07, finpaint('#f0d8dc', None, (0.3, 0.12), rays=10),
             rays=10, size=0.03, flap=0.7)
    f.eye(0.85, 0.38, 0.036, rim='#3a0610', out=0.62)
    f.lips((0.3, 0, f.zc(0.27) - 0.004), 0.019, '#b0203c', thick=0.4)
    return f


SPECIES = {'clown': clown, 'tetra': tetra, 'angel': angel, 'goldfish': goldfish, 'tang': tang, 'puffer': puffer,
           'cory': cory, 'betta': betta}


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    pv = argv[argv.index('--preview') + 1] if '--preview' in argv else None
    names = [a for a in argv if a in SPECIES] or list(SPECIES)
    for n in names:
        run(n, pv)
