"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { PriceBlock } from "@vergeo/ui/src/price-block";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

export type TicketPickerInstance = {
  id: string;
  starts_at: string;
  capacity: number;
  spots_sold: number;
  spots_remaining: number;
  is_sold_out: boolean;
};

export type TicketPickerType = {
  id: string;
  kind: "fixed" | "tier" | "free_rsvp";
  name: string;
  price_ngwee: number;
  qty_cap: number | null;
  tickets_sold: number;
  is_sold_out: boolean;
  is_free: boolean;
};

export type TicketPickerProps = {
  eventSlug: string;
  instances: TicketPickerInstance[];
  ticketTypes: TicketPickerType[];
  isSoldOut: boolean;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function getAccessToken(): Promise<string | null> {
  const { createBrowserClient } = await import("@vergeo/auth");
  const supabase = createBrowserClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

function formatInstanceDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Africa/Lusaka",
  }).format(new Date(iso));
}

function isPastInstance(iso: string): boolean {
  return new Date(iso).getTime() < Date.now();
}

function maxQtyForType(ticket: TicketPickerType, instance: TicketPickerInstance | null): number {
  if (!instance || ticket.is_sold_out || instance.is_sold_out) {
    return 0;
  }
  const caps: number[] = [20];
  if (ticket.qty_cap !== null) {
    caps.push(Math.max(0, ticket.qty_cap - ticket.tickets_sold));
  }
  caps.push(Math.max(0, instance.spots_remaining));
  return Math.min(...caps.filter((value) => value >= 0));
}

