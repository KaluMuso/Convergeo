import { describe, expect, it } from "vitest";

import { isPaused, NORMAL_BUSY_MODE, parseBusyMode } from "./busy-mode";

describe("parseBusyMode", () => {
  it("reads level and paused features", () => {
    const mode = parseBusyMode({
      level: 3,
      paused_features: ["ask_vergeo", "live_counts"],
    });
    expect(mode.level).toBe(3);
    expect(isPaused(mode, "ask_vergeo")).toBe(true);
    expect(isPaused(mode, "cart")).toBe(false);
  });

  it.each([null, "x", {}, { level: 9 }, { level: -1 }, { level: 1.5 }])(
    "falls back to normal for %j",
    (payload) => {
      expect(parseBusyMode(payload)).toEqual(NORMAL_BUSY_MODE);
    },
  );
});
