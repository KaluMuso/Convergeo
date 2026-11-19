import { afterEach, describe, expect, it } from "vitest";

import { isPhoneOtpEnabled } from "./phone-otp";

describe("isPhoneOtpEnabled", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_PHONE_OTP_ENABLED;
  });

  it("defaults to off when configuration is absent", () => {
    expect(isPhoneOtpEnabled({})).toBe(false);
    expect(isPhoneOtpEnabled()).toBe(false);
  });

  it("is off for anything but the exact string true", () => {
    for (const value of ["", "false", "TRUE", "1", "yes"]) {
      expect(isPhoneOtpEnabled({ NEXT_PUBLIC_PHONE_OTP_ENABLED: value })).toBe(false);
    }
  });

  it("is on for the exact string true", () => {
    expect(isPhoneOtpEnabled({ NEXT_PUBLIC_PHONE_OTP_ENABLED: "true" })).toBe(true);
    process.env.NEXT_PUBLIC_PHONE_OTP_ENABLED = "true";
    expect(isPhoneOtpEnabled()).toBe(true);
  });
});
