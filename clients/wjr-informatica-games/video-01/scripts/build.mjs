#!/usr/bin/env node
// Deterministic build step for video-01 (no network, no LLM, no third-party audio):
//   0) normalizes optional video plates (spec.clips) or writes black stand-ins + <id>_on flags
//   1) splits spec.json -> build/variables.json (HyperFrames --variables-file)
//   2) synthesizes an original 120 BPM track + SFX from spec.json "audio" cues, adds the cached VO lines
//      (spec.json "voice", rendered by scripts/voice.py) and ducks music/SFX under the voice
//   3) mixes them (sidechain pump, SFX ducking, fade in/out) -> build/mix.raw.wav
//   4) loudness-normalizes with ffmpeg loudnorm (2-pass) -> assets/audio/build/mix.wav
// Same spec.json => bit-identical audio (seeded PRNG).
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const spec = JSON.parse(readFileSync(join(ROOT, "spec.json"), "utf8"));
const { variables, audio } = spec;
mkdirSync(join(ROOT, "build"), { recursive: true });
mkdirSync(join(ROOT, "assets/audio/build"), { recursive: true });
// ---------- video plates (e.g. Grok Imagine clips) ----------
// Present file  -> normalized to 1080x1920/30fps/muted at slot.out, variable <id>_on = true.
// Missing file  -> tiny black stand-in at slot.out (so the static <video src> always resolves), <id>_on = false,
//                  and the scene keeps its image/graphic design.
const plates = [];
for (const slot of spec.clips?.slots ?? []) {
  const src = join(ROOT, slot.file), out = join(ROOT, slot.out), on = existsSync(src);
  mkdirSync(dirname(out), { recursive: true });
  const common = ["-y", "-hide_banner", "-loglevel", "error"];
  const enc = ["-an", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "1", "-movflags", "+faststart"];
  if (on) {
    execFileSync("ffmpeg", [...common, "-ss", String(slot.media_start_s ?? 0), "-i", src, "-t", String(slot.duration + 0.5),
      "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,tpad=stop_mode=clone:stop_duration=4", ...enc, out]);
  } else {
    execFileSync("ffmpeg", [...common, "-f", "lavfi", "-i", `color=c=black:s=1080x1920:r=30:d=${slot.duration + 0.5}`, ...enc, out]);
  }
  variables[`${slot.id}_on`] = on;
  plates.push(`${slot.id}:${on ? "on" : "off"}`);
}
writeFileSync(join(ROOT, "build/variables.json"), JSON.stringify(variables, null, 2));

const SR = 48000;
const DUR = audio.duration_s;
const N = Math.round(SR * DUR);
const BEAT = 60 / audio.bpm;
const L = new Float32Array(N), R = new Float32Array(N); // music bus
const SL = new Float32Array(N), SRr = new Float32Array(N); // sfx bus

