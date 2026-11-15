// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { decodeVapidPublicKey, WebPushOptIn } from "./web-push-opt-in";

const labels = {
  enable: "Turn on phone alerts",
  enabled: "On",
  denied: "Blocked",
  hint: "Hint",
  failed: "Failed",
};

function installPushGlobals(permission: NotificationPermission) {
  const requestPermission = vi.fn(async () => permission);
  vi.stubGlobal("Notification", { permission, requestPermission });
  vi.stubGlobal("PushManager", function PushManager() {});
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { getRegistration: vi.fn(async () => undefined) },
  });
  return requestPermission;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WebPushOptIn", () => {
  it("stays hidden while the web_push flag is off", async () => {
    installPushGlobals("default");
    const request = vi.fn(async () => ({ enabled: false, vapid_public_key: null }) as never);
    render(
      <WebPushOptIn
        request={request}
        audience="customer"
        serviceWorkerUrl="/sw.js"
        labels={labels}
      />,
    );
    await waitFor(() => expect(request).toHaveBeenCalledWith("/me/web-push"));
    expect(screen.queryByTestId("web-push-opt-in")).toBeNull();
  });

  it("offers the button when enabled but never asks permission on load", async () => {
    const requestPermission = installPushGlobals("default");
    const request = vi.fn(async () => ({ enabled: true, vapid_public_key: "AQAB" }) as never);
    render(
      <WebPushOptIn
        request={request}
        audience="vendor"
        serviceWorkerUrl="/push-sw.js"
        labels={labels}
      />,
    );
    expect(await screen.findByText("Turn on phone alerts")).toBeInTheDocument();
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("respects a denied browser permission", async () => {
    installPushGlobals("denied");
    const request = vi.fn(async () => ({ enabled: true, vapid_public_key: "AQAB" }) as never);
    render(
      <WebPushOptIn
        request={request}
        audience="customer"
        serviceWorkerUrl="/sw.js"
        labels={labels}
      />,
    );
    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("decodes a base64url VAPID public key", () => {
    expect(Array.from(decodeVapidPublicKey("AQAB"))).toEqual([1, 0, 1]);
  });
});
