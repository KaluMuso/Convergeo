import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

export type OrderSummary = {
  id: string;
  vendor_id: string;
  vendor_name: string;
  status: string;
  fulfilment: string;
  cod: boolean;
  paid: boolean;
  payment_mode: "cod" | "prepaid";
  total_ngwee: number;
  item_count: number;
  created_at: string;
};

export type CheckoutGroup = {
  checkout_group_id: string;
  created_at: string;
  total_ngwee: number;
  orders: OrderSummary[];
};

export type OrderItem = {
  id: string;
  title: string;
  qty: number;
  unit_price_ngwee: number;
  /** Chosen colour/size, snapshotted when the order was placed. */
  variant_options?: Array<{ group: string; value: string }>;
  variant_sku?: string | null;
};

export type TimelineStep = {
  step_key: string;
  state: "completed" | "current" | "upcoming" | "skipped";
  occurred_at: string | null;
  escrow_copy_key: "held" | "released" | "refunded" | "cod" | "none";
};

export type PickupCredentials = {
  qr_token: string | null;
  pin: string | null;
  stub: boolean;
};

export type InvoiceLink = {
  invoice_id: string | null;
  download_url: string | null;
  stub: boolean;
};

export type OrderDetail = {
  id: string;
  checkout_group_id: string;
  vendor_id: string;
  vendor_name: string;
  status: string;
  fulfilment: string;
  cod: boolean;
  paid: boolean;
  payment_mode: "cod" | "prepaid";
  delivery_fee_ngwee: number;
  subtotal_ngwee: number;
  total_ngwee: number;
  created_at: string;
  items: OrderItem[];
  timeline: TimelineStep[];
  pickup: PickupCredentials | null;
  invoice: InvoiceLink | null;
  related_orders: OrderSummary[];
};

export type CourierDeliveryStatus =
  "requested" | "accepted" | "picked_up" | "delivered" | "failed" | "cancelled";

export type CourierDelivery = {
  status: CourierDeliveryStatus;
  courier_name: string;
  courier_reference: string | null;
  cod_amount_ngwee: number;
  timeline: Array<{ status: CourierDeliveryStatus; at: string }>;
  /** Only ever returned to the order owner, and only while the dispatch is in flight. */
  handover_code: string | null;
};

/** Pay at the door (flag `pay_at_door`). Never carries phone numbers or Lenco references. */
export type DoorPaymentState =
  | "not_applicable"
  | "not_at_door"
  | "awaiting_arrival"
  | "awaiting_payment"
  | "pending"
  | "failed"
  | "paid"
  | "cash";

export type DoorPayment = {
  enabled: boolean;
  state: DoorPaymentState;
  amount_ngwee: number;
  arrived: boolean;
  settled_via: "mobile_money" | "cash" | null;
  attempts_used: number;
  attempts_allowed: number;
  latest_failure_reason: string | null;
  can_request: boolean;
};

export type OrderDeliveryResponse = {
  enabled: boolean;
  dispatch: CourierDelivery | null;
};

// Point the invoice link at the real signed download endpoint (M15-P07).
// The API returns a relative stub path (`/account/orders/{id}/invoice`); we lift the
// order id out of it and target the owner-scoped `/invoices/{id}` PDF stream.
export function invoiceDownloadUrl(invoice: InvoiceLink): string | null {
  if (!invoice.download_url) {
    return null;
  }
  const match = invoice.download_url.match(/\/orders\/([^/]+)\/invoice/);
  if (!match) {
    return null;
  }
  return `${getApiBaseUrl()}/invoices/${match[1]}`;
}

export function createOrdersApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listOrders: () => client.request<{ groups: CheckoutGroup[] }>("/account/orders"),
    getOrder: (orderId: string) => client.request<OrderDetail>(`/account/orders/${orderId}`),
    getDelivery: (orderId: string) =>
      client.request<OrderDeliveryResponse>(`/account/orders/${orderId}/delivery`),
    getDoorPayment: (orderId: string) =>
      client.request<DoorPayment>(`/account/orders/${orderId}/door-payment`),
  };
}