// ---------- helpers ----------
function mulberry32(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const rnd = mulberry32(audio.seed ?? 1234);
const noise = () => rnd() * 2 - 1;
const TAU = Math.PI * 2;
const midi = (m) => 440 * Math.pow(2, (m - 69) / 12);
const db = (d) => Math.pow(10, d / 20);
function biquad(type) { // RBJ biquad with settable coefficients
  let b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0, x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  return {
    set(f, q = 0.707) {
      f = Math.min(Math.max(f, 20), SR * 0.45); const w = TAU * f / SR, c = Math.cos(w), s = Math.sin(w), al = s / (2 * q);
      let B0, B1, B2; const A0 = 1 + al;
      if (type === "lp") { B0 = (1 - c) / 2; B1 = 1 - c; B2 = (1 - c) / 2; }
      else if (type === "hp") { B0 = (1 + c) / 2; B1 = -(1 + c); B2 = (1 + c) / 2; }
      else { B0 = al; B1 = 0; B2 = -al; } // bp
      b0 = B0 / A0; b1 = B1 / A0; b2 = B2 / A0; a1 = (-2 * c) / A0; a2 = (1 - al) / A0;
    },
    run(x) { const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2; x2 = x1; x1 = x; y2 = y1; y1 = y; return y; },
  };
}
function add(bufL, bufR, t0, samples, gain = 1, pan = 0) { // samples: Float32Array mono
  const i0 = Math.round(t0 * SR), gl = gain * Math.cos((pan + 1) * Math.PI / 4), gr = gain * Math.sin((pan + 1) * Math.PI / 4);
  for (let i = 0; i < samples.length; i++) { const j = i0 + i; if (j < 0 || j >= N) continue; bufL[j] += samples[i] * gl; bufR[j] += samples[i] * gr; }
}
const len = (s) => new Float32Array(Math.round(s * SR));

// ---------- instruments ----------
function kick() { const o = len(0.45); let ph = 0; for (let i = 0; i < o.length; i++) { const t = i / SR; const f = 45 + 120 * Math.exp(-t * 28); ph += TAU * f / SR; o[i] = Math.sin(ph) * Math.exp(-t * 7) + (t < 0.004 ? noise() * 0.5 : 0); } return o; }
function clap() { const o = len(0.3), bp = biquad("bp"); bp.set(1400, 0.9); for (let i = 0; i < o.length; i++) { const t = i / SR; let e = Math.exp(-t * 18); for (const d of [0, 0.011, 0.022]) if (t >= d && t < d + 0.01) e = Math.max(e, 1); o[i] = bp.run(noise()) * e * 1.6; } return o; }
function hat(open = false) { const o = len(open ? 0.25 : 0.06), hp = biquad("hp"); hp.set(7500, 0.8); const k = open ? 14 : 70; for (let i = 0; i < o.length; i++) o[i] = hp.run(noise()) * Math.exp(-(i / SR) * k); return o; }
function bassNote(freq, dur) { const o = len(dur), lp = biquad("lp"); let ph = 0; for (let i = 0; i < o.length; i++) { const t = i / SR; lp.set(180 + 900 * Math.exp(-t * 16), 1.2); ph = (ph + freq / SR) % 1; const saw = 2 * ph - 1; const sub = Math.sin(TAU * ph); o[i] = lp.run(saw * 0.6 + sub * 0.5) * Math.min(1, t * 400) * Math.min(1, (dur - t) * 60); } return o; }
function pluck(freq, dur = 0.22) { const o = len(dur), lp = biquad("lp"); let p1 = 0, p2 = 0; for (let i = 0; i < o.length; i++) { const t = i / SR; lp.set(900 + 5000 * Math.exp(-t * 22), 0.9); p1 = (p1 + freq / SR) % 1; p2 = (p2 + (freq * 1.006) / SR) % 1; const sq = (p1 < 0.5 ? 1 : -1) * 0.5 + (2 * p2 - 1) * 0.5; o[i] = lp.run(sq) * Math.exp(-t * 11) * Math.min(1, t * 800); } return o; }
function pad(freqs, dur) { const o = len(dur), lp = biquad("lp"); lp.set(1200, 0.7); const ph = freqs.flatMap(() => [0, 0, 0]); for (let i = 0; i < o.length; i++) { const t = i / SR; let s = 0; freqs.forEach((f, k) => { [-0.08, 0, 0.08].forEach((d, m) => { const idx = k * 3 + m; ph[idx] = (ph[idx] + (f * Math.pow(2, d / 12)) / SR) % 1; s += 2 * ph[idx] - 1; }); }); o[i] = lp.run(s / (freqs.length * 3)) * Math.min(1, t * 3) * Math.min(1, (dur - t) * 3); } return o; }

// ---------- SFX ----------
function whoosh(d = 0.45) { const o = len(d), bp = biquad("bp"); for (let i = 0; i < o.length; i++) { const x = i / o.length; if (i % 16 === 0) bp.set(300 + 6000 * Math.sin(Math.PI * x) ** 2, 1.4); o[i] = bp.run(noise()) * Math.sin(Math.PI * x) ** 2 * 2.2; } return o; }
function impact(d = 1.6) { const o = len(d), lp = biquad("lp"); lp.set(2500, 0.8); let ph = 0; for (let i = 0; i < o.length; i++) { const t = i / SR; const f = 28 + 90 * Math.exp(-t * 9); ph += TAU * f / SR; o[i] = Math.sin(ph) * Math.exp(-t * 2.4) * 1.1 + lp.run(noise()) * Math.exp(-t * 14) * 0.9; } return reverb(o, 0.35); }
function hit(d = 0.5) { const o = len(d), bp = biquad("bp"); bp.set(900, 0.7); let ph = 0; for (let i = 0; i < o.length; i++) { const t = i / SR; ph += TAU * (70 + 200 * Math.exp(-t * 30)) / SR; o[i] = Math.sin(ph) * Math.exp(-t * 9) + bp.run(noise()) * Math.exp(-t * 25) * 1.2; } return o; }
function click() { const o = len(0.07); for (let i = 0; i < o.length; i++) { const t = i / SR; o[i] = (Math.sin(TAU * 2200 * t) * 0.6 + Math.sin(TAU * 3300 * t) * 0.3) * Math.exp(-t * 80); } return o; }
function blip(f = 1320) { const o = len(0.12); for (let i = 0; i < o.length; i++) { const t = i / SR; const ff = t < 0.04 ? f : f * 1.5; o[i] = (Math.sin(TAU * ff * t) > 0 ? 1 : -1) * 0.35 * Math.exp(-t * 30); } return o; }
function riser(d = 1.0) { const o = len(d), bp = biquad("bp"); let ph = 0; for (let i = 0; i < o.length; i++) { const x = i / o.length; if (i % 16 === 0) bp.set(300 * Math.pow(30, x), 2); ph = (ph + (180 * Math.pow(6, x)) / SR) % 1; o[i] = (bp.run(noise()) * 1.4 + (2 * ph - 1) * 0.25) * x * x; } return o; }
function glitch(d = 0.28) { const o = len(d); const step = Math.round(SR / 90); let hold = 0; for (let i = 0; i < o.length; i++) { if (i % step === 0) hold = rnd() < 0.5 ? noise() : (rnd() < 0.5 ? 0.8 : -0.8); const t = i / SR; const sq = Math.sin(TAU * (400 + 1200 * rnd() * 0) * t) > 0 ? 0.3 : -0.3; o[i] = (Math.floor(i / (step * 3)) % 2 ? hold : sq) * 0.9; } return o; }
function reverb(x, mix = 0.3) { const out = new Float32Array(x.length); const combs = [1557, 1617, 1491, 1422].map((d) => ({ d, buf: new Float32Array(d), i: 0 })); for (let n = 0; n < x.length; n++) { let s = 0; for (const c of combs) { const y = c.buf[c.i]; c.buf[c.i] = x[n] + y * 0.78; c.i = (c.i + 1) % c.d; s += y; } out[n] = x[n] * (1 - mix) + (s / 4) * mix; } return out; }
function shimmer(d = 0.7, f = 2637) { // metallic sparkle: inharmonic partials with tremolo (liquid-metal / cleaning sparkle)
  const o = len(d), parts = [1, 1.5, 2.01, 2.76, 3.52]; for (let i = 0; i < o.length; i++) { const t = i / SR; let s = 0;
    parts.forEach((p, k) => { s += Math.sin(TAU * f * p * t + k) * Math.exp(-t * (4 + k * 2)) / (k + 1); });
    o[i] = s * 0.45 * (0.75 + 0.25 * Math.sin(TAU * 18 * t)) * Math.min(1, t * 300); } return reverb(o, 0.3); }
const SFX = { whoosh, impact, hit, click, blip, riser, glitch, shimmer };

// ---------- music (arrangement driven by spec.audio.music.sections) ----------
const prog = audio.music.progression; // array of [rootMidi, [chord midis]] per bar
const barLen = BEAT * 4;
const kickS = kick(), clapS = clap(), hatS = hat(false), ohatS = hat(true);
const sidechain = new Float32Array(N).fill(1);
const inSection = (t, name) => audio.music.sections.some((s) => s.name === name && t >= s.from && t < s.to);
for (let b = 0; b * BEAT < DUR; b++) {
  const t = b * BEAT; const bar = Math.floor(b / 4); const [root, chord] = prog[bar % prog.length];
  const intro = inSection(t, "intro"), groove = inSection(t, "groove"), build = inSection(t, "build"), drop = inSection(t, "drop");
  if (intro || groove || drop) { add(L, R, t, kickS, 0.95); for (let k = 0; k < Math.round(0.3 * SR) && Math.round(t * SR) + k < N; k++) sidechain[Math.round(t * SR) + k] = Math.min(sidechain[Math.round(t * SR) + k], 0.45 + 0.55 * Math.min(1, k / (0.3 * SR))); }
  if ((groove || drop) && b % 2 === 1) add(L, R, t, clapS, 0.5, 0.1);
  if (groove || drop) { for (let h = 0; h < 4; h++) add(L, R, t + h * BEAT / 4, h === 2 ? ohatS : hatS, h === 2 ? 0.13 : 0.09, h % 2 ? 0.35 : -0.35); }
  if (intro) add(L, R, t + BEAT / 2, hatS, 0.1, 0.3);
  if (groove || drop || intro) { for (let e = 0; e < 2; e++) add(L, R, t + e * BEAT / 2, bassNote(midi(root + (e ? 12 : 0)), BEAT / 2 * 0.9), intro ? 0.35 : 0.55); }
  if (groove || drop) { for (let s = 0; s < 4; s++) { const note = chord[(b * 4 + s) % chord.length] + 12; add(L, R, t + s * BEAT / 4, pluck(midi(note)), 0.16, s % 2 ? 0.5 : -0.5); add(L, R, t + s * BEAT / 4 + BEAT * 0.75, pluck(midi(note)), 0.05, s % 2 ? -0.6 : 0.6); } }
  if (build) { for (let s = 0; s < 4; s++) add(L, R, t + s * BEAT / 4, clapS, 0.12 + 0.3 * ((t - audio.music.sections.find((x) => x.name === "build").from) / BEAT) / 2, 0); }
  if (b % 4 === 0) { const p = pad(chord.map(midi), barLen); add(L, R, t, p, drop ? 0.2 : 0.13, -0.2); add(L, R, t, p, drop ? 0.2 : 0.13, 0.2); }
}
for (let i = 0; i < N; i++) { L[i] *= sidechain[i] ** 0.6; R[i] *= sidechain[i] ** 0.6; }

// ---------- SFX cues + ducking ----------
const duck = new Float32Array(N).fill(1);
for (const cue of audio.cues) {
  const fn = SFX[cue.sfx]; if (!fn) throw new Error(`unknown sfx ${cue.sfx}`);
  if (cue.t < 0 || cue.t >= DUR) throw new Error(`cue ${cue.id} outside duration`);
  const s = cue.args ? fn(...cue.args) : fn();
  add(SL, SRr, cue.t, s, db(cue.gain_db ?? 0), cue.pan ?? 0);
  if (cue.duck_db) { const depth = db(-cue.duck_db), a = Math.round(cue.t * SR), rel = Math.round(0.35 * SR), hold = s.length * 0.4;
    for (let k = -480; k < hold + rel; k++) { const j = a + k; if (j < 0 || j >= N) continue; const g = k < 0 ? 1 - (1 - depth) * ((k + 480) / 480) : k < hold ? depth : depth + (1 - depth) * ((k - hold) / rel); duck[j] = Math.min(duck[j], g); } }
}
// ---------- voice-over (pre-rendered by scripts/voice.py, cached in assets/audio/vo/) ----------
// VO bus is centered and level-matched per line (no extra saturation); its envelope ducks music (and SFX a little).
const VO = new Float32Array(N), voEnv = new Float32Array(N);
const voice = spec.voice;
let voLines = 0;
function readWavMono(path) { // minimal RIFF reader: PCM s16, mono, 48 kHz (what voice.py writes)
  const b = readFileSync(path); let off = 12, fmt = null;
  while (off < b.length) { const id = b.toString("ascii", off, off + 4), size = b.readUInt32LE(off + 4);
    if (id === "fmt ") fmt = { ch: b.readUInt16LE(off + 10), sr: b.readUInt32LE(off + 12), bits: b.readUInt16LE(off + 22) };
    if (id === "data") { if (!fmt || fmt.ch !== 1 || fmt.sr !== SR || fmt.bits !== 16) throw new Error(`${path}: expected 48k mono s16`);
      const n = size / 2, o = new Float32Array(n); for (let i = 0; i < n; i++) o[i] = b.readInt16LE(off + 8 + i * 2) / 32768; return o; }
    off += 8 + size + (size & 1); }
  throw new Error(`${path}: no data chunk`);
}
if (voice?.enabled) {
  const manPath = join(ROOT, "assets/audio/vo/manifest.json");
  if (!existsSync(manPath)) throw new Error("voice.enabled but assets/audio/vo/manifest.json missing - run `npm run voice`");
  const man = JSON.parse(readFileSync(manPath, "utf8"));
  for (const line of voice.lines) {
    const m = man.lines[line.id]; if (!m) throw new Error(`VO ${line.id} not rendered - run \`npm run voice\``);
    if (m.text !== line.text) throw new Error(`VO ${line.id} text changed in spec.json - run \`npm run voice\``);
    // EQ / compression / room are applied once in voice.py (spec.voice.processing); here only level-match + place
    const x = readWavMono(join(ROOT, m.file));
    let ss = 0; for (let i = 0; i < x.length; i++) ss += x[i] * x[i];
    const g = db(voice.gain_db ?? 0) * (0.16 / Math.sqrt(ss / x.length + 1e-9)); // level-match lines to the same RMS
    const i0 = Math.round(line.t * SR);
    for (let i = 0; i < x.length; i++) { const j = i0 + i; if (j >= 0 && j < N) VO[j] += x[i] * g; }
    voLines++;
  }
  // envelope follower (10 ms attack, 300 ms release) with 60 ms look-ahead so the duck lands before the word
  const att = Math.exp(-1 / (0.01 * SR)), rel = Math.exp(-1 / (0.3 * SR)), look = Math.round(0.06 * SR);
  let e = 0;
  for (let i = 0; i < N; i++) { const a = Math.abs(VO[Math.min(N - 1, i + look)]); e = a > e ? att * e + (1 - att) * a : rel * e + (1 - rel) * a; voEnv[i] = Math.min(1, e / 0.05); }
}
const duckMusicVO = db(-(voice?.duck_music_db ?? 0)), duckSfxVO = db(-(voice?.duck_sfx_db ?? 0));

const fi = audio.music.fade_in_s * SR, fo = audio.music.fade_out_s * SR;
const out = new Int16Array(N * 2);
for (let i = 0; i < N; i++) {
  const fade = Math.min(1, i / fi, (N - i) / fo);
  const v = voEnv[i], mv = 1 - (1 - duckMusicVO) * v, sv = 1 - (1 - duckSfxVO) * v;
  const m = db(audio.music.gain_db) * Math.min(duck[i], mv) * fade, sfxFade = Math.min(1, (N - i) / (0.05 * SR)) * sv;
  let l = L[i] * m + SL[i] * sfxFade + VO[i], r = R[i] * m + SRr[i] * sfxFade + VO[i];
  l = Math.tanh(l * 0.9); r = Math.tanh(r * 0.9); // soft clip
  out[i * 2] = Math.max(-32767, Math.min(32767, l * 32767)); out[i * 2 + 1] = Math.max(-32767, Math.min(32767, r * 32767));
}
function wav(path, pcm) { const h = Buffer.alloc(44); const dataLen = pcm.length * 2; h.write("RIFF", 0); h.writeUInt32LE(36 + dataLen, 4); h.write("WAVE", 8); h.write("fmt ", 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(2, 22); h.writeUInt32LE(SR, 24); h.writeUInt32LE(SR * 4, 28); h.writeUInt16LE(4, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(dataLen, 40); writeFileSync(path, Buffer.concat([h, Buffer.from(pcm.buffer)])); }
const raw = join(ROOT, "build/mix.raw.wav"); wav(raw, out);

// ---------- loudness normalize (2-pass loudnorm) ----------
const { target_lufs: I, true_peak_db: TP } = audio.master;
const pass1 = execFileSync("ffmpeg", ["-hide_banner", "-nostats", "-i", raw, "-af", `loudnorm=I=${I}:TP=${TP}:LRA=11:print_format=json`, "-f", "null", "-"], { stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" }).toString();
let meas; try { meas = JSON.parse(execFileSync("sh", ["-c", `ffmpeg -hide_banner -nostats -i "${raw}" -af loudnorm=I=${I}:TP=${TP}:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p'`]).toString()); } catch (e) { throw new Error("loudnorm pass 1 failed"); }
const af = `loudnorm=I=${I}:TP=${TP}:LRA=11:measured_I=${meas.input_i}:measured_TP=${meas.input_tp}:measured_LRA=${meas.input_lra}:measured_thresh=${meas.input_thresh}:offset=${meas.target_offset}:linear=true`;
const final = join(ROOT, "assets/audio/build/mix.wav");
execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-af", af, "-ar", String(SR), "-c:a", "pcm_s16le", final]);
console.log(`audio: ${final} (${DUR}s, ${audio.cues.length} cues, ${voLines} VO lines, input ${meas.input_i} LUFS -> target ${I} LUFS)`);
console.log(`variables: build/variables.json (${Object.keys(variables).length} keys)`);
console.log(`plates: ${plates.join(" ") || "none"}`);
void pass1;
