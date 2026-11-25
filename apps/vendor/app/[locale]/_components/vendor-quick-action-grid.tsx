"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { VendorActionIcon, VendorQuickActionIcons } from "./vendor-nav-icons";

type VendorQuickActionGridProps = { locale: string };

export function VendorQuickActionGrid({ locale }: VendorQuickActionGridProps) {
  const t = useTranslations("vendor");
  const actions = [
    {
      key: "addProduct",
      href: `/${locale}/listings/new`,
      label: t("home.quickActions.addProduct"),
      ...VendorQuickActionIcons.product,
    },
    {
      key: "scan",
      href: `/${locale}/scan`,
      label: t("home.quickActions.scan"),
      ...VendorQuickActionIcons.scan,
    },
    {
      key: "orders",
      href: `/${locale}/orders`,
      label: t("home.quickActions.orders"),
      ...VendorQuickActionIcons.orders,
    },
    {
      key: "payouts",
      href: `/${locale}/payouts`,
      label: t("home.quickActions.payouts"),
      ...VendorQuickActionIcons.payouts,
    },
  ] as const;
  return (
    <section aria-label={t("home.quickActions.ariaLabel")} data-testid="vendor-home-quick-actions">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {actions.map((action) => {
          const { Icon, hue } = action;
          return (
            <Link
              key={action.key}
              href={action.href}
              className="card-lift press-scale flex min-h-[5.5rem] flex-col items-center justify-center gap-2 rounded-xl border border-border bg-surface p-3 text-center shadow-1 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              <VendorActionIcon hue={hue} size={48}>
                <Icon className="size-6" duotone aria-hidden />
              </VendorActionIcon>
              <span className="text-sm font-semibold text-text">{action.label}</span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
