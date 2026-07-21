"use client";

import { AppHeader } from "@vergeo/ui/src/app-header";
import { IconCart } from "@vergeo/ui/src/icons";
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

export function AccountHeaderCart({
  locale,
  labels,
}: {
  locale: string;
  labels: Pick<AccountHeaderClientLabels, "cart" | "cartWithCount">;
}) {
  const { cart } = useCartStore();
  const { refresh } = useCartActions();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cartCount = getCartItemCount(cart);
  const cartAriaLabel =
    cartCount > 0
      ? labels.cartWithCount.replace("{count}", formatCartCount(cartCount))
      : labels.cart;

  return (
    <>
      <Link
        href={`/${locale}/cart`}
        aria-label={cartAriaLabel}
        className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        <IconCart aria-hidden />
        {cartCount > 0 ? (
          <span
            aria-hidden
            className="absolute -right-0.5 -top-0.5 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface"
          >
            {formatCartCount(cartCount)}
          </span>
        ) : null}
        <span className="sr-only">{labels.cart}</span>
      </Link>
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {cartCount > 0 ? cartAriaLabel : ""}
      </span>
    </>
  );
}

export function AccountAppHeaderClient({
  locale,
  labels,
  localeSwitcher,
}: AccountHeaderClientProps) {
  return (
    <AppHeader
      variant="account"
      logo={
        <Link href={`/${locale}`} className="font-display text-lg text-primary">
          {labels.appName}
        </Link>
      }
      navAriaLabel={labels.navAriaLabel}
      trailingSlot={localeSwitcher}
      searchSlot={<AccountHeaderSearch locale={locale} placeholder={labels.searchPlaceholder} />}
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
      cartSlot={<AccountHeaderCart locale={locale} labels={labels} />}
      LinkComponent={Link}
    />
  );
}
