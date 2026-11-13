import { describe, expect, it } from "vitest";

import {
  googleMapsDirectionsUrl,
  actionsFor,
  groupReadyOrders,
  nextJobKind,
  buildCourierPayload,
  canNotify,
  classifyHandoverError,
  type Courier,
  courierToForm,
  couriersForOrder,
  type Dispatch,
  groupDispatches,
  isHandoverCodeWellFormed,
  isPodPublicIdWellFormed,
  isStale,
  kwachaTextToNgwee,
  minutesWaiting,
  ngweeToKwachaText,
  targetStatusFor,
  whatsAppShareUrl,
  zonePriceNgwee,
} from "./dispatch-board-model";

function courier(overrides: Partial<Courier> = {}): Courier {
  return {
    id: "c1",
    name: "TownStar",
    contact_whatsapp_e164: "+260977000001",
    contact_email: null,
    integration_kind: "manual",
    active: true,
    notes: null,
    zones: [],
    ...overrides,
  };
}

function dispatch(overrides: Partial<Dispatch> = {}): Dispatch {
  return {
    id: "d1",
    order_id: "o1",
    order_reference: "ord-1a2b3c4d",
    courier_partner_id: "c1",
    courier_name: "TownStar",
    status: "requested",
    allowed_next: ["accepted", "failed", "cancelled"],
    courier_reference: null,
    cod_amount_ngwee: 105_050,
    quoted_price_ngwee: null,
    pod_photo_public_id: null,
    delivered_via: null,
    failure_reason: null,
    notify_count: 0,
    last_notified_at: null,
    requested_at: "2026-11-09T08:00:00.000Z",
    accepted_at: null,
    picked_up_at: null,
    delivered_at: null,
    failed_at: null,
    cancelled_at: null,
    vendor_name: "Lusaka Electronics",
    order_status: "processing",
    delivery_zone: "lusaka_a",
    handover_locked: false,
    ...overrides,
  };
}

describe("groupDispatches", () => {
  it("puts in-flight work first in pipeline order and closed work last", () => {
    const grouped = groupDispatches([
      dispatch({ id: "a", status: "picked_up", requested_at: "2026-11-09T07:00:00Z" }),
      dispatch({ id: "b", status: "delivered", requested_at: "2026-11-09T06:00:00Z" }),
      dispatch({ id: "c", status: "requested", requested_at: "2026-11-09T09:00:00Z" }),
      dispatch({ id: "d", status: "requested", requested_at: "2026-11-09T08:00:00Z" }),
      dispatch({ id: "e", status: "failed", requested_at: "2026-11-09T09:30:00Z" }),
    ]);
    expect(grouped.active.map((item) => item.id)).toEqual(["d", "c", "a"]);
    expect(grouped.closed.map((item) => item.id)).toEqual(["e", "b"]);
  });
});

describe("couriersForOrder", () => {
  const all = [
    courier({ id: "everywhere" }),
    courier({ id: "zone-a", zones: [{ zone_key: "lusaka_a", price_ngwee: 2_500 }] }),
    courier({ id: "zone-c", zones: [{ zone_key: "lusaka_c", price_ngwee: null }] }),
    courier({ id: "inactive", active: false }),
    courier({ id: "api", integration_kind: "api" }),
  ];

  it("offers only active manual couriers that serve the zone", () => {
    expect(couriersForOrder(all, "lusaka_a").map((item) => item.id)).toEqual([
      "everywhere",
      "zone-a",
    ]);
    expect(couriersForOrder(all, "lusaka_c").map((item) => item.id)).toEqual([
      "everywhere",
      "zone-c",
    ]);
  });

  it("reads the per-zone price in ngwee", () => {
    expect(zonePriceNgwee(all[1]!, "lusaka_a")).toBe(2_500);
    expect(zonePriceNgwee(all[2]!, "lusaka_c")).toBeNull();
    expect(zonePriceNgwee(all[0]!, null)).toBeNull();
  });
});

