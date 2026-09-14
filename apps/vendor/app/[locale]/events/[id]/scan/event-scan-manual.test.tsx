// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../../packages/i18n/messages/en/vendor.json";

/**
 * Organiser event-scanner manual (PIN) fallback.
 *
 * The contract under test is deliberately the EVENT one, not the order-pickup
 * scanner's: `event-scan-*` testids, `{ticket_id, event_id, instance_id, pin}`
 * against `POST /tickets/verify`, and success/rejection states that only ever
 * repeat what the server said.
 */

const ROUTE_EVENT_PARAM = "stg-launch-expo"; // a slug, as the URL may carry
const CANONICAL_EVENT_ID = "e1000000-0000-4000-8000-000000000001";
const INSTANCE_ID = "e2000000-0000-4000-8000-000000000001";
const TICKET_ID = "e4000000-0000-4000-8000-000000000001";

const getEventMock = vi.fn();
const getScanSyncMock = vi.fn();
const verifyBatchMock = vi.fn();
const verifyManualPinMock = vi.fn();
const overrideCheckInMock = vi.fn();

let sessionValue: { access_token: string } | null = {
  access_token: "test-token",
};
let sessionLoading = false;

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    loading: sessionLoading,
    session: sessionValue,
    user: null,
  }),
}));

vi.mock("../../_lib/events-client", () => ({
  createEventsClient: () => ({ getEvent: getEventMock }),
}));

vi.mock("./_lib/scan-sync-client", () => ({
  createScanSyncClient: () => ({
    getScanSync: getScanSyncMock,
    verifyBatch: verifyBatchMock,
    verifyManualPin: verifyManualPinMock,
    overrideCheckIn: overrideCheckInMock,
  }),
}));

// The camera itself is out of scope here: jsdom has no getUserMedia, and what
// this suite asserts is the fallback surface around it. The stub exposes the
// one transition that matters -- the camera reporting itself unavailable.
vi.mock("./_components/camera-scanner", () => ({
  CameraScanner: ({ onCameraDenied }: { onCameraDenied: () => void }) => (
    <div data-testid="event-scan-camera-stub">
      <button type="button" data-testid="stub-deny-camera" onClick={onCameraDenied}>
        deny camera
      </button>
    </div>
  ),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const parts = key.split(".");
    let current: unknown = vendorMessages.scan as Record<string, unknown>;
    for (const part of parts.slice(1)) {
      if (!current || typeof current !== "object") {
        return key;
      }
      current = (current as Record<string, unknown>)[part];
    }
    if (typeof current === "string") {
      return current.replace(/\{(\w+)[^}]*\}/g, (_, token: string) =>
        String(values?.[token] ?? `{${token}}`),
      );
    }
    return key;
  },
}));

import { ScannerView } from "./_components/scanner-view";
import { manualVerifyErrorKind } from "./_lib/manual-verify-errors";

function renderScanner() {
  return render(<ScannerView eventId={ROUTE_EVENT_PARAM} />);
}

/** Waits past the event-detail load so the scanner body is on screen. */
async function renderReadyScanner() {
  renderScanner();
  await screen.findByTestId("event-scan-camera-stub");
}

async function openManualFallback() {
  const user = userEvent.setup();
  await user.click(await screen.findByTestId("event-scan-switch-manual"));
  return screen.findByTestId("event-scan-manual-fallback");
}

async function submitManual(ticketId: string, pin: string) {
  const user = userEvent.setup();
  await user.clear(screen.getByTestId("event-scan-manual-ticket-id"));
  await user.type(screen.getByTestId("event-scan-manual-ticket-id"), ticketId);
  await user.clear(screen.getByTestId("event-scan-manual-pin"));
  await user.type(screen.getByTestId("event-scan-manual-pin"), pin);
  await user.click(screen.getByTestId("event-scan-manual-submit"));
}

