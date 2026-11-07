import assert from "node:assert/strict";
import { test } from "node:test";
import { assertPaidTicketSpine } from "../../../e2e/fixtures/paid-ticket-contract.ts";

const valid = () => ({
  purchase: {
    checkout_group_id: "group-1",
    order_id: "order-1",
    order_item_id: "item-1",
    subtotal_ngwee: 15000,
    platform_fee_ngwee: 0,
    total_ngwee: 15000,
  },
  payment: {
    checkout_group_id: "group-1",
    order_id: "order-1",
    status: "success",
    cod: false,
    amount_ngwee: 15000,
  },
  order: {
    id: "order-1",
    checkout_group_id: "group-1",
    paid: true,
    cod: false,
    subtotal_ngwee: 15000,
    total_ngwee: 15000,
    items: [{ id: "item-1" }],
  },
  item: { id: "item-1", order_id: "order-1", item_kind: "ticket", qty: 1, unit_price_ngwee: 15000 },
  line: { order_item_id: "item-1", ticket_type_id: "paid-1", instance_id: "instance-1" },
  tickets: [
    {
      id: "ticket-1",
      order_item_id: "item-1",
      ticket_type_id: "paid-1",
      instance_id: "instance-1",
      status: "issued",
    },
  ],
  type: { id: "paid-1", event_id: "event-1", kind: "fixed", price_ngwee: 15000 },
  instance: { id: "instance-1", event_id: "event-1" },
  event: { id: "event-1", slug: "expo", status: "published" },
  wallet: [
    {
      id: "ticket-1",
      status: "issued",
      event: { id: "event-1" },
      instance: { id: "instance-1" },
      ticket_type: { id: "paid-1", kind: "fixed" },
    },
  ],
  expected: { eventId: "event-1", slug: "expo", instanceId: "instance-1", ticketTypeId: "paid-1" },
});

test("accepts only the exact paid order to wallet spine", () =>
  assert.equal(assertPaidTicketSpine(valid()), "ticket-1"));
for (const [name, change] of [
  [
    "missing purchase item",
    (s) => {
      s.purchase.order_item_id = "";
    },
  ],
  [
    "different payment order",
    (s) => {
      s.payment.order_id = "other";
    },
  ],
  [
    "purchase fee mismatch",
    (s) => {
      s.purchase.platform_fee_ngwee = 100;
    },
  ],
  [
    "underpaid payment",
    (s) => {
      s.payment.amount_ngwee = 100;
    },
  ],
  [
    "order subtotal mismatch",
    (s) => {
      s.order.subtotal_ngwee = 100;
    },
  ],
  [
    "order total mismatch",
    (s) => {
      s.order.total_ngwee = 100;
    },
  ],
  [
    "zero item price",
    (s) => {
      s.item.unit_price_ngwee = 0;
    },
  ],
  [
    "unpaid order",
    (s) => {
      s.order.paid = false;
    },
  ],
  [
    "extra order item",
    (s) => {
      s.order.items.push({ id: "extra" });
    },
  ],
  [
    "different item order",
    (s) => {
      s.item.order_id = "other";
    },
  ],
  [
    "different ticket line",
    (s) => {
      s.line.order_item_id = "other";
    },
  ],
  [
    "free RSVP type",
    (s) => {
      s.type.kind = "free_rsvp";
      s.type.price_ngwee = 0;
    },
  ],
  [
    "different event instance",
    (s) => {
      s.instance.event_id = "other";
    },
  ],
  [
    "no issued ticket",
    (s) => {
      s.tickets = [];
    },
  ],
  [
    "different ticket item",
    (s) => {
      s.tickets[0].order_item_id = "other";
    },
  ],
  [
    "ambiguous ticket issuance",
    (s) => {
      s.tickets.push({ ...s.tickets[0], id: "ticket-2" });
    },
  ],
  [
    "wallet shows seeded free RSVP",
    (s) => {
      s.wallet = [{ ...s.wallet[0], id: "free-rsvp" }];
    },
  ],
  [
    "wallet has wrong type",
    (s) => {
      s.wallet[0].ticket_type.kind = "free_rsvp";
    },
  ],
]) {
  test(`rejects ${name}`, () => {
    const sample = valid();
    change(sample);
    assert.throws(() => assertPaidTicketSpine(sample), /paid-ticket linkage:/);
  });
}

test("accepts buyer-paid platform fee while binding order subtotal and charged total", () => {
  const sample = valid();
  sample.purchase.platform_fee_ngwee = 750;
  sample.purchase.total_ngwee = 15750;
  sample.payment.amount_ngwee = 15750;
  assert.equal(assertPaidTicketSpine(sample), "ticket-1");
});
