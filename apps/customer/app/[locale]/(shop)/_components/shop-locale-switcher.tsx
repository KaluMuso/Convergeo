"use client";

import { LocaleSwitcher, type LocaleSwitcherLabels } from "../../_components/locale-switcher";

type ShopLocaleSwitcherProps = {
  locale: string;
  labels: LocaleSwitcherLabels;
};

/** Shop-header locale control (mobile top nav + desktop header). */
export function ShopLocaleSwitcher({ locale, labels }: ShopLocaleSwitcherProps) {
  return <LocaleSwitcher locale={locale} labels={labels} variant="shop" />;
}
