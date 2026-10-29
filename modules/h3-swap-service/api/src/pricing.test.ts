import { describe, expect, it } from "vitest";
import { reserveCents, settleCents } from "./pricing";

describe("reserveCents", () => {
  it("multiplies duration by price per second", () => {
    expect(reserveCents(10, 16)).toBe(160);
    expect(reserveCents(1, 16)).toBe(16);
    expect(reserveCents(30, 16)).toBe(480);
  });

  it("rejects invalid input", () => {
    expect(() => reserveCents(0, 16)).toThrow(RangeError);
    expect(() => reserveCents(-1, 16)).toThrow(RangeError);
    expect(() => reserveCents(Number.NaN, 16)).toThrow(RangeError);
    expect(() => reserveCents(10, -1)).toThrow(RangeError);
  });
});

describe("settleCents", () => {
  it("charges ceil(output seconds) and refunds the rest", () => {
    expect(settleCents(160, 9.83, 16)).toEqual({ charged: 160, refund: 0 });
    expect(settleCents(160, 5, 16)).toEqual({ charged: 80, refund: 80 });
    expect(settleCents(160, 5.01, 16)).toEqual({ charged: 96, refund: 64 });
  });

  it("never charges more than reserved", () => {
    expect(settleCents(160, 30.5, 16)).toEqual({ charged: 160, refund: 0 });
  });

  it("refunds everything when output is zero seconds", () => {
    expect(settleCents(160, 0, 16)).toEqual({ charged: 0, refund: 160 });
  });

  it("rejects invalid input", () => {
    expect(() => settleCents(160, -1, 16)).toThrow(RangeError);
    expect(() => settleCents(160, Number.POSITIVE_INFINITY, 16)).toThrow(RangeError);
    expect(() => settleCents(-1, 5, 16)).toThrow(RangeError);
  });
});
