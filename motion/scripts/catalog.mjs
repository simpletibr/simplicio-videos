#!/usr/bin/env node
// Rebuild motion/catalog.json and the catalog table in motion/README.md from patterns/*/pattern.json.
// Checks the fields the schema requires and that files referenced by "pronto" patterns exist.
// Usage: node motion/scripts/catalog.mjs [--check]   (--check: fail if README/catalog would change)
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const MOTION = join(dirname(fileURLToPath(import.meta.url)), "..");
const REQ = ["id", "title", "description", "status", "category", "tags", "use_when", "source"];
const ORDER = { pronto: 0, lib: 1, inline: 2, proposto: 3 };
const errors = [];
const pats = readdirSync(join(MOTION, "patterns"), { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => {
  const dir = join(MOTION, "patterns", d.name), p = JSON.parse(readFileSync(join(dir, "pattern.json"), "utf8"));
  for (const k of REQ) if (p[k] === undefined) errors.push(`${d.name}: missing ${k}`);
  if (p.id !== d.name) errors.push(`${d.name}: id "${p.id}" != folder`);
  if (p.status === "pronto") for (const f of ["block.html", "preview.png"]) if (!existsSync(join(dir, f))) errors.push(`${d.name}: status pronto but ${f} missing`);
  return p;
}).sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.category.localeCompare(b.category) || a.id.localeCompare(b.id));
if (errors.length) { console.error(errors.join("\n")); process.exit(1); }

const catalog = { schema: "simplicio.motion-catalog/v1", count: pats.length,
  by_status: Object.fromEntries(Object.keys(ORDER).map((s) => [s, pats.filter((p) => p.status === s).length])),
  patterns: pats.map((p) => ({ id: p.id, title: p.title, status: p.status, category: p.category, tags: p.tags, duration_s: p.duration_s ?? null,
    params: (p.params || []).map((x) => x.id), block: p.status === "pronto" ? `patterns/${p.id}/block.html` : null,
    preview: p.status === "pronto" ? `patterns/${p.id}/preview.png` : null, source: p.source.url || p.source.ref })) };
const catJson = JSON.stringify(catalog, null, 2) + "\n";

const esc = (s) => String(s).replace(/\|/g, "\\|");
const srcCell = (s) => (s.url ? `[${esc(s.kind)}](${s.url})` : esc(s.kind === "interno" ? s.ref.replace(/ \(.*$/, "") : s.ref));
const rows = pats.map((p) => `| ${p.status === "pronto" ? `<img src="patterns/${p.id}/preview.png" width="90">` : ""} | **[${p.id}](patterns/${p.id}/)**<br>${esc(p.title)} | ${p.status} | ${esc(p.category)} | ${p.params ? p.params.map((x) => "`" + x.id + "`").join(" ") : "—"} | ${esc(p.use_when)} | ${srcCell(p.source)} |`);
const table = ["<!-- catalog:start (gerado por motion/scripts/catalog.mjs — não edite à mão) -->",
  `${pats.length} padrões: ${Object.entries(catalog.by_status).map(([k, v]) => `${v} ${k}`).join(", ")}.`, "",
  "| Preview | Padrão | Status | Categoria | Parâmetros | Quando usar | Fonte |", "|---|---|---|---|---|---|---|", ...rows, "<!-- catalog:end -->"].join("\n");
const readmePath = join(MOTION, "README.md"), readme = readFileSync(readmePath, "utf8");
const newReadme = readme.replace(/<!-- catalog:start[\s\S]*?<!-- catalog:end -->/, table);
const catPath = join(MOTION, "catalog.json"), oldCat = existsSync(catPath) ? readFileSync(catPath, "utf8") : "";
if (process.argv.includes("--check")) {
  if (newReadme !== readme || catJson !== oldCat) { console.error("catalog out of date: run node motion/scripts/catalog.mjs"); process.exit(1); }
  console.log(`catalog ok (${pats.length})`); process.exit(0);
}
writeFileSync(catPath, catJson); writeFileSync(readmePath, newReadme);
console.log(`catalog: ${pats.length} patterns (${Object.entries(catalog.by_status).map(([k, v]) => `${k} ${v}`).join(", ")})`);
