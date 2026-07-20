"use client";

import Link from "next/link";

import { useLocalWishlistSlugs } from "../../(shop)/_components/plp/use-local-wishlist";
import { useRecentlyViewed } from "../../(shop)/_components/recently-viewed/use-recently-viewed";

export type AccountOverviewLabels = {
  title: string;
  description: string;
  ordersTitle: string;
  ordersBody: string;
  ordersCta: string;
  savedTitle: string;
  savedEmpty: string;
  savedCount: string;
  savedCta: string;
  recentTitle: string;
  recentEmpty: string;
  recentCta: string;
  addressesTitle: string;
  addressesBody: string;
  addressesCta: string;
  preferencesTitle: string;
  preferencesBody: string;
  preferencesCta: string;
  helpTitle: string;
  helpBody: string;
  helpCta: string;
  deviceNote: string;
};

type Props = {
  locale: string;
  labels: AccountOverviewLabels;
};

function HubCard({
  title,
  body,
  href,
  cta,
  testId,
}: {
  title: string;
  body: string;
  href: string;
  cta: string;
  testId: string;
}) {
  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4"
      data-testid={testId}
    >
      <div className="space-y-1">
        <h3 className="font-medium text-display-ink">{title}</h3>
        <p className="text-sm text-text-2">{body}</p>
      </div>
      <Link
        href={href}
        className="inline-flex min-h-11 w-fit items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {cta}
      </Link>
    </article>
  );
}

export function AccountOverview({ locale, labels }: Props) {
  const wishlist = useLocalWishlistSlugs();
  const recent = useRecentlyViewed();

  const savedBody =
    wishlist.hydrated && wishlist.slugs.length > 0
      ? labels.savedCount.replace("{count}", String(wishlist.slugs.length))
      : labels.savedEmpty;

  const recentBody =
    recent.hydrated && recent.entries.length > 0
      ? recent.entries
          .slice(0, 3)
          .map((entry) => entry.name)
          .join(" · ")
      : labels.recentEmpty;

  return (
    <section className="space-y-5" data-testid="account-overview">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="text-sm text-text-2">{labels.description}</p>
        <p className="text-xs text-text-3">{labels.deviceNote}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <HubCard
          testId="account-hub-orders"
          title={labels.ordersTitle}
          body={labels.ordersBody}
          href={`/${locale}/account/orders`}
          cta={labels.ordersCta}
        />
        <HubCard
          testId="account-hub-saved"
          title={labels.savedTitle}
          body={savedBody}
          href={`/${locale}/wishlist`}
          cta={labels.savedCta}
        />
        <HubCard
          testId="account-hub-recent"
          title={labels.recentTitle}
          body={recentBody}
          href={`/${locale}/account/recent`}
          cta={labels.recentCta}
        />
        <HubCard
          testId="account-hub-addresses"
          title={labels.addressesTitle}
          body={labels.addressesBody}
          href={`/${locale}/account/addresses`}
          cta={labels.addressesCta}
        />
        <HubCard
          testId="account-hub-preferences"
          title={labels.preferencesTitle}
          body={labels.preferencesBody}
          href={`/${locale}/account/preferences`}
          cta={labels.preferencesCta}
        />
        <HubCard
          testId="account-hub-help"
          title={labels.helpTitle}
          body={labels.helpBody}
          href={`/${locale}/help`}
          cta={labels.helpCta}
        />
      </div>
    </section>
  );
}
