/** Pure, source-only contract for the one paid ticket order created by the picker. */
export type PaidTicketSpine = {
  purchase: {
    checkout_group_id: string;
    order_id: string;
    order_item_id: string;
    subtotal_ngwee: number;
    platform_fee_ngwee: number;
    total_ngwee: number;
  };
  payment: {
    checkout_group_id: string;
    order_id: string;
    status: string;
    cod: boolean;
    amount_ngwee: number;
  };
  order: {
    id: string;
    checkout_group_id: string;
    paid: boolean;
    cod: boolean;
    subtotal_ngwee: number;
    total_ngwee: number;
    items: { id: string }[];
  };
  item: { id: string; order_id: string; item_kind: string; qty: number; unit_price_ngwee: number };
  line: { order_item_id: string; ticket_type_id: string; instance_id: string };
  tickets: {
    id: string;
    order_item_id: string | null;
    ticket_type_id: string;
    instance_id: string;
    status: string;
  }[];
  type: { id: string; event_id: string; kind: string; price_ngwee: number };
  instance: { id: string; event_id: string };
  event: { id: string; slug: string; status: string };
  wallet: {
    id: string;
    status: string;
    event: { id: string };
    instance: { id: string };
    ticket_type: { id: string; kind: string };
  }[];
  expected: { eventId: string; slug: string; instanceId: string; ticketTypeId: string };
};

/** Reject absent, mixed, free, unpaid, or multiply-issued linkage. No credential values in errors. */
export function assertPaidTicketSpine(s: PaidTicketSpine): string {
  const fail = (reason: string): never => {
    throw new Error(`paid-ticket linkage: ${reason}`);
  };
  const p = s.purchase;
  if (
    !p.checkout_group_id ||
    !p.order_id ||
    !p.order_item_id ||
    !(p.subtotal_ngwee > 0) ||
    p.platform_fee_ngwee < 0 ||
    p.total_ngwee !== p.subtotal_ngwee + p.platform_fee_ngwee
  )
    fail("purchase identity or positive total missing");
  if (
    s.payment.checkout_group_id !== p.checkout_group_id ||
    s.payment.order_id !== p.order_id ||
    s.payment.status !== "success" ||
    s.payment.cod ||
    s.payment.amount_ngwee !== p.total_ngwee
  )
    fail("payment does not settle purchased order");
  if (
    s.order.id !== p.order_id ||
    s.order.checkout_group_id !== p.checkout_group_id ||
    !s.order.paid ||
    s.order.cod ||
    s.order.subtotal_ngwee !== p.subtotal_ngwee ||
    s.order.total_ngwee !== p.subtotal_ngwee ||
    s.order.items.length !== 1 ||
    s.order.items[0]?.id !== p.order_item_id
  )
    fail("paid order or item mismatch");
  if (
    s.item.id !== p.order_item_id ||
    s.item.order_id !== p.order_id ||
    s.item.item_kind !== "ticket" ||
    s.item.qty !== 1 ||
    s.item.unit_price_ngwee !== p.subtotal_ngwee
  )
    fail("order item mismatch");
  if (
    s.line.order_item_id !== p.order_item_id ||
    s.line.ticket_type_id !== s.expected.ticketTypeId ||
    s.line.instance_id !== s.expected.instanceId
  )
    fail("ticket line mismatch");
  if (
    s.type.id !== s.line.ticket_type_id ||
    s.type.event_id !== s.expected.eventId ||
    s.type.kind === "free_rsvp" ||
    !(s.type.price_ngwee > 0)
  )
    fail("paid ticket type mismatch");
  if (
    s.instance.id !== s.line.instance_id ||
    s.instance.event_id !== s.expected.eventId ||
    s.event.id !== s.expected.eventId ||
    s.event.slug !== s.expected.slug ||
    s.event.status !== "published"
  )
    fail("event or instance mismatch");
  if (s.tickets.length !== 1) fail("expected exactly one issued ticket for purchased item");
  const t = s.tickets[0];
  if (
    !t?.id ||
    t.order_item_id !== p.order_item_id ||
    t.ticket_type_id !== s.line.ticket_type_id ||
    t.instance_id !== s.line.instance_id ||
    t.status !== "issued"
  )
    fail("issued ticket mismatch");
  const matches = s.wallet.filter(
    (w) =>
      w.id === t.id &&
      w.status === "issued" &&
      w.event.id === s.expected.eventId &&
      w.instance.id === s.expected.instanceId &&
      w.ticket_type.id === s.expected.ticketTypeId &&
      w.ticket_type.kind !== "free_rsvp",
  );
  if (matches.length !== 1) fail("purchased ticket missing or mismatched in buyer wallet");
  return t.id;
}
