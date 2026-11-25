import { ApiError } from "@vergeo/config";
import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import {
  BrowsePager,
  parseBrowsePage,
  sliceBrowsePage,
} from "../../(shop)/_components/browse-pager";
import { AccountListBoundary } from "../_components/account-list-boundary";
import { getAccountListSession } from "../_components/account-list-server";

import { BuyAgain } from "./_components/buy-again";
import { buildBuyAgainLabels } from "./_components/buy-again-labels";
import { createOrdersApiClient } from "./_components/orders-api";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ page?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountOrdersPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const query = (await searchParams) ?? {};
  const page = parseBrowsePage(query.page);

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const { accountId, accessToken } = await getAccountListSession(locale);
  const baseMessages = await getMessages();
  const ordersMessages = await loadNamespace(locale as Locale, "orders");
  const messages = {
    ...baseMessages,
    orders: ordersMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "orders" }) as {
    (key: string, values?: Record<string, string | number>): string;
    raw(key: string): unknown;
  };
  const buyAgainLabels = buildBuyAgainLabels(t);

  const api = createOrdersApiClient(() => accessToken);
  let groups: Awaited<ReturnType<typeof api.listOrders>>["groups"] = [];
  try {
    ({ groups } = await api.listOrders());
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      throw error;
    }
    const content = (
      <section className="py-6" data-testid="orders-list-error">
        <EmptyState
          title={t("error.title")}
          body={t("error.body")}
          action={
            <LinkButton
              href={`/${locale}/account/orders`}
              variant="primary"
              className="px-5 text-sm"
              LinkComponent={Link}
            >
              {t("error.retry")}
            </LinkButton>
          }
        />
      </section>
    );
    return <AccountListBoundary accountId={accountId}>{content}</AccountListBoundary>;
  }

  const totalGroups = groups.length;
  const visibleGroups = sliceBrowsePage(groups, page);

  if (totalGroups === 0) {
    const content = (
      <section className="space-y-4 rounded border border-border bg-surface p-4 py-8 text-center lg:p-5">
        <h2 className="font-display text-h2 text-display-ink">{t("empty.title")}</h2>
        <p className="text-sm text-text-2">{t("empty.body")}</p>
        <LinkButton
          href={`/${locale}`}
          variant="primary"
          className="px-5 text-sm"
          LinkComponent={Link}
        >
          {t("empty.cta")}
        </LinkButton>
      </section>
    );
    return <AccountListBoundary accountId={accountId}>{content}</AccountListBoundary>;
  }

  const content = (
    <section className="space-y-4 sm:space-y-6">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("title")}</h2>
      </header>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {visibleGroups.map((group) => (
          <article
            key={group.checkout_group_id}
            className="space-y-3 rounded border border-border bg-surface p-4 lg:p-5"
          >
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
              <p className="text-sm font-medium text-display-ink">
                {t("list.checkoutGroup", {
                  date: new Date(group.created_at).toLocaleDateString(locale, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  }),
                })}
              </p>
              <p className="font-mono text-sm text-display-ink">
                {t("list.total", { amount: formatK(group.total_ngwee) })}
              </p>
            </header>

            <ul className="space-y-3">
              {group.orders.map((order) => (
                <li
                  key={order.id}
                  className="flex flex-col gap-3 rounded bg-bg-2 p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-medium text-display-ink">
                      {t("list.vendorOrder", { vendor: order.vendor_name })}
                    </p>
                    <p className="text-xs text-text-2">
                      {t("list.itemCount", { count: order.item_count })}
                      {" · "}
                      {t("list.status", {
                        status: t(`status.${order.status}`),
                      })}
                    </p>
                    <p className="text-xs text-text-2">
                      {order.payment_mode === "cod"
                        ? t("list.paymentCod")
                        : order.paid
                          ? t("list.paymentPrepaid")
                          : t("list.paymentPending")}
                    </p>
                    {!order.paid && order.payment_mode === "prepaid" ? (
                      <p
                        className="text-xs font-medium text-warning"
                        role="status"
                        data-testid={`order-payment-pending-${order.id}`}
                      >
                        {t("list.paymentPendingHint")}
                      </p>
                    ) : null}
                    {order.status === "cancelled" ? (
                      <p className="text-xs font-medium text-danger" role="status">
                        {t("status.cancelled")}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                    <p className="font-mono text-sm text-display-ink">
                      {formatK(order.total_ngwee)}
                    </p>
                    <LinkButton
                      href={`/${locale}/account/orders/${order.id}`}
                      variant="secondary"
                      className="border-primary px-4 text-sm text-primary"
                      LinkComponent={Link}
                    >
                      {t("list.viewOrder")}
                    </LinkButton>
                    <BuyAgain
                      orderId={order.id}
                      accessToken={accessToken}
                      locale={locale}
                      status={order.status}
                      labels={buyAgainLabels}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>

      <BrowsePager
        locale={locale}
        pathname="/account/orders"
        searchParams={{}}
        page={page}
        total={totalGroups}
        labels={{
          previous: t("pagination.previous"),
          next: t("pagination.next"),
          page: t("pagination.page"),
        }}
      />
    </section>
  );
  return <AccountListBoundary accountId={accountId}>{content}</AccountListBoundary>;
}
