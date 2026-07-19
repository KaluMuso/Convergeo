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
 * Moderation hub — the shell nav links here, but work lives on subroutes.
 * Keeps Access-authenticated admins from hitting a 404 after the Moderation tab.
 */
export default async function ModerationHubPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.hubs.moderation");

  const destinations = [
    {
      key: "products",
      href: `/${locale}/moderation/products`,
      title: t("productsTitle"),
      body: t("productsBody"),
    },
    {
      key: "flags",
      href: `/${locale}/moderation/flags`,
      title: t("flagsTitle"),
      body: t("flagsBody"),
    },
  ] as const;

  return (
    <div className="space-y-4" data-testid="admin-moderation-hub">
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
