#!/usr/bin/env python3
"""Builds the Minecraft pixel font (regular + bold) from the Java bitmap font sheets and
patches it into index.html as base64 WOFF between the FONT markers.
  python3 tools/build_font.py --font <assets/minecraft/textures/font> --html index.html
Needs: Pillow, fontTools."""
import argparse, base64, io, json, re
from PIL import Image
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ap = argparse.ArgumentParser()
ap.add_argument('--font', required=True); ap.add_argument('--html', required=True)
a = ap.parse_args()

PX = 100                     # font units per source pixel -> 8 px per em (UPM 800)
UPM, ASC, DESC = 800, 700, 100   # Minecraft ascent 7: glyph rows 0..7, row 7 hangs below the baseline

ASCII_ROWS = {2:' !"#$%&\'()*+,-./',3:'0123456789:;<=>?',4:'@ABCDEFGHIJKLMNO',5:'PQRSTUVWXYZ[\\]^_',6:'`abcdefghijklmno',7:'pqrstuvwxyz{|}~'}
EURO_CHARS = {'·':None,'×':None,'—':None,'“':None,'”':None,'…':None,'→':None}

def cells(path, rows):
    im = Image.open(path).convert('RGBA'); cs = im.width // 16
    out = {}
    for r, chars in rows.items():
        for c, ch in enumerate(chars):
            if ch == '\0': continue
            px = [[im.getpixel((c*cs+x, r*cs+y))[3] > 0 for x in range(cs)] for y in range(cs)]
            out[ch] = px
    return out

glyphs = cells(a.font + '/ascii.png', ASCII_ROWS)
# nonlatin_european.png: rows come from default.json, read the layout from the same pack
import os, glob
dj = glob.glob(os.path.join(a.font, '..', '..', 'font', 'include', 'default.json'))
if dj:
    for p in json.load(open(dj[0]))['providers']:
        if p.get('file', '').endswith('nonlatin_european.png'):
            rows = {i: r for i, r in enumerate(p['chars'])}
            allc = cells(a.font + '/nonlatin_european.png', rows)
            for ch in EURO_CHARS:
                if ch in allc: glyphs[ch] = allc[ch]

def build(bold):
    order = ['.notdef'] + ['uni%04X' % ord(c) for c in sorted(glyphs)]
    gl = {}; metrics = {}
    def draw(px, extra):
        pen = TTGlyphPen(None); w = 0
        for y, row in enumerate(px):
            x = 0
            while x < len(row):
                if row[x]:
                    x0 = x
                    while x < len(row) and row[x]: x += 1
                    w = max(w, x)
                    x1 = x + (1 if extra else 0)
                    top = (7 - y + 1) * PX + 1; bot = (7 - y) * PX - 1 - PX + PX  # row y spans (7-y)*PX .. (8-y)*PX - PX? see below
                    top = (ASC // PX - y) * PX + 1                 # baseline-relative: row 0 top at +7px
                    bot = top - PX - 2
                    L = x0 * PX - 1; R = x1 * PX + 1
                    pen.moveTo((L, bot)); pen.lineTo((L, top)); pen.lineTo((R, top)); pen.lineTo((R, bot)); pen.closePath()
                else: x += 1
        return pen.glyph(), w
    # .notdef: empty box
    pen = TTGlyphPen(None); gl['.notdef'] = pen.glyph(); metrics['.notdef'] = (5*PX, 0)
    for ch in sorted(glyphs):
        name = 'uni%04X' % ord(ch)
        g, w = draw(glyphs[ch], bold)
        adv = (4 if ch == ' ' else (w + 1 + (1 if bold else 0))) * PX
        gl[name] = g; metrics[name] = (adv, 0)
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({ord(c): 'uni%04X' % ord(c) for c in glyphs})
    fb.setupGlyf(gl)
    fb.setupHorizontalMetrics({n: (metrics[n][0], 0) for n in order})
    fb.setupHorizontalHeader(ascent=ASC, descent=-DESC)
    fb.setupNameTable({'familyName': 'KitX Pixel', 'styleName': 'Bold' if bold else 'Regular'})
    fb.setupOS2(sTypoAscender=ASC, sTypoDescender=-DESC, usWinAscent=ASC, usWinDescent=DESC, usWeightClass=700 if bold else 400)
    fb.setupPost()
    buf = io.BytesIO(); fb.font.flavor = 'woff'; fb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()

reg, bld = build(False), build(True)
css = ("/*FONT-START*/@font-face{font-family:'KitX Pixel';font-weight:400;font-style:normal;font-display:block;src:url(data:font/woff;base64,%s) format('woff')}"
       "@font-face{font-family:'KitX Pixel';font-weight:700;font-style:normal;font-display:block;src:url(data:font/woff;base64,%s) format('woff')}/*FONT-END*/") % (reg, bld)
s = open(a.html, encoding='utf-8').read()
if '/*FONT-START*/' in s: s = re.sub(r'/\*FONT-START\*/.*?/\*FONT-END\*/', lambda m: css, s, flags=re.S)
else: s = s.replace('<style>', '<style>\n  ' + css, 1)
open(a.html, 'w', encoding='utf-8').write(s)
print('font embedded: regular %d KB, bold %d KB' % (len(reg)*3//4//1024, len(bld)*3//4//1024))
