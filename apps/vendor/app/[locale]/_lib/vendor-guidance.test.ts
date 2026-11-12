import { describe, expect, it } from "vitest";

import { buildKycChecklist } from "../onboarding/_lib/kyc-checklist";
import {
  isBoundByDispatchCutoff,
  needsVendorAction,
  orderNextStep,
  orderTimelineSteps,
} from "../orders/_lib/order-guidance";

import { dispatchCutoffState } from "./dispatch-cutoff";
import { buildHomeTasks, MAX_HOME_TASKS } from "./home-tasks";

import type { KycApplication } from "../onboarding/_lib/types";

// Lusaka = UTC+2: 11:30 UTC is 13:30 in Lusaka.
const at = (utc: string) => new Date(`2026-11-13T${utc}:00.000Z`);

describe("dispatchCutoffState (14:00 Lusaka)", () => {
  it("counts down before the cut-off", () => {
    expect(dispatchCutoffState(at("07:15"))).toEqual({
      phase: "before",
      minutesLeft: 285,
      hours: 4,
      minutes: 45,
      urgent: false,
    });
  });

  it("turns urgent inside the last hour", () => {
    const state = dispatchCutoffState(at("11:30"));
    expect(state).toMatchObject({ phase: "before", minutesLeft: 30, urgent: true });
  });

  it("is after the cut-off at exactly 14:00 and later", () => {
    expect(dispatchCutoffState(at("12:00"))).toEqual({ phase: "after" });
    expect(dispatchCutoffState(at("21:59"))).toEqual({ phase: "after" });
  });

  it("wraps past UTC midnight into the next Lusaka morning", () => {
    // 22:30 UTC = 00:30 Lusaka next day → 13h30 until cut-off.
    expect(dispatchCutoffState(new Date("2026-11-12T22:30:00.000Z"))).toMatchObject({
      phase: "before",
      minutesLeft: 810,
    });
  });
});

describe("orderNextStep", () => {
  it.each([
    ["placed", "delivery", "confirm"],
    ["confirmed", "delivery", "pack"],
    ["processing", "delivery", "handToRider"],
    ["processing", "pickup", "readyForPickup"],
    ["ready", "pickup", "awaitCollection"],
    ["shipped", "delivery", "awaitDelivery"],
    ["delivered", "pickup", "awaitConfirmation"],
    ["completed", "delivery", "done"],
    ["cancelled", "delivery", "cancelled"],
    ["mystery", "delivery", "unknown"],
  ])("%s/%s → %s", (status, fulfilment, expected) => {
    expect(orderNextStep({ status, fulfilment })).toBe(expected);
  });

  it("flags only vendor steps as needing action", () => {
    expect(needsVendorAction({ status: "placed", fulfilment: "pickup" })).toBe(true);
    expect(needsVendorAction({ status: "shipped", fulfilment: "delivery" })).toBe(false);
    expect(needsVendorAction({ status: "cancelled", fulfilment: "delivery" })).toBe(false);
  });

  it("applies the dispatch cut-off to delivery orders not yet with the rider", () => {
    expect(isBoundByDispatchCutoff({ status: "confirmed", fulfilment: "delivery" })).toBe(true);
    expect(isBoundByDispatchCutoff({ status: "confirmed", fulfilment: "pickup" })).toBe(false);
    expect(isBoundByDispatchCutoff({ status: "shipped", fulfilment: "delivery" })).toBe(false);
  });
});

describe("orderTimelineSteps", () => {
  const events = [
    { to_status: "placed", note: null, created_at: "2026-11-13T07:00:00Z" },
    { to_status: "confirmed", note: null, created_at: "2026-11-13T07:10:00Z" },
  ];

  it("marks done / current / upcoming along the delivery path", () => {
    const steps = orderTimelineSteps({
      status: "confirmed",
      fulfilment: "delivery",
      timeline: events,
    });
    expect(steps.map((s) => [s.status, s.state])).toEqual([
      ["placed", "done"],
      ["confirmed", "current"],
      ["processing", "upcoming"],
      ["shipped", "upcoming"],
      ["delivered", "upcoming"],
      ["completed", "upcoming"],
    ]);
    expect(steps[1]?.at).toBe("2026-11-13T07:10:00Z");
  });

  it("uses the pickup path (ready instead of shipped)", () => {
    const steps = orderTimelineSteps({ status: "ready", fulfilment: "pickup", timeline: [] });
    expect(steps.map((s) => s.status)).toContain("ready");
    expect(steps.map((s) => s.status)).not.toContain("shipped");
  });

  it("ends a cancelled order at the cancellation with its reason", () => {
    const steps = orderTimelineSteps({
      status: "cancelled",
      fulfilment: "delivery",
      timeline: [
        ...events,
        { to_status: "cancelled", note: "Out of stock", created_at: "2026-11-13T08:00:00Z" },
      ],
    });
    expect(steps.map((s) => [s.status, s.state])).toEqual([
      ["placed", "done"],
      ["confirmed", "done"],
      ["cancelled", "current"],
    ]);
    expect(steps.at(-1)?.note).toBe("Out of stock");
  });

  it("shows completed as done, never as an open current step", () => {
    const steps = orderTimelineSteps({ status: "completed", fulfilment: "delivery", timeline: [] });
    expect(steps.every((s) => s.state === "done")).toBe(true);
  });
});

function kycApp(overrides: Partial<KycApplication>): KycApplication {
  return {
    vendor_id: "v1",
    vendor_status: "pending_kyc",
    kyc_tier: null,
    kyc_status: "draft",
    tier: null,
    kyc_record_id: null,
    kyc_record_status: null,
    business_name: "Chanda Electronics",
    business_category: "electronics",
    business_archetype: "market_trader",
    momo_phone: "0977123456",
    nrc_path: null,
    selfie_path: null,
    rejection_reason: null,
    rejected_docs: null,
    updated_at: "2026-11-12T00:00:00Z",
    ...overrides,
  };
}

