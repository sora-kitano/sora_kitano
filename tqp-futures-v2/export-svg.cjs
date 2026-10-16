// 完成した index.html の各行の位置を実測し、ページ全体を純粋な SVG として組み直す。
// 出力: tqp-futures-v2_illustrator.svg（Illustrator で文字・図を編集できる形）と svg-preview.png
const fs = require('fs');
const path = require('path');

const PAGE_W = 841.89, PAGE_H = 595.28;   // A4横（pt）

async function collect(page) {
  return page.evaluate(() => {
    const K = 0.75;                                     // px → pt
    const pg = document.getElementById('page').getBoundingClientRect();
    const X = v => (v - pg.left) * K, Y = v => (v - pg.top) * K;
    const HEX = { 'rgb(30, 30, 30)': '#1E1E1E', 'rgb(138, 138, 138)': '#8A8A8A', 'rgb(218, 218, 218)': '#DADADA',
                  'rgb(47, 93, 140)': '#2F5D8C', 'rgb(231, 238, 246)': '#E7EEF6', 'rgb(217, 119, 43)': '#D9772B',
                  'rgb(251, 238, 226)': '#FBEEE2', 'rgb(255, 255, 255)': '#FFFFFF' };
    const hex = c => { if (!HEX[c]) throw new Error('palette外の色: ' + c); return HEX[c]; };
    const fam = ff => /Shippori Mincho/.test(ff.split(',')[0]) ? 'Shippori Mincho' : 'Zen Kaku Gothic New';

    // 書体・太さ・文字サイズごとに「文字の矩形の上端 → ベースライン」の距離を実測する
    // （ブラウザはアセントを整数ピクセルに丸めるので、同じサイズで測る）
    const offCache = {};
    function baselineOffset(family, weight, sizePx) {
      const key = family + weight + '@' + sizePx;
      if (offCache[key] !== undefined) return offCache[key];
      const d = document.createElement('div');
      d.style.cssText = `position:absolute;left:0;top:0;font-family:"${family}";font-weight:${weight};font-size:${sizePx}px;line-height:3;white-space:nowrap;`;
      d.innerHTML = 'あ<i style="display:inline-block;width:0;height:0;vertical-align:baseline"></i>';
      document.body.appendChild(d);
      const rg = document.createRange(); rg.setStart(d.firstChild, 0); rg.setEnd(d.firstChild, 1);
      const top = rg.getClientRects()[0].top, base = d.querySelector('i').getBoundingClientRect().top;
      d.remove();
      return (offCache[key] = base - top);
    }

    // ---- HTMLの文字：1文字ずつ位置を測り、行ごと・書式ごとにまとめる
    const range = document.createRange();
    const blocks = [];
    const blockSel = 'h1, h2, h3, p, footer, .ms';
    document.querySelectorAll(blockSel).forEach(b => {
      if (b.closest('svg')) return;
      const lines = [];
      let cur = null;
      const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const n = walker.currentNode;
        const el = n.parentElement;
        const cs = getComputedStyle(el);
        const family = fam(cs.fontFamily), weight = Number(cs.fontWeight) >= 600 ? 'bold' : 'normal';
        const sizePx = parseFloat(cs.fontSize);
        const perChar = !!el.closest('.title') || (cs.letterSpacing !== 'normal' && parseFloat(cs.letterSpacing) !== 0);
        const style = { family, weight, size: +(sizePx * K).toFixed(2), fill: hex(cs.color), perChar };
        for (let i = 0; i < n.length; i++) {
          const ch = n.nodeValue[i];
          if (/\s/.test(ch)) continue;
          range.setStart(n, i); range.setEnd(n, i + 1);
          const r = range.getClientRects()[0];
          if (!r) continue;
          if (!cur || Math.abs(r.top - cur.top) > 2 || r.left < cur.lastLeft - 1) {
            cur = { top: r.top, lastLeft: r.left, node: n, offset: i, runs: [] }; lines.push(cur);
          }
          let run = cur.runs[cur.runs.length - 1];
          const sk = JSON.stringify(style);
          // 書式が同じでも、余白（margin など）で横に空いたところは別の tspan にして位置を保つ
          const jump = cur.lastRight !== undefined && r.left - cur.lastRight > 0.5;
          if (!run || run.sk !== sk || jump) {
            // 文字もベースラインが整数ピクセルに吸着されて描かれるので、同じ丸めをかける
            const by = r.top + baselineOffset(family, weight === 'bold' ? 700 : 400, sizePx);
            const y = Y(pg.top + Math.round(by - pg.top));
            run = { sk, style, x: X(r.left), y, chars: [], xs: [] }; cur.runs.push(run);
          }
          run.chars.push(ch); run.xs.push(X(r.left));
          cur.lastLeft = r.left; cur.lastRight = r.right;
        }
      }
      blocks.push({ el: b, lines });
    });
    // ---- インラインSVG（図・アイコン・時間軸）：座標系ごと写す
    function ser(node) {
      if (node.nodeType === 3) return node.nodeValue.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      if (node.nodeType !== 1) return '';
      const attrs = {};
      for (const a of node.attributes) attrs[a.name] = a.value;
      if (node.tagName === 'text') {
        // text-anchor は使わず、実測した先頭の位置で左揃えに直す
        if (attrs['text-anchor']) {
          attrs.x = String(Math.round(node.getStartPositionOfChar(0).x * 100) / 100);
          delete attrs['text-anchor'];
        }
      }
      const at = Object.entries(attrs).map(([k, v]) => ` ${k}="${String(v).replace(/"/g, '&quot;')}"`).join('');
      const kids = [...node.childNodes].map(ser).join('');
      return `<${node.tagName}${at}>${kids}</${node.tagName}>`;
    }
    const svgs = [...document.querySelectorAll('#page svg')].map(s => {
      const r = s.getBoundingClientRect();
      const vb = s.viewBox.baseVal;
      const sc = (r.width * K) / vb.width;
      // インラインSVGは描画時に整数ピクセルへ吸着されるので、同じ丸めをかける
      const pl = pg.left + Math.round(r.left - pg.left), pt = pg.top + Math.round(r.top - pg.top);
      return { el: s, id: s.id, x: X(pl), y: Y(pt), scale: sc, body: [...s.childNodes].map(ser).join('') };
    });

    // ---- グループ構成（DOMの順）
    const idOf = el => {
      if (el.closest('.title')) return 'title';
      if (el.closest('.subtitle')) return 'subtitle';
      if (el.closest('.meta')) return 'meta';
      if (el.closest('.lead')) return 'lead';
      if (el.tagName === 'FOOTER') return 'sources';
      return null;
    };
    const out = { header: [], cols: { col1: [], col2: [], col3: [] }, sources: [] };
    const pItems = [];
    // 段ごとに、ブロックと図を DOM 順に並べる
    const order = [...document.querySelectorAll('#page h1, #page h2, #page h3, #page p, #page footer, #page .ms, #page svg')];
    const counters = {};
    order.forEach(el => {
      const col = el.closest('.col');
      const colId = col ? col.id : null;
      let item;
      if (el.tagName.toLowerCase() === 'svg') {
        const s = svgs.find(v => v.el === el);
        const gid = { figS: 'fig-senses', figB: 'fig-hub', figD: 'fig-D-axis', icon1: 'icon-1', icon2: 'icon-2', icon3: 'icon-3' }[el.id];
        item = { kind: 'svg', gid, svg: s };
      } else {
        const b = blocks.find(v => v.el === el);
        let gid = idOf(el);
        if (!gid) {
          const base = colId ? colId.replace('col', 'col') : 'x';
          let k;
          if (el.tagName === 'H2') k = 'heading';
          else if (el.tagName === 'H3') k = 'subheading';
          else if (el.classList.contains('future')) k = 'statement';
          else if (el.classList.contains('ms')) k = 'milestone';
          else k = 'p';
          counters[base + k] = (counters[base + k] || 0) + 1;
          gid = `${base}-${k}${(k === 'heading' || k === 'statement') ? '' : '-' + counters[base + k]}`;
        }
        item = { kind: 'text', gid, lines: b.lines.map(l => l.runs.map(r => ({ style: r.style, x: r.x, y: r.y, text: r.chars.join(''), xs: r.xs }))) };
      }
      item.col = colId;
      item.inAction = el.closest('.act') ? [...document.querySelectorAll('.act')].indexOf(el.closest('.act')) + 1 : 0;
      item.inTimeline = !!el.closest('.ms') || el.id === 'figD';
      if (!colId) {
        if (el.closest('.band')) out.header.push(item); else out.sources.push(item);
      } else out.cols[colId].push(item);
    });
    return out;
  });
}

