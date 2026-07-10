// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../packages/i18n/messages/en/vendor.json";

const verifyQrMock = vi.fn();
const verifyPinMock = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    loading: false,
    session: { access_token: "test-token" },
    user: null,
  }),
}));

vi.mock("./_lib/pickup-client", () => ({
  createPickupClient: () => ({
    verifyQr: verifyQrMock,
    verifyPin: verifyPinMock,
  }),
}));

vi.mock("./_lib/qr-decode", () => ({
  decodeQrFromImageData: vi.fn(),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const scan = vendorMessages.scan as Record<string, unknown>;
    const parts = key.split(".");
    let current: unknown = scan;
    for (const part of parts.slice(1)) {
      if (!current || typeof current !== "object") {
        return key;
      }
      current = (current as Record<string, unknown>)[part];
    }
    if (typeof current === "string") {
      return current.replace(/\{(\w+)\}/g, (_, token: string) => values?.[token] ?? `{${token}}`);
    }
    return key;
  },
}));

import { ScanView } from "./_components/scan-view";
import { appendRecentVerification, readRecentVerifications } from "./_lib/recent-verifications";
import { classifyVerifyError, verifyErrorMessageKey } from "./_lib/verify-errors";

function mockCameraDenied(): void {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockRejectedValue(new Error("denied")),
    },
  });
}

async function submitPin(orderId: string, pin: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/Order ID/i), orderId);
  await user.type(screen.getByLabelText(/6-digit PIN/i), pin);
  await user.click(screen.getByRole("button", { name: /Verify pickup/i }));
}

beforeEach(() => {
  mockCameraDenied();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.sessionStorage.clear();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true, writable: true });
});

describe("vendor.scan i18n", () => {
  it("exposes nested scan keys", () => {
    expect(vendorMessages.scan.title).toBe("Scan pickup");
    expect(vendorMessages.scan.errors.wrongQr.title).toContain("Not a pickup code");
    expect(vendorMessages.scan.offline.title).toBe("You're offline");
  });
});

describe("verify error mapping", () => {
  it("maps event-ticket style failures to wrong_qr", () => {
    expect(classifyVerifyError("internal_error", "qr")).toBe("wrong_qr");
    expect(verifyErrorMessageKey("wrong_qr")).toBe("scan.errors.wrongQr");
  });

  it("maps network failures to offline", () => {
    expect(classifyVerifyError("network_error", "qr")).toBe("offline");
  });
});

describe("recent verifications storage", () => {
  it("stores verifications in session storage", () => {
    appendRecentVerification("order-abc");
    const items = readRecentVerifications();
    expect(items).toHaveLength(1);
    expect(items[0]?.orderId).toBe("order-abc");
  });
});

describe("ScanView flows", () => {
  it("PIN fallback verifies pickup successfully", async () => {
    verifyPinMock.mockResolvedValue({
      order_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      from_status: "ready",
      to_status: "delivered",
      event: "verify_pickup",
      token_version: 1,
    });

    render(<ScanView />);

    await waitFor(() => {
      expect(screen.getByTestId("scan-pin-fallback")).toBeInTheDocument();
    });

    await submitPin("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "123456");

    await waitFor(() => {
      expect(verifyPinMock).toHaveBeenCalledWith("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "123456");
      expect(screen.getByTestId("scan-success")).toBeInTheDocument();
    });
  });

  it("camera-denied falls back to PIN entry", async () => {
    render(<ScanView />);

    await waitFor(() => {
      expect(screen.getByTestId("scan-camera-denied")).toBeInTheDocument();
      expect(screen.getByTestId("scan-pin-fallback")).toBeInTheDocument();
    });
  });

  it("renders verify failure for generic errors", async () => {
    verifyPinMock.mockRejectedValue(
      new ApiError("pickup_invalid_pin", "Invalid pickup PIN", { status: 422 }),
    );

    render(<ScanView />);

    await waitFor(() => {
      expect(screen.getByTestId("scan-pin-fallback")).toBeInTheDocument();
    });

    await submitPin("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "654321");

    await waitFor(() => {
      expect(screen.getByTestId("scan-error")).toBeInTheDocument();
      expect(screen.getByText(/Invalid PIN/i)).toBeInTheDocument();
    });
  });

  it("shows offline notice when navigator is offline", () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });

    render(<ScanView />);

    expect(screen.getByTestId("scan-offline-notice")).toBeInTheDocument();
    expect(screen.getByText(/You're offline/i)).toBeInTheDocument();
  });
});
