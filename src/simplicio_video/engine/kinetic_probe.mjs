// kinetic_probe.mjs — layout guard for motion/patterns/kinetic-words (headless Chrome, same engine HyperFrames uses).
// usage: node kinetic_probe.mjs <block.html> <assets_root_dir> <jobs.json>   (jobs: [{id, vars, step}])
// For each job: mounts the block with the given variables, seeks the timeline every `step` s and measures every word
// (getBoundingClientRect, transforms included). Reports the assembled text per line, the smallest gap between two
// neighbouring visible words (px and em) and anything that leaves the 1080x1920 frame (words, panel, logo).
// env: PUPPETEER_CORE (module dir), CHROME_BIN (chrome-headless-shell), GSAP_JS (local gsap; the block's CDN tag is swapped).
import fs from "node:fs"; import path from "node:path"; import os from "node:os"; import { createRequire } from "node:module";
const [blockPath, assetsRoot, jobsPath] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER_CORE);
const block = fs.readFileSync(blockPath, "utf8");
const t0 = block.indexOf("<template>", block.indexOf("<body"));
const inner = block.slice(t0 + 10, block.lastIndexOf("</template>"))
  .replace(/<script src="[^"]*gsap[^"]*"><\/script>/, `<script src="file://${process.env.GSAP_JS}"></script>`);
const jobs = JSON.parse(fs.readFileSync(jobsPath, "utf8"));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "kprobe-"));
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_BIN, headless: true,
  args: ["--no-sandbox", "--allow-file-access-from-files", "--disable-gpu", "--font-render-hinting=none"] });
const out = [];
try {
  const page = await browser.newPage();
  const errs = []; page.on("pageerror", (e) => errs.push(String(e))); page.on("requestfailed", (q) => errs.push("requestfailed " + q.url()));
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  for (const job of jobs) {
    const html = `<!doctype html><html><head><meta charset="utf-8"><base href="file://${path.resolve(assetsRoot)}/">
<style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#333}</style>
<script>window.__hyperframes={getVariables:()=>(${JSON.stringify(job.vars)})};</script></head><body>${inner}</body></html>`;
    const f = path.join(tmp, `job-${out.length}.html`); fs.writeFileSync(f, html);
    await page.goto("file://" + f, { waitUntil: "load" });
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((i) => i.decode().catch(() => null))); });
    if (errs.length) process.stderr.write(errs.join("\n") + "\n");
    const r = await page.evaluate((dur, step) => {
      const tl = window.__timelines["kinetic-words"], root = document.getElementById("kinetic-words-root");
      const lns = [...root.querySelectorAll(".ln")];
      const text = lns.map((ln) => [...ln.querySelectorAll(".w")].map((w) => w.textContent).join(" "));
      const fs = parseFloat(getComputedStyle(root.querySelector(".kw")).fontSize);
      let min = { px: 1e9 }, oob = [];
      for (let t = 0; t <= dur + 1e-6; t += step) {
        tl.seek(t, false);
        lns.forEach((ln, li) => {
          const ws = [...ln.querySelectorAll(".w")].map((w) => ({ w: w.textContent, r: w.getBoundingClientRect(), o: parseFloat(getComputedStyle(w).opacity) }));
          for (let i = 0; i + 1 < ws.length; i++) {
            const a = ws[i], b = ws[i + 1];
            if (a.o < 0.5 || b.o < 0.5 || a.r.width < 2 || b.r.width < 2) continue;
            const g = b.r.left - a.r.right;
            if (g < min.px) min = { px: Math.round(g * 10) / 10, t: Math.round(t * 1000) / 1000, between: `${a.w}|${b.w}`, line: li };
          }
          ws.forEach((x) => { if (x.o >= 0.5 && x.r.width > 2 && (x.r.left < 0 || x.r.right > 1080 || x.r.top < 0 || x.r.bottom > 1920))
            oob.push({ t: Math.round(t * 1000) / 1000, w: x.w, l: Math.round(x.r.left), r: Math.round(x.r.right) }); });
        });
        for (const sel of [".pn", ".kl"]) { const el = root.querySelector(sel); if (!el) continue; const b = el.getBoundingClientRect();
          if (b.width > 2 && (b.left < 0 || b.right > 1080 || b.top < 0 || b.bottom > 1920)) oob.push({ t: Math.round(t * 1000) / 1000, w: sel, l: Math.round(b.left), r: Math.round(b.right) }); }
      }
      return { text, fs, min_gap_px: min.px === 1e9 ? null : min.px, min_gap_em: min.px === 1e9 ? null : Math.round(min.px / fs * 1000) / 1000, min_gap_at: min, out_of_frame: oob.slice(0, 8), out_of_frame_n: oob.length };
    }, Number(job.vars.dur || 4), Number(job.step || 1 / 30));
    out.push({ id: job.id, ...r });
  }
} finally { await browser.close(); fs.rmSync(tmp, { recursive: true, force: true }); }
process.stdout.write(JSON.stringify(out));
