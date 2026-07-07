import { describe, expect, it } from "vitest";

import { resolveMessage } from "./request";

describe("resolveMessage", () => {
  it("falls back to English for missing locale files", async () => {
    const message = await resolveMessage("bem", "app.name");
    expect(message).toBe("Vergeo5");
  });

  it("falls back to the key when missing in all locales", async () => {
    const message = await resolveMessage("en", "missing.key");
    expect(message).toBe("missing.key");
  });

  it("renders ICU-style interpolation", async () => {
    const message = await resolveMessage("en", "greeting", { name: "Vergeo" });
    expect(message).toBe("Hello, Vergeo!");
  });
});
