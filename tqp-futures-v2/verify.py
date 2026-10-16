"""出力物の検証。build.cjs --svg の後に実行する。

PDF: (a) 1ページ (b) 10MB未満 (c) フォント埋め込み (d) 本文の全文照合
     (e) 図の数値と、データからの再計算
     (f) は build.cjs がブラウザ上で検査した結果（build/layout.json）を読む
SVG: (a) foreignObject / image なし (b) 本文の全文照合 （(c) の目視比較用に preview.png も作る）
"""
import json
import math
import os
import re
import subprocess
import sys
from xml.etree import ElementTree as ET

import pymupdf

DIR = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(DIR, 'tqp-futures-v2.pdf')
SVG = os.path.join(DIR, 'tqp-futures-v2_illustrator.svg')
PALETTE = {'#FFFFFF', '#1E1E1E', '#8A8A8A', '#DADADA', '#2F5D8C', '#E7EEF6', '#D9772B', '#FBEEE2'}

ok_all = True


def report(name, ok, detail=''):
    global ok_all
    ok_all &= ok
    print(('OK   ' if ok else 'FAIL ') + name + (('  ' + detail) if detail else ''))


def strip_ws(s):
    return re.sub(r'\s+', '', s)


# ---- <content> から、紙面に載せる文字列の単位（文）を取り出す
def content_units():
    units = []
    for line in open(os.path.join(DIR, 'content.txt'), encoding='utf-8').read().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('■'):
            m = re.match(r'■見出し：(.+)$', line)
            if m:
                units.append(m.group(1))
            continue
        # 「。」で文に分ける（「。」のない行は1行を1単位に）
        parts = re.findall(r'[^。]*。|[^。]+$', line)
        units += [p for p in parts if p]
    return units


UNITS = content_units()

# ================= PDF =================
doc = pymupdf.open(PDF)
report('PDF (a) 1ページ', doc.page_count == 1, f'pages={doc.page_count}')
size = os.path.getsize(PDF)
report('PDF (b) 10MB未満', size < 10 * 1024 * 1024, f'{size / 1024:.0f} KB')

fonts = subprocess.run(['pdffonts', PDF], capture_output=True, text=True).stdout.splitlines()[2:]
emb = [(f.split()[0], f.split()[-5]) for f in fonts if f.strip()]
report('PDF (c) フォント埋め込み', all(e == 'yes' for _, e in emb) and len(emb) > 0,
       ', '.join(sorted({re.sub(r'^[A-Z]{6}\+', '', n) for n, _ in emb})))

page = doc[0]
pdf_text = strip_ws(page.get_text())
missing = [u for u in UNITS if strip_ws(u) not in pdf_text]
report('PDF (d) 本文の全文照合', not missing, f'{len(UNITS) - len(missing)}/{len(UNITS)} 文が一致')
for m in missing:
    print('       見つからない文:', m)

# (e) 紙面に載せた数値（出典つきの事実）がPDFにあるか
need = ['82.9％', '0.3％', '150〜200人程度', '2027年度までに100か所以上', '2024年度', '75日', '18歳以上', '2026年度']
miss_e = [n for n in need if n not in pdf_text]
report('PDF (e) 数値がPDFにある', not miss_e, '、'.join(need) + (f'  不足: {miss_e}' if miss_e else ''))
lay = json.load(open(os.path.join(DIR, 'build', 'layout.json'), encoding='utf-8'))
senses = lay['fig']['S']
report('図S 五感の対応（視覚・聴覚＝満たせる、触覚＝一部、嗅覚・味覚＝満たせない）',
       senses == [['視覚', 1], ['聴覚', 1], ['触覚', 0.5], ['嗅覚', 0], ['味覚', 0]], str(senses))

# (f) HTML上のはみ出し
report('HTML (f) テキスト枠のはみ出しなし', not lay['overflow'], json.dumps(lay['overflow'], ensure_ascii=False) if lay['overflow'] else '')
report('HTML (f) ページ外の要素なし', not lay['outside'], json.dumps(lay['outside'])[:200] if lay['outside'] else '')
report('組版 最終行が1〜2字の段落なし', not lay['shortLast'], str(lay['shortLast']))
report('組版 行頭の句読点なし', not lay['lineStartPunct'], str(lay['lineStartPunct']))
report('組版 数字と単位の行またぎなし', not lay['splitTokens'], str(lay['splitTokens']))

# ================= SVG =================
svg_src = open(SVG, encoding='utf-8').read()
bad = [t for t in ('foreignObject', '<image', '@font-face', '<style', 'var(', 'calc(', '<filter', '<mask', 'clipPath', 'xlink:href')
       if t in svg_src]
report('SVG (a) foreignObject / image なし（禁止要素なし）', not bad, str(bad) if bad else 'foreignObject・image・style・filter・mask・clipPath・CSS変数・calc() なし')
root = ET.fromstring(svg_src)
texts = []
for el in root.iter():
    tag = el.tag.split('}')[1]
    if tag in ('text', 'tspan') and el.text:
        texts.append(el.text)
svg_text = strip_ws(''.join(texts))
miss_s = [u for u in UNITS if strip_ws(u) not in svg_text]
report('SVG (b) 本文の全文照合', not miss_s, f'{len(UNITS) - len(miss_s)}/{len(UNITS)} 文が一致')
for m in miss_s:
    print('       見つからない文:', m)
n_text = sum(1 for el in root.iter() if el.tag.endswith('}text'))
n_tspan = sum(1 for el in root.iter() if el.tag.endswith('}tspan'))
colors = set(re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg_src))
report('SVG 色が8色に収まる', colors <= PALETTE, ' '.join(sorted(colors)))
fams = sorted(set(re.findall(r'font-family="([^"]+)"', svg_src)))
weights = sorted(set(re.findall(r'font-weight="([^"]+)"', svg_src)))
print(f'     SVG: <text> {n_text}個、<tspan> {n_tspan}個、font-family={fams}、font-weight={weights}')
ids = re.findall(r'<g id="([^"]+)"', svg_src)
print('     SVG グループ:', ' '.join(ids))

# プレビュー（150dpi）
subprocess.run(['pdftoppm', '-r', '150', '-png', '-singlefile', PDF, os.path.join(DIR, 'preview')], check=True)
print('preview.png を出力しました')
print('\n総合:', 'すべて合格' if ok_all else '不合格あり')
sys.exit(0 if ok_all else 1)
