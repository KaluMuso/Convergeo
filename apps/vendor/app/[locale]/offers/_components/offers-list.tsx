"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, Spinner } from "../../services/_lib/ui";
import { createOffersClient, type Offer } from "../_lib/offers-client";

function statusVariant(offer: Offer): "free" | "new" | "sold_out" {
  if (offer.live) {
    return "free";
  }
  return offer.status === "draft" ? "new" : "sold_out";
}

function offerSummary(offer: Offer, t: ReturnType<typeof useTranslations>): string {
  switch (offer.offer_type) {
    case "bxgy":
      return t("summary.bxgy", { buy: offer.buy_qty ?? 0, get: offer.get_qty ?? 0 });
    case "bundle":
      return offer.bundle_pricing === "fixed_price"
        ? t("summary.bundleFixed", { price: formatK(offer.bundle_price_ngwee ?? 0) })
        : t("summary.bundlePercent", { percent: offer.addon_percent_off ?? 0 });
    case "buy_n_pay_m":
      return t("summary.buyNPayM", { n: offer.buy_n ?? 0, m: offer.pay_m ?? 0 });
    default:
      return t("summary.freeGift");
  }
}

export function OffersList({ locale }: { locale: string }) {
  const t = useTranslations("vendor.offers");
  const { session, loading: sessionLoading } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const api = useMemo(() => createOffersClient(getToken), [getToken]);
  const [items, setItems] = useState<Offer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .list()
      .then((response) => {
        setItems(response.items);
        setError(null);
      })
      .catch(() => {
        setItems([]);
        setError(t("errors.loadFailed"));
      });
  }, [api, t]);

  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    load();
  }, [load, session, sessionLoading]);

  const archive = async (offer: Offer) => {
    try {
      await api.archive(offer.id);
      load();
    } catch {
      setError(t("errors.saveFailed"));
    }
  };

  if (sessionLoading || (session && items === null)) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </div>
    );
  }
  if (!session) {
    return <p className="text-sm text-text-2">{t("errors.authRequired")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold text-text">{t("list.title")}</h1>
          <p className="text-sm text-text-2">{t("list.intro")}</p>
        </div>
        <Link
          href={`/${locale}/offers/new`}
          className="inline-flex min-h-11 shrink-0 items-center rounded-md bg-primary px-3 text-sm font-medium text-[var(--primary-btn-fg)]"
          data-testid="offers-new"
        >
          {t("list.create")}
        </Link>
      </header>
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {items && items.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-text-2">{t("list.empty")}</p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {(items ?? []).map((offer) => (
          <li
            key={offer.id}
            className="flex flex-col gap-2 rounded-md border border-border bg-surface p-3"
            data-testid={`offer-row-${offer.id}`}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="m-0 min-w-0 truncate text-sm font-semibold text-text">{offer.title}</p>
              <Badge
                variant={statusVariant(offer)}
                label={
                  offer.paused_by_admin
                    ? t("status.adminPaused")
                    : offer.live
                      ? t("status.live")
                      : t(`status.${offer.status}`)
                }
              />
            </div>
            <p className="m-0 text-xs text-text-2">
              {t(`types.${offer.offer_type}.label`)} · {offerSummary(offer, t)}
            </p>
            {offer.gift_stock_total !== null ? (
              <p className="m-0 text-xs text-text-3">
                {t("list.giftStock", {
                  available: offer.gift_stock_available ?? 0,
                  total: offer.gift_stock_total,
                })}
              </p>
            ) : null}
            {!offer.cart_applicable ? (
              <p className="m-0 text-xs text-warning">{t("list.notInCart")}</p>
            ) : null}
            <div className="flex gap-3">
              <Link
                href={`/${locale}/offers/${offer.id}/edit`}
                className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
              >
                {t("list.edit")}
              </Link>
              <button
                type="button"
                className="min-h-11 text-sm text-danger"
                onClick={() => void archive(offer)}
              >
                {t("list.archive")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