beforeEach(() => {
  sessionValue = { access_token: "test-token" };
  sessionLoading = false;
  getEventMock.mockResolvedValue({
    event: {
      id: CANONICAL_EVENT_ID,
      slug: ROUTE_EVENT_PARAM,
      title: "Synthetic staging launch expo",
      instances: [
        {
          id: INSTANCE_ID,
          starts_at: new Date(Date.now() + 3_600_000).toISOString(),
          ends_at: null,
          capacity: 200,
          tickets_sold: 1,
        },
      ],
    },
  });
  getScanSyncMock.mockResolvedValue({
    event_id: CANONICAL_EVENT_ID,
    instance_id: INSTANCE_ID,
    starts_at: new Date().toISOString(),
    window_seconds: 60,
    horizon_start_window: 0,
    horizon_end_window: 0,
    tickets: [],
  });
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
    writable: true,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("event scanner · manual fallback surface", () => {
  it("renders the manual form behind an event-namespaced affordance", async () => {
    await renderReadyScanner();

    // The affordance is event-scoped, not the order-pickup scanner's control.
    expect(screen.queryByTestId("scan-switch-pin")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scan-pin-fallback")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();

    const form = await openManualFallback();

    expect(form).toBeInTheDocument();
    expect(screen.getByTestId("event-scan-manual-ticket-id")).toBeInTheDocument();
    expect(screen.getByTestId("event-scan-manual-pin")).toBeInTheDocument();
    expect(screen.getByTestId("event-scan-manual-submit")).toBeInTheDocument();
    // Both fields are required before the organiser can submit anything.
    expect(screen.getByTestId("event-scan-manual-submit")).toBeDisabled();
  });

  it("exposes the fallback automatically when the camera is denied", async () => {
    const user = userEvent.setup();
    await renderReadyScanner();

    await user.click(screen.getByTestId("stub-deny-camera"));

    expect(await screen.findByTestId("event-scan-manual-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("event-scan-camera-denied-notice")).toBeInTheDocument();
    // No dead end and no way back to a camera that will not start.
    expect(screen.queryByTestId("event-scan-switch-manual")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-switch-camera")).not.toBeInTheDocument();
  });

  it("returns to the camera from the manual form when the camera works", async () => {
    const user = userEvent.setup();
    await renderReadyScanner();
    await openManualFallback();

    await user.click(screen.getByTestId("event-scan-switch-camera"));

    expect(await screen.findByTestId("event-scan-camera-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();
  });
});

describe("event scanner · manual verification outcomes", () => {
  it("checks a ticket in on a correct PIN and reports the server's verdict", async () => {
    verifyManualPinMock.mockResolvedValue({
      ticket_id: TICKET_ID,
      from_status: "issued",
      to_status: "checked_in",
      checked_in_at: "2026-09-14T10:00:00Z",
      event_id: CANONICAL_EVENT_ID,
      instance_id: INSTANCE_ID,
      holder_name: "Chanda Mwansa",
      ticket_type_name: "General admission",
      event_title: "Synthetic staging launch expo",
      id_check_required: false,
    });

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(1));
    // The canonical event UUID from the API, never the raw route segment.
    expect(verifyManualPinMock).toHaveBeenCalledWith({
      ticket_id: TICKET_ID,
      event_id: CANONICAL_EVENT_ID,
      instance_id: INSTANCE_ID,
      pin: "654321",
    });

    expect(await screen.findByTestId("event-scan-flash-success")).toHaveTextContent("Checked in");
    expect(screen.getByTestId("event-scan-flash-success")).toHaveTextContent("Chanda Mwansa");
    expect(screen.queryByTestId("event-scan-flash-error")).not.toBeInTheDocument();
    // The PIN is a single-use credential: it never lingers in the field.
    expect(screen.getByTestId("event-scan-manual-pin")).toHaveValue("");
  });

  it("rejects an incorrect PIN and offers no override shortcut", async () => {
    verifyManualPinMock.mockRejectedValue(
      new ApiError("ticket_invalid_pin", "Invalid ticket PIN", { status: 422 }),
    );

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "000000");

    const flash = await screen.findByTestId("event-scan-flash-error");
    expect(flash).toHaveTextContent("Incorrect PIN");
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
    // A wrong PIN must never be waved through with an organiser override.
    expect(screen.queryByText("Admit with organiser override")).not.toBeInTheDocument();
  });

  it("rejects a duplicate check-in of an already-spent ticket", async () => {
    verifyManualPinMock
      .mockResolvedValueOnce({
        ticket_id: TICKET_ID,
        from_status: "issued",
        to_status: "checked_in",
        checked_in_at: "2026-09-14T10:00:00Z",
        event_id: CANONICAL_EVENT_ID,
        instance_id: INSTANCE_ID,
        holder_name: "Chanda Mwansa",
        ticket_type_name: "General admission",
        event_title: "Synthetic staging launch expo",
        id_check_required: false,
      })
      .mockRejectedValueOnce(
        new ApiError("ticket_already_checked_in", "Ticket has already been checked in", {
          status: 409,
        }),
      );

    await renderReadyScanner();
    await openManualFallback();

    await submitManual(TICKET_ID, "654321");
    expect(await screen.findByTestId("event-scan-flash-success")).toBeInTheDocument();

    // Same ticket, same PIN, second time -- single-use is enforced server-side
    // and the second attempt is a rejection, not a success.
    await submitManual(TICKET_ID, "654321");

    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("event-scan-flash-error")).toHaveTextContent(
      "Already checked in",
    );
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
  });

  it("surfaces a server authorization refusal instead of admitting the guest", async () => {
    verifyManualPinMock.mockRejectedValue(
      new ApiError("forbidden", "You do not have access to this event", {
        status: 403,
      }),
    );

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    expect(await screen.findByTestId("event-scan-flash-error")).toHaveTextContent("Not permitted");
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
  });

  it("does not attempt an offline manual check-in it cannot honestly resolve", async () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: false,
      writable: true,
    });

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    expect(await screen.findByTestId("event-scan-flash-error")).toHaveTextContent("You're offline");
    expect(verifyManualPinMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
  });
});

describe("event scanner · no unauthorized verification path", () => {
  it("renders no scanner or manual form without a session", async () => {
    sessionValue = null;

    renderScanner();

    expect(
      await screen.findByText("Sign in as the event organiser to scan tickets"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-switch-manual")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-submit")).not.toBeInTheDocument();
    expect(getEventMock).not.toHaveBeenCalled();
    expect(verifyManualPinMock).not.toHaveBeenCalled();
  });

  it("never verifies locally: every submit goes through the server client", async () => {
    verifyManualPinMock.mockRejectedValue(
      new ApiError("not_found", "Ticket not found", { status: 404 }),
    );

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("event-scan-flash-error")).toHaveTextContent("Not recognised");
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
  });
});

describe("event scanner · manual verify error mapping", () => {
  it("maps the API's verify error codes onto honest result kinds", () => {
    expect(manualVerifyErrorKind("ticket_already_checked_in")).toBe("conflict");
    expect(manualVerifyErrorKind("ticket_invalid_pin")).toBe("invalid_pin");
    expect(manualVerifyErrorKind("forbidden")).toBe("unauthorized");
    expect(manualVerifyErrorKind("not_found")).toBe("unknown_ticket");
  });

  it("never maps a wrong PIN or a spent ticket onto the overridable kind", () => {
    expect(manualVerifyErrorKind("ticket_invalid_pin")).not.toBe("rejected");
    expect(manualVerifyErrorKind("ticket_already_checked_in")).not.toBe("rejected");
  });

  it("falls back to a plain rejection for unknown and missing codes", () => {
    expect(manualVerifyErrorKind("ticket_void")).toBe("rejected");
    expect(manualVerifyErrorKind("ticket_wrong_instance")).toBe("rejected");
    expect(manualVerifyErrorKind(undefined)).toBe("rejected");
  });
});

describe("event scanner · manual fallback i18n", () => {
  it("ships every key the manual surface renders", () => {
    const eventCheckIn = vendorMessages.scan.eventCheckIn;
    expect(eventCheckIn.camera.useManual).toBeTruthy();
    expect(eventCheckIn.manual.heading).toBeTruthy();
    expect(eventCheckIn.manual.ticketIdLabel).toBeTruthy();
    expect(eventCheckIn.manual.pinLabel).toBeTruthy();
    expect(eventCheckIn.manual.submit).toBeTruthy();
    expect(eventCheckIn.result.invalidPin.title).toBe("Incorrect PIN");
    expect(eventCheckIn.result.unauthorized.title).toBe("Not permitted");
    expect(eventCheckIn.result.manualOffline.title).toBe("You're offline");
  });
});
