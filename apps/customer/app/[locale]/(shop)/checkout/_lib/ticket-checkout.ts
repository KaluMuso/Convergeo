import type { getBrowserClient } from "@vergeo/auth/browser-client-lazy";

type BrowserClient = Awaited<ReturnType<typeof getBrowserClient>>;

export type TicketOrder = {
  groupId: string;
  orderId: string;
  title: string;
  qty: number;
  totalNgwee: number;
  status: "pending" | "completed";
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** RLS reads are a display guard; payment endpoints enforce ownership again. */
export async function loadTicketOrder(
  db: BrowserClient,
  groupId: string,
  userId: string,
  allowCompleted = false,
): Promise<TicketOrder> {
  if (!UUID.test(groupId)) throw new Error("Invalid ticket checkout group");

  const { data: group, error: groupError } = await db
    .from("checkout_groups")
    .select("id,customer_id,status,total_ngwee")
    .eq("id", groupId)
    .eq("customer_id", userId)
    .maybeSingle();
  if (
    groupError ||
    !group ||
    group.id !== groupId ||
    group.customer_id !== userId ||
    (group.status !== "pending" && !(allowCompleted && group.status === "completed")) ||
    !Number.isSafeInteger(group.total_ngwee) ||
    group.total_ngwee <= 0
  ) {
    throw new Error("Ticket checkout is unavailable");
  }

  const { data: orders, error: ordersError } = await db
    .from("orders")
    .select("id,checkout_group_id,customer_id,cod")
    .eq("checkout_group_id", groupId)
    .eq("customer_id", userId);
  const order = orders?.[0];
  if (
    ordersError ||
    orders?.length !== 1 ||
    !order ||
    order.checkout_group_id !== groupId ||
    order.customer_id !== userId ||
    order.cod
  ) {
    throw new Error("Ticket order linkage is invalid");
  }

  const { data: items, error: itemsError } = await db
    .from("order_items")
    .select("id,order_id,item_kind,qty,unit_price_ngwee,title_snapshot")
    .eq("order_id", order.id);
  const item = items?.[0];
  if (
    itemsError ||
    items?.length !== 1 ||
    !item ||
    item.order_id !== order.id ||
    item.item_kind !== "ticket" ||
    !Number.isSafeInteger(item.qty) ||
    item.qty < 1 ||
    !Number.isSafeInteger(item.unit_price_ngwee) ||
    item.unit_price_ngwee <= 0
  ) {
    throw new Error("Ticket line linkage is invalid");
  }

  const { data: ticketLine, error: ticketError } = await db
    .from("order_item_tickets")
    .select("order_item_id,ticket_type_id,instance_id")
    .eq("order_item_id", item.id)
    .maybeSingle();
  if (
    ticketError ||
    !ticketLine ||
    ticketLine.order_item_id !== item.id ||
    !ticketLine.ticket_type_id ||
    !ticketLine.instance_id
  ) {
    throw new Error("Ticket detail linkage is invalid");
  }

  return {
    groupId,
    orderId: order.id,
    title: item.title_snapshot || "Ticket",
    qty: item.qty,
    totalNgwee: group.total_ngwee,
    status: group.status as "pending" | "completed",
  };
}
