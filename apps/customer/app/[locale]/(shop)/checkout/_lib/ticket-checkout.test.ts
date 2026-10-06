import { describe, expect, it, vi } from "vitest";

import { loadTicketOrder } from "./ticket-checkout";

const GROUP = "00000000-0000-4000-8000-000000000001";
const USER = "00000000-0000-4000-8000-000000000002";
const ORDER = "00000000-0000-4000-8000-000000000003";
const ITEM = "00000000-0000-4000-8000-000000000004";
const OTHER = "00000000-0000-4000-8000-000000000009";

function database(overrides: Record<string, unknown> = {}) {
  const rows: Record<string, unknown> = {
    checkout_groups: { id: GROUP, customer_id: USER, status: "pending", total_ngwee: 52_500 },
    orders: [{ id: ORDER, checkout_group_id: GROUP, customer_id: USER, cod: false }],
    order_items: [
      {
        id: ITEM,
        order_id: ORDER,
        item_kind: "ticket",
        qty: 2,
        unit_price_ngwee: 25_000,
        title_snapshot: "Evening ticket",
      },
    ],
    order_item_tickets: {
      order_item_id: ITEM,
      ticket_type_id: "type-1",
      instance_id: "instance-1",
    },
    ...overrides,
  };
  const eq = vi.fn();
  const from = vi.fn((table: string) => {
    const result = { data: rows[table], error: null };
    const query = {
      select: () => query,
      eq: (...args: unknown[]) => {
        eq(table, ...args);
        return query;
      },
      maybeSingle: async () => result,
      then: (resolve: (value: typeof result) => unknown) => Promise.resolve(result).then(resolve),
    };
    return query;
  });
  return { db: { from } as never, eq, from };
}

describe("ticket checkout source contract", () => {
  it("loads only the buyer's existing paid ticket order and server total", async () => {
    const { db, eq } = database();
    await expect(loadTicketOrder(db, GROUP, USER)).resolves.toEqual({
      groupId: GROUP,
      orderId: ORDER,
      title: "Evening ticket",
      qty: 2,
      totalNgwee: 52_500,
      status: "pending",
    });
    expect(eq).toHaveBeenCalledWith("checkout_groups", "customer_id", USER);
    expect(eq).toHaveBeenCalledWith("orders", "checkout_group_id", GROUP);
    expect(eq).toHaveBeenCalledWith("order_items", "order_id", ORDER);
    expect(eq).toHaveBeenCalledWith("order_item_tickets", "order_item_id", ITEM);
  });

  it.each([
    ["missing group", { checkout_groups: null }],
    ["completed group", { checkout_groups: { status: "completed", total_ngwee: 52_500 } }],
    ["free group", { checkout_groups: { status: "pending", total_ngwee: 0 } }],
    ["no order", { orders: [] }],
    [
      "multiple orders",
      {
        orders: [
          { id: ORDER, cod: false },
          { id: "other", cod: false },
        ],
      },
    ],
    ["COD order", { orders: [{ id: ORDER, cod: true }] }],
    ["product line", { order_items: [{ item_kind: "product", qty: 1, unit_price_ngwee: 10 }] }],
    ["multiple lines", { order_items: [{ id: ITEM }, { id: "other" }] }],
    ["missing ticket detail", { order_item_tickets: null }],
    [
      "different group ID",
      { checkout_groups: { id: OTHER, customer_id: USER, status: "pending", total_ngwee: 52_500 } },
    ],
    [
      "different group owner",
      {
        checkout_groups: { id: GROUP, customer_id: OTHER, status: "pending", total_ngwee: 52_500 },
      },
    ],
    [
      "order in another group",
      { orders: [{ id: ORDER, checkout_group_id: OTHER, customer_id: USER, cod: false }] },
    ],
    [
      "order owned by another buyer",
      { orders: [{ id: ORDER, checkout_group_id: GROUP, customer_id: OTHER, cod: false }] },
    ],
    [
      "item in another order",
      {
        order_items: [
          { id: ITEM, order_id: OTHER, item_kind: "ticket", qty: 2, unit_price_ngwee: 25_000 },
        ],
      },
    ],
    [
      "ticket line on another item",
      {
        order_item_tickets: {
          order_item_id: OTHER,
          ticket_type_id: "type-1",
          instance_id: "instance-1",
        },
      },
    ],
  ])("rejects %s before payment", async (_label, override) => {
    const { db } = database(override);
    await expect(loadTicketOrder(db, GROUP, USER)).rejects.toThrow();
  });

  it("rejects malformed group before querying", async () => {
    const { db, from } = database();
    await expect(loadTicketOrder(db, "bad", USER)).rejects.toThrow();
    expect(from).not.toHaveBeenCalled();
  });

  it("can verify a completed ticket group for read-only payment resumption", async () => {
    const { db } = database({
      checkout_groups: { id: GROUP, customer_id: USER, status: "completed", total_ngwee: 52_500 },
    });
    await expect(loadTicketOrder(db, GROUP, USER, true)).resolves.toMatchObject({
      groupId: GROUP,
      orderId: ORDER,
      status: "completed",
    });
  });
});
