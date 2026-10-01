# tqp-futures — トヨタ・コニック・プロ インターン事前課題（A4横・1枚）

| ファイル | 内容 |
|---|---|
| `tqp-futures.pdf` | 提出用PDF（A4横・1ページ・フォント埋め込み） |
| `index.html` | 組版の原本。CSS・SVG・作図スクリプトを1ファイルに内包（Google Fonts を読み込む） |
| `preview.png` | PDFの150dpiプレビュー |
| `tqp-futures_illustrator.svg` | Illustrator で文字・図を編集できるページ全体のSVG（文字はアウトライン化していない） |
| `svg-preview.png` | SVGをブラウザで描画したプレビュー |
| `content.txt` | 原稿（一字一句この通りに載せる。検証の基準） |
| `build.cjs` / `export-svg.cjs` | PDF出力とレイアウト検査 / SVG書き出し（Playwright） |
| `verify.py` / `compare_svg_pdf.py` | 出力物の検証 / PDFとSVGの文字位置の突き合わせ |

## 再生成

```sh
NODE_PATH=$(npm root -g) node build.cjs --svg   # PDF・SVG・svg-preview.png・build/layout.json
python3 verify.py                               # 検証（a〜f、SVG a〜b）＋ preview.png
python3 compare_svg_pdf.py                      # PDFとSVGの文字位置の差（pt）
```

SVGのプレビューを正しく描くには、Shippori Mincho（Regular/Bold）と Zen Kaku Gothic New（Regular/Bold）がOSに入っている必要がある。
