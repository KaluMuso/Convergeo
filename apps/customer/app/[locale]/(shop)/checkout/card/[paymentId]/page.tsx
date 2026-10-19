"use client";

import { createApiClient } from "@vergeo/config";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { resolveApiBaseUrl } from "../../../../../../lib/api-base-url";
import { customerAuth, useSession } from "../../../../../../lib/customer-session";
import { CHECKOUT_UUID } from "../../../../account/jobs/[id]/_components/service-payments";
import { resolveCardVerifyViewState } from "../../_lib/payment-outcome";

type WidgetCustomer = {
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
};

type CardSession = {
  payment_id: string;
  checkout_group_id: string;
  reference: string;
  amount_major: string;
  currency: string;
  amount_ngwee: number;
  widget_script_url: string;
  customer: WidgetCustomer;
  service_job_id?: string | null;
};

type VerifyResult = {
  payment_id: string;
  checkout_group_id: string;
  status: string;
  verified: boolean;
  order_confirmed: boolean;
  held?: boolean;
  retry_checkout?: boolean;
};

type LencoPaidResult = {
  reference: string;
};

type LencoPayConfig = {
  key: string;
  email: string;
  reference: string;
  amount: string;
  currency: string;
  label: string;
  channels: Array<"card" | "mobile-money">;
  customer: {
    firstName: string;
    lastName: string;
    phone: string;
  };
  onSuccess: (result: LencoPaidResult) => void;
  onClose: () => void;
};

type LencoPayGlobal = {
  getPaid: (config: LencoPayConfig) => void;
};

declare global {
  interface Window {
    LencoPay?: LencoPayGlobal;
  }
}

type ViewState =
  "loading" | "opening" | "verifying" | "success" | "failed" | "held" | "pending" | "error";

function getApiBaseUrl(): string | null {
  return resolveApiBaseUrl();
}

function getLencoPublicKey(): string | null {
  const key = process.env.NEXT_PUBLIC_LENCO_PUBLIC_KEY;
  return key && key.trim().length > 0 ? key.trim() : null;
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("widget_script_load_failed"));
    document.body.appendChild(script);
  });
}

export default function CardCheckoutPage() {
  const params = useParams<{ locale: string; paymentId: string }>();
  const searchParams = useSearchParams();
  const identity = useSession();
  const query = searchParams.toString();
  return (
    <IdentityCardCheckoutPage
      key={`${identity.generation}:${identity.session?.user.id}:${params.locale}:${params.paymentId}:${query}`}
      locale={params.locale}
      paymentId={params.paymentId}
      query={query}
      authGeneration={identity.generation}
      userId={identity.session?.user.id}
      sessionLoading={identity.loading}
    />
  );
}

