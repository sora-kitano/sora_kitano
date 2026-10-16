# PDF の文字の基準点（ベースライン上の左端）と、SVG の <text>/<tspan> の x,y を突き合わせる（SVG 検証 (c) の数値版）
import pymupdf as fitz, re, sys
from xml.etree import ElementTree as ET
doc = fitz.open('tqp-futures-v2.pdf'); pg = doc[0]
chars = []
for b in pg.get_text('rawdict')['blocks']:
    for l in b.get('lines', []):
        for s in l['spans']:
            for c in s['chars']:
                chars.append((c['c'], c['origin'][0], c['origin'][1], s['size'], s['font']))
pdftext = ''.join(c[0] for c in chars)
ns = {'s': 'http://www.w3.org/2000/svg'}
root = ET.parse('tqp-futures-v2_illustrator.svg').getroot()
def walk(el, tx=0, ty=0, sc=1):
    t = el.get('transform')
    if t:
        m = re.match(r'translate\(([-\d.]+) ([-\d.]+)\)(?: scale\(([-\d.]+)\))?', t)
        tx, ty = tx + float(m.group(1)) * 1, ty + float(m.group(2))
        if m.group(3): sc = float(m.group(3))
    tag = el.tag.split('}')[1]
    if tag in ('text', 'tspan') and el.text and el.text.strip():
        xs = [float(v) for v in el.get('x', '0').split()]
        yield el.text, tx + xs[0] * sc, ty + float(el.get('y', '0')) * sc
    for ch in el:
        yield from walk(ch, tx, ty, sc)
worst = []
used = set()
for text, x, y in walk(root):
    # PDF 上で同じ文字列の並びを探し、いちばん近い候補と比べる
    best = None
    for i in range(len(chars) - len(text) + 1):
        if chars[i][0] == text[0] and pdftext[i:i + len(text)] == text:
            d = ((chars[i][1] - x) ** 2 + (chars[i][2] - y) ** 2) ** 0.5
            if best is None or d < best[0]:
                best = (d, chars[i][1] - x, chars[i][2] - y)
    if best is None:
        worst.append((999, 0, 0, text)); continue
    worst.append((best[0], best[1], best[2], text))
worst.sort(reverse=True)
print('compared', len(worst), 'runs; max distance %.2fpt' % worst[0][0])
for w in worst[:12]:
    print('%.2f  dx=%.2f dy=%.2f  %s' % (w[0], w[1], w[2], w[3][:30]))