describe("actionsFor", () => {
  it("maps the API's allowed_next to board buttons", () => {
    expect(actionsFor(dispatch())).toEqual(["accept", "fail", "cancel"]);
    expect(
      actionsFor(
        dispatch({ status: "accepted", allowed_next: ["picked_up", "failed", "cancelled"] }),
      ),
    ).toEqual(["pickUp", "fail", "cancel"]);
  });

  it("offers the combined delivered + cash step first, once picked up", () => {
    expect(
      actionsFor(dispatch({ status: "picked_up", allowed_next: ["delivered", "failed"] })),
    ).toEqual(["complete", "verifyHandover", "deliverWithPhoto", "fail", "recordCost"]);
  });

  it("offers only the courier cost for terminal dispatches", () => {
    expect(actionsFor(dispatch({ status: "delivered", allowed_next: [] }))).toEqual(["recordCost"]);
    expect(actionsFor(dispatch({ status: "requested", allowed_next: [] }))).toEqual([]);
  });

  it("closes a return only by the shop's acknowledgement", () => {
    expect(
      actionsFor(
        dispatch({
          status: "picked_up",
          allowed_next: ["delivered", "failed"],
          direction: "return",
        }),
      ),
    ).toEqual(["fail", "returned", "recordCost"]);
  });

  it("groups ready orders by checkout and address, and picks the next job", () => {
    const base = {
      order_reference: "ord-x",
      status: "ready",
      vendor_name: "Shop",
      delivery_zone: "lusaka_a",
      cod: true,
      cod_amount_ngwee: 1000,
      subtotal_ngwee: 1000,
      delivery_fee_ngwee: 0,
      item_count: 1,
      created_at: "2026-11-13T08:00:00Z",
      last_failed_reason: null,
    };
    const groups = groupReadyOrders([
      { ...base, order_id: "a", group_key: "g1:addr", dropoff_landmark: "Kabulonga Spar" },
      { ...base, order_id: "b", group_key: "g1:addr", dropoff_landmark: "Kabulonga Spar" },
      { ...base, order_id: "c", group_key: null },
    ]);
    expect(groups.map((group) => group.orders.map((order) => order.order_id))).toEqual([
      ["a", "b"],
      ["c"],
    ]);
    expect(groups[0]?.landmark).toBe("Kabulonga Spar");
    expect(nextJobKind({ status: "ready", delivery_attempts: 0 })).toBe("first");
    expect(nextJobKind({ status: "shipped", delivery_attempts: 1 })).toBe("retry");
    expect(nextJobKind({ status: "shipped", delivery_attempts: 2 })).toBe("returnOnly");
  });

  it("maps actions back to target statuses", () => {
    expect(targetStatusFor("accept")).toBe("accepted");
    expect(targetStatusFor("pickUp")).toBe("picked_up");
    expect(targetStatusFor("deliverWithPhoto")).toBe("delivered");
    expect(targetStatusFor("verifyHandover")).toBeNull();
  });

  it("only allows notifying before pickup", () => {
    expect(canNotify({ status: "requested" })).toBe(true);
    expect(canNotify({ status: "accepted" })).toBe(true);
    expect(canNotify({ status: "picked_up" })).toBe(false);
  });
});

describe("input validation", () => {
  it("accepts exactly six digits for the handover code", () => {
    expect(isHandoverCodeWellFormed("004211")).toBe(true);
    expect(isHandoverCodeWellFormed(" 004211 ")).toBe(true);
    expect(isHandoverCodeWellFormed("42111")).toBe(false);
    expect(isHandoverCodeWellFormed("42a111")).toBe(false);
  });

  it("accepts Cloudinary public ids but never URLs", () => {
    expect(isPodPublicIdWellFormed("convergeo/pod/ord-1a2b3c4d")).toBe(true);
    expect(isPodPublicIdWellFormed("https://res.cloudinary.com/x.jpg")).toBe(false);
    expect(isPodPublicIdWellFormed("")).toBe(false);
  });
});

describe("handover error classification", () => {
  it("surfaces attempts remaining and lockout", () => {
    expect(
      classifyHandoverError({
        code: "dispatch_handover_invalid",
        status: 422,
        details: { attempts_remaining: 3 },
      }),
    ).toEqual({ kind: "invalid", attemptsRemaining: 3, retryAfter: null });
    expect(
      classifyHandoverError({
        code: "dispatch_handover_locked",
        status: 429,
        details: { retry_after: 900 },
      }),
    ).toEqual({ kind: "locked", attemptsRemaining: 0, retryAfter: 900 });
    expect(classifyHandoverError({ code: "rate_limited", status: 429 }).kind).toBe("rateLimited");
    expect(classifyHandoverError({ code: "boom", status: 500 }).kind).toBe("generic");
  });
});

describe("copy-message fallback", () => {
  it("builds a wa.me link with the courier number and encoded text", () => {
    expect(whatsAppShareUrl("+260977000001", "Pickup: Kamwala & co")).toBe(
      "https://wa.me/260977000001?text=Pickup%3A%20Kamwala%20%26%20co",
    );
    expect(whatsAppShareUrl(null, "hi")).toBe("https://wa.me/?text=hi");
    expect(whatsAppShareUrl("+12", "hi")).toBeNull();
  });
});

