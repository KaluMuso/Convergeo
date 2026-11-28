import Link from "next/link";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { AdminPage } from "../../_components/admin-page";

type ConfigPageShellProps = {
  locale: string;
  active:
    | "commissions"
    | "delivery-zones"
    | "area-pricing"
    | "platform"
    | "flags"
    | "categories"
    | "vendor-plans"
    | "busy-mode";
  titleKey: string;
  subtitleKey: string;
  children: React.ReactNode;
};

const TABS = [
  { slug: "commissions", key: "commissions" },
  { slug: "delivery-zones", key: "deliveryZones" },
  { slug: "area-pricing", key: "areaPricing" },
  { slug: "platform", key: "platform" },
  { slug: "flags", key: "flags" },
  { slug: "categories", key: "categories" },
  { slug: "vendor-plans", key: "vendorPlans" },
  { slug: "busy-mode", key: "busyMode" },
] as const;

export async function ConfigPageShell({
  locale,
  active,
  titleKey,
  subtitleKey,
  children,
}: ConfigPageShellProps) {
  const t = await getAdminTranslator(locale, "admin.config");

  return (
    <AdminPage title={t(titleKey)} subtitle={t(subtitleKey)}>
      <nav aria-label={t("title")} className="admin-segmented">
        {TABS.map((tab) => {
          const href = `/${locale}/config/${tab.slug}`;
          const isActive = tab.slug === active;
          return (
            <Link
              key={tab.slug}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={isActive ? "is-active" : "border border-transparent text-text"}
            >
              {t(`nav.${tab.key}`)}
            </Link>
          );
        })}
      </nav>

      {children}
    </AdminPage>
  );
}
