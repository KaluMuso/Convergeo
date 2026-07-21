import { ShopLocaleSwitcher } from "../../(shop)/_components/shop-locale-switcher";

import { AccountAppHeaderClient, type AccountHeaderClientLabels } from "./account-header-client";

type AccountAppHeaderProps = {
  locale: string;
  labels: AccountHeaderClientLabels;
  localeSwitcherLabels: {
    ariaLabel: string;
    names: Record<"en" | "bem" | "nya" | "fr", string>;
  };
};

export function AccountAppHeader({ locale, labels, localeSwitcherLabels }: AccountAppHeaderProps) {
  const localeSwitcher = <ShopLocaleSwitcher locale={locale} labels={localeSwitcherLabels} />;

  return <AccountAppHeaderClient locale={locale} labels={labels} localeSwitcher={localeSwitcher} />;
}
