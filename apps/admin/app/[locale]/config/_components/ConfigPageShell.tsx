import Link from "next/link";
import { getTranslations } from "next-intl/server";

type ConfigPageShellProps = {
  locale: string;
  active: "commissions" | "delivery-zones" | "platform" | "flags" | "categories";
  titleKey: string;
  subtitleKey: string;
  children: React.ReactNode;
};

const TABS = [
  { slug: "commissions", key: "commissions" },
  { slug: "delivery-zones", key: "deliveryZones" },
  { slug: "platform", key: "platform" },
  { slug: "flags", key: "flags" },
  { slug: "categories", key: "categories" },
] as const;

export async function ConfigPageShell({
  locale,
  active,
  titleKey,
  subtitleKey,
  children,
}: ConfigPageShellProps) {
  const t = await getTranslations("admin.config");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-serif text-xl text-text">{t(titleKey)}</h2>
        <p className="text-sm text-muted">{t(subtitleKey)}</p>
      </header>

      <nav aria-label={t("title")} className="flex flex-wrap gap-2 border-b border-border pb-3">
        {TABS.map((tab) => {
          const href = `/${locale}/config/${tab.slug}`;
          const isActive = tab.slug === active;
          return (
            <Link
              key={tab.slug}
              href={href}
              className={[
                "inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium",
                isActive
                  ? "bg-primary text-white"
                  : "border border-border bg-bg text-text hover:border-primary",
              ].join(" ")}
            >
              {t(`nav.${tab.key}`)}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
