"use client";

import { AppHeader } from "@vergeo/ui/src/app-header";
import Link from "next/link";
import { useEffect } from "react";

import {
  getCartItemCount,
  useCartActions,
  useCartStore,
} from "../../(shop)/_components/cart/mini-cart-drawer";

import { AccountHeaderMenu } from "./account-header-menu";

export type AccountHeaderClientLabels = {
  appName: string;
  navAriaLabel: string;
  searchPlaceholder: string;
  cart: string;
  cartWithCount: string;
  accountMenuAria: string;
  accountOverview: string;
  accountOrders: string;
  accountPreferences: string;
  signOut: string;
  signingOut: string;
};

type AccountHeaderClientProps = {
  locale: string;
  labels: AccountHeaderClientLabels;
  localeSwitcher: React.ReactNode;
};

function formatCartCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

export function AccountHeaderSearch({
  locale,
  placeholder,
}: {
  locale: string;
  placeholder: string;
}) {
  return (
    <Link
      href={`/${locale}/search`}
      className="flex h-11 w-full items-center gap-2 rounded-pill border border-border bg-surface px-4 text-sm text-text-3 transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span className="truncate">{placeholder}</span>
    </Link>
  );
}

export function AccountAppHeaderClient({
  locale,
  labels,
  localeSwitcher,
}: AccountHeaderClientProps) {
  const { cart } = useCartStore();
  const { refresh } = useCartActions();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cartCount = getCartItemCount(cart);
  const cartCountLabel =
    cartCount > 0 ? labels.cartWithCount.replace("{count}", formatCartCount(cartCount)) : undefined;

  const searchSlot = <AccountHeaderSearch locale={locale} placeholder={labels.searchPlaceholder} />;

  return (
    <AppHeader
      variant="account"
      features={{ showAccount: false }}
      appName={labels.appName}
      logo={
        <Link href={`/${locale}`} className="font-display text-primary">
          {labels.appName}
        </Link>
      }
      navAriaLabel={labels.navAriaLabel}
      skipLinkTargetId="account-main"
      mobileSearchSlot={searchSlot}
      desktopSearchSlot={searchSlot}
      localeSwitcher={localeSwitcher}
      cartCount={cartCount}
      cartHref={`/${locale}/cart`}
      cartLabel={labels.cart}
      cartCountLabel={cartCountLabel}
      accountMenuSlot={
        <AccountHeaderMenu
          locale={locale}
          labels={{
            accountMenuAria: labels.accountMenuAria,
            accountOverview: labels.accountOverview,
            accountOrders: labels.accountOrders,
            accountPreferences: labels.accountPreferences,
            signOut: labels.signOut,
            signingOut: labels.signingOut,
          }}
        />
      }
      LinkComponent={Link}
    />
  );
}
