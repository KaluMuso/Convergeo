import { describe, expect, it } from "vitest";

import { describeAuthFailure } from "./auth-diagnostics";
import { parseAuthError } from "./auth-utils";

describe("safe Auth failure classification", () => {
  it.each([
    ["invalid_credentials", "invalid_credentials"],
    ["user_not_found", "invalid_credentials"],
    ["email_not_confirmed", "email_not_confirmed"],
    ["email_exists", "generic"],
    ["user_already_exists", "generic"],
    ["otp_expired", "expired"],
    ["flow_state_expired", "expired"],
    ["over_request_rate_limit", "throttled"],
    ["over_email_send_rate_limit", "throttled"],
    ["over_sms_send_rate_limit", "throttled"],
  ])("uses structured %s rather than message guesses", (code, expected) => {
    expect(parseAuthError({ code, message: "unexpected wording" }).code).toBe(expected);
  });

  it("does not guess credentials from unknown codes or invalid API keys", () => {
    expect(parseAuthError({ code: "new_code", message: "invalid login credentials" }).code).toBe(
      "generic",
    );
    expect(parseAuthError({ message: "Invalid API key" }).code).toBe("generic");
    expect(parseAuthError({ message: { private: "token" } }).code).toBe("generic");
  });

  it.each([Infinity, NaN, -10, 0])("uses a safe cooldown for %s", (retryAfter) => {
    expect(parseAuthError({ status: 429, retryAfter })).toEqual({
      code: "throttled",
      retryAfterSeconds: 60,
    });
  });

  it.each([
    undefined,
    null,
    "private-token",
    { status: "private@example.com" },
    { status: 600 },
    { status: 400.5 },
  ])("emits only fixed fields for malformed error %j", (error) => {
    expect(describeAuthFailure(error, "authenticate", "vendor", "login")).toEqual({
      parsed: { code: "generic" },
      diagnostic: { stage: "authenticate", portal: "vendor", mode: "login", category: "generic" },
    });
  });

  it("drops arbitrary fields, URLs, messages, provider codes and sessions", () => {
    const error = {
      code: "private-token",
      status: 401,
      message: "private@example.com",
      url: "https://private/?code=secret",
      access_token: "secret",
      session: { password: "secret" },
    };
    expect(describeAuthFailure(error, "authenticate", "admin", "login")).toEqual({
      parsed: { code: "generic" },
      diagnostic: {
        stage: "authenticate",
        portal: "admin",
        mode: "login",
        category: "generic",
        httpStatus: 401,
      },
    });
  });
});
