import { describe, expect, it, vi } from "vitest";

import { isChunkLoadError, reloadOnceForChunkError } from "./chunk-reload";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

describe("isChunkLoadError", () => {
  it("detects webpack and ESM chunk failures", () => {
    const named = Object.assign(new Error("Loading chunk 4666 failed."), {
      name: "ChunkLoadError",
    });
    expect(isChunkLoadError(named)).toBe(true);
    expect(isChunkLoadError(new Error("Loading chunk 4666 failed."))).toBe(true);
    expect(
      isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: x.js")),
    ).toBe(true);
  });

  it("ignores ordinary errors", () => {
    expect(isChunkLoadError(new Error("boom"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("reloadOnceForChunkError", () => {
  it("reloads once, then not again within the guard window", () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    let t = 1_000_000;
    const env = { storage, reload, now: () => t };
    const err = Object.assign(new Error("x"), { name: "ChunkLoadError" });

    expect(reloadOnceForChunkError(err, env)).toBe(true);
    t += 5_000;
    expect(reloadOnceForChunkError(err, env)).toBe(false);
    t += 61_000;
    expect(reloadOnceForChunkError(err, env)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("does nothing for non-chunk errors", () => {
    const reload = vi.fn();
    expect(reloadOnceForChunkError(new Error("boom"), { storage: memoryStorage(), reload })).toBe(
      false,
    );
    expect(reload).not.toHaveBeenCalled();
  });
});
