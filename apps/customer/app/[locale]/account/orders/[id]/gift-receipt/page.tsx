import { ApiError } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { AccountListBoundary } from "../../../_components/account-list-boundary";
import { getAccountListSession } from "../../../_components/account-list-server";
import { createOrdersApiClient, type GiftReceipt } from "../../_components/orders-api";

import type { Metadata } from "next";

export const metadata: Metadata = { robots: { index: false, follow: false } };

type PageProps = { params: Promise<{ locale: string; id: string }> };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

/** A gift receipt the payer can screenshot and send: items only, never prices. */
export default async function GiftReceiptPage({ params }: PageProps) {
  const { locale, id } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const { accountId, accessToken } = await getAccountListSession(locale);
  const baseMessages = await getMessages();
  const ordersMessages = await loadNamespace(locale as Locale, "orders");
  const messages = { ...baseMessages, orders: ordersMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "orders" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  let receipt: GiftReceipt;
  try {
    receipt = await createOrdersApiClient(() => accessToken).getGiftReceipt(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const content = (
    <section className="mx-auto max-w-lg space-y-4 p-4">
      <Link href={`/${locale}/account/orders/${id}`} className="text-sm text-primary underline">
        {t("detail.back")}
      </Link>
      <div className="space-y-3 rounded-card border border-border bg-surface p-5">
        <h1 className="font-display text-h2 text-display-ink">{t("gift.receiptTitle")}</h1>
        {receipt.recipient_name ? (
          <p className="text-sm text-text-2">{t("gift.for", { name: receipt.recipient_name })}</p>
        ) : null}
        <p className="text-sm text-text-2">{t("gift.from", { shop: receipt.vendor_name })}</p>
        {receipt.message ? (
          <blockquote className="rounded bg-bg-2 p-3 text-sm italic text-display-ink">
            {receipt.message}
          </blockquote>
        ) : null}
        <ul className="divide-y divide-border">
          {receipt.items.map((item, index) => (
            <li key={`${item.title}-${index}`} className="flex justify-between gap-3 py-2 text-sm">
              <span className="text-display-ink">
                {item.title}
                {item.variant_options.length
                  ? ` · ${item.variant_options.map((option) => option.value).join(", ")}`
                  : ""}
              </span>
              <span className="shrink-0 text-text-2">{t("gift.qty", { qty: item.qty })}</span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-text-3">{t("gift.noPrices")}</p>
      </div>
    </section>
  );
  return <AccountListBoundary accountId={accountId}>{content}</AccountListBoundary>;
}
