# tqp-futures-v2 — フィードバックを受けて作り直した版（A4横・1枚）

前回版は `../tqp-futures/` にそのまま残している。

| ファイル | 内容 |
|---|---|
| `tqp-futures-v2.pdf` | 提出用PDF（A4横・1ページ・フォント埋め込み） |
| `preview.png` | PDFの150dpiプレビュー |
| `tqp-futures-v2_illustrator.svg` / `svg-preview.png` | Illustrator で編集できるページ全体のSVGと、その描画 |
| `index.html` | 組版の原本（CSS・SVG・作図スクリプトを内包） |
| `content.txt` | 原稿（検証の基準） |

色の意味：藍＝バーチャル・技術（VR、無人タクシー）／橙＝リアル・対面・ハブ（人肌）。

```sh
NODE_PATH=$(npm root -g) node build.cjs --svg && python3 verify.py && python3 compare_svg_pdf.py
```
