import { afterEach, describe, expect, it, vi } from "vitest";
import { json, mockFetch, saladEnv } from "../test-utils";
import {
  assertContainerName,
  buildCreateBody,
  containerName,
  createSaladProvider,
  loadSaladConfig,
} from "./salad";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const W = "w-123e4567e89b";
const NAME = "h3-swap-w-123e4567e89b";
const CONTAINERS = "https://api.salad.com/api/public/organizations/org1/projects/proj1/containers";
const GPU_CLASSES = "https://api.salad.com/api/public/organizations/org1/gpu-classes";
const GPUS = {
  items: [
    { id: "gpu-4090", name: "RTX 4090" },
    { id: "gpu-5090", name: "RTX 5090" },
  ],
};

type CreateBody = {
  name: string;
  display_name: string;
  container: {
    image: string;
    resources: { cpu: number; memory: number; gpu_classes: string[] };
    environment_variables: Record<string, string>;
  };
  autostart_policy: boolean;
  restart_policy: string;
  replicas: number;
  priority?: string;
};

describe("loadSaladConfig", () => {
  it("applies defaults and falls back to VAST_IMAGE", () => {
    const cfg = loadSaladConfig(
      saladEnv({ SALAD_IMAGE: "", SALAD_CPU: "", SALAD_MEMORY_MB: "", SALAD_GPU_CLASS_NAME: "", SALAD_PRIORITY: "" }),
    );
    expect(cfg).toEqual({
      org: "org1",
      project: "proj1",
      gpuClassName: "RTX 5090",
      cpu: 8,
      memoryMb: 65536,
      priority: null,
      image: "ghcr.io/x/h3:runtime",
    });
  });

  it("prefers SALAD_IMAGE over VAST_IMAGE when set", () => {
    expect(loadSaladConfig(saladEnv({ SALAD_IMAGE: "ghcr.io/x/h3:salad-runtime" })).image).toBe(
      "ghcr.io/x/h3:salad-runtime",
    );
  });

  it("requires SALAD_ORG", () => {
    expect(() => loadSaladConfig(saladEnv({ SALAD_ORG: "" }))).toThrow(/SALAD_ORG/);
  });
});

describe("containerName and assertContainerName", () => {
  it("names the container h3-swap-<worker_id>", () => {
    expect(containerName(W)).toBe(NAME);
  });

  it("accepts valid names and rejects invalid ones", () => {
    expect(() => assertContainerName(NAME)).not.toThrow();
    expect(() => assertContainerName("H3-swap")).toThrow();
    expect(() => assertContainerName("1abc")).toThrow();
    expect(() => assertContainerName("a".repeat(64))).toThrow();
  });
});

describe("buildCreateBody", () => {
  it("matches the CONTRACT 10b body, with environment_variables as an object", () => {
    const cfg = loadSaladConfig(saladEnv({}));
    const body = buildCreateBody(cfg, NAME, "gpu-5090", [
      ["INSTANCE_ID", W],
      ["PROVIDER", "salad"],
    ]);
    expect(body).toEqual({
      name: NAME,
      display_name: NAME,
      container: {
        image: "ghcr.io/x/h3:runtime",
        resources: { cpu: 8, memory: 65536, gpu_classes: ["gpu-5090"] },
        environment_variables: { INSTANCE_ID: W, PROVIDER: "salad" },
      },
      autostart_policy: true,
      restart_policy: "on_failure",
      replicas: 1,
    });
  });

  it("sends priority only when SALAD_PRIORITY is set", () => {
    const withPriority = buildCreateBody(loadSaladConfig(saladEnv({ SALAD_PRIORITY: "high" })), NAME, "g", []);
    // Salad docs: priority is `container.priority`, never a top-level field of the request.
    expect((withPriority.container as { priority?: string }).priority).toBe("high");
    expect("priority" in withPriority).toBe(false);
    const without = buildCreateBody(loadSaladConfig(saladEnv({ SALAD_PRIORITY: "" })), NAME, "g", []);
    expect("priority" in (without.container as object)).toBe(false);
    expect("priority" in without).toBe(false);
  });
});

