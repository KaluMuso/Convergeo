"use client";

import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { Button } from "@vergeo/ui/src/button";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { sortedTiers, whatsappLink, type SourcingItem } from "../_lib/source";
import { sourceErrorKey, useSourceApi } from "../_lib/use-source-api";

/** One supplier listing, supplier shop or business service. */
export function SourceCard({ item }: { item: SourcingItem }) {
  const t = useTranslations("vendor.source");
  const locale = useLocale();
  const tiers = sortedTiers(item.price_tiers);
  const link = whatsappLink(item.whatsapp_msisdn, t("card.whatsappText", { title: item.title }));
  return (
    <li
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-1"
      data-testid={`source-${item.kind}-${item.id}`}
    >
      {item.image_public_id ? (
        <CloudinaryImage
          publicId={item.image_public_id}
          alt={item.title}
          width={480}
          ratio="4/3"
          className="rounded-md"
        />
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {item.verified ? <Badge variant="public" label={t("card.verified")} /> : null}
        {item.made_in_zambia ? <Badge variant="new" label={t("card.madeInZambia")} /> : null}
        {item.kind === "shop"
          ? item.supplier_types.map((type) => (
              <Badge key={type} variant="featured" label={t(`supplierTypes.${type}`)} />
            ))
          : null}
      </div>
      <h2 className="m-0 text-base font-semibold text-text">{item.title}</h2>
      <p className="m-0 text-sm text-text-2">
        {item.kind === "listing" ? item.shop_name : null}
        {item.kind === "service" ? item.shop_name : null}
        {item.landmark ? ` · ${item.landmark}` : null}
      </p>
      {item.kind === "listing" && item.prices_locked ? (
        <div className="space-y-1 text-sm text-text" data-testid="prices-locked">
          <p className="m-0 text-text-2">{t("card.pricesLocked")}</p>
          <Link href={`/${locale}/onboarding`} className="font-medium text-primary underline">
            {t("card.verifyCta")}
          </Link>
          {item.moq && item.moq > 1 ? (
            <p className="m-0 font-medium">{t("card.moq", { qty: item.moq })}</p>
          ) : null}
        </div>
      ) : null}
      {item.kind === "listing" && !item.prices_locked ? (
        <div className="space-y-1 text-sm text-text">
          {tiers.length > 0 ? (
            <ul className="m-0 list-none space-y-0.5 p-0">
              {tiers.map((tier) => (
                <li key={tier.min_qty}>
                  {t("card.tier", {
                    qty: tier.min_qty,
                    price: formatK(tier.price_ngwee),
                  })}
                </li>
              ))}
            </ul>
          ) : item.price_ngwee !== null ? (
            <p className="m-0">{t("card.retail", { price: formatK(item.price_ngwee) })}</p>
          ) : null}
          {item.moq && item.moq > 1 ? (
            <p className="m-0 font-medium">{t("card.moq", { qty: item.moq })}</p>
          ) : null}
        </div>
      ) : null}
      {item.kind === "service" && item.price_ngwee !== null ? (
        <p className="m-0 text-sm text-text">
          {t("card.from", { price: formatK(item.price_ngwee) })}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap gap-2">
        {link ? (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-11 min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body text-text hover:bg-bg-2"
          >
            {t("card.whatsapp")}
          </a>
        ) : null}
        {item.kind === "service" ? <ServiceQuote serviceId={item.id} /> : null}
      </div>
    </li>
  );
}

/** Existing service RFQ flow (`POST /rfq`) opened inline; no payment is involved. */
function ServiceQuote({ serviceId }: { serviceId: string }) {
  const t = useTranslations("vendor.source");
  const { client, ready } = useSourceApi();
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setMessage(null);
    try {
      await client.request("/rfq", {
        method: "POST",
        body: JSON.stringify({
          service_id: serviceId,
          requested_details: details.trim(),
        }),
      });
      setMessage(t("rfq.sent"));
      setOpen(false);
      setDetails("");
    } catch (error) {
      void sourceErrorKey(error);
      setMessage(t("rfq.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full space-y-2">
      {open ? (
        <div className="space-y-2">
          <label className="block text-sm text-text" htmlFor={`rfq-${serviceId}`}>
            {t("rfq.label")}
          </label>
          <textarea
            id={`rfq-${serviceId}`}
            value={details}
            maxLength={1000}
            placeholder={t("rfq.placeholder")}
            onChange={(event) => setDetails(event.target.value)}
            className="min-h-20 w-full rounded-md border border-border bg-surface p-3 text-body text-text"
          />
          <Button
            type="button"
            size="sm"
            loading={busy}
            loadingLabel={t("rfq.sending")}
            disabled={!ready || details.trim().length === 0}
            onClick={() => void send()}
          >
            {t("rfq.send")}
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          loadingLabel=""
          onClick={() => setOpen(true)}
        >
          {t("card.requestQuote")}
        </Button>
      )}
      {message ? (
        <p role="status" className="m-0 text-sm text-text-2">
          {message}
        </p>
      ) : null}
    </div>
  );
}
