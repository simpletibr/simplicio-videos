import { afterEach, describe, expect, it, vi } from "vitest";
import { json, mockFetch, vastEnv } from "../test-utils";
import { NoCapacityError, workerEnvPairs, workerIdFromUuid } from "./types";
import {
  buildEnvString,
  buildOfferFilter,
  createVastProvider,
  filterOffers,
  instanceLabel,
  workerIdFromLabel,
} from "./vast";

afterEach(() => vi.unstubAllGlobals());

const W = "w-123e4567e89b";

describe("worker ids and instance labels", () => {
  it("derives w-<12 hex chars> from a uuid", () => {
    expect(workerIdFromUuid("123e4567-e89b-42d3-a456-426614174000")).toBe(W);
  });

  it("rejects input that is not a uuid", () => {
    expect(() => workerIdFromUuid("not-a-uuid")).toThrow();
  });

  it("builds labels with the h3-swap- prefix and parses them back", () => {
    expect(instanceLabel(W)).toBe(`h3-swap-${W}`);
    expect(workerIdFromLabel(`h3-swap-${W}`)).toBe(W);
    expect(workerIdFromLabel("other-label")).toBeNull();
    expect(workerIdFromLabel("h3-swap-")).toBeNull();
    expect(workerIdFromLabel(null)).toBeNull();
  });
});

describe("workerEnvPairs", () => {
  it("passes INSTANCE_ID and PROVIDER so the worker reports the id the autoscaler stored", () => {
    const pairs = workerEnvPairs(vastEnv(), W, "vast");
    expect(pairs).toContainEqual(["INSTANCE_ID", W]);
    expect(pairs).toContainEqual(["PROVIDER", "vast"]);
    expect(buildEnvString(pairs)).toContain(`-e INSTANCE_ID=${W}`);
  });
});

describe("workerEnvPairs optional boot variables", () => {
  it("forwards FETCH_OPTIONAL, MODELS_MODE and WORKFLOW_OPTIONAL only when set", () => {
    const keys = (pairs: Array<[string, string]>) => pairs.map(([k]) => k);
    expect(keys(workerEnvPairs(vastEnv(), W, "vast"))).not.toContain("FETCH_OPTIONAL");
    const pairs = workerEnvPairs(
      vastEnv({ FETCH_OPTIONAL: "diffusion_models/a.safetensors,loras/b.safetensors", MODELS_MODE: "runtime", WORKFLOW_OPTIONAL: "" }),
      W,
      "vast",
    );
    expect(pairs).toContainEqual(["FETCH_OPTIONAL", "diffusion_models/a.safetensors,loras/b.safetensors"]);
    expect(pairs).toContainEqual(["MODELS_MODE", "runtime"]);
    expect(keys(pairs)).not.toContain("WORKFLOW_OPTIONAL");
    expect(buildEnvString(pairs)).toContain("-e FETCH_OPTIONAL=diffusion_models/a.safetensors,loras/b.safetensors");
  });
});

describe("buildEnvString", () => {
  it("renders Docker -e flags", () => {
    expect(
      buildEnvString([
        ["A", "1"],
        ["B_C", "https://api.example.com"],
      ]),
    ).toBe("-e A=1 -e B_C=https://api.example.com");
  });

  it("rejects values with whitespace or shell-special characters", () => {
    expect(() => buildEnvString([["A", "has space"]])).toThrow(/A/);
    expect(() => buildEnvString([["A", "$HOME"]])).toThrow(/A/);
    expect(() => buildEnvString([["A", "a'b"]])).toThrow(/A/);
  });

  it("rejects bad keys and missing values before any instance is rented", () => {
    expect(() => buildEnvString([["1BAD", "x"]])).toThrow();
    expect(() => buildEnvString([["WORKER_SECRET", ""]])).toThrow(/missing.*WORKER_SECRET/);
  });
});

