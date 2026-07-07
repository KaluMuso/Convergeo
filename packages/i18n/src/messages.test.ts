import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { NAMESPACES } from "./request";

const messagesDir = join(fileURLToPath(new URL("../messages/en", import.meta.url)));

describe("namespace message files", () => {
  it("has exactly 16 namespace JSON files with valid content", () => {
    const files = readdirSync(messagesDir).filter((file) => file.endsWith(".json"));
    expect(files).toHaveLength(16);
    expect(files.map((file) => file.replace(".json", "")).sort()).toEqual([...NAMESPACES].sort());

    for (const namespace of NAMESPACES) {
      const raw = readFileSync(join(messagesDir, `${namespace}.json`), "utf8");
      const parsed = JSON.parse(raw) as Record<string, string>;
      expect(Object.keys(parsed).length).toBeGreaterThanOrEqual(2);
    }
  });
});