describe("createSaladProvider.create (fetch mocked)", () => {
  it("resolves the GPU class, posts the container and returns its name", async () => {
    const calls = mockFetch((c) => (c.url === GPU_CLASSES ? json(GPUS) : json({}, 201)));
    const name = await createSaladProvider(saladEnv({})).create(W);
    expect(name).toBe(NAME);

    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(CONTAINERS);
    expect(post?.headers["Salad-Api-Key"]).toBe("salad-key");
    const body = post?.body as CreateBody;
    expect(body.container.resources.gpu_classes).toEqual(["gpu-5090"]);
    expect(body.container.environment_variables.INSTANCE_ID).toBe(W);
    expect(body.autostart_policy).toBe(true);
    expect(body.restart_policy).toBe("on_failure");
    expect(body.replicas).toBe(1);
  });

  it("caches the GPU class per provider instance, but not across instances (per tick)", async () => {
    const calls = mockFetch((c) => (c.url === GPU_CLASSES ? json(GPUS) : json({}, 201)));
    const provider = createSaladProvider(saladEnv({}));
    await provider.create("w-aaaaaaaaaaaa");
    await provider.create("w-bbbbbbbbbbbb");
    expect(calls.filter((c) => c.url === GPU_CLASSES)).toHaveLength(1);

    await createSaladProvider(saladEnv({})).create("w-cccccccccccc");
    expect(calls.filter((c) => c.url === GPU_CLASSES)).toHaveLength(2);
  });

  it("throws without posting when the GPU class name is not listed", async () => {
    const calls = mockFetch((c) => (c.url === GPU_CLASSES ? json({ items: [] }) : json({}, 201)));
    await expect(createSaladProvider(saladEnv({})).create(W)).rejects.toThrow(/not found/);
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("throws before any request when SALAD_API_KEY is missing", async () => {
    const calls = mockFetch(() => json({}));
    await expect(createSaladProvider(saladEnv({ SALAD_API_KEY: "" })).create(W)).rejects.toThrow(/SALAD_API_KEY/);
    expect(calls).toHaveLength(0);
  });
});

describe("createSaladProvider destroy, refFor and listWorkers", () => {
  it("DELETEs the container by its deterministic name", async () => {
    const calls = mockFetch(() => json({}, 202));
    await createSaladProvider(saladEnv({})).destroy(NAME);
    expect(calls[0]?.method).toBe("DELETE");
    expect(calls[0]?.url).toBe(`${CONTAINERS}/${NAME}`);
  });

  it("treats 404 as already gone and rejects other errors", async () => {
    mockFetch(() => json({}, 404));
    await expect(createSaladProvider(saladEnv({})).destroy(NAME)).resolves.toBeUndefined();

    mockFetch(() => json({}, 500));
    await expect(createSaladProvider(saladEnv({})).destroy(NAME)).rejects.toThrow();
  });

  it("refFor returns the deterministic container name", () => {
    expect(createSaladProvider(saladEnv({})).refFor?.(W)).toBe(NAME);
  });

  it("lists this app's containers as worker ids", async () => {
    mockFetch(() => json({ items: [{ name: "h3-swap-w-aaaaaaaaaaaa" }, { name: "some-other-app" }] }));
    expect(await createSaladProvider(saladEnv({})).listWorkers?.()).toEqual([
      { workerId: "w-aaaaaaaaaaaa", providerRef: "h3-swap-w-aaaaaaaaaaaa" },
    ]);
  });

  it("returns an empty list and logs when the listing fails (best-effort)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetch(() => json({}, 500));
    expect(await createSaladProvider(saladEnv({})).listWorkers?.()).toEqual([]);
    expect(errorSpy).toHaveBeenCalled();
  });
});
