// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

vi.mock("next-intl", () => {
  const translate = (key: string, values?: Record<string, string | number>) => {
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
  };
  // ONE translator instance, deliberately. Real next-intl memoises the
  // function it returns (use-intl's `useTranslationsImpl` wraps it in
  // `useMemo`), so `t` is referentially stable across renders. A mock that
  // returned a fresh closure per render would put a changing value in the
  // dependency list of ScannerView's event-load effect, so the effect would
  // re-run on every render, flip `loadingEvent` back to true, and silently
  // unmount the whole scanner — including the form the operator is typing in —
  // behind the loading spinner. That is an artefact of the mock and does not
  // happen in the app, but it makes anything to do with focus or retained
  // field state untestable, so the mock matches next-intl here.
  return { useTranslations: () => translate };
});

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

/**
 * The readiness contract `e2e/specs/event-ticket.spec.ts` depends on.
 *
 * The spec cannot ask "is the camera available?" — it settles on whichever
 * supported state the browser reaches. That only works if, once the event
 * detail resolves, EXACTLY ONE of `event-scan-manual-fallback` /
 * `event-scan-switch-manual` is on screen, and NEITHER is on screen before it.
 * An immediate probe used to answer "no switch" while still loading, skip the
 * click, and strand a camera-capable browser on the camera view.
 */
describe("event scanner · readiness contract for the E2E spec", () => {
  it("offers neither settled affordance while the event is still loading", async () => {
    let resolveEvent: (value: unknown) => void = () => {};
    getEventMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveEvent = resolve;
      }),
    );

    renderScanner();

    // The window the old immediate isVisible() probe fell into.
    expect(screen.queryByTestId("event-scan-root")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-switch-manual")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();

    resolveEvent({
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

    // Settles late — the spec waits for this rather than probing early.
    expect(await screen.findByTestId("event-scan-switch-manual")).toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();
  });

  it("settles on the switch — not the manual form — when a camera is available", async () => {
    await renderReadyScanner();

    // Exactly one of the two settled affordances, so `.or()` cannot double-match.
    expect(screen.getByTestId("event-scan-switch-manual")).toBeInTheDocument();
    expect(screen.queryByTestId("event-scan-manual-fallback")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByTestId("event-scan-switch-manual"));
    expect(await screen.findByTestId("event-scan-manual-fallback")).toBeInTheDocument();
  });

  it("settles on the manual form — with no switch to click — when the camera is denied", async () => {
    const user = userEvent.setup();
    await renderReadyScanner();

    await user.click(screen.getByTestId("stub-deny-camera"));

    expect(await screen.findByTestId("event-scan-manual-fallback")).toBeInTheDocument();
    // The spec's conditional click must find nothing here; a switch would mean
    // it clicked its way back out of the only usable surface.
    expect(screen.queryByTestId("event-scan-switch-manual")).not.toBeInTheDocument();
  });
});

describe("event scanner · instance identity is explicit, not defaulted", () => {
  it("publishes the canonical event and instance the verify call will carry", async () => {
    await renderReadyScanner();

    const root = screen.getByTestId("event-scan-root");
    // The route param is a slug; the published id is the resolved primary key.
    expect(root).toHaveAttribute("data-event-id", CANONICAL_EVENT_ID);
    expect(root).toHaveAttribute("data-instance-id", INSTANCE_ID);
    // Single-instance events render no picker — the spec must still be able to
    // assert the identity, which is why it lives on the root and not the select.
    expect(screen.queryByTestId("event-scan-instance-select")).not.toBeInTheDocument();
  });

  it("lets a second session be selected instead of inheriting the default pick", async () => {
    const OTHER_INSTANCE_ID = "e2000000-0000-4000-8000-000000000002";
    getEventMock.mockResolvedValue({
      event: {
        id: CANONICAL_EVENT_ID,
        slug: ROUTE_EVENT_PARAM,
        title: "Synthetic staging launch expo",
        instances: [
          {
            // Earliest upcoming — what pickDefaultInstance() selects unprompted.
            id: OTHER_INSTANCE_ID,
            starts_at: new Date(Date.now() + 3_600_000).toISOString(),
            ends_at: null,
            capacity: 200,
            tickets_sold: 0,
          },
          {
            id: INSTANCE_ID,
            starts_at: new Date(Date.now() + 90_000_000).toISOString(),
            ends_at: null,
            capacity: 200,
            tickets_sold: 1,
          },
        ],
      },
    });

    await renderReadyScanner();

    const root = screen.getByTestId("event-scan-root");
    // The default is NOT the seeded instance here — exactly the drift the spec
    // must not inherit silently.
    expect(root).toHaveAttribute("data-instance-id", OTHER_INSTANCE_ID);

    const picker = await screen.findByTestId("event-scan-instance-select");
    await userEvent.setup().selectOptions(picker, INSTANCE_ID);

    await waitFor(() => expect(root).toHaveAttribute("data-instance-id", INSTANCE_ID));
  });
});

