/**
 * Server-created checkout groups (paid tickets, service deposits).
 *
 * `POST /tickets/checkout` and `POST /jobs/{job}/quotes/{quote}/accept` create the
 * group + order up front and send the buyer to `/checkout?group=<id>`. Every amount
 * shown here comes from the API; nothing is computed client-side.
 */

export type GroupKind = "ticket" | "service_deposit" | "order";

export type CheckoutGroupLine = {
  order_item_id: string;
  item_kind: string;
  title: string | null;
  qty: number;
  unit_price_ngwee: number;
  line_total_ngwee: number;
  ticket_type_name: string | null;
};

export type CheckoutGroupSummary = {
  checkout_group_id: string;
  kind: GroupKind;
  status: string;
  expired: boolean;
  payable: boolean;
  order_id: string;
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  platform_fee_ngwee: number;
  total_ngwee: number;
  lines: CheckoutGroupLine[];
  event: {
    event_id: string;
    title: string;
    slug: string | null;
    venue: string | null;
    starts_at: string | null;
  } | null;
  service: {
    job_id: string;
    quote_id: string | null;
    vendor_id: string;
    vendor_name: string;
    category: string | null;
  } | null;
  available_methods: Array<"momo" | "card">;
};

export type GroupPaymentStatus = {
  checkout_group_id: string;
  payment_id: string | null;
  status: string;
  rail: string | null;
  cod: boolean;
  order_id: string;
};

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const WAITING = new Set(["initiated", "ussd_pushed", "pay_offline"]);

export function isUuid(value: string | null | undefined): value is string {
  return typeof value === "string" && UUID_RE.test(value);
}

/** Query string carried through pending/card pages so they know where success lands. */
export function groupContextQuery(kind: GroupKind | null, jobId: string | null): string {
  const params = new URLSearchParams();
  if (kind === "ticket" || kind === "service_deposit") params.set("kind", kind);
  if (kind === "service_deposit" && isUuid(jobId)) params.set("job", jobId);
  return params.toString();
}

export type GroupPaths = {
  checkout: string;
  pending: string;
  card: (paymentId: string) => string;
  /** Where a confirmed payment lands: ticket wallet, job thread, or the order. */
  success: (orderId: string | null) => string;
};

export function groupPaths(
  locale: string,
  groupId: string,
  kind: GroupKind | null,
  jobId: string | null,
): GroupPaths {
  const ctx = groupContextQuery(kind, jobId);
  const suffix = ctx ? `&${ctx}` : "";
  return {
    checkout: `/${locale}/checkout?group=${encodeURIComponent(groupId)}`,
    pending: `/${locale}/checkout/pending/${encodeURIComponent(groupId)}${ctx ? `?${ctx}` : ""}`,
    card: (paymentId) =>
      `/${locale}/checkout/card/${encodeURIComponent(paymentId)}?group=${encodeURIComponent(groupId)}${suffix}`,
    success: (orderId) => {
      if (kind === "ticket") return `/${locale}/account/tickets`;
      if (kind === "service_deposit" && isUuid(jobId)) return `/${locale}/account/jobs/${jobId}`;
      return orderId ? `/${locale}/account/orders/${orderId}` : `/${locale}/account/orders`;
    },
  };
}

/**
 * Decide whether an existing attempt should be resumed instead of offering rails
 * again. Terminal failures (failed/expired/cancelled) return null: the buyer picks a
 * rail and `/payments/retry` or `/payments/card/session` opens a fresh attempt.
 */
export function resumeTarget(status: GroupPaymentStatus | null, paths: GroupPaths): string | null {
  if (!status || status.cod) return null;
  if (status.status === "success") return paths.pending;
  if (!WAITING.has(status.status)) return null;
  if (status.rail === "card" && isUuid(status.payment_id)) return paths.card(status.payment_id);
  return paths.pending;
}

export type SearchParams = Record<string, string | string[] | undefined>;

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * Server-created checkout group id when this visit is a paid-ticket or service-deposit
 * checkout. `?group=` is canonical; `?session=…&kind=service_deposit` is the legacy
 * hand-off older clients still send. `undefined` means the cart checkout.
 */
export function resolveGroupParam(query: SearchParams | undefined): string | null | undefined {
  if (!query) return undefined;
  if (Object.hasOwn(query, "group")) return single(query.group);
  if (single(query.kind) === "service_deposit" && Object.hasOwn(query, "session")) {
    return single(query.session);
  }
  return undefined;
}

/**
 * Pending/card pages receive `?kind=ticket` or `?kind=service_deposit&job=<id>` from
 * the group checkout. Returns the success/back routes for that group, or `undefined`
 * for cart checkouts (which keep their order-page behaviour).
 */
export function groupRoutesFromQuery(
  locale: string,
  groupId: string,
  query: SearchParams | undefined,
): { success: string; checkout: string } | undefined {
  const kind = single(query?.kind);
  if (!isUuid(groupId) || (kind !== "ticket" && kind !== "service_deposit")) return undefined;
  const paths = groupPaths(locale, groupId, kind, single(query?.job));
  return { success: paths.success(null), checkout: paths.checkout };
}