describe("stale requested dispatch (45 minutes)", () => {
  const now = new Date("2026-11-09T08:46:00.000Z");
  it("flags requested dispatches waiting 45+ minutes", () => {
    expect(minutesWaiting("2026-11-09T08:00:00.000Z", now)).toBe(46);
    expect(isStale(dispatch(), now)).toBe(true);
    expect(isStale(dispatch({ requested_at: "2026-11-09T08:30:00.000Z" }), now)).toBe(false);
    expect(isStale(dispatch({ status: "accepted" }), now)).toBe(false);
  });
});

describe("courier form", () => {
  it("converts kwacha text to integer ngwee without float math", () => {
    expect(kwachaTextToNgwee("25")).toBe(2_500);
    expect(kwachaTextToNgwee("25.5")).toBe(2_550);
    expect(kwachaTextToNgwee("0.07")).toBe(7);
    expect(kwachaTextToNgwee("")).toBeNull();
    expect(kwachaTextToNgwee("25.555")).toBeNaN();
    expect(kwachaTextToNgwee("-3")).toBeNaN();
    expect(ngweeToKwachaText(2_550)).toBe("25.50");
    expect(ngweeToKwachaText(null)).toBe("");
  });

  it("builds a manual courier payload with zone prices in ngwee", () => {
    const form = courierToForm(null, ["lusaka_a", "lusaka_b"]);
    form.name = " TownStar ";
    form.whatsapp = "+260977000001";
    form.zones.lusaka_a = { enabled: true, priceKwacha: "25" };
    const result = buildCourierPayload(form);
    expect(result).toEqual({
      ok: true,
      payload: {
        name: "TownStar",
        contact_whatsapp_e164: "+260977000001",
        contact_email: null,
        integration_kind: "manual",
        active: true,
        notes: null,
        zones: [{ zone_key: "lusaka_a", price_ngwee: 2_500 }],
      },
    });
  });

  it("rejects missing contact, bad phone and bad price", () => {
    const form = courierToForm(null, ["lusaka_a"]);
    form.name = "Platinum";
    expect(buildCourierPayload(form)).toEqual({ ok: false, error: "contact" });
    form.whatsapp = "0977000001";
    expect(buildCourierPayload(form)).toEqual({ ok: false, error: "whatsapp" });
    form.whatsapp = "+260977000001";
    form.zones.lusaka_a = { enabled: true, priceKwacha: "abc" };
    expect(buildCourierPayload(form)).toEqual({ ok: false, error: "price" });
  });

  it("round-trips an existing courier into the form", () => {
    const form = courierToForm(courier({ zones: [{ zone_key: "lusaka_b", price_ngwee: 4_500 }] }), [
      "lusaka_a",
      "lusaka_b",
    ]);
    expect(form.zones).toEqual({
      lusaka_a: { enabled: false, priceKwacha: "" },
      lusaka_b: { enabled: true, priceKwacha: "45.00" },
    });
  });
});

describe("googleMapsDirectionsUrl (dispatcher link-out, no Maps API call)", () => {
  const order = {
    order_id: "o1",
    order_reference: "ord-1",
    status: "ready",
    vendor_name: "Shop",
    delivery_zone: "lusaka_a",
    cod: false,
    cod_amount_ngwee: 0,
    subtotal_ngwee: 1000,
    delivery_fee_ngwee: 3000,
    item_count: 1,
    created_at: "2026-11-13T10:00:00Z",
    last_failed_reason: null,
  };

  it("routes shop pin to customer pin", () => {
    const url = googleMapsDirectionsUrl({
      ...order,
      pickup_lat: -15.43,
      pickup_lng: 28.305,
      dropoff_lat: -15.425,
      dropoff_lng: 28.327,
    });
    expect(url).toBe(
      "https://www.google.com/maps/dir/?api=1&destination=-15.425000%2C28.327000&travelmode=driving&origin=-15.430000%2C28.305000",
    );
  });

  it("falls back to the area name, and to nothing without a destination", () => {
    const url = googleMapsDirectionsUrl({ ...order, dropoff_area: "Kabulonga" });
    expect(url).toContain("destination=Kabulonga%2C+Lusaka%2C+Zambia");
    expect(url).not.toContain("origin=");
    expect(googleMapsDirectionsUrl(order)).toBeNull();
  });
});
