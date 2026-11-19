"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Spinner } from "../../services/_lib/ui";
import { createOffersClient, type Offer } from "../_lib/offers-client";

import { OfferForm } from "./offer-form";

export function OfferEditView({ locale, offerId }: { locale: string; offerId: string }) {
  const t = useTranslations("vendor.offers");
  const { session, loading: sessionLoading } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const api = useMemo(() => createOffersClient(getToken), [getToken]);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    let cancelled = false;
    api
      .get(offerId)
      .then((row) => {
        if (!cancelled) {
          setOffer(row);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, offerId, session, sessionLoading]);

  if (failed) {
    return <p className="text-sm text-danger">{t("errors.notFound")}</p>;
  }
  if (!offer) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </div>
    );
  }
  return <OfferForm key={offer.id} locale={locale} mode="edit" initialOffer={offer} />;
}
