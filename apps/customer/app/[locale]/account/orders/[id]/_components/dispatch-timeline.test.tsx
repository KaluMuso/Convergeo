// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  buildDispatchStatusUpdates,
  DispatchTimeline,
  extractDispatchFromEvents,
  parseDispatchNote,
} from "./dispatch-timeline";

afterEach(() => {
  cleanup();
});

const labels = {
  title: "Delivery updates",
  courier: "Courier",
  tracking: "Tracking note",
  empty: "No dispatch updates yet.",
  statusUpdates: "Status updates",
};

describe("parseDispatchNote", () => {
  it("parses M13-P06 admin dispatch note format", () => {
    const parsed = parseDispatchNote(
      "[dispatch] courier=Yango | tracking: Driver en route, plate BAK 1234",
    );
    expect(parsed).toEqual({
      courier: "Yango",
      trackingNote: "Driver en route, plate BAK 1234",
    });
  });

  it("returns null for non-dispatch notes", () => {
    expect(parseDispatchNote("Order shipped by vendor")).toBeNull();
  });
});

describe("extractDispatchFromEvents", () => {
  it("returns the latest dispatch entry", () => {
    const result = extractDispatchFromEvents([
      { note: "Vendor shipped", toStatus: "shipped", occurredAt: "2026-07-01T10:00:00Z" },
      {
        note: "[dispatch] courier=InDrive | tracking: ETA 30 min",
        toStatus: "shipped",
        occurredAt: "2026-07-01T11:00:00Z",
      },
    ]);
    expect(result).toEqual({
      courier: "InDrive",
      trackingNote: "ETA 30 min",
    });
  });
});

describe("DispatchTimeline", () => {
  it("renders courier, tracking, and status updates", () => {
    render(
      <DispatchTimeline
        fulfilment="delivery"
        status="shipped"
        courier="Yango"
        trackingNote="Driver John, plate BAK 1234"
        statusUpdates={[
          {
            statusKey: "shipped",
            label: "On the way to you",
            occurredAt: "2026-07-10T12:00:00.000Z",
          },
          {
            statusKey: "dispatch-shipped",
            label: "Yango",
            occurredAt: "2026-07-10T12:05:00.000Z",
            detail: "Driver John, plate BAK 1234",
          },
        ]}
        labels={labels}
      />,
    );

    expect(screen.getByRole("heading", { name: "Delivery updates" })).toBeInTheDocument();
    expect(screen.getAllByText("Yango").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Driver John, plate BAK 1234").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("On the way to you")).toBeInTheDocument();
    expect(screen.getByText("Status updates")).toBeInTheDocument();
  });

  it("hides for pickup fulfilment", () => {
    const { container } = render(
      <DispatchTimeline
        fulfilment="pickup"
        status="ready"
        courier="Yango"
        trackingNote="N/A"
        statusUpdates={[]}
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("buildDispatchStatusUpdates", () => {
  it("maps timeline steps and dispatch events", () => {
    const updates = buildDispatchStatusUpdates(
      [
        {
          step_key: "shipped",
          state: "completed",
          occurred_at: "2026-07-10T10:00:00.000Z",
          escrow_copy_key: "none",
        },
      ],
      { shipped: "On the way" },
      [
        {
          note: "[dispatch] courier=Yango | tracking: Plate ABC",
          toStatus: "shipped",
          occurredAt: "2026-07-10T10:05:00.000Z",
        },
      ],
    );

    expect(updates).toHaveLength(2);
    expect(updates[0]?.label).toBe("On the way");
    expect(updates[1]?.detail).toBe("Plate ABC");
  });
});
