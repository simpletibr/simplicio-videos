#!/usr/bin/env node
// OPTIONAL / UNTESTED (no GEMINI_API_KEY on the build box): generate the narration with the Gemini API instead of
// clicking through Google AI Studio. Writes assets/audio/vo/external/line-NN.wav (one per spec.voice.lines entry),
// which `VOICE_PROVIDER=file npm run voice` then trims/processes like the AI Studio downloads.
//   export GEMINI_API_KEY=...            (aistudio.google.com -> Get API key; never commit it)
//   export GEMINI_TTS_MODEL=...          (default gemini-3.8-flash-tts; lite: gemini-3.8-flash-lite-tts)
// Request shape follows https://ai.google.dev/gemini-api/docs/speech-generation (Interactions API, read 30/09/2026):
// Gemini 3.8 TTS reads `text` verbatim, so the delivery style goes in a speech_metadata annotation (never in the text).
//   node scripts/gemini-tts.mjs [vo2 vo5 ...]   (no args = all lines)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const spec = JSON.parse(readFileSync(join(ROOT, "spec.json"), "utf8"));
const key = process.env.GEMINI_API_KEY;
if (!key) { console.error("GEMINI_API_KEY not set"); process.exit(1); }
const model = process.env.GEMINI_TTS_MODEL || "gemini-3.8-flash-tts";
const G = spec.voice.providers.file?.gemini ?? {};
const voice = process.env.GEMINI_TTS_VOICE || G.voice || "Sulafat";
const style = process.env.GEMINI_TTS_STYLE || G.style || "Voz feminina brasileira, calorosa e sorridente.";
const only = process.argv.slice(2);
const outDir = join(ROOT, spec.voice.providers.file?.dir ?? "assets/audio/vo/external");
mkdirSync(outDir, { recursive: true });

function wav(pcm, sr = 24000) { // 3.8 unary returns WAV already; older models returned raw 16-bit mono PCM at 24 kHz
  if (pcm.subarray(0, 4).toString("ascii") === "RIFF") return pcm;
  const h = Buffer.alloc(44); h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8); h.write("fmt ", 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(sr, 24); h.writeUInt32LE(sr * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(pcm.length, 40); return Buffer.concat([h, pcm]); }

for (const [i, line] of spec.voice.lines.entries()) {
  if (only.length && !only.includes(line.id)) continue;
  const res = await fetch("https://generativelanguage.googleapis.com/v1beta/interactions", {
    method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
    body: JSON.stringify({ model,
      input: [{ type: "user_input", content: [{ type: "text", text: line.gemini_say ?? line.text, annotations: [{ type: "speech_metadata", style }] }] }],
      response_format: { type: "audio" }, generation_config: { speech_config: [{ voice }] } }),
  });
  if (!res.ok) { console.error(`${line.id}: HTTP ${res.status} ${await res.text()}`); process.exit(1); }
  const body = await res.json();
  const audio = (body.steps || []).filter((st) => st.type === "model_output").flatMap((st) => st.content || []).filter((c) => c.type === "audio").pop();
  const data = audio?.data;
  if (!data) { console.error(`${line.id}: no audio in response`); process.exit(1); }
  const f = join(outDir, `line-${String(i + 1).padStart(2, "0")}.wav`);
  writeFileSync(f, wav(Buffer.from(data, "base64")));
  console.log(`${line.id} -> ${f}`);
}