describe("buildKycChecklist", () => {
  it("points a draft vendor at the first missing document", () => {
    const list = buildKycChecklist(kycApp({}));
    expect(list.overall).toBe("draft");
    expect(list.items.find((i) => i.key === "business")?.state).toBe("saved");
    expect(list.items.find((i) => i.key === "nrc")?.state).toBe("not_started");
    expect(list.nextKey).toBe("nrc");
    expect(list.doneCount).toBe(2);
  });

  it("shows every submitted item as under review while the team checks", () => {
    const list = buildKycChecklist(
      kycApp({ kyc_status: "under_review", nrc_path: "a", selfie_path: "b" }),
    );
    expect(list.overall).toBe("pending");
    expect(list.items.map((i) => i.state)).toEqual([
      "under_review",
      "under_review",
      "under_review",
      "under_review",
      "under_review",
    ]);
    expect(list.nextKey).toBeNull();
  });

  it("marks only the rejected document as needing a fix", () => {
    const list = buildKycChecklist(
      kycApp({
        kyc_status: "resubmit",
        nrc_path: "a",
        selfie_path: "b",
        rejected_docs: ["selfie"],
        rejection_reason: "Face not visible",
      }),
    );
    expect(list.overall).toBe("needs_fix");
    expect(list.items.find((i) => i.key === "selfie")?.state).toBe("rejected");
    expect(list.items.find((i) => i.key === "nrc")?.state).toBe("submitted");
    expect(list.items.find((i) => i.key === "review")?.state).toBe("rejected");
    expect(list.nextKey).toBe("selfie");
  });

  it("asks for both photos again when the API names no specific document", () => {
    const list = buildKycChecklist(
      kycApp({
        kyc_status: "rejected",
        momo_phone: null,
        nrc_path: "a",
        selfie_path: "b",
        rejected_docs: null,
      }),
    );
    expect(list.items.find((i) => i.key === "nrc")?.state).toBe("rejected");
    expect(list.items.find((i) => i.key === "selfie")?.state).toBe("rejected");
    // Submitted applications always carried a MoMo number, even though
    // /kyc/status does not echo it back.
    expect(list.items.find((i) => i.key === "momo")?.state).toBe("submitted");
  });

  it("never claims approval without an auditable KYC record", () => {
    const list = buildKycChecklist(
      kycApp({ kyc_status: "approved", kyc_record_id: null, nrc_path: "a", selfie_path: "b" }),
    );
    expect(list.overall).toBe("pending");
    expect(list.items.some((i) => i.state === "approved")).toBe(false);
  });

  it("approves every item when the record exists", () => {
    const list = buildKycChecklist(
      kycApp({ kyc_status: "approved", kyc_record_id: "rec-1", nrc_path: "a", selfie_path: "b" }),
    );
    expect(list.overall).toBe("approved");
    expect(list.items.every((i) => i.state === "approved")).toBe(true);
    expect(list.doneCount).toBe(5);
  });
});

describe("buildHomeTasks", () => {
  const before = dispatchCutoffState(at("07:00"));
  const urgent = dispatchCutoffState(at("11:30"));
  const after = dispatchCutoffState(at("13:00"));

  it("puts a verification fix first, then waiting orders, capped at three", () => {
    const tasks = buildHomeTasks({
      kycOverall: "needs_fix",
      needsActionCount: 2,
      hasDeliveryWaiting: true,
      cutoff: before,
      sellerKind: "products",
    });
    expect(tasks.map((t) => t.key)).toEqual(["kycFix", "ordersWaiting", "catalogueProducts"]);
    expect(tasks).toHaveLength(MAX_HOME_TASKS);
    expect(tasks[1]?.count).toBe(2);
  });

  it("escalates waiting delivery orders in the last hour before 14:00", () => {
    const tasks = buildHomeTasks({
      kycOverall: "approved",
      needsActionCount: 1,
      hasDeliveryWaiting: true,
      cutoff: urgent,
      sellerKind: "products",
    });
    expect(tasks[0]).toMatchObject({ key: "ordersWaitingUrgent", tone: "danger" });
  });

  it("explains the missed cut-off but not for pickup-only queues", () => {
    expect(
      buildHomeTasks({
        kycOverall: "approved",
        needsActionCount: 1,
        hasDeliveryWaiting: true,
        cutoff: after,
        sellerKind: "products",
      })[0]?.key,
    ).toBe("ordersWaitingAfterCutoff");
    expect(
      buildHomeTasks({
        kycOverall: "approved",
        needsActionCount: 1,
        hasDeliveryWaiting: false,
        cutoff: after,
        sellerKind: "products",
      })[0]?.key,
    ).toBe("ordersWaiting");
  });

  it("falls back to catalogue + profile upkeep for an approved, idle vendor", () => {
    const tasks = buildHomeTasks({
      kycOverall: "approved",
      needsActionCount: 0,
      hasDeliveryWaiting: false,
      cutoff: before,
      sellerKind: "services",
    });
    expect(tasks.map((t) => t.key)).toEqual(["catalogueServices", "profile"]);
  });

  it("does not block home on an unknown KYC state", () => {
    const tasks = buildHomeTasks({
      kycOverall: null,
      needsActionCount: 0,
      hasDeliveryWaiting: false,
      cutoff: before,
      sellerKind: "events",
    });
    expect(tasks[0]?.key).toBe("catalogueEvents");
  });
});
