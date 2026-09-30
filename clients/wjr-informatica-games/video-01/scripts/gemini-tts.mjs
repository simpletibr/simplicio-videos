#!/usr/bin/env node
// OPTIONAL / UNTESTED (no GEMINI_API_KEY on the build box): generate the narration with the Gemini API instead of
// clicking through Google AI Studio. Writes assets/audio/vo/external/line-NN.wav (one per spec.voice.lines entry),
// which `VOICE_PROVIDER=file npm run voice` then trims/processes like the AI Studio downloads.
//   export GEMINI_API_KEY=...            (aistudio.google.com -> Get API key; never commit it)
//   export GEMINI_TTS_MODEL=...          (copy the exact model id from AI Studio -> "Get code"; default below is a guess)
//   node scripts/gemini-tts.mjs [vo2 vo5 ...]   (no args = all lines)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const spec = JSON.parse(readFileSync(join(ROOT, "spec.json"), "utf8"));
const key = process.env.GEMINI_API_KEY;
if (!key) { console.error("GEMINI_API_KEY not set"); process.exit(1); }
const model = process.env.GEMINI_TTS_MODEL || "gemini-3.8-flash-preview-tts";
const voice = process.env.GEMINI_TTS_VOICE || "Puck";
const style = process.env.GEMINI_TTS_STYLE ||
  "Locutor brasileiro de propaganda de loja de games, tom animado, natural e próximo, português do Brasil, ritmo ágil sem correr.";
const only = process.argv.slice(2);
const outDir = join(ROOT, spec.voice.providers.file?.dir ?? "assets/audio/vo/external");
mkdirSync(outDir, { recursive: true });

function wav(pcm, sr = 24000) { // Gemini TTS returns raw 16-bit mono PCM at 24 kHz
  const h = Buffer.alloc(44); h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8); h.write("fmt ", 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(sr, 24); h.writeUInt32LE(sr * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(pcm.length, 40); return Buffer.concat([h, pcm]); }

for (const [i, line] of spec.voice.lines.entries()) {
  if (only.length && !only.includes(line.id)) continue;
  const text = `${style}\n\nDiga: ${line.gemini_say ?? line.text}`;
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
    method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text }] }], generationConfig: { responseModalities: ["AUDIO"],
      speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: voice } } } } }),
  });
  if (!res.ok) { console.error(`${line.id}: HTTP ${res.status} ${await res.text()}`); process.exit(1); }
  const data = (await res.json()).candidates?.[0]?.content?.parts?.find((p) => p.inlineData)?.inlineData?.data;
  if (!data) { console.error(`${line.id}: no audio in response`); process.exit(1); }
  const f = join(outDir, `line-${String(i + 1).padStart(2, "0")}.wav`);
  writeFileSync(f, wav(Buffer.from(data, "base64")));
  console.log(`${line.id} -> ${f}`);
}
