import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { getTranslations, setRequestLocale } from "next-intl/server";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Configuration hub — shell nav targets `/config`, while editors live on
 * concrete subroutes. Read-only navigation only; no invented settings UI.
 */
export default async function ConfigHubPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.hubs.config");

  const destinations = [
    {
      key: "flags",
      href: `/${locale}/config/flags`,
      title: t("flagsTitle"),
      body: t("flagsBody"),
    },
    {
      key: "commissions",
      href: `/${locale}/config/commissions`,
      title: t("commissionsTitle"),
      body: t("commissionsBody"),
    },
    {
      key: "delivery",
      href: `/${locale}/config/delivery-zones`,
      title: t("deliveryTitle"),
      body: t("deliveryBody"),
    },
    {
      key: "categories",
      href: `/${locale}/config/categories`,
      title: t("categoriesTitle"),
      body: t("categoriesBody"),
    },
    {
      key: "platform",
      href: `/${locale}/config/platform`,
      title: t("platformTitle"),
      body: t("platformBody"),
    },
  ] as const;

  return (
    <div className="space-y-4" data-testid="admin-config-hub">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <ul className="grid list-none gap-3 p-0 sm:grid-cols-2">
        {destinations.map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              className="block rounded border border-border bg-surface p-4 no-underline transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              <p className="font-semibold text-text">{item.title}</p>
              <p className="mt-1 text-sm text-muted">{item.body}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