export function TicketPicker({ eventSlug, instances, ticketTypes, isSoldOut }: TicketPickerProps) {
  const t = useTranslations("events.ticketPurchase");
  const tEvents = useTranslations("events");
  const locale = useLocale();
  const [selectedInstanceId, setSelectedInstanceId] = useState(
    () => instances.find((instance) => !isPastInstance(instance.starts_at))?.id ?? "",
  );
  const [selectedTypeId, setSelectedTypeId] = useState(() => ticketTypes[0]?.id ?? "");
  const [qty, setQty] = useState(1);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAuthed, setIsAuthed] = useState<boolean | null>(null);

  const upcomingInstances = useMemo(
    () => instances.filter((instance) => !isPastInstance(instance.starts_at)),
    [instances],
  );

  const selectedInstance = useMemo(
    () => upcomingInstances.find((instance) => instance.id === selectedInstanceId) ?? null,
    [upcomingInstances, selectedInstanceId],
  );

  const selectedType = useMemo(
    () => ticketTypes.find((ticket) => ticket.id === selectedTypeId) ?? null,
    [ticketTypes, selectedTypeId],
  );

  const maxQty = useMemo(() => {
    if (!selectedType) {
      return 0;
    }
    return maxQtyForType(selectedType, selectedInstance);
  }, [selectedType, selectedInstance]);

  const lineTotalNgwee = useMemo(() => {
    if (!selectedType || selectedType.is_free) {
      return 0;
    }
    return selectedType.price_ngwee * qty;
  }, [selectedType, qty]);

  const canSubmit =
    !isSoldOut &&
    selectedInstance !== null &&
    selectedType !== null &&
    maxQty > 0 &&
    qty >= 1 &&
    qty <= maxQty &&
    !loading;

  const checkAuth = useCallback(async () => {
    const token = await getAccessToken();
    setIsAuthed(Boolean(token));
    return token;
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  const handleSubmit = useCallback(async () => {
    setError(null);
    setMessage(null);
    if (!selectedInstance || !selectedType) {
      return;
    }

    const token = await checkAuth();
    if (!token) {
      setError(t("loginRequired"));
      return;
    }

    setLoading(true);
    const path = selectedType.is_free ? "/tickets/rsvp" : "/tickets/checkout";
    try {
      const response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
        body: JSON.stringify({
          instance_id: selectedInstance.id,
          ticket_type_id: selectedType.id,
          qty,
        }),
      });

      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError =
          payload &&
          typeof payload === "object" &&
          "error" in payload &&
          typeof (payload as { error?: { code?: string; message?: string } }).error?.code ===
            "string"
            ? (payload as { error: { code: string; message: string } }).error
            : null;
        if (apiError?.code === "tickets.oversell") {
          setError(t("errors.oversell"));
        } else {
          setError(apiError?.message ?? t("errors.generic"));
        }
        return;
      }

      const redirectTo =
        payload &&
        typeof payload === "object" &&
        "redirect_to" in payload &&
        typeof (payload as { redirect_to?: string }).redirect_to === "string"
          ? (payload as { redirect_to: string }).redirect_to
          : null;

      setMessage(selectedType.is_free ? t("successRsvp") : t("successCheckout"));
      if (redirectTo) {
        window.location.assign(`/${locale}${redirectTo}`);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t("errors.generic"));
      }
    } finally {
      setLoading(false);
    }
  }, [checkAuth, locale, qty, selectedInstance, selectedType, t]);

  if (ticketTypes.length === 0) {
    return null;
  }

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4"
      aria-labelledby={`ticket-picker-${eventSlug}`}
    >
      <h2 id={`ticket-picker-${eventSlug}`} className="font-display text-h3 text-display-ink">
        {tEvents("detail.tickets")}
      </h2>

      {upcomingInstances.length > 0 ? (
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-text-2">{t("selectInstance")}</span>
          <select
            className="min-h-11 rounded-md border border-border bg-bg-1 px-3 text-text-1"
            value={selectedInstanceId}
            onChange={(event) => {
              setSelectedInstanceId(event.target.value);
              setQty(1);
            }}
          >
            {upcomingInstances.map((instance) => (
              <option key={instance.id} value={instance.id} disabled={instance.is_sold_out}>
                {formatInstanceDate(instance.starts_at, locale)}
                {instance.is_sold_out ? ` — ${t("soldOut")}` : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-text-2">{t("selectType")}</span>
        <select
          className="min-h-11 rounded-md border border-border bg-bg-1 px-3 text-text-1"
          value={selectedTypeId}
          onChange={(event) => {
            setSelectedTypeId(event.target.value);
            setQty(1);
          }}
        >
          {ticketTypes.map((ticket) => (
            <option key={ticket.id} value={ticket.id} disabled={ticket.is_sold_out}>
              {ticket.name}
              {ticket.is_free ? "" : ` — ${formatK(ticket.price_ngwee)}`}
              {ticket.is_sold_out ? ` (${t("soldOut")})` : ""}
            </option>
          ))}
        </select>
      </label>

      {selectedType && selectedType.qty_cap !== null ? (
        <p className="text-xs text-text-3">
          {t("remaining", {
            count: Math.max((selectedType.qty_cap ?? 0) - selectedType.tickets_sold, 0),
          })}
        </p>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-text-2">{t("quantity")}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-lg font-semibold text-text-1"
            aria-label={t("decrease")}
            disabled={qty <= 1 || maxQty === 0}
            onClick={() => setQty((value) => Math.max(1, value - 1))}
          >
            {t("decreaseSymbol")}
          </button>
          <span className="min-w-8 text-center font-mono text-sm font-semibold">{qty}</span>
          <button
            type="button"
            className="flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-lg font-semibold text-text-1"
            aria-label={t("increase")}
            disabled={qty >= maxQty || maxQty === 0}
            onClick={() => setQty((value) => Math.min(maxQty, value + 1))}
          >
            {t("increaseSymbol")}
          </button>
        </div>
      </div>

      {selectedType && !selectedType.is_free ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-text-2">{t("total")}</span>
          <PriceBlock ngwee={lineTotalNgwee} />
        </div>
      ) : null}

      {isAuthed === false ? (
        <p className="text-sm text-text-2">
          <Link href={`/${locale}/login`} className="font-semibold text-primary">
            {t("loginRequired")}
          </Link>
        </p>
      ) : null}

      <Button
        type="button"
        variant="primary"
        className="w-full"
        disabled={!canSubmit}
        loading={loading}
        loadingLabel={t("processing")}
        onClick={() => {
          void handleSubmit();
        }}
      >
        {selectedType?.is_free ? t("freeRsvpCta") : t("payCta")}
      </Button>

      {message ? <p className="text-center text-sm text-success">{message}</p> : null}
      {error ? <p className="text-center text-sm text-danger">{error}</p> : null}
    </section>
  );
}