describe("buildOfferFilter", () => {
  it("defaults to verified, rentable, on-demand RTX 5090 x1 sorted by price ascending", () => {
    expect(buildOfferFilter("{}")).toMatchObject({
      verified: { eq: true },
      rentable: { eq: true },
      gpu_name: { eq: "RTX 5090" },
      num_gpus: { eq: 1 },
      type: "on-demand",
      order: [["dph_total", "asc"]],
    });
  });

  it("merges VAST_OFFER_FILTER_JSON over the defaults", () => {
    const f = buildOfferFilter('{"gpu_name":{"eq":"RTX_5090"},"limit":5}');
    expect(f.gpu_name).toEqual({ eq: "RTX_5090" });
    expect(f.limit).toBe(5);
    expect(f.verified).toEqual({ eq: true });
  });

  it("rejects non-object or invalid JSON", () => {
    expect(() => buildOfferFilter("[]")).toThrow();
    expect(() => buildOfferFilter("null")).toThrow();
    expect(() => buildOfferFilter("{not json")).toThrow();
  });
});

describe("filterOffers", () => {
  it("drops offers above MAX_DPH and sorts the rest by price ascending", () => {
    const raw = [
      { id: 11, dph_total: 0.9 },
      { id: 12, dph_total: 0.5 },
      { id: 13, dph_total: 1.2 },
    ];
    expect(filterOffers(raw, 1.0)).toEqual([
      { id: "12", dph_total: 0.5 },
      { id: "11", dph_total: 0.9 },
    ]);
  });

  it("keeps an offer exactly at MAX_DPH", () => {
    expect(filterOffers([{ id: 1, dph_total: 1.0 }], 1.0)).toHaveLength(1);
    expect(filterOffers([{ id: 1, dph_total: 1.01 }], 1.0)).toHaveLength(0);
  });

  it("skips malformed offers", () => {
    const raw: unknown[] = [null, { dph_total: 0.5 }, { id: 2 }, { id: 3, dph_total: "0.5" }, { id: 4, dph_total: 0.5 }];
    expect(filterOffers(raw, 1.0)).toEqual([{ id: "4", dph_total: 0.5 }]);
  });
});

describe("createVastProvider (fetch mocked)", () => {
  it("rents the next offer when the first rental fails, and returns the contract id", async () => {
    const calls = mockFetch((c) => {
      if (c.method === "POST" && c.url.endsWith("/bundles/")) {
        return json({
          offers: [
            { id: 11, dph_total: 0.5 },
            { id: 12, dph_total: 0.9 },
          ],
        });
      }
      if (c.url.endsWith("/asks/11/")) return json({ success: false, msg: "gone" }, 500);
      if (c.url.endsWith("/asks/12/")) return json({ success: true, new_contract: 778 });
      return json({}, 404);
    });

    const id = await createVastProvider(vastEnv()).create(W);
    expect(id).toBe("778");

    const put = calls.find((c) => c.method === "PUT" && c.url.endsWith("/asks/12/"));
    const body = put?.body as { label: string; env: string };
    expect(body.label).toBe(`h3-swap-${W}`);
    expect(body.env).toContain(`-e INSTANCE_ID=${W}`);
    expect(put?.headers.Authorization).toBe("Bearer vast-key");
  });

  it("throws NoCapacityError without renting when no offer is under MAX_DPH", async () => {
    const calls = mockFetch((c) =>
      c.url.endsWith("/bundles/") ? json({ offers: [{ id: 13, dph_total: 5 }] }) : json({}),
    );
    await expect(createVastProvider(vastEnv()).create(W)).rejects.toBeInstanceOf(NoCapacityError);
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("maps labelled instances to worker ids for orphan detection", async () => {
    mockFetch((c) =>
      c.url.endsWith("/instances/")
        ? json({
            instances: [
              { id: 5, label: `h3-swap-${W}`, actual_status: "running" },
              { id: 6, label: "manual", actual_status: "running" },
            ],
          })
        : json({}),
    );
    expect(await createVastProvider(vastEnv()).listWorkers?.()).toEqual([{ workerId: W, providerRef: "5" }]);
  });

  it("treats a missing instance (404) as destroyed and rejects other errors", async () => {
    mockFetch((c) => (c.url.endsWith("/instances/5/") ? json({}, 404) : json({}, 500)));
    await expect(createVastProvider(vastEnv()).destroy("5")).resolves.toBeUndefined();
    await expect(createVastProvider(vastEnv()).destroy("6")).rejects.toThrow();
  });
});
