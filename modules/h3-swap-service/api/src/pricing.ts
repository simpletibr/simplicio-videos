// Pure credit math (CONTRACT section 5). All amounts are BRL centavos.

function assertNonNegativeFinite(value: number, name: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`${name} must be a finite number >= 0 (got ${value})`);
  }
}

/** Credits reserved at job creation: duration_s * price per second. */
export function reserveCents(durationS: number, pricePerSecond: number): number {
  if (!Number.isFinite(durationS) || durationS <= 0) {
    throw new RangeError(`durationS must be a finite number > 0 (got ${durationS})`);
  }
  assertNonNegativeFinite(pricePerSecond, "pricePerSecond");
  return Math.ceil(durationS) * pricePerSecond;
}

/**
 * Settlement on success: charge ceil(output seconds) * price, capped at the
 * reserved amount. The rest is refunded.
 */
export function settleCents(
  reserved: number,
  outputDurationS: number,
  pricePerSecond: number,
): { charged: number; refund: number } {
  assertNonNegativeFinite(reserved, "reserved");
  assertNonNegativeFinite(outputDurationS, "outputDurationS");
  assertNonNegativeFinite(pricePerSecond, "pricePerSecond");
  const raw = Math.ceil(outputDurationS) * pricePerSecond;
  const charged = Math.min(raw, reserved);
  return { charged, refund: reserved - charged };
}
