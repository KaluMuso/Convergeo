"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { resolveApiBaseUrl } from "../../../../../../lib/api-base-url";
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
  const locale = params.locale;
  const paymentId = params.paymentId;
  const t = useTranslations("checkout.card");
  const { session, loading: sessionLoading } = useSession();

  const [viewState, setViewState] = useState<ViewState>("loading");
  const [sessionData, setSessionData] = useState<CardSession | null>(null);
  const widgetOpened = useRef(false);

  const checkoutPaymentPath = useMemo(() => `/${locale}/checkout`, [locale]);
  const ordersPath = useMemo(() => `/${locale}/account/orders`, [locale]);

  const verifyReturn = useCallback(
    async (clientStatus: "success" | "failed" | "closed" | "pending") => {
      if (!session?.access_token) {
        setViewState("error");
        return null;
      }
      const apiBase = getApiBaseUrl();
      if (!apiBase) {
        setViewState("error");
        return null;
      }
      setViewState("verifying");
      const client = createApiClient({
        baseUrl: apiBase,
        getToken: () => session.access_token,
      });
      try {
        return await client.request<VerifyResult>(`/payments/card/${paymentId}/verify`, {
          method: "POST",
          body: JSON.stringify({ client_status: clientStatus }),
        });
      } catch {
        setViewState("error");
        return null;
      }
    },
    [paymentId, session?.access_token],
  );

  const handleVerifyOutcome = useCallback((result: VerifyResult | null) => {
    if (!result) {
      return;
    }
    setViewState(resolveCardVerifyViewState(result));
  }, []);

  const openWidget = useCallback(
    async (cardSession: CardSession) => {
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
          void (async () => {
            const result = await verifyReturn("success");
            handleVerifyOutcome(result);
          })();
        },
        onClose: () => {
          void (async () => {
            const result = await verifyReturn("closed");
            handleVerifyOutcome(result);
          })();
        },
      });
    },
    [handleVerifyOutcome, verifyReturn],
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session?.access_token) {
      setViewState("error");
      return;
    }

    const returnStatus = searchParams.get("status");
    if (returnStatus === "success" || returnStatus === "failed") {
      void (async () => {
        const result = await verifyReturn(returnStatus === "success" ? "success" : "failed");
        handleVerifyOutcome(result);
      })();
      return;
    }

    if (widgetOpened.current) {
      return;
    }

    void (async () => {
      const apiBase = getApiBaseUrl();
      if (!apiBase) {
        setViewState("error");
        return;
      }
      const client = createApiClient({
        baseUrl: apiBase,
        getToken: () => session.access_token,
      });
      try {
        const cardSession = await client.request<CardSession>(
          `/payments/card/${paymentId}/session`,
        );
        setSessionData(cardSession);
        const publicKey = getLencoPublicKey();
        if (!publicKey) {
          setViewState("error");
          return;
        }
        await loadScript(cardSession.widget_script_url);
        widgetOpened.current = true;
        await openWidget(cardSession);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          setViewState("error");
          return;
        }
        setViewState("error");
      }
    })();
  }, [
    handleVerifyOutcome,
    openWidget,
    paymentId,
    searchParams,
    session?.access_token,
    sessionLoading,
    verifyReturn,
  ]);

  const statusMessage = (() => {
    switch (viewState) {
      case "loading":
        return t("loading");
      case "opening":
        return t("openingWidget");
      case "verifying":
        return t("verifying");
      case "success":
        return t("successBody");
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
        return t("successTitle");
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
        <Link
          href={ordersPath}
          className="inline-flex min-h-11 w-full items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
        >
          {t("viewOrders")}
        </Link>
      ) : null}

      {viewState === "failed" || viewState === "error" ? (
        <Link
          href={checkoutPaymentPath}
          className="inline-flex min-h-11 w-full items-center justify-center rounded border border-border bg-surface px-5 text-sm font-medium text-text"
        >
          {t("retryPayment")}
        </Link>
      ) : null}

      {viewState === "pending" ? (
        <button
          type="button"
          className="inline-flex min-h-11 w-full items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
          onClick={() => {
            void (async () => {
              const result = await verifyReturn("pending");
              handleVerifyOutcome(result);
            })();
          }}
        >
          {t("verifying")}
        </button>
      ) : null}
    </div>
  );
}
