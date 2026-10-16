// index.html → tqp-futures.pdf（＋レイアウト検査）
// 使い方: NODE_PATH=$(npm root -g) node build.cjs [--svg]
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DIR = __dirname;
const HTML = 'file://' + path.join(DIR, 'index.html');

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1123, height: 794 } });
  const failed = [];
  page.on('requestfailed', r => failed.push(r.url() + ' ' + (r.failure() || {}).errorText));
  await page.goto(HTML, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  return { page, failed };
}

// (f) と組版の検査をブラウザ内で行う
async function layoutChecks(page) {
  return page.evaluate(() => {
    const res = { overflow: [], outside: [], shortLast: [], lineStartPunct: [], splitTokens: [], lines: [], fonts: [] };
    const pg = document.getElementById('page').getBoundingClientRect();
    // 枠からのはみ出し
    // scrollHeight/clientHeight は整数に丸められるため 1px の誤差を許し、
    // 併せて子要素の下端・右端（小数）が枠の内側に収まっているかも確かめる
    document.querySelectorAll('.band, .tblock, .rblock, .col, .tl, .src, p, h1, h2, h3, figure').forEach(el => {
      const r = el.getBoundingClientRect();
      let maxB = r.top, maxR = r.left;
      el.querySelectorAll('*').forEach(c => { const cr = c.getBoundingClientRect(); if (cr.width || cr.height) { maxB = Math.max(maxB, cr.bottom); maxR = Math.max(maxR, cr.right); } });
      const scrollOver = el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
      const childOver = maxB > r.bottom + 0.5 || maxR > r.right + 0.5;
      if (scrollOver || childOver) {
        res.overflow.push({ el: el.className || el.tagName, id: el.id, sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth, childOverPx: +(maxB - r.bottom).toFixed(2) });
      }
    });
    // ページ外に出る要素（SVGの子要素を含む）
    document.querySelectorAll('#page *').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      if (r.left < pg.left - 0.5 || r.top < pg.top - 0.5 || r.right > pg.right + 0.5 || r.bottom > pg.bottom + 0.5) {
        res.outside.push({ tag: el.tagName, cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className), r: [r.left, r.top, r.right, r.bottom].map(v => Math.round(v)) });
      }
    });
    // 段落ごとの行を文字単位で取り出す
    const blocks = document.querySelectorAll('p, h1, h2, h3, footer, .ms');
    const range = document.createRange();
    blocks.forEach(b => {
      const lines = [];
      const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
      let cur = null;
      while (walker.nextNode()) {
        const n = walker.currentNode;
        for (let i = 0; i < n.length; i++) {
          range.setStart(n, i); range.setEnd(n, i + 1);
          const rs = range.getClientRects();
          if (!rs.length) continue;
          const r = rs[0];
          if (!cur || Math.abs(r.top - cur.top) > 2) { cur = { top: r.top, left: r.left, text: '' }; lines.push(cur); }
          cur.text += n.nodeValue[i];
          cur.right = r.right;
        }
      }
      const name = b.tagName + (b.className ? '.' + b.className : '') + ':' + (b.textContent.slice(0, 12));
      const right = b.getBoundingClientRect().right;
      res.lines.push({ name, n: lines.length, lens: lines.map(l => l.text.length), widthPt: (b.getBoundingClientRect().width * 0.75).toFixed(1) });
      if (b.tagName === 'P' && lines.length > 1) {
        const lastLen = [...lines[lines.length - 1].text].length;
        if (lastLen <= 2) res.shortLast.push({ name, last: lines[lines.length - 1].text });
      }
      lines.forEach((l, i) => { if (i > 0 && /^[、。」）％・：]/.test(l.text)) res.lineStartPunct.push({ name, line: l.text }); });
    });
    // 数字と単位のまとまりが1行に収まっているか
    document.querySelectorAll('.nw').forEach(s => { const rs = s.getClientRects(); if (rs.length > 1) res.splitTokens.push(s.textContent); });
    // 実際に使われたフォント
    res.fonts = [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight).filter((v, i, a) => a.indexOf(v) === i);
    res.sizes = {};
    document.querySelectorAll('#page *').forEach(el => {
      if (el.closest('svg')) return;
      const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim());
      if (!hasText) return;
      const fsz = parseFloat(getComputedStyle(el).fontSize) * 0.75;
      res.sizes[fsz.toFixed(2)] = (res.sizes[fsz.toFixed(2)] || 0) + 1;
    });
    res.svgTextSizes = [...new Set([...document.querySelectorAll('svg text')].map(t => parseFloat(t.getAttribute('font-size'))))].sort((a, b) => a - b);
    // 段の下端の余り（mm）
    res.colSlack = [...document.querySelectorAll('.col')].map(c => {
      const cr = c.getBoundingClientRect();
      let maxB = 0;
      c.querySelectorAll('p, figure, h2, h3, .ms').forEach(e => { maxB = Math.max(maxB, e.getBoundingClientRect().bottom); });
      return { id: c.id, slackMm: ((cr.bottom - maxB) * 25.4 / 96).toFixed(1) };
    });
    res.fig = window.__FIG;
    return res;
  });
}

(async () => {
  const browser = await chromium.launch({ proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
  const { page, failed } = await openPage(browser);
  const chk = await layoutChecks(page);
  fs.mkdirSync(path.join(DIR, 'build'), { recursive: true });
  fs.writeFileSync(path.join(DIR, 'build', 'layout.json'), JSON.stringify(chk, null, 1));
  console.log('request failures:', failed.length ? failed : 'none');
  console.log('fonts loaded:', chk.fonts.join(' / '));
  console.log('overflow:', JSON.stringify(chk.overflow));
  console.log('outside page:', JSON.stringify(chk.outside));
  console.log('short last lines:', JSON.stringify(chk.shortLast));
  console.log('punct at line start:', JSON.stringify(chk.lineStartPunct));
  console.log('split number tokens:', JSON.stringify(chk.splitTokens));
  console.log('col slack:', JSON.stringify(chk.colSlack));
  console.log('html text sizes (pt:count):', JSON.stringify(chk.sizes));
  console.log('svg text sizes (pt):', JSON.stringify(chk.svgTextSizes));
  await page.pdf({ path: path.join(DIR, 'tqp-futures-v2.pdf'), preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  console.log('PDF written');
  if (process.argv.includes('--svg')) {
    const { exportSvg } = require('./export-svg.cjs');
    await exportSvg(browser, page, DIR);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
