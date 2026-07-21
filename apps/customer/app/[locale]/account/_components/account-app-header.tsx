import { NextIntlClientProvider } from "next-intl";

import { ShopLocaleSwitcher } from "../../(shop)/_components/shop-locale-switcher";

import { AccountAppHeaderClient, type AccountHeaderClientLabels } from "./account-header-client";

type AccountAppHeaderProps = {
  locale: string;
  labels: AccountHeaderClientLabels;
  localeSwitcherLabels: {
    ariaLabel: string;
    names: Record<"en" | "bem" | "nya" | "fr", string>;
  };
  catalogMessages: Record<string, unknown>;
};

export function AccountAppHeader({
  locale,
  labels,
  localeSwitcherLabels,
  catalogMessages,
}: AccountAppHeaderProps) {
  const localeSwitcher = <ShopLocaleSwitcher locale={locale} labels={localeSwitcherLabels} />;

  return (
    <NextIntlClientProvider locale={locale} messages={{ catalog: catalogMessages }}>
      <AccountAppHeaderClient locale={locale} labels={labels} localeSwitcher={localeSwitcher} />
    </NextIntlClientProvider>
  );
}
