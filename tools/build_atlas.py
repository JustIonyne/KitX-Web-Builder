#!/usr/bin/env python3
"""
KitX Web Builder - item icon atlas builder (part 1 + 2)

Bakes one 64x64 icon per Bedrock item id into a single sprite atlas and patches
the DATA block + ATLAS_URL in index.html. Only real Bedrock item ids are included.

Icon sources (Java assets are used only to draw the icons):
  sprite      flat 2D item textures, layered + tinted
  cube        full cubes rendered from the Java block model (GUI view)
  3d-model    stairs, slabs, fences, walls, trapdoors, anvils... rendered from their Java models
              (own GUI transform, element rotation, depth buffer)
  3d-entity   chests, shulker boxes, banners, heads, conduit built from the entity textures
  3d-bed      beds (head + foot block models)
  baked       fallback to the KitX addon's pre-rendered icon (shield, decorated pot, dragon/piglin head)
  (none)      no art -> the site shows its monogram fallback

Usage:
  python3 build_atlas.py --java <.../assets/minecraft> --map bedrock_to_java_map.json \
      --models java_models_resolved.json --baked <KitX_RP/textures/ui/kitx/blocks> \
      --html ../index.html --out ../assets/item_atlas.webp [--qa qa.png]

Requires: Pillow, numpy
"""
import argparse, collections, hashlib, json, math, os
import numpy as np
from PIL import Image

CELL = 64            # px per icon cell in the atlas
PAD = 1              # transparent pad around flat sprites (stops bilinear bleed)
SCALE = 2.43         # px per model unit for the GUI cube (matches the addon's baked cubes)

TINT_FALLBACK = {'grass': '#79C05A', 'foliage': '#48B518', 'dye': '#A06540',
                 'potion': '#385DC6', 'firework': '#8A8A8A', 'constant': '#FFFFFF'}


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255.0


def tint_rgb(t):
    return hex2rgb(t.get('value') or t.get('default') or TINT_FALLBACK.get(t.get('type'), '#FFFFFF'))


class Ctx:
    pass


C = Ctx()
_tex_cache = {}


def tex(path):
    """RGBA uint8 array of a Java texture (first frame if it is an animation strip)."""
    path = path.replace('minecraft:', '')
    if path in _tex_cache:
        return _tex_cache[path]
    f = os.path.join(C.java, 'textures', path + '.png')
    a = None
    if os.path.exists(f):
        im = Image.open(f).convert('RGBA')
        w, h = im.size
        if h > w and h % w == 0:
            im = im.crop((0, 0, w, w))
        a = np.array(im)
    _tex_cache[path] = a
    return a