const f2 = v => (Math.round(v * 100) / 100).toString();
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function textItem(item, ind) {
  const lines = item.lines.map(runs => {
    const first = runs[0];
    const st = first.style;
    const attr = (s, explicit) => `font-family="${s.family}" font-size="${f2(s.size)}"${s.weight === 'bold' ? ' font-weight="bold"' : (explicit ? ' font-weight="normal"' : '')} fill="${s.fill}"`;
    const xAttr = r => r.style.perChar ? r.xs.map(f2).join(' ') : f2(r.x);
    if (runs.length === 1) {
      return `${ind}<text x="${xAttr(first)}" y="${f2(first.y)}" ${attr(st)}>${esc(first.text)}</text>`;
    }
    const tsp = runs.map(r => `<tspan x="${xAttr(r)}" y="${f2(r.y)}" ${attr(r.style, true)}>${esc(r.text)}</tspan>`).join('');
    return `${ind}<text x="${f2(first.x)}" y="${f2(first.y)}" ${attr(st)}>${tsp}</text>`;
  });
  return `${ind}<g id="${item.gid}">\n${lines.join('\n')}\n${ind}</g>`;
}
function svgItem(item, ind) {
  const s = item.svg;
  const tf = `translate(${f2(s.x)} ${f2(s.y)})` + (Math.abs(s.scale - 1) > 1e-4 ? ` scale(${(Math.round(s.scale * 10000) / 10000)})` : '');
  return `${ind}<g id="${item.gid}" transform="${tf}">${s.body}</g>`;
}
function render(item, ind) { return item.kind === 'svg' ? svgItem(item, ind) : textItem(item, ind); }

