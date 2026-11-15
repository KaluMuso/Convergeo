import { describe, expect, it } from "vitest";

import { parsePushPayload, safeNotificationUrl } from "./push-payload";

const FALLBACK = "/en/account/notifications";

describe("push payload", () => {
  it("parses a well-formed payload", () => {
    expect(
      parsePushPayload(
        JSON.stringify({
          title: "Convergeo",
          body: "Order AB12 shipped",
          url: "/en/account/orders/1",
          badge: 3,
        }),
        FALLBACK,
      ),
    ).toEqual({
      title: "Convergeo",
      body: "Order AB12 shipped",
      url: "/en/account/orders/1",
      badge: 3,
    });
  });

  it("refuses off-origin and malformed links", () => {
    expect(safeNotificationUrl("https://evil.example/x", FALLBACK)).toBe(FALLBACK);
    expect(safeNotificationUrl("//evil.example", FALLBACK)).toBe(FALLBACK);
    expect(safeNotificationUrl("/en/a?b=<script>", FALLBACK)).toBe(FALLBACK);
  });

  it("survives garbage input", () => {
    expect(parsePushPayload("not json", FALLBACK)).toEqual({
      title: "Convergeo",
      body: "",
      url: FALLBACK,
      badge: null,
    });
  });
});