describe("event scanner · rejection evidence names the verdict", () => {
  it("marks a spent ticket as `conflict`, distinct from every other failure", async () => {
    verifyManualPinMock.mockRejectedValue(
      new ApiError("ticket_already_checked_in", "Ticket has already been checked in", {
        status: 409,
      }),
    );

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    const flash = await screen.findByTestId("event-scan-flash-error");
    expect(flash).toHaveAttribute("data-scan-result-kind", "conflict");
  });

  it.each([
    ["ticket_invalid_pin", "invalid_pin"],
    ["forbidden", "unauthorized"],
    ["not_found", "unknown_ticket"],
  ])("does not let %s masquerade as single-use enforcement", async (code, expectedKind) => {
    verifyManualPinMock.mockRejectedValue(new ApiError(code, "refused", { status: 422 }));

    await renderReadyScanner();
    await openManualFallback();
    await submitManual(TICKET_ID, "654321");

    const flash = await screen.findByTestId("event-scan-flash-error");
    // Same testid as a duplicate rejection — only the kind separates them,
    // which is why the E2E spec asserts the kind and not the testid alone.
    expect(flash).toHaveAttribute("data-scan-result-kind", expectedKind);
    expect(flash).not.toHaveAttribute("data-scan-result-kind", "conflict");
  });

  it("marks a successful check-in as `valid`", async () => {
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

    expect(await screen.findByTestId("event-scan-flash-success")).toHaveAttribute(
      "data-scan-result-kind",
      "valid",
    );
  });
});

/**
 * Door-queue hazard: one operator, one form, successive guests.
 *
 * The manual form stays mounted under the result flash by design, so staff move
 * to the next guest without a dismiss tap. That makes the flash's lifetime a
 * correctness property, not a cosmetic one: whatever it shows while the NEXT
 * verification is in flight is what the operator reads when deciding to admit.
 */
describe("event scanner · one verdict belongs to one guest", () => {
  const SECOND_TICKET_ID = "e4000000-0000-4000-8000-000000000002";

  function checkedIn(holder: string) {
    return {
      ticket_id: TICKET_ID,
      from_status: "issued",
      to_status: "checked_in",
      checked_in_at: "2026-09-14T10:00:00Z",
      event_id: CANONICAL_EVENT_ID,
      instance_id: INSTANCE_ID,
      holder_name: holder,
      ticket_type_name: "General admission",
      event_title: "Synthetic staging launch expo",
      id_check_required: false,
    };
  }

  it("does not keep showing the previous guest's success while the next check is in flight", async () => {
    verifyManualPinMock
      .mockResolvedValueOnce(checkedIn("Chanda Mwansa"))
      // Second guest: the server has not answered yet.
      .mockReturnValueOnce(new Promise(() => {}));

    await renderReadyScanner();
    await openManualFallback();

    await submitManual(TICKET_ID, "654321");
    expect(await screen.findByTestId("event-scan-flash-success")).toHaveTextContent(
      "Chanda Mwansa",
    );

    await submitManual(SECOND_TICKET_ID, "112233");
    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(2));

    // The pending guest must not inherit the previous guest's green verdict —
    // an operator reading it would admit guest two on guest one's check-in.
    expect(screen.queryByTestId("event-scan-flash-success")).not.toBeInTheDocument();
    expect(screen.queryByText("Chanda Mwansa")).not.toBeInTheDocument();
    // …and the surface must still say it is working, not look idle.
    expect(screen.getByTestId("event-scan-manual-submit")).toBeDisabled();
  });

  it("sends exactly one verification when two submits land in the same tick", async () => {
    verifyManualPinMock.mockReturnValue(new Promise(() => {}));

    await renderReadyScanner();
    await openManualFallback();

    // Synchronous fills: userEvent awaits between keystrokes, which would let
    // React re-render and hide the very race under test.
    fireEvent.change(screen.getByTestId("event-scan-manual-ticket-id"), {
      target: { value: TICKET_ID },
    });
    fireEvent.change(screen.getByTestId("event-scan-manual-pin"), {
      target: { value: "654321" },
    });

    // Realistic simultaneous dispatch: an Enter-key submit racing the click on
    // the same form, both delivered before React re-renders the busy state.
    const form = screen.getByTestId("event-scan-manual-fallback");
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });

    // One guest, one server-side single-use claim attempt.
    expect(verifyManualPinMock).toHaveBeenCalledTimes(1);
  });

  it("still accepts the next guest after a completed check-in", async () => {
    verifyManualPinMock
      .mockResolvedValueOnce(checkedIn("Chanda Mwansa"))
      .mockResolvedValueOnce(checkedIn("Mutale Banda"));

    await renderReadyScanner();
    await openManualFallback();

    await submitManual(TICKET_ID, "654321");
    expect(await screen.findByTestId("event-scan-flash-success")).toHaveTextContent(
      "Chanda Mwansa",
    );

    await submitManual(SECOND_TICKET_ID, "112233");

    // A lock that never releases would strand the queue after one guest.
    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("event-scan-flash-success")).toHaveTextContent("Mutale Banda");
  });

  it("still accepts a retry after a failed check-in", async () => {
    verifyManualPinMock
      .mockRejectedValueOnce(new ApiError("ticket_invalid_pin", "Incorrect PIN", { status: 422 }))
      .mockResolvedValueOnce(checkedIn("Chanda Mwansa"));

    await renderReadyScanner();
    await openManualFallback();

    await submitManual(TICKET_ID, "000000");
    expect(await screen.findByTestId("event-scan-flash-error")).toHaveAttribute(
      "data-scan-result-kind",
      "invalid_pin",
    );

    // A failure must release the lock: the guest retypes their PIN.
    await submitManual(TICKET_ID, "654321");
    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("event-scan-flash-success")).toBeInTheDocument();
  });
});

