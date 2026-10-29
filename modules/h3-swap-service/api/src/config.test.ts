import { describe, expect, it } from "vitest";
import { parseProviderOrder } from "./config";

describe("parseProviderOrder", () => {
  it("defaults to vast then salad", () => {
    expect(parseProviderOrder(undefined)).toEqual(["vast", "salad"]);
    expect(parseProviderOrder("   ")).toEqual(["vast", "salad"]);
  });

  it("keeps the configured order", () => {
    expect(parseProviderOrder("salad,vast")).toEqual(["salad", "vast"]);
  });

  it("trims whitespace and removes duplicates", () => {
    expect(parseProviderOrder(" vast , salad, vast ")).toEqual(["vast", "salad"]);
  });

  it("rejects unknown provider names", () => {
    expect(() => parseProviderOrder("vast,aws")).toThrow(/aws/);
  });
});