function buildSvg(data) {
  const L = [];
  L.push('<?xml version="1.0" encoding="UTF-8"?>');
  L.push(`<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="${PAGE_W}pt" height="${PAGE_H}pt" viewBox="0 0 ${PAGE_W} ${PAGE_H}">`);
  L.push(`  <rect id="paper" x="0" y="0" width="${PAGE_W}" height="${PAGE_H}" fill="#FFFFFF"/>`);
  L.push('  <g id="header">');
  data.header.forEach(it => L.push(render(it, '    ')));
  L.push('  </g>');
  const colNames = { col1: 'col1-imagine', col2: 'col2-future', col3: 'col3-actions' };
  for (const c of ['col1', 'col2', 'col3']) {
    L.push(`  <g id="${colNames[c]}">`);
    const items = data.cols[c];
    if (c !== 'col3') items.forEach(it => L.push(render(it, '    ')));
    else {
      // 右段：見出し → 図D（軸と節目）→ ①②③（アイコン・小見出し・本文）
      items.filter(it => !it.inTimeline && !it.inAction).forEach(it => L.push(render(it, '    ')));
      L.push('    <g id="fig-D">');
      items.filter(it => it.inTimeline).forEach(it => L.push(render(it, '      ')));
      L.push('    </g>');
      for (const a of [1, 2, 3]) {
        L.push(`    <g id="action-${a}">`);
        items.filter(it => it.inAction === a).forEach(it => L.push(render(it, '      ')));
        L.push('    </g>');
      }
    }
    L.push('  </g>');
  }
  data.sources.forEach(it => L.push(render(it, '  ')));
  L.push('</svg>');
  return L.join('\n') + '\n';
}

async function exportSvg(browser, page, dir) {
  const data = await collect(page);
  const svg = buildSvg(data);
  const out = path.join(dir, 'tqp-futures-v2_illustrator.svg');
  fs.writeFileSync(out, svg);
  console.log('SVG written:', out, (svg.length / 1024).toFixed(1) + ' KB');
  // svg-preview.png（150dpi相当）
  const p2 = await browser.newPage({ viewport: { width: 1123, height: 794 }, deviceScaleFactor: 150 / 96 });
  await p2.goto('file://' + out);
  await p2.evaluate(() => document.fonts.ready);
  await p2.waitForTimeout(300);
  await p2.screenshot({ path: path.join(dir, 'svg-preview.png'), clip: { x: 0, y: 0, width: 1122.52, height: 793.7 } });
  await p2.close();
  console.log('svg-preview.png written');
}

module.exports = { exportSvg };