type CardContext = {
  kind: "product" | "service" | "ticket";
  jobId?: string;
  paymentId: string;
  groupId: string;
  orderId: string;
  amountNgwee: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && CHECKOUT_UUID.test(value);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function majorAmount(amountNgwee: number): string {
  const digits = String(amountNgwee).padStart(3, "0");
  return `${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

// This projection binds navigation to the exact authenticated payment. Resume and
// verify retain financial authority; URL hints never select the checkout domain.
function resolveCardContext(value: unknown, paymentId: string, buyerId: string): CardContext {
  const context = isRecord(value) ? value.checkout_context : null;
  if (
    !isRecord(value) ||
    !isRecord(context) ||
    context.version !== 1 ||
    !isUuid(context.buyer_id) ||
    context.buyer_id !== buyerId ||
    context.payment_id !== paymentId ||
    value.payment_id !== paymentId ||
    !isUuid(context.checkout_group_id) ||
    context.checkout_group_id !== value.checkout_group_id ||
    !Array.isArray(context.order_ids) ||
    context.order_ids.length === 0 ||
    !context.order_ids.every(isUuid) ||
    new Set(context.order_ids).size !== context.order_ids.length ||
    !isUuid(value.order_id) ||
    !context.order_ids.includes(value.order_id) ||
    context.rail !== "card" ||
    value.rail !== "card" ||
    context.cod !== false ||
    value.cod !== false ||
    context.currency !== "ZMW" ||
    !isPositiveInteger(context.amount_ngwee) ||
    context.amount_ngwee !== value.amount_ngwee
  )
    throw new Error("invalid_card_payment_context");

  let jobId: string | undefined;
  switch (context.kind) {
    case "product": {
      if (
        "service" in context ||
        "ticket" in context ||
        !Array.isArray(context.orders) ||
        context.orders.length !== context.order_ids.length
      )
        throw new Error("invalid_product_context");
      const orders = new Set<string>();
      const items = new Set<string>();
      for (const order of context.orders) {
        if (
          !isRecord(order) ||
          !isUuid(order.order_id) ||
          !context.order_ids.includes(order.order_id) ||
          orders.has(order.order_id) ||
          !Array.isArray(order.lines) ||
          order.lines.length === 0
        )
          throw new Error("invalid_product_order");
        orders.add(order.order_id);
        for (const line of order.lines) {
          if (
            !isRecord(line) ||
            !isUuid(line.order_item_id) ||
            items.has(line.order_item_id) ||
            line.item_kind !== "product" ||
            !isUuid(line.listing_id) ||
            ("product_id" in line && !isUuid(line.product_id))
          )
            throw new Error("invalid_product_line");
          items.add(line.order_item_id);
        }
      }
      break;
    }
    case "service": {
      const service = context.service;
      if (
        "orders" in context ||
        "ticket" in context ||
        !isRecord(service) ||
        !isUuid(service.job_id) ||
        !isUuid(service.obligation_id) ||
        (service.leg !== "deposit" && service.leg !== "balance") ||
        context.order_ids.length !== 1 ||
        service.order_id !== context.order_ids[0] ||
        service.obligation_amount_ngwee !== context.amount_ngwee ||
        service.current_payment_id !== paymentId
      )
        throw new Error("invalid_service_context");
      jobId = service.job_id;
      break;
    }
    case "ticket": {
      const ticket = context.ticket;
      if (
        "orders" in context ||
        "service" in context ||
        !isRecord(ticket) ||
        context.order_ids.length !== 1 ||
        ticket.order_id !== context.order_ids[0] ||
        !Array.isArray(ticket.lines) ||
        ticket.lines.length !== 1
      )
        throw new Error("invalid_ticket_context");
      const line: unknown = ticket.lines[0];
      if (
        !isRecord(line) ||
        !isUuid(line.order_item_id) ||
        !isUuid(line.ticket_type_id) ||
        !isUuid(line.instance_id) ||
        !isPositiveInteger(line.qty) ||
        !isPositiveInteger(line.unit_price_ngwee)
      )
        throw new Error("invalid_ticket_line");
      // The line is the subtotal. The server's full charge also binds stored
      // buyer-paid fees; do not recalculate fees or equate these two amounts.
      break;
    }
    default:
      throw new Error("unknown_card_context");
  }
  return {
    kind: context.kind,
    jobId,
    paymentId,
    groupId: context.checkout_group_id,
    orderId: value.order_id,
    amountNgwee: context.amount_ngwee,
  };
}

function IdentityCardCheckoutPage({
  locale,
  paymentId,
  query,
  authGeneration,
  userId,
  sessionLoading,
}: {
  locale: string;
  paymentId: string;
  query: string;
  authGeneration: number;
  userId?: string;
  sessionLoading: boolean;
}) {
  const t = useTranslations("checkout.card");
  const funding = useTranslations("services.funding");

  const [viewState, setViewState] = useState<ViewState>("loading");
  const [sessionData, setSessionData] = useState<CardSession | null>(null);
  // Context survives return handling independently of the mutating widget-session GET.
  const [context, setContext] = useState<CardContext | null>(null);
  const contextRef = useRef<CardContext | null>(null);
  const active = useRef(false);
  const verifyInFlight = useRef<Promise<VerifyResult | null> | null>(null);
  const widgetCallbackHandled = useRef(false);
  const isCurrent = useCallback(() => {
    const auth = customerAuth.snapshot();
    return (
      active.current &&
      !auth.loading &&
      !auth.error &&
      auth.generation === authGeneration &&
      !!userId &&
      auth.session?.user.id === userId
    );
  }, [authGeneration, userId]);
  const getToken = useCallback(
    () => (isCurrent() ? (customerAuth.snapshot().session?.access_token ?? null) : null),
    [isCurrent],
  );
  const jobPath =
    context?.kind === "service"
      ? `/${locale}/account/jobs/${encodeURIComponent(context.jobId!)}`
      : null;
  const checkoutPaymentPath =
    jobPath ??
    (context?.kind === "ticket"
      ? `/${locale}/checkout?group=${encodeURIComponent(context.groupId)}&retry=1`
      : null);
  const ordersPath = `/${locale}/account/orders`;

  const verifyReturn = useCallback(
    (clientStatus: "success" | "failed" | "closed" | "pending"): Promise<VerifyResult | null> => {
      if (!isCurrent() || !contextRef.current) return Promise.resolve(null);
      if (verifyInFlight.current) return verifyInFlight.current;
      const apiBase = getApiBaseUrl();
      if (!apiBase) {
        setViewState("error");
        return Promise.resolve(null);
      }
      setViewState("verifying");
      const client = createApiClient({
        baseUrl: apiBase,
        getToken,
      });
      const operation = (async () => {
        try {
          const result = await client.request<VerifyResult>(`/payments/card/${paymentId}/verify`, {
            method: "POST",
            body: JSON.stringify({ client_status: clientStatus }),
          });
          if (!isCurrent()) return null;
          if (
            result.payment_id !== paymentId ||
            result.checkout_group_id !== contextRef.current?.groupId
          )
            throw new Error("card_verify_context_mismatch");
          setViewState(resolveCardVerifyViewState(result));
          return result;
        } catch {
          if (isCurrent()) setViewState("error");
          return null;
        } finally {
          verifyInFlight.current = null;
        }
      })();
      verifyInFlight.current = operation;
      return operation;
    },
    [getToken, isCurrent, paymentId],
  );

  const openWidget = useCallback(
    async (cardSession: CardSession) => {
      if (!isCurrent()) return;
      const publicKey = getLencoPublicKey();
      if (!publicKey || !window.LencoPay) {
        setViewState("error");
        return;
      }
      setViewState("opening");
      window.LencoPay.getPaid({
        key: publicKey,
        email: cardSession.customer.email,
        reference: cardSession.reference,
        amount: cardSession.amount_major,
        currency: cardSession.currency,
        label: t("widgetLabel"),
        channels: ["card"],
        customer: {
          firstName: cardSession.customer.first_name,
          lastName: cardSession.customer.last_name,
          phone: cardSession.customer.phone,
        },
        onSuccess: () => {
          if (widgetCallbackHandled.current || !isCurrent()) return;
          widgetCallbackHandled.current = true;
          void verifyReturn("success");
        },
        onClose: () => {
          if (widgetCallbackHandled.current || !isCurrent()) return;
          widgetCallbackHandled.current = true;
          void verifyReturn("closed");
        },
      });
    },
    [isCurrent, t, verifyReturn],
  );

  useEffect(() => {
    active.current = true;
    let cancelled = false;
    const current = () => !cancelled && isCurrent();
    if (sessionLoading) {
      return () => {
        cancelled = true;
        active.current = false;
      };
    }
    if (!current()) {
      setViewState("error");
      return () => {
        cancelled = true;
        active.current = false;
      };
    }

    void (async () => {
      const apiBase = getApiBaseUrl();
      if (!apiBase) {
        setViewState("error");
        return;
      }
      const client = createApiClient({
        baseUrl: apiBase,
        getToken,
      });
      try {
        const hints = new URLSearchParams(query);
        const jobs = hints.getAll("job");
        const groups = hints.getAll("group");
        const statuses = hints.getAll("status");
        if (
          !CHECKOUT_UUID.test(paymentId) ||
          statuses.length > 1 ||
          (statuses.length === 1 && !["success", "failed"].includes(statuses[0]!)) ||
          hints.has("session") ||
          hints.has("kind") ||
          jobs.length > 1 ||
          groups.length > 1 ||
          (jobs.length === 1 && !isUuid(jobs[0])) ||
          (groups.length === 1 && !isUuid(groups[0]))
        )
          throw new Error("invalid_card_context");
        const payment = await client.request<unknown>(
          `/payments/status?payment=${encodeURIComponent(paymentId)}`,
        );
        if (!current()) return;
        const resolved = resolveCardContext(payment, paymentId, userId!);
        if (
          (jobs.length === 1 && (resolved.kind !== "service" || jobs[0] !== resolved.jobId)) ||
          (groups.length === 1 && groups[0] !== resolved.groupId)
        )
          throw new Error("card_context_hint_mismatch");
        contextRef.current = resolved;
        setContext(resolved);
        const returnStatus = statuses[0];
        if (returnStatus === "success" || returnStatus === "failed") {
          await verifyReturn(returnStatus);
          return;
        }
        // This GET claims/resumes an attempt. It is deliberately after the
        // read-only context checks and is never used to discover return context.
        const cardSession = await client.request<CardSession>(
          `/payments/card/${paymentId}/session`,
        );
        if (!current()) return;
        if (
          cardSession.payment_id !== paymentId ||
          cardSession.checkout_group_id !== resolved.groupId ||
          cardSession.amount_ngwee !== resolved.amountNgwee ||
          cardSession.amount_major !== majorAmount(resolved.amountNgwee) ||
          cardSession.currency !== "ZMW" ||
          (resolved.kind === "service"
            ? cardSession.service_job_id !== resolved.jobId
            : !!cardSession.service_job_id)
        )
          throw new Error("card_session_context_mismatch");
        setSessionData(cardSession);
        const publicKey = getLencoPublicKey();
        if (!publicKey) {
          setViewState("error");
          return;
        }
        await loadScript(cardSession.widget_script_url);
        if (!current()) return;
        await openWidget(cardSession);
      } catch {
        if (current()) setViewState("error");
      }
    })();
    return () => {
      cancelled = true;
      active.current = false;
    };
  }, [getToken, isCurrent, openWidget, paymentId, query, userId, sessionLoading, verifyReturn]);

  const statusMessage = (() => {
    switch (viewState) {
      case "loading":
        return t("loading");
      case "opening":
        return t("openingWidget");
      case "verifying":
        return t("verifying");
      case "success":
        return context?.kind === "service" ? funding("status.success") : t("successBody");
      case "failed":
        return t("failedBody");
      case "held":
        return t("heldBody");
      case "pending":
        return t("pendingBody");
      default:
        return t("error");
    }
  })();

  const title = (() => {
    switch (viewState) {
      case "success":
        return context?.kind === "service" ? funding("title") : t("successTitle");
      case "failed":
        return t("failedTitle");
      case "held":
        return t("heldTitle");
      case "pending":
        return t("pendingTitle");
      case "error":
        return t("widgetUnavailable");
      default:
        return t("pageTitle");
    }
  })();

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6 py-8">
      <header className="space-y-2 text-center">
        <h1 className="font-display text-h1 text-display-ink">{title}</h1>
        <p className="font-body text-sm text-text-2">{t("subtitle")}</p>
      </header>

      <section
        className="space-y-4 rounded-card border border-border bg-surface p-5 text-center"
        aria-live="polite"
        data-testid={`payment-card-${viewState}`}
      >
        <p className="font-body text-sm text-text-2">{statusMessage}</p>
        {sessionData ? (
          <p className="font-mono text-sm text-text">
            {sessionData.amount_major} {sessionData.currency}
          </p>
        ) : null}
        <p className="font-body text-xs text-text-3">{t("secureNote")}</p>
      </section>

      {viewState === "success" ? (
        <LinkButton
          href={jobPath ? jobPath : ordersPath}
          variant="primary"
          className="w-full px-5 text-sm"
          LinkComponent={Link}
        >
          {jobPath ? funding("backToJob") : t("viewOrders")}
        </LinkButton>
      ) : null}

      {(viewState === "failed" || viewState === "error") && checkoutPaymentPath ? (
        <LinkButton
          href={checkoutPaymentPath}
          variant="secondary"
          className="w-full px-5 text-sm"
          LinkComponent={Link}
        >
          {t("retryPayment")}
        </LinkButton>
      ) : null}

      {viewState === "pending" ? (
        <button
          type="button"
          className="inline-flex min-h-11 w-full items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
          onClick={() => {
            void verifyReturn("pending");
          }}
        >
          {t("verifying")}
        </button>
      ) : null}
    </div>
  );
}
