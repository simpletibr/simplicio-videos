// simplicio-videos · motion/lib/retime.js
// RETIME: author choreography on a base grid (beats), then remap it piecewise-linearly to the real cuts
// that the narration needs (TTS durations change per voice/provider). Pure + deterministic.
// Extracted from clients/wjr-informatica-games/video-01/index.html.
//
//   const { M, Minv, TL } = createRetime(tl, BASE, CUTS);
//   TL.fromTo(el, from, to, 4.0);   // 4.0 on the base grid -> moved to the matching real time
//   TL.to(el, vars, "@2.55");       // "@t" = absolute seconds (word-synced hits from ASR timestamps)
//
// BASE and CUTS must have the same length and be strictly increasing (scene boundaries, first 0, last = duration).
export function lerpMap(t, A, B) {
  for (let i = 1; i < A.length; i++) {
    if (t <= A[i]) return +(B[i - 1] + ((t - A[i - 1]) * (B[i] - B[i - 1])) / (A[i] - A[i - 1])).toFixed(4);
  }
  return t;
}

export function createRetime(tl, BASE, CUTS) {
  if (BASE.length !== CUTS.length) throw new Error("retime: BASE and CUTS must have the same length");
  const M = (t) => lerpMap(t, BASE, CUTS);
  const Minv = (t) => lerpMap(t, CUTS, BASE);
  const pos = (p) => (typeof p === "number" ? M(p) : typeof p === "string" && p[0] === "@" ? +p.slice(1) : p);
  const TL = {
    fromTo: (a, b, c, p) => tl.fromTo(a, b, c, pos(p)),
    to: (a, b, p) => tl.to(a, b, pos(p)),
    set: (a, b, p) => tl.set(a, b, pos(p)),
  };
  return { M, Minv, pos, TL };
}

// Browser/HyperFrames (no modules): expose on window when loaded via <script src>.
if (typeof window !== "undefined") window.SimplicioRetime = { lerpMap, createRetime };