def over(dst, src):
    """Straight-alpha 'over' on float RGBA arrays (same shape)."""
    sa, da = src[..., 3:4], dst[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = np.where(oa > 0, (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
    return np.concatenate([rgb, oa], axis=-1)


def to_cell(arr, content=CELL - 2 * PAD):
    """Fit an RGBA array into a CELL x CELL transparent cell, nearest-neighbour."""
    h, w = arr.shape[:2]
    k = content / max(w, h)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    im = Image.fromarray(arr, 'RGBA')
    im = im.resize((nw, nh), Image.NEAREST if k >= 1 else Image.BOX)
    cell = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
    cell.paste(im, ((CELL - nw) // 2, (CELL - nh) // 2))
    return np.array(cell)


# ------------------------------------------------------------------ sprites
def render_layers(paths, tints=None):
    layers = []
    for i, p in enumerate(paths):
        a = tex(p)
        if a is None:
            continue
        f = a.astype(float) / 255.0
        if tints and i < len(tints):
            f[..., :3] *= tint_rgb(tints[i])
        layers.append(f)
    if not layers:
        return None
    S = max(l.shape[0] for l in layers)
    out = np.zeros((S, S, 4))
    for l in layers:
        if l.shape[0] != S:
            l = np.array(Image.fromarray((l * 255).astype(np.uint8)).resize((S, S), Image.NEAREST)) / 255.0
        out = over(out, l)
    return to_cell((out * 255 + 0.5).astype(np.uint8))


# ------------------------------------------------------------ 3D pipeline
# Every 3D icon is a list of textured quads (corner TL, TR, BL + normal, in 0..16 model px)
# rasterised with a depth buffer using the model's own GUI transform.
K = SCALE / 0.625          # px per model unit per unit of GUI scale


def rotmat(rx, ry, rz):
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


# face -> (TL, TR, BL) corners as picks from (from|to) per axis, plus the outward normal
FACES = {
    'up':    ((0, 1, 0), (1, 1, 0), (0, 1, 1), (0, 1, 0)),
    'down':  ((0, 0, 1), (1, 0, 1), (0, 0, 0), (0, -1, 0)),
    'north': ((1, 1, 0), (0, 1, 0), (1, 0, 0), (0, 0, -1)),
    'south': ((0, 1, 1), (1, 1, 1), (0, 0, 1), (0, 0, 1)),
    'west':  ((0, 1, 0), (0, 1, 1), (0, 0, 0), (-1, 0, 0)),
    'east':  ((1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0)),
}


def default_uv(name, f, t):
    x0, y0, z0 = f
    x1, y1, z1 = t
    return {'up': [x0, z0, x1, z1], 'down': [x0, 16 - z1, x1, 16 - z0],
            'north': [16 - x1, 16 - y1, 16 - x0, 16 - y0], 'south': [x0, 16 - y1, x1, 16 - y0],
            'west': [z0, 16 - y1, z1, 16 - y0], 'east': [16 - z1, 16 - y1, 16 - z0, 16 - y0]}[name]


def face_pts(name, f, t):
    tl, tr, bl, n = FACES[name]
    P = lambda s: np.array([t[0] if s[0] else f[0], t[1] if s[1] else f[1], t[2] if s[2] else f[2]], float)
    return P(tl), P(tr), P(bl), np.array(n, float)


def get_tex(path, solid=False):
    a = tex(path)
    if a is not None and solid:       # leaves: fill see-through holes with a dark backing
        a = a.copy()
        op = a[..., 3] > 0
        if op.any():
            dark = (a[..., :3][op].mean(axis=0) * 0.35).astype(np.uint8)
            hole = ~op
            a[..., :3][hole] = dark
            a[..., 3][hole] = 255
    return a


def element_quads(model, tints, offset=(0, 0, 0), solid=False):
    """Quads for a Java block/item model (elements may carry their own rotation)."""
    out = []
    off = np.array(offset, float)
    for el in model.get('elements', []):
        f, t = el['from'], el['to']
        r = el.get('rotation')
        if r:
            Rm = rotmat(*({'x': (r['angle'], 0, 0), 'y': (0, r['angle'], 0), 'z': (0, 0, r['angle'])}[r['axis']]))
            org = np.array(r['origin'], float)
            sc = np.ones(3)
            if r.get('rescale'):
                k = 1 / max(math.cos(math.radians(r['angle'])), 1e-3)
                sc = np.array([k if ax != r['axis'] else 1 for ax in 'xyz'], float)
        for name, face in el['faces'].items():
            a = get_tex(face['texture'], solid)
            if a is None:
                continue
            tl, tr, bl, n = face_pts(name, f, t)
            if r:
                tl, tr, bl = [org + (Rm @ (p - org)) * sc for p in (tl, tr, bl)]
                n = Rm @ n
            uv = face.get('uv') or default_uv(name, f, t)
            out.append(dict(tl=tl + off, tr=tr + off, bl=bl + off, n=n, tex=a,
                            uv=[uv[0] / 16, uv[1] / 16, uv[2] / 16, uv[3] / 16],
                            rot=face.get('rotation', 0) % 360, ti=face.get('tintindex')))
    return out


def entity_box(a, u, v, w, h, d, f, t, tint=None, flipped=False):
    """Quads of a vanilla entity-model cube: texOffs (u,v), UV dims (w,h,d), geometry f..t (block-space px,
    y up, front = south)."""
    H, W = a.shape[:2]
    uvs = {'south': (u + d, v + d, u + d + w, v + d + h), 'north': (u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h),
           'west': (u, v + d, u + d, v + d + h), 'east': (u + d + w, v + d, u + 2 * d + w, v + d + h),
           'up': (u + d, v, u + d + w, v + d), 'down': (u + d + w, v, u + d + 2 * w, v + d)}
    if flipped:      # block-entity models (chest) are stored upside-down: swap up/down and north/south regions
        uvs['up'], uvs['down'] = uvs['down'], uvs['up']
        uvs['north'], uvs['south'] = uvs['south'], uvs['north']
    out = []
    for name, (u0, v0, u1, v1) in uvs.items():
        tl, tr, bl, n = face_pts(name, f, t)
        out.append(dict(tl=tl, tr=tr, bl=bl, n=n, tex=a, uv=[u0 / W, v0 / H, u1 / W, v1 / H], rot=0, ti=None, tint=tint))
    return out


def render_quads(quads, gui, tints=None, flat_light=False):
    gui = gui or {}
    R = rotmat(*(gui.get('rotation') or [30, 225, 0]))
    sc = K * (gui.get('scale') or [0.625])[0]
    tx, ty = (gui.get('translation') or [0, 0, 0])[:2]
    canvas = np.zeros((CELL, CELL, 4))
    depth = np.full((CELL, CELL), -1e9)
    cen = np.array([8.0, 8.0, 8.0])

    def proj(p):
        v = R @ (p - cen)
        return np.array([CELL / 2 - v[0] * sc - tx * K, CELL / 2 - v[1] * sc - ty * K]), v[2] * sc

    for q in quads:
        n = R @ q['n']
        if n[2] <= 1e-6:                       # facing away
            continue
        (O, z0), (E, z1), (Bp, z2) = proj(q['tl']), proj(q['tr']), proj(q['bl'])
        A, B = E - O, Bp - O
        det = A[0] * B[1] - A[1] * B[0]
        if abs(det) < 1e-6:
            continue
        pts = np.array([O, O + A, O + B, O + A + B])
        x0, x1 = max(0, int(math.floor(pts[:, 0].min()))), min(CELL, int(math.ceil(pts[:, 0].max())))
        y0, y1 = max(0, int(math.floor(pts[:, 1].min()))), min(CELL, int(math.ceil(pts[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        qx, qy = xs + 0.5 - O[0], ys + 0.5 - O[1]
        u = (qx * B[1] - qy * B[0]) / det
        v = (A[0] * qy - A[1] * qx) / det
        eps = 0.012
        m = (u >= -eps) & (u < 1 + eps) & (v >= -eps) & (v < 1 + eps)
        u, v = np.clip(u, 0, 0.9999), np.clip(v, 0, 0.9999)
        z = z0 + u * (z1 - z0) + v * (z2 - z0)
        rot = q['rot']
        if rot == 90:
            u, v = v, 1 - u
        elif rot == 180:
            u, v = 1 - u, 1 - v
        elif rot == 270:
            u, v = 1 - v, u
        a = q['tex']
        H, W = a.shape[:2]
        uv = q['uv']
        tu = uv[0] + u * (uv[2] - uv[0])
        tv = uv[1] + v * (uv[3] - uv[1])
        px = np.clip((tu * W).astype(int), 0, W - 1)
        py = np.clip((tv * H).astype(int), 0, H - 1)
        col = a[py, px].astype(float) / 255.0
        ti = q.get('ti')
        if q.get('tint') is not None:
            col[..., :3] *= q['tint']
        elif ti is not None and tints and ti < len(tints):
            col[..., :3] *= tint_rgb(tints[ti])
        if flat_light:
            shade = 1.0
        else:                                  # screen-space shading: top 1.0, left 0.8, right 0.6
            nxs, ny = -n[0], n[1]
            shade = (0.7 - 0.1 * np.clip(nxs / 0.612, -1, 1)) + 0.3 * np.clip((ny - 0.5) / 0.366, 0, 1)
        col[..., :3] *= shade
        ok = m & (col[..., 3] > 0) & (z >= depth[y0:y1, x0:x1] - 1e-3)
        dst = canvas[y0:y1, x0:x1]
        blend = over(dst, col)
        dst[ok] = blend[ok]
        depth[y0:y1, x0:x1][ok] = z[ok]
    return (np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)


def blank(img):
    return img is None or (img[..., 3] > 0).sum() < 40


def render_model(model, tints, solid=False):
    return render_quads(element_quads(model, tints, solid=solid), model.get('gui'), tints,
                        flat_light=model.get('gui_light') == 'front')


def is_full_box(model):
    els = model.get('elements') or []
    return bool(els) and all(e['from'] == [0, 0, 0] and e['to'] == [16, 16, 16] and 'rotation' not in e for e in els)


def is_axis_aligned(model):
    els = model.get('elements') or []
    return bool(els) and all('rotation' not in e for e in els)


# ------------------------------------------------------------ entity items
DYE = {'white': 'F9FFFE', 'orange': 'F9801D', 'magenta': 'C74EBD', 'light_blue': '3AB3DA', 'yellow': 'FED83D',
       'lime': '80C71F', 'pink': 'F38BAA', 'gray': '474F52', 'light_gray': '9D9D97', 'cyan': '169C9C',
       'purple': '8932B8', 'blue': '3C44AA', 'brown': '835432', 'green': '5E7C16', 'red': 'B02E26', 'black': '1D1D21'}
GUI45 = {'rotation': [30, 45, 0], 'translation': [0, 0, 0], 'scale': [0.625] * 3}


def render_special(sp):
    t = sp['type']
    if t == 'chest':
        a = tex(f"entity/chest/{sp.get('texture', 'normal')}")
        if a is None:
            return None
        q = (entity_box(a, 0, 19, 14, 10, 14, (1, 0, 1), (15, 10, 15), flipped=True) +
             entity_box(a, 0, 0, 14, 5, 14, (1, 9, 1), (15, 14, 15), flipped=True) +
             entity_box(a, 0, 0, 2, 4, 1, (7, 7, 15), (9, 11, 16), flipped=True))
        return render_quads(q, GUI45)
    if t == 'shulker_box':
        a = tex(f"entity/shulker/{sp.get('texture', 'shulker')}")
        if a is None:
            return None
        q = (entity_box(a, 0, 28, 16, 8, 16, (0, 0, 0), (16, 8, 16)) +
             entity_box(a, 0, 0, 16, 12, 16, (0, 4, 0), (16, 16, 16)))
        return render_quads(q, GUI45)
    if t in ('head', 'player_head'):
        kind = sp.get('kind', 'player')
        path = {'skeleton': 'entity/skeleton/skeleton', 'wither_skeleton': 'entity/skeleton/wither_skeleton',
                'zombie': 'entity/zombie/zombie', 'creeper': 'entity/creeper/creeper',
                'player': 'entity/player/wide/steve'}.get(kind)
        a = tex(path) if path else None
        if a is None:
            return None
        q = entity_box(a, 0, 0, 8, 8, 8, (4, 0, 4), (12, 8, 12))
        if kind == 'player':
            q += entity_box(a, 32, 0, 8, 8, 8, (3.75, -0.25, 3.75), (12.25, 8.25, 12.25))
        return render_quads(q, {'rotation': [30, 45, 0], 'translation': [0, 3, 0], 'scale': [1, 1, 1]})
    if t == 'banner':
        a = tex('entity/banner/banner_base')
        if a is None:
            return None
        s = 2 / 3
        col = hex2rgb(DYE.get(sp.get('color', 'white'), 'F9FFFE'))
        cx = cz = 8.0
        # entity space (y down, front -z) -> block space via (x, -y, -z) * 2/3 + (8, 0, 8)
        flag = entity_box(a, 0, 0, 20, 40, 1, (cx - 10 * s, -8 * s, cz + 1 * s), (cx + 10 * s, 32 * s, cz + 2 * s), tint=col)
        pole = entity_box(a, 44, 0, 2, 42, 2, (cx - 1 * s, -12 * s, cz - 1 * s), (cx + 1 * s, 30 * s, cz + 1 * s))
        bar = entity_box(a, 0, 42, 20, 2, 2, (cx - 10 * s, 30 * s, cz - 1 * s), (cx + 10 * s, 32 * s, cz + 1 * s))
        return render_quads(pole + bar + flag, {'rotation': [30, 20, 0], 'translation': [0, -3.25, 0], 'scale': [0.5325] * 3},
                            flat_light=True)
    if t == 'conduit':
        a = tex('entity/conduit/base')
        if a is None:
            return None
        return render_quads(entity_box(a, 0, 0, 6, 6, 6, (5, 5, 5), (11, 11, 11)),
                            {'rotation': [30, 45, 0], 'translation': [0, 0, 0], 'scale': [1, 1, 1]})
    return None


def render_bed(parts):
    """Beds are two block models (head + foot); foot is shifted one block south."""
    quads, gui = [], None
    for i, p in enumerate(parts or []):
        m = C.models.get(p.get('model') or '')
        if not m or not m.get('elements'):
            return None
        gui = gui or m.get('gui')
        quads += element_quads(m, None, offset=(0, 0, 16 * i))
    return render_quads(quads, gui) if quads else None



# ------------------------------------------------------------ potion variants
# Bedrock potions are ONE item id with the potion type in the data value (Damage/aux).
# The aux numbering below is Bedrock's; `bk` is the effect's key in Bedrock's item_texture.json
# (potion_bottle_drinkable / _splash / _lingering texture lists), verified at build time.
EFFECT_RGB = {'night_vision': '1F1FA1', 'invisibility': 'F6F6F6', 'jump': 'FDFF84', 'fire_resistance': 'FF9900',
              'speed': '33EBFF', 'slowness': '8BAFE0', 'water_breathing': '98DAC0', 'instant_health': 'F82423',
              'instant_damage': 'A9656A', 'poison': '4E9331', 'regeneration': 'CD5CAB', 'strength': '932423',
              'weakness': '484D48', 'wither': '352A27', 'resistance': '9146F0', 'slow_falling': 'F3CFB9',
              'wind_charged': 'BDC9FF', 'weaving': '78695A', 'oozing': '99FFA3', 'infested': '8C9B8C'}
NO_EFFECT_RGB = '385DC6'
# (aux, name, suffix, [(effect, weight)], bedrock texture key)
_E, _II = ' (Extended)', ' II'
POTION_TYPES = [
    (5, 'Night Vision', '', [('night_vision', 1)], 'nightVision'), (6, 'Night Vision', _E, [('night_vision', 1)], 'nightVision'),
    (7, 'Invisibility', '', [('invisibility', 1)], 'invisibility'), (8, 'Invisibility', _E, [('invisibility', 1)], 'invisibility'),
    (9, 'Leaping', '', [('jump', 1)], 'jump'), (10, 'Leaping', _E, [('jump', 1)], 'jump'), (11, 'Leaping', _II, [('jump', 1)], 'jump'),
    (12, 'Fire Resistance', '', [('fire_resistance', 1)], 'fireResistance'), (13, 'Fire Resistance', _E, [('fire_resistance', 1)], 'fireResistance'),
    (14, 'Swiftness', '', [('speed', 1)], 'moveSpeed'), (15, 'Swiftness', _E, [('speed', 1)], 'moveSpeed'), (16, 'Swiftness', _II, [('speed', 1)], 'moveSpeed'),
    (17, 'Slowness', '', [('slowness', 1)], 'moveSlowdown'), (18, 'Slowness', _E, [('slowness', 1)], 'moveSlowdown'),
    (19, 'Water Breathing', '', [('water_breathing', 1)], 'waterBreathing'), (20, 'Water Breathing', _E, [('water_breathing', 1)], 'waterBreathing'),
    (21, 'Healing', '', [('instant_health', 1)], 'heal'), (22, 'Healing', _II, [('instant_health', 1)], 'heal'),
    (23, 'Harming', '', [('instant_damage', 1)], 'harm'), (24, 'Harming', _II, [('instant_damage', 1)], 'harm'),
    (25, 'Poison', '', [('poison', 1)], 'poison'), (26, 'Poison', _E, [('poison', 1)], 'poison'), (27, 'Poison', _II, [('poison', 1)], 'poison'),
    (28, 'Regeneration', '', [('regeneration', 1)], 'regeneration'), (29, 'Regeneration', _E, [('regeneration', 1)], 'regeneration'),
    (30, 'Regeneration', _II, [('regeneration', 1)], 'regeneration'),
    (31, 'Strength', '', [('strength', 1)], 'damageBoost'), (32, 'Strength', _E, [('strength', 1)], 'damageBoost'), (33, 'Strength', _II, [('strength', 1)], 'damageBoost'),
    (34, 'Weakness', '', [('weakness', 1)], 'weakness'), (35, 'Weakness', _E, [('weakness', 1)], 'weakness'),
    (36, 'Decay', '', [('wither', 1)], 'wither'),
    (37, 'the Turtle Master', '', [('slowness', 4), ('resistance', 3)], 'turtleMaster'),
    (38, 'the Turtle Master', _E, [('slowness', 4), ('resistance', 3)], 'turtleMaster'),
    (39, 'the Turtle Master', _II, [('slowness', 6), ('resistance', 4)], 'turtleMaster'),
    (40, 'Slow Falling', '', [('slow_falling', 1)], 'slowFall'), (41, 'Slow Falling', _E, [('slow_falling', 1)], 'slowFall'),
    (42, 'Slowness IV', '', [('slowness', 1)], 'moveSlowdown'),
    (43, 'Wind Charging', '', [('wind_charged', 1)], 'windCharged'), (44, 'Weaving', '', [('weaving', 1)], 'weaving'),
    (45, 'Oozing', '', [('oozing', 1)], 'oozing'), (46, 'Infestation', '', [('infested', 1)], 'infested'),
]
PLAIN_TYPES = [(0, 'Water Bottle', 'Splash Water Bottle', 'Lingering Water Bottle'),
               (1, 'Mundane Potion', 'Mundane Splash Potion', 'Mundane Lingering Potion'),
               (2, 'Mundane Potion (Extended)', 'Mundane Splash Potion (Extended)', 'Mundane Lingering Potion (Extended)'),
               (3, 'Thick Potion', 'Thick Splash Potion', 'Thick Lingering Potion'),
               (4, 'Awkward Potion', 'Awkward Splash Potion', 'Awkward Lingering Potion')]


def mix_rgb(effects):
    tot = sum(w for _, w in effects)
    c = sum(hex2rgb(EFFECT_RGB[e]) * w for e, w in effects) / tot
    return '#%02X%02X%02X' % tuple(int(round(v * 255)) for v in c)


def potion_variants(items):
    """-> [(id, aux, title, icon)] for potion / splash_potion / lingering_potion (aux 0-46) and tipped_arrow (aux 6-47)."""
    out = []

    def layers(id_):
        return C.models[items[id_]['model']]['layers']

    def icon(id_, hexcol):
        # the tinted layer is layer 0 (potion_overlay / tipped_arrow_head)
        return render_layers(layers(id_), [{'type': 'constant', 'value': hexcol}])

    for kind, prefix in (('potion', 'Potion of '), ('splash_potion', 'Splash Potion of '), ('lingering_potion', 'Lingering Potion of ')):
        if kind not in items:
            continue
        for aux, a, b, c_ in PLAIN_TYPES:
            title = {'potion': a, 'splash_potion': b, 'lingering_potion': c_}[kind]
            out.append((kind, aux, title, icon(kind, '#' + NO_EFFECT_RGB)))
        for aux, name, suf, eff, _bk in POTION_TYPES:
            out.append((kind, aux, f'{prefix}{name}{suf}', icon(kind, mix_rgb(eff))))
    if 'tipped_arrow' in items:
        for aux, name, suf, eff, _bk in POTION_TYPES:
            out.append(('tipped_arrow', aux + 1, f'Arrow of {name}{suf}', icon('tipped_arrow', mix_rgb(eff))))
    return [v for v in out if v[3] is not None]


def load_json_c(path):
    import re
    return json.loads(re.sub(r'^\s*//.*$', '', open(path, encoding='utf-8').read(), flags=re.M))


def verify_bedrock(dirpath, items, ids):
    """Cross-check the id list and potion table against the Bedrock identifier files."""
    it = load_json_c(os.path.join(dirpath, 'item_texture.json'))['texture_data']
    te = load_json_c(os.path.join(dirpath, 'terrain_texture.json'))['texture_data']
    paths = set()
    for d in (it, te):
        for v in d.values():
            t = v.get('textures') if isinstance(v, dict) else None
            for x in (t if isinstance(t, list) else [t]):
                if isinstance(x, str):
                    paths.add(x)
                elif isinstance(x, dict) and isinstance(x.get('path'), str):
                    paths.add(x['path'])
    kitx = {f[:-4] for f in os.listdir(C.baked)} if os.path.isdir(C.baked) else set()
    bad = []
    for i in ids:
        bi = items[i].get('bedrock_icon')
        if bi and bi not in paths and not (bi.startswith('textures/ui/kitx/blocks/') and bi.rsplit('/', 1)[1] in kitx):
            bad.append((i, bi))
    print(f'bedrock check: {len(ids) - len(bad)}/{len(ids)} ids resolve to a Bedrock texture in item_texture/terrain_texture/KitX blocks')
    if bad:
        print('  not in the Bedrock identifier files -> dropped:', [b[0] for b in bad])
    pk = {k: [x.split('/')[-1] for x in (it[k]['textures'] if isinstance(it[k]['textures'], list) else [it[k]['textures']])]
          for k in ('potion_bottle_drinkable', 'potion_bottle_splash', 'potion_bottle_lingering')}
    miss = sorted({bk for *_, bk in POTION_TYPES
                   if 'potion_bottle_' + bk not in pk['potion_bottle_drinkable']})
    print('potion types vs Bedrock potion_bottle_drinkable list:', 'all effect keys found' if not miss else f'MISSING {miss}')
    return {b[0] for b in bad}


def baked(id_):
    f = os.path.join(C.baked, id_ + '.png')
    if os.path.exists(f):
        return np.array(Image.open(f).convert('RGBA').resize((CELL, CELL), Image.NEAREST))
    return None


def dominant_texture(model):
    c = collections.Counter(fc['texture'] for e in model.get('elements', []) for fc in e['faces'].values())
    return c.most_common(1)[0][0] if c else None


def resolve(id_, e):
    """-> (RGBA uint8 CELLxCELL | None, source tag)"""
    model = C.models.get(e.get('model') or '') or {}
    tints = e.get('tints')
    r = e['render']
    ji = e.get('java_item')

    if r == 'sprite':
        paths = model.get('layers') or ([model['textures']['layer0']] if 'layer0' in model.get('textures', {}) else [])
        a = render_layers(paths, tints)
        if a is not None:
            return a, 'sprite'
    elif r == 'model3d' and (e.get('model') or '').startswith('item/') and e.get('variants') \
            and render_layers([e['variants'][0]]) is not None:
        return render_layers([e['variants'][0]]), 'sprite'      # e.g. spyglass: the GUI icon is flat
    elif r in ('cube', 'model3d') and model.get('elements'):
        img = render_model(model, tints, solid='_leaves' in id_)
        if not blank(img):
            return img, 'cube' if (r == 'cube' or is_full_box(model)) else '3d-model'
    elif r == 'special' and e.get('special'):
        img = render_special(e['special'])
        if not blank(img):
            return img, '3d-entity'
    elif r == 'composite' and e.get('parts'):
        img = render_bed(e['parts'])
        if not blank(img):
            return img, '3d-bed'

    # flat item texture, if Java ships one (spyglass, trident, ...)
    for p in ([e['variants'][0]] if e.get('variants') else []) + ([f'item/{ji}'] if ji else []):
        a = render_layers([p])
        if a is not None:
            return a, 'sprite'
    b = baked(id_)
    if b is not None:
        return b, 'baked'
    if model:
        p = dominant_texture(model)
        a = render_layers([p]) if p else None
        if a is not None:
            return a, 'flat-fallback'
    return None, 'none'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--java', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--models', required=True)
    ap.add_argument('--baked', required=True)
    ap.add_argument('--html', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--bedrock', help='folder with Bedrock item_texture.json + terrain_texture.json (verification)')
    ap.add_argument('--qa', help='write a QA contact sheet (ours vs baked) to this png')
    ap.add_argument('--cols', type=int, default=41)
    a = ap.parse_args()
    C.java, C.baked = a.java, a.baked
    items = json.load(open(a.map))['items']
    C.models = json.load(open(a.models))

    # Only real Bedrock item identifiers go into the Kit Builder. The mapping also contains
    # texture keys (bundle_*_open/_front/_back, bow_pulling_*, potion_overlay, empty_armor_slot_*,
    # egg_*, map_*, *_atlas ...): those are art for other items, not items, so they are dropped.
    ids = sorted(i for i, e in items.items() if e.get('class') in ('item', 'bedrock_only'))
    dropped = sorted(set(items) - set(ids))
    print(f'items kept: {len(ids)}  dropped texture keys: {len(dropped)}')
    if a.bedrock:
        # an id must resolve in the Bedrock identifier files to be listed (drops texture-name duplicates like
        # `boat` / `spawn_egg_sulfur_cube` and stand-ins like `hoglin_meat_*`)
        bad = verify_bedrock(a.bedrock, items, ids)
        ids = [i for i in ids if i not in bad]
        print(f'items listed: {len(ids)}')
    imgs, tags = {}, collections.Counter()
    missing = []
    for id_ in ids:
        img, tag = resolve(id_, items[id_])
        imgs[id_] = img
        tags[tag] += 1
        if img is None:
            missing.append(id_)
    print('sources:', dict(tags))
    print('no art :', missing)

    variants = potion_variants(items)
    print(f'potion variants: {len(variants)}')
    # dedupe identical icons (many ids share art) and pack
    uniq, key_of, order = {}, {}, []
    for id_ in ids:
        img = imgs[id_]
        if img is None:
            continue
        h = hashlib.md5(img.tobytes()).hexdigest()
        if h not in uniq:
            uniq[h] = len(order)
            order.append(img)
        key_of[id_] = uniq[h]
    var_rows = []
    for id_, aux, title, img in variants:
        h = hashlib.md5(img.tobytes()).hexdigest()
        if h not in uniq:
            uniq[h] = len(order)
            order.append(img)
        var_rows.append([id_, aux, title, uniq[h]])
    cols = a.cols
    rows = math.ceil(len(order) / cols)
    atlas = Image.new('RGBA', (cols * CELL, rows * CELL), (0, 0, 0, 0))
    pos = {}
    for i, img in enumerate(order):
        c, r = i % cols, i // cols
        atlas.paste(Image.fromarray(img, 'RGBA'), (c * CELL, r * CELL))
        pos[str(i)] = [c, r]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    atlas.save(a.out, lossless=True, quality=100, method=6)
    print(f'atlas {atlas.size}, {len(order)} unique icons, {os.path.getsize(a.out)/1024:.0f} KB')

    data = {'cols': cols, 'rows': rows, 'cell': CELL,
            'items': [[i, key_of.get(i)] for i in ids], 'vars': var_rows, 'pos': pos}
    s = open(a.html, encoding='utf-8').read()
    k = s.index('const DATA = ')
    _, end = json.JSONDecoder().raw_decode(s[k + len('const DATA = '):])
    s = s[:k] + 'const DATA = ' + json.dumps(data, separators=(',', ':')) + s[k + len('const DATA = ') + end:]
    rel = os.path.relpath(a.out, os.path.dirname(os.path.abspath(a.html))).replace(os.sep, '/')
    import re
    s = re.sub(r"const ATLAS_URL = '[^']*';", f"const ATLAS_URL = '{rel}';", s)
    open(a.html, 'w', encoding='utf-8').write(s)
    print('patched', a.html, '->', rel)

    if a.qa:
        qa_ids = ['furnace', 'crafting_table', 'grass_block', 'oak_log', 'stone', 'tnt', 'bookshelf', 'oak_leaves',
                  'glass', 'diamond_sword', 'leather_helmet', 'potion', 'clock', 'oak_stairs', 'chest', 'white_bed',
                  'enchanted_golden_apple', 'firework_star', 'spyglass', 'oak_boat', 'pumpkin', 'jukebox', 'sandstone', 'cake']
        qa_ids = [i for i in qa_ids if imgs.get(i) is not None]
        W = 8
        sheet = Image.new('RGBA', (W * 2 * 66, math.ceil(len(qa_ids) / W) * 66), (70, 70, 74, 255))
        for n, i in enumerate(qa_ids):
            x, y = (n % W) * 132, (n // W) * 66
            sheet.alpha_composite(Image.fromarray(imgs[i], 'RGBA'), (x + 1, y + 1))
            b = baked(i)
            if b is not None:
                sheet.alpha_composite(Image.fromarray(b, 'RGBA'), (x + 67, y + 1))
        sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
        sheet.save(a.qa)
        # numeric check: cube renders vs the addon's baked cubes
        diffs = []
        for i, e in items.items():
            if e['render'] == 'cube' and imgs[i] is not None and baked(i) is not None:
                A_, B_ = imgs[i].astype(float), baked(i).astype(float)
                m = (A_[..., 3] > 200) & (B_[..., 3] > 200)
                if m.sum() > 400:
                    diffs.append((np.abs(A_[..., :3] - B_[..., :3])[m].mean(), i))
        diffs.sort()
        print('cube vs baked: n=%d median diff=%.1f worst=%s' % (len(diffs), diffs[len(diffs)//2][0], diffs[-8:]))


if __name__ == '__main__':
    main()
