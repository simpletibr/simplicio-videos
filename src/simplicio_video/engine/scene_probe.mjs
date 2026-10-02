// scene_probe.mjs — "nothing covers text" guard for a whole scene (all blocks of the scene mounted together, z = track).
// usage: node scene_probe.mjs <assets_root_dir> <jobs.json>   jobs: [{id, blocks: [{id, src, vars, start, dur, track}], t0, t1, step}]
// Every `step` s it collects, per block: text boxes (Range rects of visible text nodes) and shape boxes (visible elements with a
// background/border/img/svg fill and no own text). Reports (a) a shape painted above a text box it is not an ancestor of and
// (b) text boxes of different elements overlapping. Ignores full-frame layers (backgrounds) and invisible/zero-size nodes.
// env: PUPPETEER_CORE, CHROME_BIN, GSAP_JS (as kinetic_probe.mjs)
import fs from "node:fs"; import path from "node:path"; import os from "node:os"; import { createRequire } from "node:module";
const [assetsRoot, jobsPath] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER_CORE);
const jobs = JSON.parse(fs.readFileSync(jobsPath, "utf8"));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sprobe-"));
const inner = (src) => { const b = fs.readFileSync(src, "utf8"); const t0 = b.indexOf("<template>", b.indexOf("<body"));
  return b.slice(t0 + 10, b.lastIndexOf("</template>")).replace(/<script src="[^"]*gsap[^"]*"><\/script>/, ""); };
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_BIN, headless: true,
  args: ["--no-sandbox", "--allow-file-access-from-files", "--disable-gpu", "--font-render-hinting=none"] });
const out = [];
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  for (const job of jobs) {
    const body = job.blocks.map((b, i) => `<script>window.__hyperframes={getVariables:()=>(${JSON.stringify(b.vars)})};</script>
<div class="blk" data-blk="${b.id}" data-start="${b.start}" data-comp="${b.comp}" style="position:absolute;inset:0;z-index:${b.track}">${inner(b.src)}</div>`).join("\n");
    const html = `<!doctype html><html><head><meta charset="utf-8"><base href="file://${path.resolve(assetsRoot)}/">
<style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#333}</style>
<script src="file://${process.env.GSAP_JS}"></script></head><body>${body}</body></html>`;
    const f = path.join(tmp, `job-${out.length}.html`); fs.writeFileSync(f, html);
    await page.goto("file://" + f, { waitUntil: "load" });
    await page.evaluate((m) => { window.__measure = m; }, job.measure || []);
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((i) => i.decode().catch(() => null))); await new Promise((r) => setTimeout(r, 50)); });
    const r = await page.evaluate((t0, t1, step) => {
      const blks = [...document.querySelectorAll(".blk")];
      const vis = (el) => { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e);
        if (cs.display === "none" || cs.visibility === "hidden") return 0; o *= parseFloat(cs.opacity); } return o; };
      const inter = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
      const box = (r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom, w: r.width, h: r.height });
      const hits = new Map();
      for (let t = t0; t <= t1 + 1e-6; t += step) {
        const texts = [], shapes = [];
        blks.forEach((bk, bi) => {
          const comp = bk.dataset.comp, tl = window.__timelines[comp]; if (!tl) return;
          const lt = t - Number(bk.dataset.start); if (lt < 0 || lt > tl.duration() + 1e-6) return;
          tl.seek(lt, false);
          const all = [...bk.querySelectorAll("*")];
          all.forEach((el, order) => {
            if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return;
            const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
            const o = vis(el); if (o < 0.3) return;
            if (own.length) { own.forEach((n) => { const rg = document.createRange(); rg.selectNodeContents(n); const rr = rg.getBoundingClientRect();
              if (rr.width > 2 && rr.height > 2) texts.push({ bi, order, el, txt: n.textContent.trim().slice(0, 40), r: box(rr), blk: bk.dataset.blk }); }); return; }
            const rr = el.getBoundingClientRect(); if (rr.width < 8 || rr.height < 8 || (rr.width > 900 && rr.height > 1500)) return;
            const cs = getComputedStyle(el), bg = cs.backgroundColor, m = bg.match(/rgba?\(([^)]+)\)/);
            const alpha = m ? (m[1].split(",")[3] === undefined ? 1 : parseFloat(m[1].split(",")[3])) : 0;
            const svgFill = el instanceof SVGElement && el.tagName !== "svg" && ((cs.fill && cs.fill !== "none" && parseFloat(cs.fillOpacity) > 0.3) || (cs.stroke && cs.stroke !== "none"));
            const painted = alpha > 0.3 || el.tagName === "IMG" || svgFill || (parseFloat(cs.borderTopWidth) > 2 && cs.borderTopStyle !== "none");
            if (painted) shapes.push({ bi, order, el, tag: el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : ""), r: box(rr), blk: bk.dataset.blk, empty: !el.textContent.trim() });
          });
        });
        for (const tx of texts) {
          const ta = tx.r.w * tx.r.h;
          for (const sh of shapes) {
            if (sh.el.contains(tx.el)) continue;  // panel/chip behind its own text
            const above = sh.bi !== tx.bi ? Number(blks[sh.bi].style.zIndex) > Number(blks[tx.bi].style.zIndex) || (Number(blks[sh.bi].style.zIndex) === Number(blks[tx.bi].style.zIndex) && sh.bi > tx.bi)
                                          : (sh.order > tx.order && !tx.el.contains(sh.el));
            if (!above) continue;
            const a = inter(sh.r, tx.r); if (a < 120 || a < 0.06 * ta) continue;
            const k = `forma ${sh.blk}:${sh.tag}${sh.empty ? " (vazia)" : ""} cobre "${tx.txt}" (${tx.blk})`;
            if (!hits.has(k)) hits.set(k, { t: Math.round(t * 100) / 100, n: 0, area: Math.round(a) }); hits.get(k).n++;
          }
          for (const o of texts) {
            if (o === tx || o.el === tx.el || o.el.contains(tx.el) || tx.el.contains(o.el) || o.blk + o.txt <= tx.blk + tx.txt) continue;
            const a = inter(o.r, tx.r); if (a < 0.25 * Math.min(ta, o.r.w * o.r.h)) continue;  // text boxes include the font's ascent/descent: neighbouring lines touch ~7% by design
            if (o.bi === tx.bi && o.el.parentElement === tx.el.parentElement) continue;
            const k = `texto "${o.txt}" (${o.blk}) sobre "${tx.txt}" (${tx.blk})`;
            if (!hits.has(k)) hits.set(k, { t: Math.round(t * 100) / 100, n: 0, area: Math.round(a) }); hits.get(k).n++;
          }
        }
      }
      // shapes over text count from one frame on; text over text only when it lasts (word drop-ins cross the line above for a few frames by design)
      const measure = {};  // optional: rects of selectors at the end of the window (tests)
      (window.__measure || []).forEach((sel) => { const el = document.querySelector(sel); if (!el) return; const r = el.getBoundingClientRect();
        measure[sel] = { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), shown: vis(el) > 0.3 && r.width > 0 }; });
      window.__measured = measure;
      return { hits: [...hits.entries()].filter(([k, v]) => k.startsWith("forma") || v.n * step >= 0.4).map(([k, v]) => ({ what: k, ...v })), measure };
    }, job.t0, job.t1, job.step || 1 / 15);
    out.push({ id: job.id, hits: r.hits, measure: r.measure });
  }
} finally { await browser.close(); fs.rmSync(tmp, { recursive: true, force: true }); }
process.stdout.write(JSON.stringify(out));
