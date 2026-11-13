#!/usr/bin/env python3
"""
KitX Web Builder - item icon atlas builder (part 1)

Bakes one 64x64 icon per Bedrock item id into a single sprite atlas and patches
the DATA block + ATLAS_URL in index.html.

Icon sources, in order of preference:
  sprite    flat 2D item textures (Java assets/minecraft/textures/item/*), layered + tinted
  cube      full 3D cubes rendered from the Java block model (GUI view, 30/225/0)
  baked     KitX addon's own pre-rendered icon (used for stairs, slabs, chests, banners,
            heads, shulker boxes... until the complex 3D renderer exists - part 2)
  bed       flat top-view built from textures/entity/bed/<colour>.png
  (none)    no art available -> the site shows its monogram fallback

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
RENDER_COMPLEX = False   # part 2: render non-cube 3D models with the same renderer

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


# -------------------------------------------------------------------- cubes
def rotmat(rx, ry, rz):
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


# face -> (TL, TR, BL) corners as (x,y,z) picks from (x0|x1, y0|y1, z0|z1); u runs TL->TR, v runs TL->BL
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


def render_model(model, tints, solid=False):
    """Isometric GUI render of an axis-aligned element model. Returns CELL x CELL RGBA uint8."""
    gui = model.get('gui') or {'rotation': [30, 225, 0], 'scale': [0.625] * 3}
    R = rotmat(*gui['rotation'])
    sc = SCALE * gui.get('scale', [0.625])[0] / 0.625
    flat_light = model.get('gui_light') == 'front'
    canvas = np.zeros((CELL, CELL, 4))
    quads = []
    for ei, el in enumerate(model['elements']):
        f, t = el['from'], el['to']
        for name, face in el['faces'].items():
            tl, tr, bl, nrm = FACES[name]
            n = R @ np.array(nrm, float)
            if n[2] <= 1e-6:          # facing away from the camera
                continue

            def P(sel):
                p = np.array([(t[0] if sel[0] else f[0]), (t[1] if sel[1] else f[1]), (t[2] if sel[2] else f[2])], float) - 8
                v = R @ p
                return np.array([CELL / 2 - v[0] * sc, CELL / 2 - v[1] * sc]), v[2]

            (O, z0), (E, z1), (Bp, z2) = P(tl), P(tr), P(bl)
            quads.append((ei, name, face, O, E - O, Bp - O, (z0 + z1 + z2) / 3, n, f, t))
    quads.sort(key=lambda q: q[6])        # far -> near, stable for coplanar overlays
    for ei, name, face, O, A, B, _, n, f, t in quads:
        a = tex(face['texture'])
        if a is None:
            continue
        H, W = a.shape[:2]
        det = A[0] * B[1] - A[1] * B[0]
        if abs(det) < 1e-6:
            continue
        pts = np.array([O, O + A, O + B, O + A + B])
        x0, x1 = max(0, int(math.floor(pts[:, 0].min()))), min(CELL, int(math.ceil(pts[:, 0].max())))
        y0, y1 = max(0, int(math.floor(pts[:, 1].min()))), min(CELL, int(math.ceil(pts[:, 1].max())))
        ys, xs = np.mgrid[y0:y1, x0:x1]
        qx, qy = xs + 0.5 - O[0], ys + 0.5 - O[1]
        u = (qx * B[1] - qy * B[0]) / det
        v = (A[0] * qy - A[1] * qx) / det
        eps = 0.012
        m = (u >= -eps) & (u < 1 + eps) & (v >= -eps) & (v < 1 + eps)
        u, v = np.clip(u, 0, 0.9999), np.clip(v, 0, 0.9999)
        rot = face.get('rotation', 0) % 360
        if rot == 90:
            u, v = v, 1 - u
        elif rot == 180:
            u, v = 1 - u, 1 - v
        elif rot == 270:
            u, v = 1 - v, u
        uv = face.get('uv') or default_uv(name, f, t)
        tu = uv[0] + u * (uv[2] - uv[0])
        tv = uv[1] + v * (uv[3] - uv[1])
        px = np.clip((tu / 16 * W).astype(int), 0, W - 1)
        py = np.clip((tv / 16 * H).astype(int), 0, H - 1)
        col = a[py, px].astype(float) / 255.0
        if solid:     # leaves: fill the see-through holes with a dark backing, like the in-game icon
            op = a[..., 3] > 0
            dark = a[..., :3][op].mean(axis=0) / 255.0 * 0.35 if op.any() else np.zeros(3)
            hole = col[..., 3] == 0
            col[..., :3][hole] = dark
            col[..., 3][hole] = 1.0
        ti = face.get('tintindex')
        if ti is not None and tints and ti < len(tints):
            col[..., :3] *= tint_rgb(tints[ti])
        if flat_light:
            shade = 1.0
        elif name == 'up':
            shade = 1.0
        elif name == 'down':
            shade = 0.5
        else:
            shade = 0.8 if (-n[0]) < 0 else 0.6     # left face 0.8, right face 0.6
        col[..., :3] *= shade
        col[..., 3] *= m
        canvas[y0:y1, x0:x1] = over(canvas[y0:y1, x0:x1], col)
    return (np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)


def is_full_box(model):
    els = model.get('elements') or []
    return bool(els) and all(e['from'] == [0, 0, 0] and e['to'] == [16, 16, 16] and 'rotation' not in e for e in els)


def is_axis_aligned(model):
    els = model.get('elements') or []
    return bool(els) and all('rotation' not in e for e in els)


# ------------------------------------------------------------------- others
def render_bed(parts):
    """Flat top-view of a bed: head part (pillow) + foot part, laid out head-left."""
    tops = []
    for p in parts or []:
        m = C.models.get(p.get('model') or '') or {}
        path = None
        for el in m.get('elements', []):
            if 'up' in el['faces']:
                path = el['faces']['up']['texture']
                if 'entity' not in path:
                    break
        a = tex(path) if path else None
        if a is None or a.shape[0] != a.shape[1]:
            return None
        tops.append(a)
    if len(tops) != 2:
        return None
    top = np.concatenate(tops, axis=0)               # head on top, foot below
    return to_cell(np.ascontiguousarray(np.rot90(top, 1)))   # head ends up on the left


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
    elif r == 'cube' or (r == 'model3d' and model.get('elements') and
                         (is_full_box(model) or (RENDER_COMPLEX and is_axis_aligned(model)))):
        return render_model(model, tints, solid='_leaves' in id_), 'cube'

    # flat item texture, if Java ships one (spyglass, boats, ...)
    for p in ([e['variants'][0]] if e.get('variants') else []) + ([f'item/{ji}'] if ji else []):
        a = render_layers([p])
        if a is not None:
            return a, 'sprite'
    b = baked(id_)
    if b is not None:
        return b, 'baked'
    if r == 'composite' and e.get('parts'):
        a = render_bed(e['parts'])
        if a is not None:
            return a, 'bed'
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
    ap.add_argument('--qa', help='write a QA contact sheet (ours vs baked) to this png')
    ap.add_argument('--cols', type=int, default=41)
    a = ap.parse_args()
    C.java, C.baked = a.java, a.baked
    items = json.load(open(a.map))['items']
    C.models = json.load(open(a.models))

    ids = sorted(items)
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
            'items': [[i, key_of.get(i)] for i in ids], 'pos': pos}
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
