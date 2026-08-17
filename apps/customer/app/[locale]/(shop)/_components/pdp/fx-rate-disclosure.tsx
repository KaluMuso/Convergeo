"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

type PublicFxRateResponse = {
  published: boolean;
  stale: boolean;
  rate_zmw_per_usd_micros: number | null;
};

function microsToNgweePerUsd(micros: number): number {
  return Math.trunc(micros / 10_000);
}

export function FxRateDisclosure({ currencyCode }: { currencyCode?: string }) {
  const t = useTranslations("catalog");
  const [rate, setRate] = useState<PublicFxRateResponse | null>(null);

  useEffect(() => {
    if (currencyCode !== "USD") {
      return;
    }
    const url = absoluteApiUrl("/public/config/fx-rate");
    if (!url) {
      setRate({ published: false, stale: true, rate_zmw_per_usd_micros: null });
      return;
    }
    let cancelled = false;
    void fetch(url)
      .then(async (response) => {
        if (!response.ok) {
          return { published: false, stale: true, rate_zmw_per_usd_micros: null };
        }
        return (await response.json()) as PublicFxRateResponse;
      })
      .then((payload) => {
        if (!cancelled) {
          setRate(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRate({ published: false, stale: true, rate_zmw_per_usd_micros: null });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currencyCode]);

  if (currencyCode !== "USD") {
    return null;
  }
  if (rate === null) {
    return (
      <p className="mt-1 text-xs text-text-2" data-testid="pdp-fx-disclosure">
        {t("pdp.buyBox.fxLoading")}
      </p>
    );
  }
  if (!rate.published || rate.rate_zmw_per_usd_micros == null) {
    return (
      <p className="mt-1 text-xs text-danger" data-testid="pdp-fx-disclosure" role="status">
        {t("pdp.buyBox.fxUnavailable")}
      </p>
    );
  }
  if (rate.stale) {
    return (
      <p className="mt-1 text-xs text-danger" data-testid="pdp-fx-disclosure" role="status">
        {t("pdp.buyBox.fxStale")}
      </p>
    );
  }
  return (
    <p className="mt-1 text-xs text-text-2" data-testid="pdp-fx-disclosure">
      {t("pdp.buyBox.fxPublished", {
        rate: formatK(microsToNgweePerUsd(rate.rate_zmw_per_usd_micros)),
      })}
    </p>
  );
}