describe("event scanner · the operator's keyboard survives a verification", () => {
  /** A verification held open, so the in-flight surface can be inspected. */
  function heldVerification() {
    let release: (value: unknown) => void = () => {};
    verifyManualPinMock.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    return {
      settle: async () => {
        await act(async () => {
          release({
            ticket_id: TICKET_ID,
            checked_in_at: new Date().toISOString(),
            holder_name: "Chanda Mwale",
            ticket_type_name: "General",
            event_title: "Synthetic staging launch expo",
            id_check_required: false,
          });
        });
      },
    };
  }

  /**
   * Submits with the operator's focus still in the PIN field — the state a real
   * browser is in when Enter implicitly submits the form.
   *
   * The form is submitted directly rather than with `userEvent`'s `{Enter}`:
   * userEvent implements implicit submission by routing through the submit
   * button, which moves focus there first, so it cannot observe what happens to
   * focus that was in the field. Real Chromium does not do that — the 360/390px
   * evidence harness drives a genuine Enter keypress and records the same
   * outcome this test asserts (docs/design/evidence/event-scanner-mobile).
   */
  async function submitFromPinField() {
    const user = userEvent.setup();
    await user.type(screen.getByTestId("event-scan-manual-ticket-id"), TICKET_ID);
    const pin = screen.getByTestId("event-scan-manual-pin");
    await user.type(pin, "123456");
    expect(document.activeElement).toBe(pin);
    fireEvent.submit(screen.getByTestId("event-scan-manual-fallback"));
    await waitFor(() => expect(verifyManualPinMock).toHaveBeenCalledTimes(1));
    return pin;
  }

  /*
   * Focus itself is NOT asserted here, deliberately. jsdom does not implement
   * the browser behaviour that makes this bug a bug: it leaves `activeElement`
   * on an input that has just been disabled, where a real browser drops focus
   * to <body>. A focus assertion in jsdom therefore passes against the old
   * `disabled` code as well as the new one, so it would prove nothing.
   *
   * The focus claim is asserted where it can actually fail — in real Chromium
   * at 360px and 390px, by scripts/qa/evidence/event-scanner-mobile/run.mjs,
   * which exits non-zero if focus leaves the field mid-verification. The
   * recorded before/after is in docs/design/evidence/event-scanner-mobile.
   *
   * What jsdom CAN hold onto is the mechanism that produces the focus
   * behaviour: the fields must be locked read-only rather than disabled.
   */
  it("locks the fields in flight without disabling them", async () => {
    await renderReadyScanner();
    await openManualFallback();
    const held = heldVerification();

    const pin = await submitFromPinField();
    const ticketId = screen.getByTestId("event-scan-manual-ticket-id");

    expect(pin).toHaveAttribute("readonly");
    expect(pin).not.toBeDisabled();
    expect(pin).toHaveAttribute("aria-busy", "true");
    expect(ticketId).toHaveAttribute("readonly");
    expect(ticketId).not.toBeDisabled();

    await held.settle();
  });

  it("still refuses edits to the locked fields while the check-in is in flight", async () => {
    await renderReadyScanner();
    await openManualFallback();
    const held = heldVerification();

    const pin = await submitFromPinField();
    // The PIN is cleared at submit; a read-only field must not let the next
    // guest's digits be typed into a verification that is already in flight.
    await userEvent.setup().type(pin, "999999");
    expect((pin as HTMLInputElement).value).toBe("");

    await held.settle();
  });

  it("hands the fields back as editable once the check-in settles", async () => {
    await renderReadyScanner();
    await openManualFallback();
    const held = heldVerification();

    const pin = await submitFromPinField();
    await held.settle();

    await waitFor(() => expect(pin).not.toHaveAttribute("readonly"));
    expect(pin).not.toBeDisabled();
    expect(pin).not.toHaveAttribute("aria-busy");
  });
});
