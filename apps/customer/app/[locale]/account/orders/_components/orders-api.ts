import { createApiClient } from "@vergeo/config";

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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createOrdersApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listOrders: () => client.request<{ groups: CheckoutGroup[] }>("/account/orders"),
    getOrder: (orderId: string) => client.request<OrderDetail>(`/account/orders/${orderId}`),
  };
}
