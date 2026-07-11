import { beforeEach, describe, expect, it } from "vitest";

import { checkRateLimit, DEFAULT_LIMIT, resetRateLimits } from "./_components/rate-limit";
import { MESSAGE_MAX, validateContact } from "./_components/validation";

describe("contact validation", () => {
  it("rejects an empty submission", () => {
    const result = validateContact({ name: "", message: "" });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.name).toBe("nameRequired");
      expect(result.errors.message).toBe("messageRequired");
    }
  });

  it("rejects a message that is too short", () => {
    const result = validateContact({ name: "Chanda", message: "hi" });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.message).toBe("messageTooShort");
    }
  });

  it("rejects an over-long message", () => {
    const result = validateContact({ name: "Chanda", message: "x".repeat(MESSAGE_MAX + 1) });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.message).toBe("messageTooLong");
    }
  });

  it("strips CR/LF from the name to block email-header injection", () => {
    const result = validateContact({
      name: "Chanda\r\nBcc: evil@example.com",
      message: "Please help me with my order thanks.",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.name).not.toContain("\n");
      expect(result.value.name).not.toContain("\r");
    }
  });

  it("accepts a valid submission and keeps the message body", () => {
    const result = validateContact({
      name: "Chanda Mwansa",
      contact: "chanda@example.com",
      message: "Hello, I have a question about my recent order.",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.name).toBe("Chanda Mwansa");
      expect(result.value.message).toContain("question about my recent order");
    }
  });
});

describe("contact rate limiting", () => {
  beforeEach(() => resetRateLimits());

  it("allows up to the limit then blocks further attempts in the window", () => {
    const key = "test-ip";
    for (let i = 0; i < DEFAULT_LIMIT; i += 1) {
      expect(checkRateLimit(key).allowed).toBe(true);
    }
    expect(checkRateLimit(key).allowed).toBe(false);
  });

  it("resets after the window elapses", () => {
    const key = "test-ip-2";
    const now = 1_000_000;
    for (let i = 0; i < DEFAULT_LIMIT; i += 1) {
      checkRateLimit(key, DEFAULT_LIMIT, 60_000, now);
    }
    expect(checkRateLimit(key, DEFAULT_LIMIT, 60_000, now).allowed).toBe(false);
    expect(checkRateLimit(key, DEFAULT_LIMIT, 60_000, now + 60_001).allowed).toBe(true);
  });
});
